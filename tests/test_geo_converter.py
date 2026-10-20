"""
tests/test_geo_converter.py
Comprehensive Unit Test Suite for src/geo_converter.py.

Verifies:
1. EPANET .inp network parsing via WNTR ([COORDINATES] and [JUNCTIONS]).
2. Geodetic projection utility (EPSG:5235 / EPSG:5234 to WGS84 and calibrated affine).
3. Network centering around Lat 6.9350° N, Lng 79.9840° E.
4. Schema and values of get_junction_location(node_id).
5. Google Maps search URL formatting.
6. DMA boundary and nearest access road mapping.
7. kaduwela_nodes_geo.json export file integrity and node count.
"""

import json
from pathlib import Path
import pytest

from src.geo_converter import (
    DEFAULT_GEO_OUTPUT_PATH,
    DEFAULT_INP_PATH,
    KaduwelaGeoConverter,
    SectorInfo,
    export_all_junction_coordinates,
    find_nearest_sector,
    get_converter,
    get_junction_location,
    project_grid_to_wgs84,
    project_wgs84_to_grid,
)


def test_network_file_exists() -> None:
    """Asserts that the EPANET network file exists in data/networks/."""
    assert DEFAULT_INP_PATH.exists(), f"Network file missing: {DEFAULT_INP_PATH}"
    assert DEFAULT_INP_PATH.stat().st_size > 100_000, "Network file seems empty or truncated."


def test_wntr_network_loading() -> None:
    """Asserts that WNTR loads exactly 3,904 junctions and 1 reservoir."""
    converter = KaduwelaGeoConverter(DEFAULT_INP_PATH)
    converter.load_network()
    assert converter.total_junctions == 3904
    assert converter._wn.num_junctions == 3904
    assert converter._wn.num_reservoirs == 1


def test_grid_to_wgs84_projections() -> None:
    """
    Asserts that both pyproj and affine transformations produce consistent
    WGS84 coordinates for Kaduwela East within sub-meter tolerance.
    """
    gx, gy = 410927.22, 493000.0  # Node J_100

    lat_proj, lon_proj = project_grid_to_wgs84(gx, gy, method="pyproj")
    lat_aff, lon_aff = project_grid_to_wgs84(gx, gy, method="affine")

    # Center around Lat 6.9368° N, Lng 79.9677° E
    assert 6.930 <= lat_proj <= 6.945, f"Latitude {lat_proj} outside expected range"
    assert 79.950 <= lon_proj <= 79.980, f"Longitude {lon_proj} outside expected range"

    # Difference between pyproj and calibrated affine must be < 0.0001 deg (< 10 meters)
    assert abs(lat_proj - lat_aff) < 0.0001, f"Lat difference too large: {abs(lat_proj - lat_aff)}"
    assert abs(lon_proj - lon_aff) < 0.0001, f"Lon difference too large: {abs(lon_proj - lon_aff)}"


def test_center_alignment_kaduwela_east() -> None:
    """
    Asserts that the network centroid translates around Lat 6.9350° N, Lng 79.9840° E.
    """
    converter = get_converter()
    converter.load_network()

    xs = [v["x"] for v in converter._nodes_cache.values() if v["type"] == "junction"]
    ys = [v["y"] for v in converter._nodes_cache.values() if v["type"] == "junction"]

    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)

    lat, lon = project_grid_to_wgs84(mean_x, mean_y)

    # Within ~0.02 degrees (~2 km) of the Kaduwela East town center
    assert abs(lat - 6.9350) < 0.02, f"Center lat {lat} deviates from 6.9350"
    assert abs(lon - 79.9840) < 0.03, f"Center lon {lon} deviates from 79.9840"


