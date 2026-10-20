"""
tests/test_edge_gateway.py
Unit and Integration Tests for Kaduwela Physical Edge Telemetry Concentrators
Component 2: NWSDB Unauthorized Water Withdrawal & Physical Twin Surveillance Engine

Validates:
  1. Deadband Filtering (ΔP < 0.05m suppressed, 60-min periodic heartbeat transmitted)
  2. Battery Voltage (3.4V to 4.2V) and Cellular RSSI (-115 to -65 dBm) Synthesis
  3. Local SQLite Store-and-Forward Buffer with Strict Chronological FIFO Ordering
  4. FastAPI Endpoint GET /api/v1/sensors/gateway-health
"""

import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app, init_gateway_health_registry, get_gateway_health_summary
from src.edge_gateway_sim import EdgeGateway, EdgeBufferManager, EdgeConcentratorNetwork


@pytest.fixture
def test_client():
    init_gateway_health_registry()
    return TestClient(app)


@pytest.fixture
def temp_buffer_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    yield db_path
    if db_path.exists():
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_deadband_filtering_suppression():
    """
    Asserts that pressure changes |ΔP| < 0.05m are suppressed when elapsed time < 60 minutes.
    """
    gw = EdgeGateway(
        node_id="J_100",
        dma_id="DMA 01",
        gateway_id="GW-DMA01-J100",
        deadband_threshold_m=0.05,
        heartbeat_interval_sec=3600.0,
    )

    # 1. Initial boot reading -> must transmit
    tx, payload, meta = gw.evaluate_reading(
        actual_pressure=34.70,
        expected_pressure=34.70,
        sim_timestamp_sec=0.0,
    )
    assert tx is True
    assert payload is not None
    assert payload["is_heartbeat"] is False

    # 2. Reading at +15 min with |ΔP| = 0.01m < 0.05m -> must suppress
    tx_sub, payload_sub, meta_sub = gw.evaluate_reading(
        actual_pressure=34.71,
        expected_pressure=34.70,
        sim_timestamp_sec=900.0,
    )
    assert tx_sub is False
    assert payload_sub is None
    assert gw.deadband_suppressed_count == 1

    # 3. Reading at +30 min with |ΔP| = 0.02m < 0.05m -> must suppress
    tx_sub2, payload_sub2, meta_sub2 = gw.evaluate_reading(
        actual_pressure=34.69,
        expected_pressure=34.70,
        sim_timestamp_sec=1800.0,
    )
    assert tx_sub2 is False
    assert payload_sub2 is None
    assert gw.deadband_suppressed_count == 2


def test_deadband_60min_heartbeat():
    """
    Asserts that even when |ΔP| < 0.05m, a periodic heartbeat is emitted once 60 minutes elapse.
    """
    gw = EdgeGateway(
        node_id="J_10",
        dma_id="DMA 01",
        gateway_id="GW-DMA01-J10",
        deadband_threshold_m=0.05,
        heartbeat_interval_sec=3600.0,
    )

    # Boot reading at t=0s
    gw.evaluate_reading(actual_pressure=35.10, expected_pressure=35.10, sim_timestamp_sec=0.0)

    # Reading at t=3600s (60 min elapsed) with |ΔP| = 0.01m < 0.05m -> must emit heartbeat
    tx_hb, payload_hb, meta_hb = gw.evaluate_reading(
        actual_pressure=35.11,
        expected_pressure=35.10,
        sim_timestamp_sec=3600.0,
    )
    assert tx_hb is True
    assert payload_hb is not None
    assert payload_hb["is_heartbeat"] is True
    assert gw.heartbeat_count == 1


def test_deadband_significant_pressure_trigger():
    """
    Asserts that pressure changes |ΔP| >= 0.05m immediately trigger transmission.
    """
    gw = EdgeGateway(
        node_id="J_100",
        dma_id="DMA 01",
        gateway_id="GW-DMA01-J100",
        deadband_threshold_m=0.05,
    )

    # Baseline at t=0s
    gw.evaluate_reading(actual_pressure=34.70, expected_pressure=34.70, sim_timestamp_sec=0.0)

    # Unauthorized withdrawal drops pressure by 6.20m at t=300s -> immediate trigger
    tx_theft, payload_theft, meta_theft = gw.evaluate_reading(
        actual_pressure=28.50,
        expected_pressure=34.70,
        sim_timestamp_sec=300.0,
    )
    assert tx_theft is True
    assert payload_theft is not None
    assert payload_theft["is_heartbeat"] is False
    assert abs(payload_theft["actual_pressure"] - 28.50) < 1e-3


