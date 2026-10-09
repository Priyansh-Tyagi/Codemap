"""
Deterministic guided-tour tests. This module must work standalone with no AI
involved. Several tests are regression tests built from failures found by
running the tour on real repos (PitSynapse, Flask, Express) - noted inline.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from graph.analysis import run_full_analysis
from graph.builder import build_dependency_graph
from graph.tour import MAX_STOPS, generate_tour


def _build(tmp_path, files: dict[str, str]):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return build_dependency_graph(str(tmp_path))


def _full(result, mode="trace"):
    a = run_full_analysis(result.graph)
    return generate_tour(result.graph, a["metrics"]["perNode"], a["architecture"],
                         a["nodes_in_cycles"], mode=mode)


def _tour(result, mode="trace"):
    return _full(result, mode)["stops"]


def _paths(stops):
    return [s["filePath"] for s in stops]


LAYERED = {
    "src/utils.py": "x = 1\n",
    "src/service.py": "from . import utils\n",
    "src/routes.py": "from . import service, utils\n",
}


# ---------- the two modes ----------

def test_trace_mode_walks_top_down_from_the_entry_point(tmp_path):
    order = _paths(_tour(_build(tmp_path, LAYERED), "trace"))
    assert order.index("src/routes.py") < order.index("src/service.py") < order.index("src/utils.py")


def test_foundation_mode_reads_bottom_up(tmp_path):
    order = _paths(_tour(_build(tmp_path, LAYERED), "foundation"))
    assert order.index("src/utils.py") < order.index("src/service.py") < order.index("src/routes.py")


def test_stages_are_named_by_role(tmp_path):
    stages = {s["filePath"]: s["stage"] for s in _tour(_build(tmp_path, LAYERED))}
    assert stages["src/routes.py"] == "Entry points"
    assert stages["src/service.py"] == "Core logic"
    assert stages["src/utils.py"] == "Building blocks"


# ---------- PitSynapse regression ----------

PITSYNAPSE_SHAPE = {
    "frontend/src/main.jsx": "import App from './App';\nimport './index.css';\n",
    "frontend/src/index.css": "body {}\n",
    "frontend/src/App.jsx": "import Dashboard from './Dashboard';\n",
    "frontend/src/Dashboard.jsx": "".join(f"import C{i} from './C{i}';\n" for i in range(8)),
    **{f"frontend/src/C{i}.jsx": "export default 1;\n" for i in range(8)},
    "frontend/vite.config.js": "export default {};\n",
    "backend/main.py": "x = 1\n",
    "backend/events.py": "y = 2\n",
}


def test_pitsynapse_shape_traces_main_app_dashboard_then_groups_the_components(tmp_path):
    """Regression: the old bottom-up tour listed 9 identical leaf components
    alphabetically, put index.css in the tour, and buried Dashboard.jsx
    (the hub importing 8 files) at stop 10 under the label 'Foundation'."""
    stops = _tour(_build(tmp_path, PITSYNAPSE_SHAPE))
    names = [s["filePath"].split("/")[-1] for s in stops]
    assert names[:3] == ["main.jsx", "App.jsx", "Dashboard.jsx"]
    group = stops[3]
    assert group["filePath"] == "8 files used by Dashboard.jsx"
    assert len(group["members"]) == 8
    assert len(stops) == 4                      # not 12 near-identical rows


def test_the_hub_is_labelled_an_orchestrator_not_foundation(tmp_path):
    stops = {s["filePath"].split("/")[-1]: s for s in _tour(_build(tmp_path, PITSYNAPSE_SHAPE))}
    assert stops["Dashboard.jsx"]["stage"] == "Orchestrators"
    assert "Imports 8 files - it wires them together" in stops["Dashboard.jsx"]["reasons"]


def test_noise_files_never_appear(tmp_path):
    result = _build(tmp_path, PITSYNAPSE_SHAPE)
    for mode in ("trace", "foundation"):
        shown = " ".join(_paths(_tour(result, mode)))
        assert "index.css" not in shown and "vite.config.js" not in shown


def test_unconnected_files_are_left_out_and_the_response_says_so(tmp_path):
    """Regression: the PitSynapse Python backend shares no imports with the
    React frontend (they talk over HTTP) - it must not pad the tour."""
    full = _full(_build(tmp_path, PITSYNAPSE_SHAPE))
    assert not any("backend" in p for p in _paths(full["stops"]))
    assert "no import connections" in full["note"]


# ---------- Flask / Express regressions ----------

def test_example_and_test_directories_are_excluded(tmp_path):
    """Regression: on Flask and Express the examples/ and test/ apps were the
    only files nothing imports, so the trace started in demo code."""
    result = _build(tmp_path, {
        "examples/demo/app.py": "from lib import core\n",
        "test/app.test_helpers.py": "from lib import core\n",
        "lib/core.py": "from . import helpers\n",
        "lib/helpers.py": "x = 1\n",
        "lib/entry.py": "from . import core\n",
    })
    shown = " ".join(_paths(_tour(result)))
    assert "examples" not in shown and "test/" not in shown
    assert "lib/entry.py" in shown


def test_important_but_deep_file_is_not_crowded_out_by_many_trivial_leaves(tmp_path):
    """Regression (Flask): depth-first selection filled all slots with trivial
    leaves before reaching the files everything depends on."""
    files = {f"src/trivial{i}.py": "x = 1\n" for i in range(MAX_STOPS * 2)}
    files["src/core.py"] = "x = 1\n"
    for i in range(10):
        files[f"src/user{i}.py"] = "from . import core\n"
    stops = _tour(_build(tmp_path, files), "foundation")
    assert any(s["filePath"] == "src/core.py" for s in stops)


def test_hubs_are_ranked_by_what_they_import_too(tmp_path):
    """The best explainer on a small app imports many files but is imported
    by only one - ranking by dependents alone buried it."""
    files = {"src/top.py": "from . import hub\n",
             "src/hub.py": "".join(f"from . import leaf{i}\n" for i in range(5))}
    files.update({f"src/leaf{i}.py": "x = 1\n" for i in range(5)})
    files.update({f"src/other{i}.py": "x = 1\n" for i in range(MAX_STOPS)})
    stops = _tour(_build(tmp_path, files), "foundation")
    assert any(s["filePath"] == "src/hub.py" for s in stops)


# ---------- general behaviour ----------

def test_widely_depended_on_file_is_explained(tmp_path):
    result = _build(tmp_path, {
        "src/config.py": "x = 1\n",
        "src/a.py": "from . import config\n",
        "src/b.py": "from . import config\n",
        "src/c.py": "from . import config\n",
    })
    by_path = {s["filePath"]: s for s in _tour(result, "foundation")}
    assert "3 other files depend on this" in by_path["src/config.py"]["reasons"]


def test_trace_stops_say_what_imported_them(tmp_path):
    by_path = {s["filePath"]: s for s in _tour(_build(tmp_path, LAYERED))}
    assert "Imported by routes.py" in by_path["src/service.py"]["reasons"]


def test_empty_project_returns_an_empty_tour(tmp_path):
    (tmp_path / "README.md").write_text("no source files here\n")
    assert _tour(_build(tmp_path, {})) == []


def test_repo_with_no_import_connections_explains_instead_of_padding(tmp_path):
    full = _full(_build(tmp_path, {f"src/f{i}.py": "x = 1\n" for i in range(6)}))
    assert full["stops"] == []
    assert "no dependency order" in full["note"]


def test_tour_is_capped_at_max_stops_on_a_large_chain(tmp_path):
    files = {f"src/f{i}.py": f"from . import f{i+1}\n" if i < 49 else "x = 1\n" for i in range(50)}
    for mode in ("trace", "foundation"):
        assert len(_tour(_build(tmp_path, files), mode)) == MAX_STOPS


def test_cyclic_files_are_flagged_and_a_cycle_with_no_entry_point_still_gets_a_tour(tmp_path):
    result = _build(tmp_path, {"src/a.py": "from . import b\n", "src/b.py": "from . import a\n"})
    stops = _tour(result)
    assert len(stops) == 2
    assert all("circular dependency" in " ".join(s["reasons"]) for s in stops)


def test_tour_is_deterministic(tmp_path):
    result = _build(tmp_path, PITSYNAPSE_SHAPE)
    for mode in ("trace", "foundation"):
        assert _full(result, mode) == _full(result, mode)


def test_real_demo_repo_produces_a_sensible_tour_in_both_modes():
    demo = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "demo-repo")
    if not os.path.isdir(demo):
        return
    result = build_dependency_graph(demo)
    for mode in ("trace", "foundation"):
        stops = _tour(result, mode)
        assert stops
        assert all(s["stage"] in ("Entry points", "Orchestrators", "Core logic", "Building blocks") for s in stops)
