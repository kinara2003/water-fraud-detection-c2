"""
tests/test_viva_rehearsal.py
Automated test suite validating the 2-minute live demonstration rehearsal script.
Component 2: NWSDB Water Fraud Surveillance Platform
"""

import pytest
from scripts.run_viva_rehearsal import RehearsalClient, VivaRehearsalEngine


def test_rehearsal_engine_full_run():
    """
    Asserts that the VivaRehearsalEngine executes all 5 milestones with 100% pass rate.
    """
    client = RehearsalClient(backend_url="http://127.0.0.1:8000", frontend_url="http://127.0.0.1:5173")
    engine = VivaRehearsalEngine(client=client, speed=0.01, is_live=False)

    success = engine.run_rehearsal()
    assert success is True
    assert engine.report_card["all_passed"] is True

    # Validate Phase 1 assertions
    p1 = engine.report_card["phase_results"]["phase_1_baseline"]
    assert p1["passed"] is True
    assert p1["max_risk_score"] < 20.0
    assert p1["map_marker_verified"] == "GREEN"

    # Validate Phase 2 assertions
    p2 = engine.report_card["phase_results"]["phase_2_refill"]
    assert p2["passed"] is True
    assert p2["observed_risk_score"] < 45.0
    assert p2["transient_dampening_active"] is True

    # Validate Phase 3 assertions
    p3 = engine.report_card["phase_results"]["phase_3_theft"]
    assert p3["passed"] is True
    assert p3["fraud_risk_score"] >= 85.0
    assert p3["classification"] == "partial_bypass"
    assert p3["map_marker_verified"] == "RED"

    # Validate Phase 4 assertions
    p4 = engine.report_card["phase_results"]["phase_4_feedback"]
    assert p4["passed"] is True
    assert p4["ledger_verified"] is True
    assert p4["ppv_percentage"] > 0.0

    # Validate latency profiling
    lats = engine.report_card["latency_metrics"]
    assert lats["mean_ms"] > 0.0
    assert lats["total_requests"] >= 10
