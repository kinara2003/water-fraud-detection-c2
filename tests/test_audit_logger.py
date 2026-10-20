"""
tests/test_audit_logger.py
Unit and integration test suite for structured inspection audit trail & operational accuracy ledger.
Component 2: NWSDB Water Fraud Surveillance Platform
"""

import json
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from app.main import app
from src.audit_logger import (
    ensure_ledger_exists,
    get_inspection_ledger,
    calculate_operational_metrics,
    record_field_inspection,
    generate_candidate_retraining_batch,
    GROUND_TRUTH_BYPASS,
    GROUND_TRUTH_LEAK,
    GROUND_TRUTH_FALSE_ALARM,
    LEDGER_PATH,
    CANDIDATE_BATCH_PATH,
    CANDIDATE_MANIFEST_PATH,
)

client = TestClient(app)


def test_ensure_ledger_exists():
    """Validates that the inspection audit ledger exists and contains valid records."""
    records = ensure_ledger_exists()
    assert isinstance(records, list)
    assert len(records) > 0
    assert LEDGER_PATH.exists()

    first = records[0]
    required_keys = [
        "inspection_id",
        "alert_id",
        "node_id",
        "dma_id",
        "dispatch_time",
        "inspection_time",
        "assigned_officer",
        "ground_truth_finding",
        "action_taken",
        "notes",
    ]
    for key in required_keys:
        assert key in first


def test_calculate_operational_metrics_ppv():
    """Validates PPV = Confirmed Bypasses / Total Dispatched Inspections."""
    sample_ledger = [
        {"ground_truth_finding": GROUND_TRUTH_BYPASS, "batched_for_retraining": True},
        {"ground_truth_finding": GROUND_TRUTH_BYPASS, "batched_for_retraining": True},
        {"ground_truth_finding": GROUND_TRUTH_LEAK, "batched_for_retraining": True},
        {"ground_truth_finding": GROUND_TRUTH_FALSE_ALARM, "batched_for_retraining": False},
    ]

    metrics = calculate_operational_metrics(sample_ledger)
    assert metrics["total_inspections"] == 4
    assert metrics["confirmed_bypass_count"] == 2
    assert metrics["confirmed_leak_count"] == 1
    assert metrics["false_alarm_count"] == 1

    # PPV = 2 / 4 = 0.50 (50.0%)
    assert metrics["ppv"] == 0.5
    assert metrics["ppv_percentage"] == 50.0

    # FAR = 1 / 4 = 0.25 (25.0%)
    assert metrics["false_alarm_rate"] == 0.25
    assert metrics["false_alarm_percentage"] == 25.0


def test_record_field_inspection_and_ppv_update():
    """Validates recording a new field inspection and real-time operational PPV update."""
    res = record_field_inspection(
        alert_id="ALT-UNITTEST-001",
        node_id="J_100",
        dma_id="DMA 01",
        ground_truth_finding=GROUND_TRUTH_BYPASS,
        action_taken="Illegal tap disconnected; fine served.",
        assigned_officer="Eng. K. Perera (Team 3)",
        notes="Concealed polyethylene pipe uncovered.",
    )

    assert res["status"] == "success"
    assert "INSP-" in res["record"]["inspection_id"]
    assert res["record"]["ground_truth_finding"] == GROUND_TRUTH_BYPASS

    metrics = res["metrics"]
    assert metrics["total_inspections"] > 0
    assert metrics["confirmed_bypass_count"] > 0
    # PPV must equal confirmed_bypass / total
    expected_ppv = round(metrics["confirmed_bypass_count"] / metrics["total_inspections"], 4)
    assert metrics["ppv"] == expected_ppv


def test_retraining_trigger_when_ten_unbatched_inspections():
    """Validates that candidate_batch.csv is generated when >= 10 unbatched inspections accumulate."""
    test_ledger = []
    for i in range(10):
        test_ledger.append({
            "inspection_id": f"INSP-TRIG-{i}",
            "alert_id": f"ALT-TRIG-{i}",
            "node_id": "J_100" if i % 2 == 0 else "J_500",
            "dma_id": "DMA 01",
            "dispatch_time": "2026-10-19T08:00:00Z",
            "inspection_time": "2026-10-19T09:30:00Z",
            "ground_truth_finding": GROUND_TRUTH_BYPASS if i < 7 else GROUND_TRUTH_LEAK,
            "assigned_officer": "Eng. Test",
            "action_taken": f"Action {i}",
            "notes": "Trigger test",
            "batched_for_retraining": False,
        })

    batch_path = generate_candidate_retraining_batch(test_ledger, batch_size=10)
    assert batch_path is not None
    assert batch_path.exists()
    assert CANDIDATE_MANIFEST_PATH.exists()

    with open(CANDIDATE_MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        assert manifest["status"] == "AWAITING_HUMAN_IN_THE_LOOP_VALIDATION"
        assert manifest["batch_size"] == 10


def test_api_inspections_endpoints():
    """Tests GET /api/v1/inspections/ledger and GET /api/v1/inspections/metrics."""
    # 1. Metrics endpoint
    resp_metrics = client.get("/api/v1/inspections/metrics")
    assert resp_metrics.status_code == 200
    m_data = resp_metrics.json()
    assert "ppv" in m_data
    assert "false_alarm_rate" in m_data
    assert "total_inspections" in m_data

    # 2. Ledger endpoint
    resp_ledger = client.get("/api/v1/inspections/ledger?limit=5")
    assert resp_ledger.status_code == 200
    l_data = resp_ledger.json()
    assert isinstance(l_data, list)
    assert len(l_data) <= 5


def test_api_alert_investigation_patch_syncs_ledger():
    """Tests PATCH /api/v1/alerts/{alert_id}/investigation writing to field_inspections_ledger.json."""
    alert_id = "ALT-1791355886-J_100"
    payload = {
        "status": "confirmed",
        "assignedTo": "Eng. K. Perera (Team 3)",
        "inspectionDate": "2026-10-19",
        "notes": "Verified secondary branch tap via acoustic stethoscope.",
        "node_id": "J_100",
        "dma_id": "DMA 01",
        "ground_truth_finding": "CONFIRMED_BYPASS",
        "action_taken": "Unauthorized tap confiscated; legal penalty filed.",
    }

    patch_resp = client.patch(f"/api/v1/alerts/{alert_id}/investigation", json=payload)
    assert patch_resp.status_code == 200
    res = patch_resp.json()
    assert res["status"] == "confirmed"
    assert res["audit_ledger_recorded"] is True
    assert res["audit_ledger_details"]["record"]["ground_truth_finding"] == "CONFIRMED_BYPASS"
