"""
tests/test_build_zone_boundaries.py
Unit and integration tests for operational zone boundaries generation (src/build_zone_boundaries.py).
"""

import json
from pathlib import Path
import pytest
from src.build_zone_boundaries import (
    DEFAULT_OUTPUT_GEOJSON,
    ZONE_SPECIFICATIONS,
    build_kaduwela_zones_geojson,
    export_zone_boundaries_geojson,
    group_nodes_by_operational_zones,
    load_junction_nodes,
)


def test_load_junction_nodes():
    """Asserts that junction coordinates load successfully with expected keys."""
    nodes = load_junction_nodes()
    assert len(nodes) == 3904
    for key in ["J_10", "J_20", "J_100", "J_500", "J_1200", "J_2200", "J_3000"]:
        assert key in nodes
        node = nodes[key]
        assert "grid_x" in node
        assert "grid_y" in node
        assert "latitude" in node
        assert "longitude" in node
        assert "dma_id" in node


def test_group_nodes_by_operational_zones():
    """Asserts that all 3,904 nodes are grouped and designated sensors are mapped."""
    nodes = load_junction_nodes()
    groups = group_nodes_by_operational_zones(nodes)

    assert len(groups) == 6
    expected_zones = {"zone-01", "zone-02", "zone-03", "zone-04", "zone-05", "zone-06"}
    assert set(groups.keys()) == expected_zones

    total_assigned = sum(len(nids) for nids in groups.values())
    assert total_assigned == len(nodes)

    # DMA 01 designated sensor placements
    assert "J_10" in groups["zone-01"]
    assert "J_20" in groups["zone-02"]
    assert "J_100" in groups["zone-04"]

    # DMA 02 designated sensor placements
    assert "J_500" in groups["zone-03"]
    assert "J_1200" in groups["zone-05"]
    assert "J_3000" in groups["zone-06"]
    assert "J_2200" in groups["zone-06"]


def test_build_kaduwela_zones_geojson():
    """Asserts that build_kaduwela_zones_geojson creates valid RFC 7946 GeoJSON."""
    gj = build_kaduwela_zones_geojson(buffer_m=25.0)

    assert gj["type"] == "FeatureCollection"
    assert gj["name"] == "kaduwela_zones"
    features = gj["features"]
    assert len(features) == 6

    for f in features:
        assert f["type"] == "Feature"
        assert f["geometry"]["type"] == "Polygon"
        ring = f["geometry"]["coordinates"][0]
        assert len(ring) >= 4
        # Assert ring is closed (first point equals last point)
        assert ring[0] == ring[-1]

        # Verify GPS coordinates within Kaduwela geographic bounds
        for lon, lat in ring:
            assert 79.94 <= lon <= 80.06, f"Longitude {lon} out of expected range"
            assert 6.89 <= lat <= 6.96, f"Latitude {lat} out of expected range"

        props = f["properties"]
        assert "zone_id" in props
        assert "name" in props
        assert "dma_id" in props
        assert "sensor_node_id" in props
        assert "default_status" in props
        assert props["default_status"] == "NORMAL"
        assert props["buffer_applied_m"] == 25.0


def test_dma_assignment_properties():
    """Asserts that DMA 01 has zones 01, 02, 04 and DMA 02 has zones 03, 05, 06."""
    gj = build_kaduwela_zones_geojson()
    by_id = {f["properties"]["zone_id"]: f["properties"] for f in gj["features"]}

    # DMA 01
    assert by_id["zone-01"]["dma_id"] == "DMA 01"
    assert by_id["zone-01"]["sensor_node_id"] == "J_10"
    assert by_id["zone-02"]["dma_id"] == "DMA 01"
    assert by_id["zone-02"]["sensor_node_id"] == "J_20"
    assert by_id["zone-04"]["dma_id"] == "DMA 01"
    assert by_id["zone-04"]["sensor_node_id"] == "J_100"

    # DMA 02
    assert by_id["zone-03"]["dma_id"] == "DMA 02"
    assert by_id["zone-03"]["sensor_node_id"] == "J_500"
    assert by_id["zone-05"]["dma_id"] == "DMA 02"
    assert by_id["zone-05"]["sensor_node_id"] == "J_1200"
    assert by_id["zone-06"]["dma_id"] == "DMA 02"
    assert by_id["zone-06"]["sensor_node_id"] == "J_3000"


def test_export_zone_boundaries_geojson(tmp_path: Path):
    """Asserts that export_zone_boundaries_geojson writes file to disk properly."""
    tmp_file = tmp_path / "kaduwela_zones_test.geojson"
    out = export_zone_boundaries_geojson(output_path=tmp_file, buffer_m=20.0)

    assert out.exists()
    assert out.stat().st_size > 10_000

    with open(out, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 6


def test_default_output_geojson_file_exists():
    """Asserts that frontend/public/data/kaduwela_zones.geojson exists and is populated."""
    assert DEFAULT_OUTPUT_GEOJSON.exists()
    assert DEFAULT_OUTPUT_GEOJSON.stat().st_size > 10_000

    with open(DEFAULT_OUTPUT_GEOJSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 6