def test_battery_and_signal_bounds():
    """
    Asserts that synthetic battery voltage (3.4V to 4.2V) and cellular RSSI (-115 to -65 dBm)
    remain within physical specification limits across simulated diurnal cycles.
    """
    gw = EdgeGateway(
        node_id="J_500",
        dma_id="DMA 01",
        gateway_id="GW-DMA01-J500",
        initial_battery=3.88,
        base_rssi=-82,
    )

    for step_sec in range(0, 86400, 3600):  # 24 hours
        tx, payload, meta = gw.evaluate_reading(
            actual_pressure=34.80 + (step_sec % 7 == 0) * 0.10,
            expected_pressure=34.80,
            sim_timestamp_sec=float(step_sec),
        )
        assert 3.40 <= gw.battery_voltage <= 4.20
        assert -115 <= gw.current_rssi <= -65


def test_sqlite_buffer_fifo_ordering(temp_buffer_db):
    """
    Asserts that readings stored in the SQLite buffer during an outage are retrieved
    in strict chronological FIFO order (sim_timestamp_sec ASC, id ASC).
    """
    buf = EdgeBufferManager(temp_buffer_db)
    assert buf.get_pending_count() == 0

    # Insert 3 readings out of chronological order
    r2 = {"node_id": "J_100", "zone_id": "DMA 01", "actual_pressure": 34.65, "expected_pressure": 34.70}
    r1 = {"node_id": "J_10",  "zone_id": "DMA 01", "actual_pressure": 35.12, "expected_pressure": 35.10}
    r3 = {"node_id": "J_500", "zone_id": "DMA 01", "actual_pressure": 34.75, "expected_pressure": 34.80}

    buf.queue_reading(r2, sim_sec=1020.0)
    buf.queue_reading(r1, sim_sec=1000.0)
    buf.queue_reading(r3, sim_sec=1050.0)

    assert buf.get_pending_count() == 3

    # Query pending readings
    rows = buf.get_pending_readings()
    timestamps = [r["sim_timestamp_sec"] for r in rows]
    nodes = [r["node_id"] for r in rows]

    # Verify chronological FIFO sort
    assert timestamps == [1000.0, 1020.0, 1050.0]
    assert nodes == ["J_10", "J_100", "J_500"]

    # Mark first record flushed
    buf.mark_as_flushed(rows[0]["id"])
    assert buf.get_pending_count() == 2
    assert buf.get_flushed_count() == 1


def test_gateway_health_api_endpoint(test_client):
    """
    Asserts that GET /api/v1/sensors/gateway-health returns valid health records
    for all 6 designated edge concentrators across Kaduwela DMAs 01 & 02.
    """
    resp = test_client.get("/api/v1/sensors/gateway-health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "operational"
    assert data["total_gateways"] == 6
    assert data["online_gateways"] == 6
    assert data["dma_distribution"]["DMA 01"] == 3
    assert data["dma_distribution"]["DMA 02"] == 3

    gateways = {g["node_id"]: g for g in data["gateways"]}
    expected_nodes = ["J_10", "J_100", "J_500", "J_1200", "J_2200", "J_3000"]

    for n in expected_nodes:
        assert n in gateways
        gw = gateways[n]
        assert gw["status"] in ("ONLINE", "DEGRADED")
        assert 3.4 <= gw["battery_voltage"] <= 4.2
        assert 0 <= gw["battery_percent"] <= 100
        assert -115 <= gw["cellular_rssi_dbm"] <= -65
        assert gw["signal_quality"] in ("EXCELLENT", "GOOD", "FAIR", "POOR")
        assert gw["firmware_version"] == "v2.4.1-edge-kaduwela"


def test_telemetry_ingestion_updates_gateway_registry(test_client):
    """
    Asserts that ingesting live telemetry at POST /api/v1/sensors/telemetry
    updates the edge gateway health registry dynamically.
    """
    payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 28.5,
        "expected_pressure": 34.7,
        "spatial_deviation": 5.8,
        "recurrence_count": 3,
        "battery_voltage": 3.94,
        "cellular_rssi_dbm": -76,
        "is_heartbeat": False,
        "is_store_and_forward": True,
        "buffered_readings_count": 0,
        "deadband_suppressed_count": 12,
    }

    resp = test_client.post("/api/v1/sensors/telemetry", json=payload)
    assert resp.status_code == 200
    result = resp.json()
    assert result["battery_voltage"] == 3.94
    assert result["cellular_rssi_dbm"] == -76
    assert result["is_store_and_forward"] is True

    # Check updated gateway-health
    health_resp = test_client.get("/api/v1/sensors/gateway-health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()

    j100_gw = next(g for g in health_data["gateways"] if g["node_id"] == "J_100")
    assert j100_gw["battery_voltage"] == 3.94
    assert j100_gw["cellular_rssi_dbm"] == -76
    assert j100_gw["deadband_suppressed_count"] >= 12
    assert j100_gw["offline_buffer_queue_depth"] == 0
