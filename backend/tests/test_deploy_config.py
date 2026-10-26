"""
Guards for the deployment files. These cannot prove a container works (that is
what docker/e2e_replication.py is for), but each one pins a mistake that was
actually made or nearly made:

  * part-size "5MB"  -> Litestream reads it as 5,000,000 bytes, below S3's 5 MiB
                        minimum: every upload failed while the app ran fine with
                        NO backup. Found only by running the S3 config for real.
  * CRLF endings     -> a Windows checkout turns entrypoint.sh into "not found".
  * secrets in image -> an .env or *.db copied into a layer is there forever.
"""
import os
import re
import subprocess

import pytest

BACKEND = os.path.join(os.path.dirname(__file__), "..")
DOCKER = os.path.join(BACKEND, "docker")


def read(*parts):
    with open(os.path.join(BACKEND, *parts), "rb") as f:
        return f.read().decode("utf-8")


def test_s3_part_size_is_at_least_5_mib_in_plain_bytes():
    text = read("docker", "litestream.yml")
    m = re.search(r"^\s*part-size:\s*(\S+)\s*$", text, re.M)
    assert m, "part-size not set"
    assert m.group(1).isdigit(), "write part-size in bytes: '5MB' means 5,000,000 and S3 rejects it"
    assert int(m.group(1)) >= 5 * 1024 * 1024


def test_shutdown_sync_finishes_inside_render_30s_grace_period():
    for name in ("litestream.yml", "litestream.file.yml"):
        m = re.search(r"^shutdown-sync-timeout:\s*(\d+)s\s*$", read("docker", name), re.M)
        assert m, f"{name}: shutdown-sync-timeout missing"
        assert int(m.group(1)) < 30


@pytest.mark.parametrize("path", [
    ("Dockerfile",), ("docker", "entrypoint.sh"), ("docker", "litestream.yml"),
    ("docker", "litestream.file.yml"), ("docker", "check_db.py"), ("docker", "healthcheck.py"),
])
def test_deploy_files_use_lf_line_endings(path):
    assert b"\r" not in open(os.path.join(BACKEND, *path), "rb").read()


def test_entrypoint_is_valid_shell_and_keeps_its_safety_rules():
    script = os.path.join(DOCKER, "entrypoint.sh")
    assert subprocess.run(["sh", "-n", script]).returncode == 0
    text = read("docker", "entrypoint.sh")
    assert "umask 077" in text                       # DB, -wal, -shm owner-only
    assert "-if-replica-exists" in text              # first boot must not be an error
    assert "degrade()" in text                       # an unusable backup degrades; it never replicates an empty DB
    assert "timeout " in text                        # unreachable bucket must not hang forever
    assert "exec litestream replicate" in text       # signals reach litestream (PID 1)
    assert "write_status ok" in text                 # the UI is told replication is running


def test_dockerfile_bakes_in_no_secrets_and_runs_unprivileged():
    text = read("Dockerfile")
    assert not re.search(r"^\s*(COPY|ADD)\b.*\.env\b", text, re.M)
    assert not re.search(r"^\s*(ARG|ENV)\s+\S*(SECRET|TOKEN|PASSWORD|API_KEY|ACCESS_KEY)\S*\s*=", text, re.M | re.I)
    assert re.search(r"^USER\s+codemap\s*$", text, re.M)
    assert "--require-hashes" in text
    assert "sha256sum -c" in text                    # the downloaded replicator is verified
    assert "CODEMAP_ALLOW_LOCAL_PATHS=false" in text


def test_dockerignore_keeps_secrets_and_databases_out_of_the_image():
    lines = {l.strip() for l in read(".dockerignore").splitlines()}
    for must in ("**/.env", "**/*.db", "**/*.db-*", "venv"):
        assert must in lines, must


# --- B2 free-tier incident: background timers must stay slow ---------------------------
# Litestream's default timers made ~650 LIST requests an hour on an idle service
# (measured). Backblaze B2's free tier allows 2,500 list-type requests a DAY; the cap
# was hit, B2 answered 403 to everything (including the restore at startup) and the
# service could not boot. These tests pin the slowed-down values.

def _to_minutes(value):
    m = re.fullmatch(r"(\d+)(s|m|h)", value)
    assert m, f"unrecognised duration {value!r}"
    return int(m.group(1)) * {"s": 1 / 60, "m": 1, "h": 60}[m.group(2)]


def _yml_levels():
    return [_to_minutes(v) for v in re.findall(r"^\s*-\s*interval:\s*(\d+[smh])\b", read("docker", "litestream.yml"), re.M)]


def _yml_value(key):
    m = re.search(rf"^{re.escape(key)}:\s*(\d+[smh])\b", read("docker", "litestream.yml"), re.M)
    assert m, f"{key} is not set to a literal duration in litestream.yml"
    return _to_minutes(m.group(1))


def test_litestream_timers_are_slow_and_literal():
    # Literal values on purpose: a restore run by hand during an outage has no
    # entrypoint to export variables, and ${UNSET} expands to an empty string.
    text = read("docker", "litestream.yml")
    assert not re.search(r"interval:\s*\$\{|l0-retention[\w-]*:\s*\$\{", text)
    levels = _yml_levels()
    assert levels[0] >= 10      # Litestream default: 30 s
    assert levels[1] >= 60      # Litestream default: 5 min
    assert _yml_value("l0-retention-check-interval") >= 10   # default: 15 s
    assert _yml_value("l0-retention") >= _yml_value("l0-retention-check-interval")


def test_estimated_idle_list_rate_fits_the_b2_free_daily_cap():
    # Measured: ~5 LIST requests per 10 minutes at 10m/1h/30m/10m. Scale by the
    # first compaction interval so loosening a timer without thought fails here.
    per_10_min = 5 * (10 / _yml_levels()[0])
    per_day_awake_24h = per_10_min * 6 * 24
    assert per_day_awake_24h < 1000, "an always-awake service would use over 40% of B2's free daily cap on idling alone"


def _function_body(text, name):
    m = re.search(rf"^{name}\(\) \{{.*?^\}}", text, re.M | re.S)
    assert m, f"{name}() not found in entrypoint.sh"
    return m.group(0)


def test_degraded_mode_can_never_replicate():
    # The one thing that could destroy existing backup history is replicating a
    # fresh database over it. If this ever fails, someone put replication in the
    # degraded path.
    body = _function_body(read("docker", "entrypoint.sh"), "degrade")
    assert "replicate" not in body
    assert "exec $APP_CMD" in body
    assert "write_status degraded" in body


def test_every_unusable_backup_path_degrades_instead_of_refusing_or_replicating():
    text = read("docker", "entrypoint.sh")
    assert 'degrade "${FAIL_REASON:-unreachable}"' in text    # restore failed (403, timeout, unreachable)
    assert "degrade corrupt" in text                          # a backup exists but nothing usable
    assert "NOT starting" not in text                         # the old refuse-to-start policy is gone


def test_status_file_only_ever_gets_fixed_words():
    text = read("docker", "entrypoint.sh")
    assert 'FAIL_REASON=provider_refused' in text and 'FAIL_REASON=timeout' in text
    # provider text (rlog) is grepped, never written into the status file
    body = _function_body(text, "write_status")
    assert "rlog" not in body


def test_entrypoint_explains_provider_refusals():
    text = read("docker", "entrypoint.sh")
    assert "HINT" in text and "daily request cap" in text
