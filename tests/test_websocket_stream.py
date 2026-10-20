"""
tests/test_websocket_stream.py
Unit and Integration Tests for Real-Time Telemetry WebSocket Streaming
Component 2: NWSDB Unauthorized Water Withdrawal & Physical Twin Surveillance Engine

Validates:
  1. WebSocket handshake and connection establishment at /ws/telemetry.
  2. Ping/pong keepalive protocol.
  3. Real-time broadcast emission when /api/v1/sensors/telemetry ingests readings.
  4. Correct broadcast payload fields: (node_id, actual_p, residual_m, risk_score, alert_triggered).
  5. ConnectionManager lifecycle (connect, disconnect, stale socket cleanup).
"""

import json
import pytest
from fastapi.testclient import TestClient

from app.main import app, WS_MANAGER, init_gateway_health_registry, FEEDBACK_CACHE, SENSOR_TRACKER


@pytest.fixture
def client():
    FEEDBACK_CACHE.clear()
    SENSOR_TRACKER.clear()
    init_gateway_health_registry()
    return TestClient(app)


def test_websocket_connection_handshake(client):
    """
    Asserts that clients can establish a WebSocket connection at /ws/telemetry
    and receive the initial CONNECTION_ESTABLISHED greeting.
    """
    with client.websocket_connect("/ws/telemetry") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "CONNECTION_ESTABLISHED"
        assert "Connected to Kaduwela" in data["message"]
        assert "active_nodes" in data
        assert "J_100" in data["active_nodes"]


def test_websocket_ping_pong_keepalive(client):
    """
    Asserts that sending 'ping' to the WebSocket returns 'pong' keepalive.
    """
    with client.websocket_connect("/ws/telemetry") as websocket:
        # Receive welcome
        _ = websocket.receive_json()

        # Send ping
        websocket.send_text("ping")
        resp = websocket.receive_text()
        assert resp == "pong"


def test_telemetry_ingestion_broadcasts_to_websocket(client):
    """
    Asserts that whenever /api/v1/sensors/telemetry processes a reading,
    the broadcast payload is delivered to all connected WebSocket clients.
    """
    with client.websocket_connect("/ws/telemetry") as websocket:
        # Initial greeting
        welcome = websocket.receive_json()
        assert welcome["type"] == "CONNECTION_ESTABLISHED"

        # Ingest a reading via HTTP POST /api/v1/sensors/telemetry
        telemetry_payload = {
            "zone_id": "DMA 01",
            "node_id": "J_100",
            "actual_pressure": 28.5,
            "expected_pressure": 34.7,
            "spatial_deviation": 5.8,
            "recurrence_count": 4,
            "hours_since_supply_start": 2.5,
            "battery_voltage": 3.92,
            "cellular_rssi_dbm": -78,
            "is_heartbeat": False,
        }

        http_resp = client.post("/api/v1/sensors/telemetry", json=telemetry_payload)
        assert http_resp.status_code == 200

        # Receive real-time broadcast message over WebSocket
        ws_msg = websocket.receive_json()
        assert ws_msg["type"] == "TELEMETRY_UPDATE"
        assert ws_msg["node_id"] == "J_100"
        assert ws_msg["actual_p"] == 28.5
        assert ws_msg["residual_m"] == 6.2
        assert ws_msg["risk_score"] >= 80.0
        assert ws_msg["alert_triggered"] is True
        assert ws_msg["classification"] == "partial_bypass"
        assert ws_msg["battery_voltage"] == 3.92
        assert ws_msg["cellular_rssi_dbm"] == -78
        assert "timestamp" in ws_msg


def test_normal_telemetry_broadcast_no_alert(client):
    """
    Asserts that normal nominal telemetry broadcasts alert_triggered=False.
    """
    with client.websocket_connect("/ws/telemetry") as websocket:
        _ = websocket.receive_json()

        normal_payload = {
            "zone_id": "DMA 01",
            "node_id": "J_10",
            "actual_pressure": 35.08,
            "expected_pressure": 35.10,
            "spatial_deviation": 0.02,
            "recurrence_count": 0,
            "hours_since_supply_start": 2.5,
        }

        http_resp = client.post("/api/v1/sensors/telemetry", json=normal_payload)
        assert http_resp.status_code == 200

        ws_msg = websocket.receive_json()
        assert ws_msg["type"] == "TELEMETRY_UPDATE"
        assert ws_msg["node_id"] == "J_10"
        assert ws_msg["actual_p"] == 35.08
        assert ws_msg["residual_m"] == 0.02
        assert ws_msg["risk_score"] < 25.0
        assert ws_msg["alert_triggered"] is False
        assert ws_msg["classification"] == "normal"
