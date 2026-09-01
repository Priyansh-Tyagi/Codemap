"""
Parser bridge.

Invokes the Node/Babel parser script (backend/parser/parse.js) as a single
subprocess for a batch of files, and returns the parsed results as Python
objects. This is the only place that talks to Node - everything else in
the analyzer works with plain Python data.
"""

from __future__ import annotations

import json
import os
import subprocess

PARSER_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", "..", "parser", "parse.js"
)


class ParserBridgeError(RuntimeError):
    pass


def parse_files(file_paths: list[str], timeout_seconds: int = 60) -> list[dict]:
    """
    Run the Node parser against a batch of absolute file paths.

    Returns a list of dicts: {filePath, linesOfCode, imports, error}
    in the same order as `file_paths` is not guaranteed by the subprocess
    contract, but parse.js processes them in input order, so in practice
    it matches. Callers should key results by filePath if order matters.
    """
    if not file_paths:
        return []

    payload = json.dumps({"files": file_paths})

    try:
        proc = subprocess.run(
            ["node", os.path.abspath(PARSER_SCRIPT)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise ParserBridgeError(
            "node executable not found - is Node.js installed and on PATH?"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ParserBridgeError(
            f"parser timed out after {timeout_seconds}s for {len(file_paths)} files"
        ) from exc

    if proc.returncode != 0:
        raise ParserBridgeError(f"parser process failed: {proc.stderr.strip()}")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ParserBridgeError(f"parser returned invalid JSON: {exc}") from exc
