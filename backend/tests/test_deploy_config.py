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
    assert "NOT starting" in text                    # fail closed rather than replicate an empty DB
    assert "timeout " in text                        # unreachable bucket must not hang forever
    assert "exec litestream replicate" in text       # signals reach litestream (PID 1)


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
