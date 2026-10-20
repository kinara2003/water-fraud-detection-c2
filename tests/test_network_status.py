"""
tests/test_network_status.py
Unit and integration tests for GET /api/v1/network/live-map-state endpoint (app/routes/network_status.py).
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_live_map_state_normal(client: TestClient):
    """
    Asserts normal state specifications:
    - active_incident is null
    - All 6 zones have status 'NORMAL' and color '#10b981' (green)
    - No GPS coordinates or junction pins are returned
    """
    response = client.get("/api/v1/network/live-map-state?state=normal")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["simulation_state"] == "normal"
    assert data["active_incident"] is None
    assert data["total_zones"] == 6
    assert data["incident_count"] == 0

    zones = data["zones"]
    assert len(zones) == 6
    for z in zones:
        assert z["status"] == "NORMAL"
        assert z["color"] == "#10b981"
        assert "coordinates" not in z
        assert "latitude" not in z
        assert "longitude" not in z


def test_live_map_state_simulated_bypass(client: TestClient):
    """
    Asserts simulated bypass anomaly state specifications:
    - Flagged zone has status 'FRAUD_ALERT' and color '#ef4444' (red)
    - active_incident contains:
        * zone_id: 'Zone 04'
        * suspect_junction: 'J_100'
        * coordinates: [6.93541, 79.98425]
        * search_radius_m: 50
        * landmark: 'Kaduwela East Sector Road (Near Node J_100 Chamber)'
        * google_maps_url: 'https://www.google.com/maps/search/?api=1&query=6.93541,79.98425'
        * reasons: ['Missing 6.0m pressure', 'Recurring 06:45–09:30 AM', 'Acoustic leak check negative']
    """
    response = client.get("/api/v1/network/live-map-state?state=bypass")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["simulation_state"] == "bypass"
    assert data["incident_count"] == 1

    # Verify active_incident dossier
    incident = data["active_incident"]
    assert incident is not None
    assert incident["zone_id"] == "Zone 04"
    assert incident["suspect_junction"] == "J_100"
    assert incident["coordinates"] == [6.93541, 79.98425]
    assert incident["search_radius_m"] == 50
    assert incident["landmark"] == "Kaduwela East Sector Road (Near Node J_100 Chamber)"
    assert incident["google_maps_url"] == "https://www.google.com/maps/search/?api=1&query=6.93541,79.98425"
    assert incident["reasons"] == [
        "Missing 6.0m pressure",
        "Recurring 06:45–09:30 AM",
        "Acoustic leak check negative",
    ]

    # Verify zones: Zone 04 is FRAUD_ALERT (#ef4444); all other 5 zones remain NORMAL (#10b981)
    zones_by_id = {z["zone_id"]: z for z in data["zones"]}
    assert len(zones_by_id) == 6

    # Zone 04
    z4 = zones_by_id["Zone 04"]
    assert z4["status"] == "FRAUD_ALERT"
    assert z4["color"] == "#ef4444"
    assert z4["sensor_node_id"] == "J_100"
    assert z4["risk_score"] >= 70.0

    # Other zones remain normal
    for zid in ["Zone 01", "Zone 02", "Zone 03", "Zone 05", "Zone 06"]:
        z = zones_by_id[zid]
        assert z["status"] == "NORMAL"
        assert z["color"] == "#10b981"


def test_simulation_toggle_post_endpoint(client: TestClient):
    """Asserts that POST /api/v1/network/live-map-state/simulate toggles server simulation state."""
    # 1. Toggle to bypass
    resp_post = client.post("/api/v1/network/live-map-state/simulate?state=bypass")
    assert resp_post.status_code == 200
    assert resp_post.json()["active_incident"] is not None

    # Verify GET without parameters reflects bypass state
    resp_get = client.get("/api/v1/network/live-map-state")
    assert resp_get.json()["active_incident"] is not None
    assert resp_get.json()["zones"][3]["status"] == "FRAUD_ALERT"

    # 2. Toggle back to normal
    resp_normal = client.post("/api/v1/network/live-map-state/simulate?state=normal")
    assert resp_normal.status_code == 200
    assert resp_normal.json()["active_incident"] is None

    # Verify GET without parameters reflects normal state
    resp_get2 = client.get("/api/v1/network/live-map-state")
    assert resp_get2.json()["active_incident"] is None
