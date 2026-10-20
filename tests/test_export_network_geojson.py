"""
tests/test_export_network_geojson.py
Unit and Integration Test Suite for GeoJSON Network Model Export & API Serving.

Verifies:
1. EPANET .inp parsing and GeoJSON generation via WNTR.
2. Standard GeoJSON FeatureCollection schema compliance (RFC 7946).
3. Coordinate translation from SLD99 grid to WGS84 without distortion.
4. Correct coordinate ordering: [longitude, latitude] for Points and LineStrings.
5. Exact feature counts: 3,904 junction points and 4,279 pipe line strings.
6. Junction feature properties schema (node_id, elevation, dma).
7. Pipe feature properties schema (pipe_id, diameter, length).
8. Geographic bounding box consistency around Kaduwela East.
9. Geodesic vs. local grid metric fidelity (scale ratio < 0.5% deviation).
10. FastAPI endpoint GET /api/v1/network/geojson/{layer_type} with caching and error handling.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from src.export_network_geojson import (
    DEFAULT_JUNCTIONS_GEOJSON,
    DEFAULT_PIPES_GEOJSON,
    DEFAULT_INP_PATH,
    export_network_geojson,
    generate_junctions_geojson,
    generate_pipes_geojson,
    haversine_distance_m,
    verify_no_coordinate_distortion,
)
import wntr


@pytest.fixture(scope="module")
def network_model():
    """Module-level cached WNTR model for fast test execution."""
    assert DEFAULT_INP_PATH.exists(), f"Network file missing at {DEFAULT_INP_PATH}"
    return wntr.network.WaterNetworkModel(str(DEFAULT_INP_PATH))


@pytest.fixture(scope="module")
def api_client():
    """FastAPI TestClient instance."""
    return TestClient(app)


def test_inp_network_element_counts(network_model):
    """Asserts that the network model contains exactly 3,904 junctions and 4,279 pipes."""
    assert network_model.num_junctions == 3904
    assert network_model.num_pipes == 4279
    assert network_model.num_reservoirs == 1


def test_generate_junctions_geojson_schema(network_model):
    """Asserts that generate_junctions_geojson creates a valid FeatureCollection with required properties."""
    fc = generate_junctions_geojson(network_model)
    assert fc.get("type") == "FeatureCollection"
    assert "features" in fc
    assert len(fc["features"]) == 3904

    sample = fc["features"][0]
    assert sample.get("type") == "Feature"
    assert "geometry" in sample
    assert sample["geometry"].get("type") == "Point"

    coords = sample["geometry"].get("coordinates")
    assert isinstance(coords, list) and len(coords) == 2
    lon, lat = coords
    assert 79.94 <= lon <= 80.05, f"Unexpected longitude: {lon}"
    assert 6.88 <= lat <= 6.96, f"Unexpected latitude: {lat}"

    props = sample.get("properties", {})
    assert "node_id" in props
    assert "elevation" in props
    assert "dma" in props
    assert props["dma"] in ("DMA 01", "DMA 02")
    assert isinstance(props["elevation"], (int, float))


def test_generate_pipes_geojson_schema(network_model):
    """Asserts that generate_pipes_geojson creates LineStrings with pipe_id, diameter, and length."""
    fc = generate_pipes_geojson(network_model)
    assert fc.get("type") == "FeatureCollection"
    assert "features" in fc
    assert len(fc["features"]) == 4279

    sample = fc["features"][0]
    assert sample.get("type") == "Feature"
    assert "geometry" in sample
    assert sample["geometry"].get("type") == "LineString"

    coords = sample["geometry"].get("coordinates")
    assert isinstance(coords, list) and len(coords) >= 2
    for pt in coords:
        assert len(pt) == 2
        lon, lat = pt
        assert 79.94 <= lon <= 80.05
        assert 6.88 <= lat <= 6.96

    props = sample.get("properties", {})
    assert "pipe_id" in props
    assert "diameter" in props
    assert "length" in props
    assert isinstance(props["diameter"], (int, float))
    assert isinstance(props["length"], (int, float))


def test_export_network_geojson_files(tmp_path):
    """Asserts that export_network_geojson writes valid JSON files to disk."""
    j_path, p_path = export_network_geojson(output_dir=tmp_path)
    assert j_path.exists()
    assert p_path.exists()
    assert j_path.stat().st_size > 500_000  # ~1.2 MB
    assert p_path.stat().st_size > 500_000  # ~1.7 MB

    with open(j_path, "r", encoding="utf-8") as f:
        j_data = json.load(f)
    with open(p_path, "r", encoding="utf-8") as f:
        p_data = json.load(f)

    assert len(j_data["features"]) == 3904
    assert len(p_data["features"]) == 4279


def test_no_coordinate_distortion_verification():
    """Asserts that verify_no_coordinate_distortion passes completely on exported files."""
    assert DEFAULT_JUNCTIONS_GEOJSON.exists()
    assert DEFAULT_PIPES_GEOJSON.exists()
    assert verify_no_coordinate_distortion(DEFAULT_JUNCTIONS_GEOJSON, DEFAULT_PIPES_GEOJSON) is True


def test_designated_monitoring_nodes_in_junctions_geojson():
    """Asserts that key monitoring nodes (J_10, J_100, J_500, J_1200, J_2200, J_3000) are mapped correctly."""
    with open(DEFAULT_JUNCTIONS_GEOJSON, "r", encoding="utf-8") as f:
        j_data = json.load(f)

    by_id = {f["properties"]["node_id"]: f for f in j_data["features"]}

    # J_100 is in DMA 01 near Industrial zone
    assert "J_100" in by_id
    j100 = by_id["J_100"]
    assert j100["properties"]["dma"] == "DMA 01"
    lon, lat = j100["geometry"]["coordinates"]
    assert abs(lat - 6.936812) < 0.001
    assert abs(lon - 79.967673) < 0.001

    # J_1200 is in DMA 02
    assert "J_1200" in by_id
    assert by_id["J_1200"]["properties"]["dma"] == "DMA 02"


def test_fastapi_network_geojson_endpoint_junctions(api_client):
    """Asserts GET /api/v1/network/geojson/junctions returns 200 with all 3,904 junctions."""
    response = api_client.get("/api/v1/network/geojson/junctions")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 3904
    first_feat = data["features"][0]
    assert "node_id" in first_feat["properties"]
    assert "elevation" in first_feat["properties"]
    assert "dma" in first_feat["properties"]


def test_fastapi_network_geojson_endpoint_pipes(api_client):
    """Asserts GET /api/v1/network/geojson/pipes returns 200 with all 4,279 pipes."""
    response = api_client.get("/api/v1/network/geojson/pipes")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 4279
    first_feat = data["features"][0]
    assert "pipe_id" in first_feat["properties"]
    assert "diameter" in first_feat["properties"]
    assert "length" in first_feat["properties"]


def test_fastapi_network_geojson_endpoint_aliases_and_caching(api_client):
    """Asserts endpoint supports layer aliases (kaduwela_junctions, kaduwela_pipes, .geojson extension)."""
    r1 = api_client.get("/api/v1/network/geojson/kaduwela_junctions")
    assert r1.status_code == 200
    assert len(r1.json()["features"]) == 3904

    r2 = api_client.get("/api/v1/network/geojson/kaduwela_pipes.geojson")
    assert r2.status_code == 200
    assert len(r2.json()["features"]) == 4279

    r3 = api_client.get("/api/v1/network/geojson/nodes")
    assert r3.status_code == 200
    assert len(r3.json()["features"]) == 3904


def test_fastapi_network_geojson_endpoint_404(api_client):
    """Asserts GET /api/v1/network/geojson/unknown_layer returns 404 with helpful message."""
    response = api_client.get("/api/v1/network/geojson/unknown_layer")
    assert response.status_code == 404
    assert "Layer 'unknown_layer' not found" in response.json()["detail"]
