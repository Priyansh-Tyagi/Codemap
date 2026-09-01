"""
Deterministic risk scoring.

risk = dependents_score + centrality_score + complexity_score + cycle_score,
each capped before summing, normalized to 0-100.

Bands: 0-30 Low, 31-60 Medium, 61-80 High, 81-100 Critical.

Every score comes with a human-readable "reasons" list explaining which
factors fired, so the UI can show *why* a file is flagged - not just a
number. This is intentionally simple per the Phase 1 spec: not meant to be
a sophisticated model, just a transparent, explainable heuristic.
"""

from __future__ import annotations

DEPENDENTS_WEIGHT_CAP = 40
CENTRALITY_WEIGHT_CAP = 20
COMPLEXITY_WEIGHT_CAP = 20
CYCLE_SCORE = 20

# Rough normalization ceilings - a file with this many dependents/lines
# is already "as risky as it gets" on that dimension. Tuned for MVP-sized
# repos, not derived from any formal study.
DEPENDENTS_CEILING = 20
LOC_CEILING = 500


def _dependents_score(in_degree: int) -> tuple[int, str | None]:
    score = min(DEPENDENTS_WEIGHT_CAP, round((in_degree / DEPENDENTS_CEILING) * DEPENDENTS_WEIGHT_CAP))
    reason = f"{in_degree} files depend on this module" if in_degree > 0 else None
    return score, reason


def _centrality_score(degree_centrality: float) -> tuple[int, str | None]:
    # degree_centrality is already 0-1 from networkx
    score = min(CENTRALITY_WEIGHT_CAP, round(degree_centrality * CENTRALITY_WEIGHT_CAP * 2))
    reason = "High centrality in the dependency graph" if score >= CENTRALITY_WEIGHT_CAP * 0.5 else None
    return score, reason


def _complexity_score(lines_of_code: int) -> tuple[int, str | None]:
    score = min(COMPLEXITY_WEIGHT_CAP, round((lines_of_code / LOC_CEILING) * COMPLEXITY_WEIGHT_CAP))
    reason = f"{lines_of_code} lines of code" if lines_of_code >= LOC_CEILING * 0.4 else None
    return score, reason


def _cycle_score(in_cycle: bool) -> tuple[int, str | None]:
    if in_cycle:
        return CYCLE_SCORE, "Part of a circular dependency"
    return 0, None


def risk_level(score: int) -> str:
    if score <= 30:
        return "Low"
    if score <= 60:
        return "Medium"
    if score <= 80:
        return "High"
    return "Critical"


def compute_risk(
    in_degree: int,
    degree_centrality: float,
    lines_of_code: int,
    in_cycle: bool,
) -> dict:
    """Returns {"score": int, "level": str, "reasons": list[str]}."""
    dep_score, dep_reason = _dependents_score(in_degree)
    cent_score, cent_reason = _centrality_score(degree_centrality)
    complexity_score, complexity_reason = _complexity_score(lines_of_code)
    cyc_score, cyc_reason = _cycle_score(in_cycle)

    total = min(100, dep_score + cent_score + complexity_score + cyc_score)
    reasons = [r for r in (dep_reason, cent_reason, complexity_reason, cyc_reason) if r]

    return {
        "score": total,
        "level": risk_level(total),
        "reasons": reasons,
    }
