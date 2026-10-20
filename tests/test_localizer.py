"""
tests/test_localizer.py
Unit and integration tests for anomaly localization and hydraulic sensitivity engine (src/localizer.py).
"""

import pytest
from src.localizer import (
    MONITORED_SENSOR_NODES,
    AnomalyLocalizer,
    build_sensitivity_dictionary,
    get_localizer,
    localize_anomaly,
    test_zone_04_localization,
)


def test_wntr_model_loading():
    """Asserts that the EPANET model loads into WNTR with full topology graph."""
    localizer = get_localizer()
    localizer.load_network()
    assert localizer._graph is not None
    assert localizer._graph.number_of_nodes() >= 3900
    assert localizer._graph.number_of_edges() >= 4200


def test_sensitivity_dictionary_structure():
    """Asserts that sensitivity dictionary contains all 6 sensors with decreasing influence."""
    sens = build_sensitivity_dictionary()
    assert len(sens) == len(MONITORED_SENSOR_NODES)

    for sensor in MONITORED_SENSOR_NODES:
        assert sensor in sens
        entries = sens[sensor]
        assert len(entries) > 0

        # Primary entry is self with distance 0 and sensitivity 1.0
        assert entries[0]["junction"] == sensor
        assert entries[0]["pipe_distance_m"] == 0.0
        assert entries[0]["hydraulic_sensitivity"] == 1.0

        # Verify monotonicity of distances
        for i in range(len(entries) - 1):
            assert entries[i]["pipe_distance_m"] <= entries[i + 1]["pipe_distance_m"]
            assert entries[i]["hydraulic_sensitivity"] >= entries[i + 1]["hydraulic_sensitivity"]


def test_localize_anomaly_normal_threshold():
    """Asserts that pressure gaps below 2.0m return None (no localization needed)."""
    assert localize_anomaly("zone-04", "J_100", 0.0) is None
    assert localize_anomaly("zone-04", "J_100", 1.2) is None
    assert localize_anomaly("zone-04", "J_100", 1.99) is None
    assert localize_anomaly("zone-01", "J_10", 1.5) is None


def test_localize_anomaly_zone_04_target_coordinates():
    """Asserts that an anomaly in Zone 04 pinpoint suspect junction J_100 with exact coordinates."""
    result = localize_anomaly(zone_id="zone-04", sensor_node_id="J_100", pressure_gap=6.0)

    assert result is not None
    assert result["suspect_junction"] == "J_100"
    assert result["zone_id"] == "zone-04"
    assert result["sensor_node_id"] == "J_100"
    assert result["pressure_gap"] == 6.0
    assert result["radius_meters"] == 50

    # Physical corridor properties
    assert result["physical_inspection_corridor"]["radius_meters"] == 50
    assert "Kaduwela East Main Road - Valve Box #4" in result["access_landmark"]

    # Target GPS coordinates for Node J_100
    assert abs(result["latitude"] - 6.936812) < 0.001
    assert abs(result["longitude"] - 79.967673) < 0.001

    # Direct Google Maps URL
    expected_url = f"https://www.google.com/maps/search/?api=1&query={result['latitude']:.6f},{result['longitude']:.6f}"
    assert result["google_maps_url"] == expected_url


def test_exported_test_zone_04_localization_function():
    """Asserts that the exported test_zone_04_localization() function succeeds."""
    assert test_zone_04_localization() is True


def test_localize_other_monitored_zones():
    """Asserts that localization functions correctly across all monitored sensors."""
    test_cases = [
        ("zone-01", "J_10", 3.5, "J_10", 6.930155, 80.009042),
        ("zone-02", "J_20", 2.5, "J_20", 6.933550, 79.992495),
        ("zone-03", "J_500", 4.0, "J_500", 6.927512, 80.002094),
        ("zone-05", "J_1200", 3.0, "J_1200", 6.922984, 80.011280),
        ("zone-06", "J_3000", 2.8, "J_3000", 6.916456, 80.012390),
    ]

    for zid, sid, gap, expected_suspect, exp_lat, exp_lon in test_cases:
        res = localize_anomaly(zone_id=zid, sensor_node_id=sid, pressure_gap=gap)
        assert res is not None
        assert res["suspect_junction"] == expected_suspect
        assert abs(res["latitude"] - exp_lat) < 0.002
        assert abs(res["longitude"] - exp_lon) < 0.002
        assert res["radius_meters"] == 50
        assert "https://www.google.com/maps" in res["google_maps_url"]
