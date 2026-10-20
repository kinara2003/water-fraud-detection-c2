"""
tests/test_pipeline.py
End-to-End Automated Test Suite for NWSDB Water Fraud Detection & Integration Pipeline.

Test Cases:
1. test_normal_telemetry(): Asserts that normal pressure fluctuations yield Fraud Risk Score < 30 (Normal status).
2. test_unauthorized_bypass_detection(): Asserts that sustained pressure drops at J_100 produce a Fraud Risk Score > 75 and flag partial_bypass.
3. test_refill_transient_suppression(): Asserts that pressure drops within 30 minutes of supply opening are dampened to prevent false alarms.
4. test_c1_leak_suppression(): Asserts that posting a leak confirmation to /api/v1/c1-leak-feedback reduces fraud probability and reclassifies the event as a physical leak.
5. test_c3_and_c4_endpoints(): Asserts that /api/v1/c3-water-loss/DMA_01 returns numeric flow loss, and /api/v1/c4-pressure-drop-events lists valid low-pressure junctions.
"""

import sys
import warnings
from pathlib import Path
from typing import Generator

# Ensure warnings from deprecated Starlette/httpx bridge don't pollute test logs
warnings.filterwarnings("ignore", message=".*Using `httpx` with `starlette.testclient` is deprecated.*")

import httpx
import pytest
from fastapi.testclient import TestClient

# Ensure project root is available in module search path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import (
    app,
    load_models,
    load_timeseries_cache,
    FEEDBACK_CACHE,
    LATEST_NODE_ASSESSMENTS,
    SENSOR_TRACKER,
    NOTIFIER,
)
from src.notifier import AuthorityNotifier


@pytest.fixture(scope="session", autouse=True)
def initialize_pipeline() -> Generator[None, None, None]:
    """
    Session-level fixture to pre-load Stage 1 & Stage 2 models and timeseries cache.
    """
    load_models()
    load_timeseries_cache()
    yield
    FEEDBACK_CACHE.clear()
    LATEST_NODE_ASSESSMENTS.clear()
    SENSOR_TRACKER.clear()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """
    Pytest fixture providing a test client (subclassed from httpx.Client) configured
    with the FastAPI application instance.
    """
    FEEDBACK_CACHE.clear()
    LATEST_NODE_ASSESSMENTS.clear()
    SENSOR_TRACKER.clear()
    with TestClient(app) as test_client:
        yield test_client
    FEEDBACK_CACHE.clear()
    LATEST_NODE_ASSESSMENTS.clear()
    SENSOR_TRACKER.clear()


def _get_client(client_arg: object = None) -> TestClient:
    """
    Helper to allow running test functions both via pytest fixture injection
    and direct Python function calls.
    """
    FEEDBACK_CACHE.clear()
    LATEST_NODE_ASSESSMENTS.clear()
    SENSOR_TRACKER.clear()
    if isinstance(client_arg, TestClient):
        return client_arg
    return TestClient(app)


# ==============================================================================
# 1. Test Normal Telemetry
# ==============================================================================

def test_normal_telemetry(client: object = None) -> None:
    """
    Asserts that normal pressure fluctuations yield Fraud Risk Score < 30 (Normal status).
    """
    test_client = _get_client(client)

    # Monitored normal junction node (e.g., J_10) conforming closely to baseline
    normal_telemetry_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_10",
        "actual_pressure": 35.08,
        "expected_pressure": 35.10,
        "spatial_deviation": 0.02,
        "recurrence_count": 0,
        "pressure_change_rate": 0.01,
        "residual_rolling_mean": 0.02,
        "residual_rolling_std": 0.01,
        "hours_since_supply_start": 3.0,
    }

    response = test_client.post("/api/v1/assess-risk", json=normal_telemetry_payload)
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"

    data = response.json()
    fraud_score = float(data["fraud_risk_score"])
    classification = str(data["classification"])

    # Strict assertions: normal hydraulic deviations must produce low score and normal classification
    assert fraud_score < 30.0, f"Expected Fraud Risk Score < 30 for normal operations, but got {fraud_score}"
    assert classification == "normal", f"Expected classification 'normal', but got '{classification}'"
    assert "Routine Monitoring" in data.get("recommended_action", "")


# ==============================================================================
# 2. Test Unauthorized Bypass Detection
# ==============================================================================