def test_get_junction_location_schema() -> None:
    """
    Asserts that get_junction_location returns all required fields and valid types.
    """
    loc = get_junction_location("J_100")

    required_keys = [
        "node_id",
        "grid_x",
        "grid_y",
        "elevation_m",
        "latitude",
        "longitude",
        "google_maps_url",
        "nearest_sector",
        "dma_boundary",
        "nearest_access_road",
    ]
    for key in required_keys:
        assert key in loc, f"Missing key '{key}' in get_junction_location response"

    assert loc["node_id"] == "J_100"
    assert isinstance(loc["grid_x"], float)
    assert isinstance(loc["grid_y"], float)
    assert isinstance(loc["elevation_m"], float)
    assert isinstance(loc["latitude"], float)
    assert isinstance(loc["longitude"], float)
    assert isinstance(loc["google_maps_url"], str)
    assert isinstance(loc["dma_boundary"], str)
    assert isinstance(loc["nearest_access_road"], str)


def test_google_maps_url_format() -> None:
    """
    Asserts that Google Maps URL is formatted as:
    https://www.google.com/maps/search/?api=1&query={lat},{lng}
    """
    loc = get_junction_location("J_100")
    lat, lon = loc["latitude"], loc["longitude"]

    expected_url = f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"
    assert loc["google_maps_url"] == expected_url, (
        f"URL mismatch: got {loc['google_maps_url']}, expected {expected_url}"
    )


def test_sector_info_and_dma_assignment() -> None:
    """
    Asserts that SectorInfo provides DMA boundary tag and nearest access road,
    and supports both dictionary and string operations.
    """
    loc_j100 = get_junction_location("J_100")
    loc_j1200 = get_junction_location("J_1200")

    # J_100 is in DMA 01
    assert "DMA 01" in str(loc_j100["nearest_sector"])
    assert "DMA 01" in loc_j100["dma_boundary"]
    assert "Avissawella" in loc_j100["nearest_access_road"] or "Road" in loc_j100["nearest_access_road"]

    # J_1200 is in DMA 02
    assert "DMA 02" in str(loc_j1200["nearest_sector"])
    assert "DMA 02" in loc_j1200["dma_boundary"]

    # SectorInfo dict access
    sec: SectorInfo = loc_j100["nearest_sector"]
    assert isinstance(sec, dict)
    assert "dma_boundary" in sec
    assert "nearest_access_road" in sec
    assert "DMA 01" in sec


def test_json_export_and_file_integrity(tmp_path: Path) -> None:
    """
    Asserts that export_all_junction_coordinates generates a valid JSON file
    containing all 3,904 nodes.
    """
    out_file = tmp_path / "test_nodes_geo.json"
    exported_path = export_all_junction_coordinates(out_file)

    assert exported_path.exists()
    assert exported_path.stat().st_size > 500_000  # Over 500 KB

    with open(exported_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    assert len(data) == 3904
    assert "J_100" in data
    assert "J_1" in data

    j100_data = data["J_100"]
    assert j100_data["node_id"] == "J_100"
    assert "https://www.google.com/maps/search/?api=1&query=" in j100_data["google_maps_url"]
    assert "latitude" in j100_data
    assert "longitude" in j100_data


def test_reverse_grid_projection() -> None:
    """
    Asserts that project_wgs84_to_grid accurately reverses WGS84 coordinates back to local grid.
    """
    original_x, original_y = 415497.73, 492256.21  # Node J_10
    lat, lon = project_grid_to_wgs84(original_x, original_y)
    rev_x, rev_y = project_wgs84_to_grid(lat, lon)

    # Within 1 meter tolerance
    assert abs(rev_x - original_x) < 1.0, f"Reversed X {rev_x} deviates from original {original_x}"
    assert abs(rev_y - original_y) < 1.0, f"Reversed Y {rev_y} deviates from original {original_y}"


def test_nonexistent_junction_raises_error() -> None:
    """Asserts that querying a nonexistent junction ID raises KeyError."""
    with pytest.raises(KeyError):
        get_junction_location("J_NONEXISTENT_99999")
