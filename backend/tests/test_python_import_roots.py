"""
Regression tests for a real bug: a project's Python backend showed ZERO
connections. Its files import each other relative to backend/ (the folder the
app is run from), e.g. `from routes.simulation import router` in
backend/main.py, but the resolver only looked for `routes/` at the repo root,
so every import was classified as an external package.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from analyzer.python_resolver import ResolutionKind, resolve_python_import
from graph.builder import build_dependency_graph


def _write(tmp_path, files):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def _edges(tmp_path):
    g = build_dependency_graph(str(tmp_path)).graph
    return {(u, v) for u, v in g.edges}


PITSYNAPSE_LAYOUT = {
    "PitSynapse/backend/main.py": "from routes.simulation import router\n",
    "PitSynapse/backend/routes/simulation.py": "from services.simulation_runner import run_simulation\n",
    "PitSynapse/backend/services/simulation_runner.py": (
        "from models.events import LapEvent\n"
        "from prl_system import update_traits\n"
        "from services.agent_logic import decide\n"
    ),
    "PitSynapse/backend/services/agent_logic.py": "def decide(): pass\n",
    "PitSynapse/backend/models/events.py": "class LapEvent: pass\n",
    "PitSynapse/backend/prl_system.py": "def update_traits(): pass\n",
}


def test_imports_relative_to_the_app_folder_are_connected(tmp_path):
    _write(tmp_path, PITSYNAPSE_LAYOUT)
    edges = _edges(tmp_path)
    b = "PitSynapse/backend/"
    assert (b + "main.py", b + "routes/simulation.py") in edges
    assert (b + "routes/simulation.py", b + "services/simulation_runner.py") in edges
    assert (b + "services/simulation_runner.py", b + "models/events.py") in edges
    assert (b + "services/simulation_runner.py", b + "prl_system.py") in edges
    assert (b + "services/simulation_runner.py", b + "services/agent_logic.py") in edges


def test_third_party_imports_stay_external(tmp_path):
    _write(tmp_path, {**PITSYNAPSE_LAYOUT,
                      "PitSynapse/backend/api.py": "from fastapi import FastAPI\nimport pydantic\n"})
    result = build_dependency_graph(str(tmp_path))
    assert not any(u.endswith("api.py") for u, _ in result.graph.edges)
    assert {"fastapi", "pydantic"} <= set(result.external_dependencies)


def test_src_layout_absolute_imports_resolve(tmp_path):
    _write(tmp_path, {
        "src/mypkg/__init__.py": "",
        "src/mypkg/core.py": "x = 1\n",
        "tests/test_core.py": "from mypkg.core import x\n",
        "src/mypkg/cli.py": "from mypkg.core import x\n",
    })
    edges = _edges(tmp_path)
    assert ("tests/test_core.py", "src/mypkg/core.py") in edges
    assert ("src/mypkg/cli.py", "src/mypkg/core.py") in edges


def test_a_local_folder_cannot_hijack_a_standard_library_import(tmp_path):
    """A stray backend/json/ or backend/types/ directory must not turn
    `import json` into a project dependency."""
    _write(tmp_path, {
        "backend/json/__init__.py": "",
        "backend/types/__init__.py": "",
        "backend/app.py": "import json\nfrom types import SimpleNamespace\n",
    })
    assert _edges(tmp_path) == set()


def test_project_root_still_wins_when_both_roots_could_match(tmp_path):
    """Priority order is documented and locked: root first, so projects that
    already worked keep resolving exactly as before."""
    _write(tmp_path, {
        "utils.py": "x = 1\n",
        "backend/utils.py": "y = 2\n",
        "backend/main.py": "import utils\n",
    })
    assert ("backend/main.py", "utils.py") in _edges(tmp_path)


def test_search_never_climbs_outside_the_project(tmp_path):
    outside = tmp_path / "outside_pkg"
    outside.mkdir()
    (outside / "__init__.py").write_text("")
    project = tmp_path / "project"
    (project / "app").mkdir(parents=True)
    f = project / "app" / "main.py"
    f.write_text("import outside_pkg\n")
    resolved, kind = resolve_python_import(str(f), "outside_pkg", 0, str(project))
    assert resolved is None and kind == ResolutionKind.EXTERNAL


def test_existing_relative_import_behaviour_is_unchanged(tmp_path):
    _write(tmp_path, {"pkg/__init__.py": "", "pkg/a.py": "from . import b\n", "pkg/b.py": "x = 1\n"})
    assert ("pkg/a.py", "pkg/b.py") in _edges(tmp_path)
