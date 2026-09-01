"""
Integration test for the Day 1-2 pipeline: scanner -> parser bridge ->
classifier -> resolver, run against a small fixture repo built in-test
(not the examples/sample-app used for manual exploration).

Requires `node` on PATH with the parser/ dependencies installed
(npm install in backend/parser).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest
from analyzer.scanner import scan_repository
from analyzer.parser_bridge import parse_files
from analyzer.classifier import classify_imports
from analyzer.resolver import resolve_specifier


@pytest.fixture
def fake_repo(tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    (src / "app.js").write_text(
        "import React from 'react';\n"
        "import Button from './components/Button';\n"
        "import Missing from './does-not-exist';\n"
    )

    components = src / "components"
    components.mkdir()
    (components / "Button.jsx").write_text(
        "import React from 'react';\n"
        "export default function Button() { return null; }\n"
    )

    return tmp_path


def test_pipeline_produces_correct_edges_and_external_deps(fake_repo):
    scan_result = scan_repository(str(fake_repo))
    parsed = parse_files(scan_result.files)

    edges = []
    external_deps = set()
    unresolved = []

    for file_result in parsed:
        assert file_result["error"] is None
        local_imports, external_imports = classify_imports(file_result["imports"])
        external_deps.update(i["specifier"] for i in external_imports)

        for imp in local_imports:
            resolved = resolve_specifier(
                file_result["filePath"], imp["specifier"], str(fake_repo)
            )
            if resolved is None:
                unresolved.append((file_result["filePath"], imp["specifier"]))
            else:
                edges.append((file_result["filePath"], resolved))

    assert external_deps == {"react"}

    # app.js -> Button.jsx should resolve
    resolved_targets = {os.path.basename(target) for _, target in edges}
    assert "Button.jsx" in resolved_targets

    # the missing import should be reported as unresolved, not silently dropped
    assert any(spec == "./does-not-exist" for _, spec in unresolved)
