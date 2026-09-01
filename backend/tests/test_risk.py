import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from graph.risk import compute_risk, risk_level


def test_zero_signal_file_is_low_risk():
    result = compute_risk(in_degree=0, degree_centrality=0.0, lines_of_code=10, in_cycle=False)
    assert result["score"] == 0
    assert result["level"] == "Low"
    assert result["reasons"] == []


def test_many_dependents_raises_score():
    low = compute_risk(in_degree=1, degree_centrality=0.0, lines_of_code=10, in_cycle=False)
    high = compute_risk(in_degree=20, degree_centrality=0.0, lines_of_code=10, in_cycle=False)
    assert high["score"] > low["score"]


def test_cycle_membership_adds_fixed_score_and_reason():
    without_cycle = compute_risk(in_degree=0, degree_centrality=0.0, lines_of_code=10, in_cycle=False)
    with_cycle = compute_risk(in_degree=0, degree_centrality=0.0, lines_of_code=10, in_cycle=True)
    assert with_cycle["score"] == without_cycle["score"] + 20
    assert "circular dependency" in with_cycle["reasons"][0].lower()


def test_score_never_exceeds_100():
    result = compute_risk(in_degree=999, degree_centrality=1.0, lines_of_code=99999, in_cycle=True)
    assert result["score"] <= 100


def test_risk_level_bands():
    assert risk_level(0) == "Low"
    assert risk_level(30) == "Low"
    assert risk_level(31) == "Medium"
    assert risk_level(60) == "Medium"
    assert risk_level(61) == "High"
    assert risk_level(80) == "High"
    assert risk_level(81) == "Critical"
    assert risk_level(100) == "Critical"


def test_high_loc_produces_a_reason():
    result = compute_risk(in_degree=0, degree_centrality=0.0, lines_of_code=480, in_cycle=False)
    assert any("lines of code" in r for r in result["reasons"])


def test_reasons_only_include_fired_factors():
    # only cycle membership should produce a reason here; everything else is minimal
    result = compute_risk(in_degree=0, degree_centrality=0.0, lines_of_code=5, in_cycle=True)
    assert len(result["reasons"]) == 1
