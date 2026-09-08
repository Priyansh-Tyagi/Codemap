"""
Tests for cli.py, run as subprocess calls - this is a CLI, so testing it
by actually invoking it (like a CI runner would) catches real
argument-parsing and exit-code issues that importing functions directly
wouldn't.
"""

import json
import os
import subprocess
import sys

import pytest

CLI_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "cli.py")


def run_cli(*args):
    result = subprocess.run(
        [sys.executable, CLI_PATH, "analyze", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


@pytest.fixture
def linear_repo(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text("import b from './b';\n")
    (src / "b.js").write_text("export default 1;\n")
    return tmp_path


@pytest.fixture
def cyclic_repo(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text("import b from './b';\n")
    (src / "b.js").write_text("import a from './a';\n")
    return tmp_path


def test_analyze_nonexistent_path_exits_2():
    result = run_cli("/definitely/not/a/real/path")
    assert result.returncode == 2
    assert "error" in result.stderr.lower()


def test_analyze_with_no_gating_flags_always_passes(linear_repo):
    result = run_cli(str(linear_repo))
    assert result.returncode == 0
    assert "PASSED" in result.stdout


def test_risk_threshold_below_actual_risk_fails(linear_repo, tmp_path):
    # a.js has an outgoing dependent, so its risk score is > 0
    result = run_cli(str(linear_repo), "--risk-threshold", "0")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_risk_threshold_above_actual_risk_passes(linear_repo):
    result = run_cli(str(linear_repo), "--risk-threshold", "100")
    assert result.returncode == 0
    assert "PASSED" in result.stdout


def test_output_writes_valid_json_baseline(linear_repo, tmp_path):
    output_path = tmp_path / "baseline.json"
    result = run_cli(str(linear_repo), "--output", str(output_path))
    assert result.returncode == 0
    assert output_path.exists()

    data = json.loads(output_path.read_text())
    assert data["fileCount"] == 2
    assert "cycles" in data
    assert "risk" in data


def test_fail_on_new_cycle_without_baseline_treats_existing_cycle_as_new(cyclic_repo):
    result = run_cli(str(cyclic_repo), "--fail-on-new-cycle")
    assert result.returncode == 1
    assert "NEW circular dependencies" in result.stdout


def test_fail_on_new_cycle_with_matching_baseline_passes(cyclic_repo, tmp_path):
    baseline_path = tmp_path / "baseline.json"
    # generate a baseline FROM the cyclic repo itself - so the cycle is "known"
    run_cli(str(cyclic_repo), "--output", str(baseline_path))

    result = run_cli(str(cyclic_repo), "--baseline", str(baseline_path), "--fail-on-new-cycle")
    assert result.returncode == 0
    assert "No new circular dependencies" in result.stdout


def test_fail_on_new_cycle_detects_a_genuinely_new_one(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.js").write_text("import b from './b';\n")
    (src / "b.js").write_text("export default 1;\n")

    baseline_path = tmp_path / "baseline.json"
    run_cli(str(tmp_path), "--output", str(baseline_path))  # baseline: no cycles

    # now introduce a cycle
    (src / "b.js").write_text("import a from './a';\n")

    result = run_cli(str(tmp_path), "--baseline", str(baseline_path), "--fail-on-new-cycle")
    assert result.returncode == 1
    assert "NEW circular dependencies" in result.stdout


def test_json_format_is_valid_and_machine_readable(cyclic_repo):
    result = run_cli(str(cyclic_repo), "--fail-on-new-cycle", "--format", "json")
    body = json.loads(result.stdout)
    assert body["passed"] is False
    assert body["cycleCount"] == 1
    assert len(body["newCycles"]) == 1


def test_markdown_format_includes_result_line(linear_repo):
    result = run_cli(str(linear_repo), "--format", "markdown")
    assert "### CodeMap Analysis" in result.stdout
    assert "**Result: PASSED**" in result.stdout


def test_combining_risk_and_cycle_checks(cyclic_repo):
    """Both gates active; failure on either should fail the whole run."""
    result = run_cli(str(cyclic_repo), "--fail-on-new-cycle", "--risk-threshold", "100")
    assert result.returncode == 1  # cycle check fails even though risk threshold doesn't
    assert "NEW circular dependencies" in result.stdout
    assert "No files at or above risk threshold" in result.stdout