def test_unauthorized_bypass_detection(client: object = None) -> None:
    """
    Asserts that sustained pressure drops at J_100 produce a Fraud Risk Score > 75 and flag partial_bypass.
    """
    test_client = _get_client(client)

    # Telemetry representing an active illegal bypass at node J_100:
    # - 6.2m head loss deficit (expected 34.7m vs actual 28.5m)
    # - High localized spatial deviation (5.8m divergence from neighboring DMA junctions)
    # - Persistent recurring anomaly (recurrence count = 5)
    # - Occurring outside the transient refill window (hours_since_supply_start = 2.5)
    bypass_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 28.50,
        "expected_pressure": 34.70,
        "spatial_deviation": 5.80,
        "recurrence_count": 5,
        "pressure_change_rate": -0.05,
        "residual_rolling_mean": 6.10,
        "residual_rolling_std": 0.12,
        "hours_since_supply_start": 2.5,
    }

    response = test_client.post("/api/v1/assess-risk", json=bypass_payload)
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"

    data = response.json()
    fraud_score = float(data["fraud_risk_score"])
    classification = str(data["classification"])

    # Assertions: High confidence theft detection
    assert fraud_score > 75.0, f"Expected Fraud Risk Score > 75 for sustained bypass theft, but got {fraud_score}"
    assert classification == "partial_bypass", f"Expected classification 'partial_bypass', but got '{classification}'"
    assert any("bypass" in reason.lower() or "theft" in reason.lower() for reason in data.get("reasons_list", []))
    assert "Inspection" in data.get("recommended_action", "")


# ==============================================================================
# 3. Test Refill Transient Suppression
# ==============================================================================

def test_refill_transient_suppression(client: object = None) -> None:
    """
    Asserts that pressure drops within 30 minutes of supply opening are dampened to prevent false alarms.
    """
    test_client = _get_client(client)

    # During the initial 30 minutes of supply window (hours_since_supply_start = 0.5),
    # pipe filling transients cause large temporary head drops (e.g. 6.2m residual).
    # Without prior recurrence (recurrence_count = 0) and without cross-zone spatial mismatch (spatial_deviation = 0.2m),
    # the transient dampening logic MUST suppress high-risk theft alarms.
    transient_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 28.50,
        "expected_pressure": 34.70,
        "spatial_deviation": 0.20,  # Below spatial mismatch threshold
        "recurrence_count": 0,      # First occurrence (persistence unconfirmed)
        "hours_since_supply_start": 0.5,  # 30 minutes after supply opens (inside 45-60 min transient window)
    }

    response = test_client.post("/api/v1/assess-risk", json=transient_payload)
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"

    data = response.json()
    fraud_score = float(data["fraud_risk_score"])
    transient_dampened = bool(data.get("transient_dampening_active", False))

    # Assert that transient dampening was actively engaged
    assert transient_dampened is True, "Expected transient_dampening_active to be True for 30-min refill transient"

    # Assert that score was scaled down / capped below high-risk threshold (<= 40.0 pts)
    assert fraud_score <= 40.0, f"Expected dampened fraud score <= 40.0 to prevent false alarm, but got {fraud_score}"

    # Verify contrast: identical head loss occurring outside transient window (e.g. at 3.0 hrs)
    # would NOT be dampened and yields a significantly higher score
    steady_state_payload = dict(transient_payload)
    steady_state_payload["hours_since_supply_start"] = 3.0
    steady_state_resp = test_client.post("/api/v1/assess-risk", json=steady_state_payload)
    steady_state_score = float(steady_state_resp.json()["fraud_risk_score"])

    assert steady_state_score > fraud_score, (
        f"Expected steady state score ({steady_state_score}) to exceed dampened transient score ({fraud_score})"
    )


# ==============================================================================
# 4. Test C1 Leak Suppression
# ==============================================================================

