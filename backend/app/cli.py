"""
CodeMap CLI - the same analysis engine used by the web API (graph/builder.py,
graph/analysis.py), wrapped as a command-line tool for CI/CD use.

Run from backend/app/ (same convention as `uvicorn main:app`):

    python cli.py analyze <path> [options]

Examples:
    # Human-readable summary, no gating - exit code always 0
    python cli.py analyze ../../examples/demo-repo

    # Fail (exit 1) if any file's risk score is 80+
    python cli.py analyze ../../examples/demo-repo --risk-threshold 80

    # Compare cycles against a baseline, fail only on a genuinely NEW one
    python cli.py analyze ../../examples/demo-repo --baseline baseline.json --fail-on-new-cycle

    # Write a baseline for future runs to compare against (e.g. on main)
    python cli.py analyze ../../examples/demo-repo --output baseline.json

See the repo root's action.yml for how this is wrapped as a GitHub Action.
"""

from __future__ import annotations

import argparse
import json
import sys

import networkx as nx

from graph.builder import build_dependency_graph
from graph.analysis import run_full_analysis


def _cycle_key_set(cycles: list[dict]) -> set[frozenset[str]]:
    """
    Order/rotation-independent representation of a set of cycles, so
    "A->B->C->A" and "B->C->A->B" (the same cycle, walked from a different
    starting node) compare as equal instead of looking like two different
    cycles.
    """
    return {frozenset(c["chain"][:-1]) for c in cycles}


def _components_from_cycles(cycles: list[dict]) -> list[frozenset[str]]:
    """
    Derives cyclic components from a list of cycles (for baselines written
    before components were stored). The union of all cycle edges has exactly
    the same strongly connected components as the original graph.
    """
    g = nx.DiGraph()
    for c in cycles:
        chain = c["chain"]
        g.add_edges_from(zip(chain, chain[1:]))
    return [
        frozenset(comp)
        for comp in nx.strongly_connected_components(g)
        if len(comp) > 1 or any(g.has_edge(n, n) for n in comp)
    ]


def _find_new_cycles(analysis: dict, baseline: dict | None) -> list[frozenset[str]]:
    """
    Normal case: compare individual cycles against the baseline's cycles.

    If EITHER side's cycle list was truncated (dense repo, more cycles than
    are listed), per-cycle comparison would flap - which subset gets listed
    can change when unrelated code changes, failing PRs that introduced
    nothing. So fall back to comparing cyclic components: a component is
    "new" only if it isn't contained in any baseline component (i.e. it's a
    genuinely new tangle, or an existing tangle that grew).
    """
    if baseline is None:
        baseline = {"cycles": []}

    if analysis["cycles_truncated"] or baseline.get("cyclesTruncated"):
        current = [frozenset(c) for c in analysis["cycle_components"]]
        if "cycleComponents" in baseline:
            base = [frozenset(c) for c in baseline["cycleComponents"]]
        else:
            base = _components_from_cycles(baseline["cycles"])
        return [c for c in current if not any(c <= b for b in base)]

    current_keys = _cycle_key_set(analysis["cycles"])
    baseline_keys = _cycle_key_set(baseline["cycles"])
    return [k for k in current_keys if k not in baseline_keys]


def _cycle_count_label(serialized: dict) -> str:
    n = len(serialized["cycles"])
    return f"{n}+" if serialized.get("cyclesTruncated") else str(n)


def _serialize_analysis(graph, analysis: dict) -> dict:
    """A stable, comparable JSON shape - this is what --output writes and
    what --baseline reads back in on a later run."""
    return {
        "fileCount": graph.number_of_nodes(),
        "edgeCount": graph.number_of_edges(),
        "cycles": analysis["cycles"],
        "cyclesTruncated": analysis["cycles_truncated"],
        "cycleComponents": analysis["cycle_components"],
        "risk": {node_id: r["score"] for node_id, r in analysis["risk"].items()},
    }


