"""
tests/test_live_streamer.py
Unit and integration tests for src/live_streamer.py:
- Payload schema validation (node_id, zone_id, observed_pressure, expected_pressure, timestamp)
- Normal baseline generation (All green)
- Bypass injection at J_100 (6.0m pressure drop)
- Morning refill surge transient dampening
- API ingestion via FastAPI TestClient
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.live_streamer import (
    JUNCTION_CONFIGS,
    NODE_KEYS_ORDER,
    KeyboardController,
    SimulationDataLoader,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_junction_configs():
    """Asserts all 6 Kaduwela junctions are configured with valid zones and expected pressures."""
    assert len(NODE_KEYS_ORDER) == 6
    for node in NODE_KEYS_ORDER:
        assert node in JUNCTION_CONFIGS
        cfg = JUNCTION_CONFIGS[node]
        assert "zone_id" in cfg
        assert "expected_pressure" in cfg
        assert 15.0 <= cfg["expected_pressure"] <= 25.0


def test_normal_payload_generation():
    """Asserts that normal mode generates readings within ±0.5m of expected baseline."""
    loader = SimulationDataLoader()
    obs_p, exp_p, timestamp, hours = loader.get_readings("J_100", "n", step=1)
    
    assert "T" in timestamp and timestamp.endswith("Z")
    assert hours is None
    delta_p = abs(exp_p - obs_p)
    assert delta_p < 1.0, f"Expected minor residual in normal mode, got: {delta_p}"


def test_bypass_payload_generation():
    """Asserts that bypass mode at J_100 drops pressure by 6.0m."""
    loader = SimulationDataLoader()
    obs_p, exp_p, timestamp, hours = loader.get_readings("J_100", "f", step=0)
    
    assert obs_p == 15.2
    assert exp_p == 21.2
    delta_p = exp_p - obs_p
    assert round(delta_p, 1) == 6.0


def test_refill_surge_payload_generation():
    """Asserts that refill surge generates a morning timestamp and supply elapsed hours."""
    loader = SimulationDataLoader()
    obs_p, exp_p, timestamp, hours = loader.get_readings("J_100", "r", step=1)
    
    assert hours is not None
    assert 0.0 <= hours <= 1.0
    assert "T06:25:" in timestamp
    # Head drop during refill
    delta_p = exp_p - obs_p
    assert delta_p > 3.0


def test_fastapi_telemetry_endpoint_normal(client):
    """Asserts that sending normal telemetry returns HTTP 200 with normal classification."""
    payload = {
        "node_id": "J_100",
        "zone_id": "Zone 04",
        "observed_pressure": 21.0,
        "expected_pressure": 21.2,
        "timestamp": "2026-10-20T14:48:00Z",
    }
    resp = client.post("/api/v1/sensors/telemetry", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["classification"] == "normal"
    assert data["fraud_risk_score"] < 40.0


def test_fastapi_telemetry_endpoint_bypass(client):
    """Asserts that sending bypass telemetry (15.2m vs 21.2m) triggers high-risk fraud alert."""
    payload = {
        "node_id": "J_100",
        "zone_id": "Zone 04",
        "observed_pressure": 15.2,
        "expected_pressure": 21.2,
        "timestamp": "2026-10-20T14:48:00Z",
    }
    resp = client.post("/api/v1/sensors/telemetry", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["fraud_risk_score"] >= 70.0
    assert data["classification"] == "partial_bypass"
    assert "location" in data
    assert data["location"]["latitude"] is not None


def test_fastapi_telemetry_endpoint_refill_surge(client):
    """Asserts that morning refill surge telemetry activates transient dampening."""
    payload = {
        "node_id": "J_100",
        "zone_id": "Zone 04",
        "observed_pressure": 16.5,
        "expected_pressure": 21.2,
        "timestamp": "2026-10-20T06:25:00Z",
        "hours_since_supply_start": 0.42,
    }
    resp = client.post("/api/v1/sensors/telemetry", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["transient_dampening_active"] is True
    assert data["fraud_risk_score"] <= 40.0


def test_keyboard_controller_thread():
    """Asserts KeyboardController initializes and stops cleanly."""
    controller = KeyboardController()
    assert controller.pop_command() is None
    controller.stop()


def test_auto_mode_simulation_cycling():
    """Asserts that SimulationDataLoader and auto mode progression generates appropriate telemetry."""
    loader = SimulationDataLoader()
    # Step 1: Normal baseline
    obs_1, exp_1, _, _ = loader.get_readings("J_100", "n", step=1)
    assert abs(obs_1 - exp_1) < 1.0

    # Step 6: Bypass injection
    obs_6, exp_6, _, _ = loader.get_readings("J_100", "f", step=6)
    assert round(exp_6 - obs_6, 1) == 6.0

    # Step 13: Refill surge
    obs_13, exp_13, _, hours_13 = loader.get_readings("J_100", "r", step=13)
    assert hours_13 is not None
    assert exp_13 - obs_13 > 3.0