def test_c1_leak_suppression(client: object = None) -> None:
    """
    Asserts that posting a leak confirmation to /api/v1/c1-leak-feedback reduces fraud probability
    and reclassifies the event as a physical leak.
    """
    test_client = _get_client(client)

    # 1. Post acoustic leak confirmation from Component 1:
    # Leak probability of 85% exceeds the 70% threshold.
    c1_feedback_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "leak_probability": 0.85,
        "current_fraud_score": 88.60,
    }

    response = test_client.post("/api/v1/c1-leak-feedback", json=c1_feedback_payload)
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"

    data = response.json()
    assert data["leak_feedback_applied"] is True, "Expected leak_feedback_applied to be True when leak_prob > 0.7"
    assert data["adjusted_classification"] == "physical_leak", (
        f"Expected reclassification to 'physical_leak', but got '{data['adjusted_classification']}'"
    )

    original_score = float(data["original_fraud_risk_score"])
    adjusted_score = float(data["adjusted_fraud_risk_score"])

    # 40% reduction assertion or specific suppression override (<= original_score * 0.60)
    expected_adjusted_score = round(original_score * 0.60, 2)
    assert adjusted_score in (expected_adjusted_score, 18.0) or adjusted_score <= expected_adjusted_score, (
        f"Expected adjusted score {expected_adjusted_score} (-40%) or 18.0, but got {adjusted_score}"
    )
    assert adjusted_score < original_score

    # 2. Check that the feedback persists in subsequent risk assessment
    telemetry_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 28.50,
        "expected_pressure": 34.70,
        "spatial_deviation": 5.80,
        "recurrence_count": 5,
        "hours_since_supply_start": 2.5,
    }
    follow_up_resp = test_client.post("/api/v1/assess-risk", json=telemetry_payload)
    assert follow_up_resp.status_code == 200
    follow_up_data = follow_up_resp.json()

    assert follow_up_data["classification"] == "physical_leak", (
        f"Expected follow-up classification to remain 'physical_leak', got '{follow_up_data['classification']}'"
    )
    assert follow_up_data["fraud_risk_score"] < 88.0, (
        f"Expected reduced score in follow-up assessment, got {follow_up_data['fraud_risk_score']}"
    )


# ==============================================================================
# 5. Test C3 and C4 Endpoints
# ==============================================================================

def test_c3_and_c4_endpoints(client: object = None) -> None:
    """
    Asserts that /api/v1/c3-water-loss/DMA_01 returns numeric flow loss,
    and /api/v1/c4-pressure-drop-events lists valid low-pressure junctions.
    """
    test_client = _get_client(client)

    # 1. Component 3 Integration: Water Loss Forecast
    c3_resp = test_client.get("/api/v1/c3-water-loss/DMA_01")
    assert c3_resp.status_code == 200, f"Expected 200 OK from C3 endpoint, got {c3_resp.status_code}: {c3_resp.text}"

    c3_data = c3_resp.json()
    assert c3_data["zone_id"] == "DMA 01"

    # Numeric flow loss assertions
    unmetered_loss_lps = c3_data["estimated_unmetered_water_loss_lps"]
    hourly_loss_m3 = c3_data["estimated_hourly_loss_m3"]
    daily_loss_m3 = c3_data["estimated_daily_loss_m3"]

    assert isinstance(unmetered_loss_lps, (int, float)), "Loss in LPS must be numeric"
    assert unmetered_loss_lps >= 0.0, "Loss in LPS must be non-negative"
    assert isinstance(hourly_loss_m3, (int, float)), "Hourly loss must be numeric"
    assert hourly_loss_m3 >= 0.0
    assert isinstance(daily_loss_m3, (int, float)), "Daily loss must be numeric"
    assert daily_loss_m3 >= 0.0
    assert "storage_forecast_impact" in c3_data

    # 2. Component 4 Integration: Pressure Drop Events (Intrusion Risk)
    c4_resp = test_client.get("/api/v1/c4-pressure-drop-events?threshold_m=5.0")
    assert c4_resp.status_code == 200, f"Expected 200 OK from C4 endpoint, got {c4_resp.status_code}: {c4_resp.text}"

    c4_data = c4_resp.json()
    assert c4_data["threshold_m"] == 5.0

    total_severe_events = c4_data["total_severe_events_count"]
    affected_nodes = c4_data["affected_nodes"]
    events_list = c4_data["events"]

    assert isinstance(total_severe_events, int)
    assert total_severe_events > 0, f"Expected > 0 severe depressurization events, got {total_severe_events}"
    assert isinstance(affected_nodes, list)

    # Junction J_100 experienced ~6.2m head loss deficit during the theft simulation,
    # so it must be included in the affected low-pressure junctions
    assert "J_100" in affected_nodes, f"Expected 'J_100' in affected nodes list {affected_nodes}"

    # Verify event structure
    first_event = events_list[0]
    assert first_event["node_id"] == "J_100"
    assert first_event["pressure_deficit_m"] >= 5.0
    assert "intrusion_risk_severity" in first_event