def cmd_analyze(args: argparse.Namespace) -> int:
    try:
        build_result = build_dependency_graph(args.path)
    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    analysis = run_full_analysis(build_result.graph)
    serialized = _serialize_analysis(build_result.graph, analysis)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(serialized, f, indent=2)

    baseline = None
    if args.baseline:
        try:
            with open(args.baseline) as f:
                baseline = json.load(f)
        except FileNotFoundError:
            baseline = None  # first run - nothing to compare against yet

    new_cycles: list[frozenset[str]] = []
    if args.fail_on_new_cycle:
        new_cycles = _find_new_cycles(analysis, baseline)

    high_risk_files: list[tuple[str, int]] = []
    if args.risk_threshold is not None:
        high_risk_files = [
            (node_id, r["score"])
            for node_id, r in analysis["risk"].items()
            if r["score"] >= args.risk_threshold
        ]
        high_risk_files.sort(key=lambda item: -item[1])

    passed = not new_cycles and not high_risk_files

    if args.format == "json":
        _print_json_report(serialized, new_cycles, high_risk_files, passed)
    elif args.format == "markdown":
        _print_markdown_report(serialized, new_cycles, high_risk_files, passed, args)
    else:
        _print_text_report(serialized, new_cycles, high_risk_files, passed, args)

    return 0 if passed else 1


def _print_json_report(serialized, new_cycles, high_risk_files, passed) -> None:
    print(
        json.dumps(
            {
                "passed": passed,
                "fileCount": serialized["fileCount"],
                "edgeCount": serialized["edgeCount"],
                "cycleCount": len(serialized["cycles"]),
                "cyclesTruncated": serialized.get("cyclesTruncated", False),
                "newCycles": [sorted(c) for c in new_cycles],
                "highRiskFiles": [{"file": f, "score": s} for f, s in high_risk_files],
            },
            indent=2,
        )
    )


def _print_text_report(serialized, new_cycles, high_risk_files, passed, args) -> None:
    print(
        f"CodeMap analysis: {serialized['fileCount']} files, "
        f"{serialized['edgeCount']} dependencies, "
        f"{_cycle_count_label(serialized)} circular dependencies"
    )
    print()

    if args.fail_on_new_cycle:
        if new_cycles:
            print(f"NEW circular dependencies introduced ({len(new_cycles)}):")
            for cycle in new_cycles:
                print(f"  - {' <-> '.join(sorted(cycle))}")
        else:
            print("No new circular dependencies.")
        print()

    if args.risk_threshold is not None:
        if high_risk_files:
            print(f"Files at or above risk threshold {args.risk_threshold}:")
            for node_id, score in high_risk_files:
                print(f"  - {node_id}: {score}/100")
        else:
            print(f"No files at or above risk threshold {args.risk_threshold}.")
        print()

    print("PASSED" if passed else "FAILED")


def _print_markdown_report(serialized, new_cycles, high_risk_files, passed, args) -> None:
    lines = [
        "### CodeMap Analysis",
        "",
        f"**{serialized['fileCount']} files &middot; {serialized['edgeCount']} dependencies "
        f"&middot; {_cycle_count_label(serialized)} circular dependencies**",
        "",
    ]

    if args.fail_on_new_cycle:
        if new_cycles:
            lines.append(f"#### New circular dependency introduced ({len(new_cycles)})")
            for cycle in new_cycles:
                lines.append(f"- `{'` &harr; `'.join(sorted(cycle))}`")
        else:
            lines.append("No new circular dependencies.")
        lines.append("")

    if args.risk_threshold is not None:
        if high_risk_files:
            lines.append(f"#### Files at or above risk threshold ({args.risk_threshold})")
            lines.append("| File | Risk |")
            lines.append("|---|---|")
            for node_id, score in high_risk_files:
                lines.append(f"| `{node_id}` | {score} |")
        else:
            lines.append(f"No files at or above risk threshold {args.risk_threshold}.")
        lines.append("")

    lines.append(f"**Result: {'PASSED' if passed else 'FAILED'}**")
    print("\n".join(lines))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codemap", description="CodeMap static analysis CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a repository")
    analyze_parser.add_argument("path", help="Path to the repository to analyze")
    analyze_parser.add_argument(
        "--baseline", help="Path to a baseline JSON file to compare cycles against"
    )
    analyze_parser.add_argument(
        "--fail-on-new-cycle",
        action="store_true",
        help="Exit 1 if a cycle not present in the baseline is found",
    )
    analyze_parser.add_argument(
        "--risk-threshold",
        type=int,
        default=None,
        help="Exit 1 if any file's risk score is at or above this value (0-100)",
    )
    analyze_parser.add_argument("--output", help="Write the full analysis JSON to this path")
    analyze_parser.add_argument(
        "--format", choices=["text", "json", "markdown"], default="text"
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