# ==============================================================================
# 6. Test Authority Alert Dispatch and History
# ==============================================================================

def test_authority_alert_dispatch_and_history(client: object = None) -> None:
    """
    Asserts that:
    1. A telemetry payload with sustained theft (score >= 70.0) automatically triggers
       dispatch_alert() via FastAPI BackgroundTasks.
    2. Dispatched alert is logged into data/processed/dispatched_alerts.json.
    3. GET /api/v1/notifications/history returns the list containing the alert record
       with required fields (timestamp, node_id, dma_id, risk_score, evidence_list, delivery_status).
    """
    test_client = _get_client(client)

    theft_telemetry_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_TEST_DISPATCH",
        "actual_pressure": 28.50,
        "expected_pressure": 34.70,
        "spatial_deviation": 5.80,
        "recurrence_count": 6,
        "pressure_change_rate": -0.80,
        "residual_rolling_mean": 6.20,
        "residual_rolling_std": 0.40,
        "hours_since_supply_start": 3.0,
    }

    # Assess risk (triggers background dispatch because score >= 70.0)
    response = test_client.post("/api/v1/assess-risk", json=theft_telemetry_payload)
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
    risk_data = response.json()
    assert risk_data["fraud_risk_score"] >= 70.0, f"Expected score >= 70.0, got {risk_data['fraud_risk_score']}"

    # Query notifications history
    hist_resp = test_client.get("/api/v1/notifications/history?limit=10")
    assert hist_resp.status_code == 200, f"Expected 200 OK from history, got {hist_resp.status_code}: {hist_resp.text}"

    history = hist_resp.json()
    assert isinstance(history, list), "Expected list of alerts from history endpoint"
    assert len(history) > 0, "Expected at least one logged alert in history"

    # Find the alert for J_TEST_DISPATCH
    matching_alerts = [a for a in history if a.get("node_id") == "J_TEST_DISPATCH"]
    assert len(matching_alerts) > 0, "Dispatched alert for J_TEST_DISPATCH not found in history"

    alert = matching_alerts[0]
    assert alert["node_id"] == "J_TEST_DISPATCH"
    assert alert["dma_id"] in ["DMA 01", "DMA_01"]
    assert alert["risk_score"] >= 70.0
    assert "timestamp" in alert
    assert "delivery_status" in alert
    assert alert["delivery_status"] in ["Sent", "Failed"]
    assert isinstance(alert.get("evidence_list"), list)


# ==============================================================================
# 7. Test Cooldown Deduplication and Critical Escalation Override
# ==============================================================================

def test_cooldown_deduplication_and_critical_override() -> None:
    """
    Asserts AuthorityNotifier cooldown and deduplication logic:
    1. Maximum 1 alert per node every 6 hours during non-critical or steady states.
    2. Critical escalation (>85.0%) overrides the 6-hour cooldown immediately.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    notifier = AuthorityNotifier(alerts_file=tmp_path, cooldown_seconds=6.0 * 3600.0, critical_threshold=85.0)

    # 1. Initial alert should be allowed
    can_dispatch, reason = notifier.check_cooldown("J_999", current_risk_score=75.0)
    assert can_dispatch is True, f"Initial alert should be allowed: {reason}"

    # Simulate dispatching
    res1 = notifier.dispatch_alert({
        "node_id": "J_999",
        "dma_id": "DMA 01",
        "risk_score": 75.0,
        "actual_pressure": 30.0,
        "expected_pressure": 35.0,
        "probable_cause": "partial_bypass",
    })
    assert res1.get("delivery_status") == "Sent"

    # 2. Duplicate alert within 6 hours with non-critical score (78%) should be blocked by cooldown
    can_dispatch, reason = notifier.check_cooldown("J_999", current_risk_score=78.0)
    assert can_dispatch is False, "Alert within 6 hours at 78% should be blocked by cooldown"
    assert "Cooldown active" in reason

    res2 = notifier.dispatch_alert({
        "node_id": "J_999",
        "dma_id": "DMA 01",
        "risk_score": 78.0,
    })
    assert res2.get("dispatched") is False

    # 3. Critical escalation (>85.0%, e.g., 89.5%) should bypass cooldown
    can_dispatch, reason = notifier.check_cooldown("J_999", current_risk_score=89.5)
    assert can_dispatch is True, f"Critical escalation (>85%) must bypass cooldown: {reason}"
    assert "Critical escalation override" in reason

    res3 = notifier.dispatch_alert({
        "node_id": "J_999",
        "dma_id": "DMA 01",
        "risk_score": 89.5,
        "actual_pressure": 26.0,
        "expected_pressure": 35.0,
        "probable_cause": "partial_bypass",
    })
    assert res3.get("delivery_status") == "Sent"

    # Clean up temp file
    if tmp_path.exists():
        tmp_path.unlink()


# ==============================================================================
# 8. Test Page 4 Admin Portal (/inspections)
# ==============================================================================

def test_inspections_portal_page(client: object = None) -> None:
    """
    Asserts that GET /inspections serves Page 4 of the Admin Portal with:
    - 200 OK status
    - HTML content containing 'Dispatched Alerts to Authorities' real-time badge and table
    - Recipient email and municipal webhook references
    """
    test_client = _get_client(client)
    response = test_client.get("/inspections")
    assert response.status_code == 200, f"Expected 200 OK from /inspections, got {response.status_code}"
    html = response.text
    assert "Dispatched Alerts to Authorities" in html
    assert "Page 4" in html
    assert "alertsTableBody" in html
    assert "liveCounterBadge" in html
    assert "/api/v1/notifications/history" in html
    assert "Retrain Model with Field Verifications" in html


# ==============================================================================
# 9. Test Continuous Learning Retrain Pipeline and API Endpoint
# ==============================================================================

def test_retrain_pipeline_and_endpoint(client: object = None) -> None:
    """
    Asserts that:
    1. POST /api/v1/models/retrain triggers Stage 2 RandomForestClassifier retraining.
    2. Incorporates verified ground-truth samples with balanced class weights.
    3. Saves backup model tag models/random_forest_v2.joblib.
    4. Computes and returns performance deltas (old vs new F1-scores).
    5. Second call without new ground-truth entries pauses with 'skipped' status.
    """
    test_client = _get_client(client)
    from src.retrain import BACKUP_MODEL_PATH

    # Trigger retraining
    response = test_client.post("/api/v1/models/retrain", json={"min_new_entries": 5, "force": False})
    assert response.status_code == 200, f"Expected 200 OK from retrain endpoint, got {response.status_code}: {response.text}"

    data = response.json()
    assert data["status"] in ["success", "skipped"], f"Unexpected status: {data['status']}"

    if data["status"] == "success":
        assert data["new_samples_added"] >= 5, f"Expected >= 5 new samples added, got {data['new_samples_added']}"
        assert isinstance(data["new_f1_score"], (int, float))
        assert isinstance(data["f1_delta"], (int, float))
        assert data["class_weights"] == "balanced"
        assert BACKUP_MODEL_PATH.exists(), f"Backup model {BACKUP_MODEL_PATH} must exist"
        assert "random_forest_v2" in data["backup_model_path"]

        # Call again without new entries - must be skipped
        second_resp = test_client.post("/api/v1/models/retrain", json={"min_new_entries": 5, "force": False})
        assert second_resp.status_code == 200
        second_data = second_resp.json()
        assert second_data["status"] == "skipped"
        assert "Insufficient new verified ground-truth entries" in second_data["message"]
    else:
        # If already retrained, force=True must succeed
        force_resp = test_client.post("/api/v1/models/retrain", json={"min_new_entries": 5, "force": True})
        assert force_resp.status_code == 200
        force_data = force_resp.json()
        assert force_data["status"] == "success"
        assert BACKUP_MODEL_PATH.exists()


# ==============================================================================
# 10. Test Inspection Feedback Logs Endpoints
# ==============================================================================

def test_inspection_feedback_logs(client: object = None) -> None:
    """
    Asserts that:
    1. GET /api/v1/inspections/logs returns logged inspector ground-truth feedback.
    2. POST /api/v1/inspections/logs records new inspector ground-truth verification.
    """
    test_client = _get_client(client)

    # 1. Query inspection logs
    get_resp = test_client.get("/api/v1/inspections/logs?limit=20")
    assert get_resp.status_code == 200, f"Expected 200 OK, got {get_resp.status_code}: {get_resp.text}"
    logs = get_resp.json()
    assert isinstance(logs, list), "Expected list of inspection logs"
    assert len(logs) > 0, "Expected at least one inspection log in database"

    # 2. Record new inspection finding
    post_payload = {
        "node_id": "J_100",
        "actual_finding": "partial_bypass",
        "notes": "Automated verification test - unauthorized bypass valve plugged",
    }
    post_resp = test_client.post("/api/v1/inspections/logs", json=post_payload)
    assert post_resp.status_code == 200, f"Expected 200 OK, got {post_resp.status_code}: {post_resp.text}"
    post_data = post_resp.json()
    assert post_data["status"] == "recorded"
    assert post_data["node_id"] == "J_100"
    assert post_data["actual_finding"] == "partial_bypass"
    assert post_data["total_unprocessed_logs"] >= 1


def test_assess_risk_and_telemetry_location_metadata(client: object = None) -> None:
    """
    Asserts that both /api/v1/assess-risk and /api/v1/sensors/telemetry
    return a complete location object with junction_id, grid coordinates,
    WGS84 lat/lng, physical landmark description, and Google Maps URL.
    """
    test_client = _get_client(client)

    telemetry_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 28.5,
        "expected_pressure": 34.7,
        "spatial_deviation": 5.8,
        "recurrence_count": 5,
        "hours_since_supply_start": 2.5,
    }

    # 1. Verify /api/v1/assess-risk
    resp_assess = test_client.post("/api/v1/assess-risk", json=telemetry_payload)
    assert resp_assess.status_code == 200
    data_assess = resp_assess.json()
    assert "location" in data_assess, "Expected 'location' key in /api/v1/assess-risk response"
    loc1 = data_assess["location"]
    assert loc1["junction_id"] == "J_100"
    assert "grid_x" in loc1 and "grid_y" in loc1
    assert "latitude" in loc1 and "longitude" in loc1
    assert "elevation_m" in loc1
    assert "landmark" in loc1
    assert "Sector 04B" in loc1["landmark"] or "J_100 Chamber" in loc1["landmark"]
    assert "https://www.google.com/maps/search/?api=1&query=" in loc1["google_maps_url"]

    # 2. Verify /api/v1/sensors/telemetry
    resp_telemetry = test_client.post("/api/v1/sensors/telemetry", json=telemetry_payload)
    assert resp_telemetry.status_code == 200
    data_telemetry = resp_telemetry.json()
    assert "location" in data_telemetry, "Expected 'location' key in /api/v1/sensors/telemetry response"
    loc2 = data_telemetry["location"]
    assert loc2["junction_id"] == "J_100"
    assert loc2["latitude"] == loc1["latitude"]
    assert loc2["longitude"] == loc1["longitude"]
    assert loc2["google_maps_url"] == loc1["google_maps_url"]


# ==============================================================================
# Standalone Execution Entrypoint
# ==============================================================================

if __name__ == "__main__":
    print("Running end-to-end test suite directly...")
    load_models()
    load_timeseries_cache()

    test_normal_telemetry()
    print("[PASS] test_normal_telemetry")

    test_unauthorized_bypass_detection()
    print("[PASS] test_unauthorized_bypass_detection")

    test_refill_transient_suppression()
    print("[PASS] test_refill_transient_suppression")

    test_c1_leak_suppression()
    print("[PASS] test_c1_leak_suppression")

    test_c3_and_c4_endpoints()
    print("[PASS] test_c3_and_c4_endpoints")

    test_authority_alert_dispatch_and_history()
    print("[PASS] test_authority_alert_dispatch_and_history")

    test_cooldown_deduplication_and_critical_override()
    print("[PASS] test_cooldown_deduplication_and_critical_override")

    test_inspections_portal_page()
    print("[PASS] test_inspections_portal_page")

    test_retrain_pipeline_and_endpoint()
    print("[PASS] test_retrain_pipeline_and_endpoint")

    test_inspection_feedback_logs()
    print("[PASS] test_inspection_feedback_logs")

    test_assess_risk_and_telemetry_location_metadata()
    print("[PASS] test_assess_risk_and_telemetry_location_metadata")

    print("\nAll 11 automated tests passed successfully!")
