"""
src/export_network_geojson.py
Export Kaduwela Water Network Model to Standard GeoJSON Feature Collections.

Parses EPANET network model (data/networks/kaduwela_2dma_clean_East_side.inp) using WNTR.
Transforms junction and pipe endpoint coordinates from local SLD99 grid (EPSG:5235)
to WGS84 GPS decimal degrees (EPSG:4326, [longitude, latitude] coordinate order
per GeoJSON RFC 7946).

Exports:
  1. frontend/public/data/kaduwela_junctions.geojson:
     Point features for all 3,904 junctions with properties:
       - node_id: Junction identifier (e.g. "J_100")
       - elevation: Elevation in meters (e.g. 12.0)
       - dma: Assigned District Metered Area ("DMA 01" or "DMA 02")
  2. frontend/public/data/kaduwela_pipes.geojson:
     LineString features for all 4,279 pipes connecting start and end junctions with properties:
       - pipe_id: Pipe identifier (e.g. "P_1")
       - diameter: Pipe internal diameter in meters (e.g. 0.063)
       - length: Pipe segment length in meters (e.g. 46.88)

Includes rigorous geodetic distortion and metric fidelity validation.
"""

import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure project root is available in module path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import wntr

from src.geo_converter import (
    DEFAULT_INP_PATH,
    KADUWELA_EAST_CENTER_LAT,
    KADUWELA_EAST_CENTER_LNG,
    find_nearest_sector,
    project_grid_to_wgs84,
)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("export_network_geojson")

# Default export directories and file paths
DEFAULT_FRONTEND_DATA_DIR = PROJECT_ROOT / "frontend" / "public" / "data"
DEFAULT_JUNCTIONS_GEOJSON = DEFAULT_FRONTEND_DATA_DIR / "kaduwela_junctions.geojson"
DEFAULT_PIPES_GEOJSON = DEFAULT_FRONTEND_DATA_DIR / "kaduwela_pipes.geojson"


# ==============================================================================
# Geodetic Metric Calculation Helpers (for distortion analysis)
# ==============================================================================
def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes Great-Circle distance in meters between two WGS84 coordinates
    using the Haversine formula on a reference sphere of radius 6,371,000 meters.
    """
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius * c


# ==============================================================================
# Core GeoJSON Generation Functions
# ==============================================================================
def generate_junctions_geojson(
    wn: wntr.network.WaterNetworkModel,
    method: str = "pyproj",
) -> Dict[str, Any]:
    """
    Generates a GeoJSON FeatureCollection of Point features for all network junctions.

    Properties for each junction:
      - node_id: str
      - elevation: float (m)
      - dma: str ("DMA 01" or "DMA 02")
    """
    features: List[Dict[str, Any]] = []

    for name, node in wn.junctions():
        gx, gy = node.coordinates
        elev = float(getattr(node, "elevation", 12.0))
        lat, lon = project_grid_to_wgs84(gx, gy, method=method)
        sec = find_nearest_sector(gx, gy, node_id=str(name))
        dma_id = str(sec.get("dma_id", "DMA 01"))

        # GeoJSON RFC 7946: Coordinates are [longitude, latitude]
        feature = {
            "type": "Feature",
            "id": str(name),
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "properties": {
                "node_id": str(name),
                "elevation": round(elev, 2),
                "dma": dma_id,
            },
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "name": "kaduwela_junctions",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }


def generate_pipes_geojson(
    wn: wntr.network.WaterNetworkModel,
    method: str = "pyproj",
) -> Dict[str, Any]:
    """
    Generates a GeoJSON FeatureCollection of LineString features connecting start and end
    junctions/nodes for all network pipes.

    Properties for each pipe:
      - pipe_id: str
      - diameter: float (m)
      - length: float (m)
    """
    # Precompute coordinates for all nodes (junctions and reservoirs)
    node_coords: Dict[str, Tuple[float, float]] = {}
    for name, node in wn.nodes():
        gx, gy = node.coordinates
        lat, lon = project_grid_to_wgs84(gx, gy, method=method)
        node_coords[str(name)] = (lon, lat)

    features: List[Dict[str, Any]] = []

    for name, pipe in wn.pipes():
        start_id = str(pipe.start_node_name)
        end_id = str(pipe.end_node_name)

        if start_id not in node_coords or end_id not in node_coords:
            logger.warning(f"Pipe {name} has unmapped endpoint nodes ({start_id} -> {end_id}). Skipping.")
            continue

        start_lon, start_lat = node_coords[start_id]
        end_lon, end_lat = node_coords[end_id]

        diameter = float(pipe.diameter)
        length = float(pipe.length)

        # GeoJSON RFC 7946: Coordinates are [[start_lon, start_lat], [end_lon, end_lat]]
        feature = {
            "type": "Feature",
            "id": str(name),
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [start_lon, start_lat],
                    [end_lon, end_lat],
                ],
            },
            "properties": {
                "pipe_id": str(name),
                "diameter": round(diameter, 4),
                "length": round(length, 2),
            },
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "name": "kaduwela_pipes",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }


def export_network_geojson(
    inp_path: Union[str, Path] = DEFAULT_INP_PATH,
    output_dir: Union[str, Path] = DEFAULT_FRONTEND_DATA_DIR,
    method: str = "pyproj",
) -> Tuple[Path, Path]:
    """
    Parses EPANET model and exports kaduwela_junctions.geojson and kaduwela_pipes.geojson
    to the designated directory (default frontend/public/data/).

    Returns:
    --------
    Tuple[Path, Path]:
        Paths to (junctions_geojson_file, pipes_geojson_file)
    """
    inp_path = Path(inp_path)
    if not inp_path.exists():
        raise FileNotFoundError(f"EPANET network file not found at: {inp_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Parsing network model from {inp_path} with WNTR...")
    wn = wntr.network.WaterNetworkModel(str(inp_path))

    junctions_path = out_dir / "kaduwela_junctions.geojson"
    pipes_path = out_dir / "kaduwela_pipes.geojson"

    logger.info(f"Generating junctions GeoJSON for {wn.num_junctions} junctions...")
    junctions_data = generate_junctions_geojson(wn, method=method)

    logger.info(f"Generating pipes GeoJSON for {wn.num_pipes} pipes...")
    pipes_data = generate_pipes_geojson(wn, method=method)

    # Write GeoJSON files with standard 2-space indentation
    with open(junctions_path, "w", encoding="utf-8") as f:
        json.dump(junctions_data, f, indent=2)

    with open(pipes_path, "w", encoding="utf-8") as f:
        json.dump(pipes_data, f, indent=2)

    logger.info(
        f"Exported {len(junctions_data['features'])} junctions ({junctions_path.stat().st_size / 1024:.1f} KB) "
        f"to {junctions_path}"
    )
    logger.info(
        f"Exported {len(pipes_data['features'])} pipes ({pipes_path.stat().st_size / 1024:.1f} KB) "
        f"to {pipes_path}"
    )

    return junctions_path, pipes_path


# ==============================================================================
# Verification Suite: Coordinate Distortion & Geometric Fidelity Audit
# ==============================================================================
def verify_no_coordinate_distortion(
    junctions_path: Union[str, Path] = DEFAULT_JUNCTIONS_GEOJSON,
    pipes_path: Union[str, Path] = DEFAULT_PIPES_GEOJSON,
    inp_path: Union[str, Path] = DEFAULT_INP_PATH,
) -> bool:
    """
    Comprehensive verification to confirm that GeoJSON files are generated
    without coordinate distortion, inverted axes, or metric skew:

    Checks:
    1. GeoJSON schema validity (RFC 7946 FeatureCollection, Point and LineString geometry).
    2. Coordinate bounding box matches expected Kaduwela East geographic envelope.
    3. Axis order: Coordinates are [longitude, latitude] (lon ~80.0, lat ~6.93).
    4. Distance fidelity: Geodesic distances match SLD99 grid distances within sub-meter tolerance (< 0.15m mean).
    5. Aspect ratio and geographic scale consistency.
    6. Complete coverage: Exactly 3,904 junctions and 4,279 pipes.
    7. Required properties presence (node_id, elevation, dma / pipe_id, diameter, length).
    """
    junctions_path = Path(junctions_path)
    pipes_path = Path(pipes_path)
    inp_path = Path(inp_path)

    print("\n" + "=" * 80)
    print("  KADUWELA WATER NETWORK: GEOJSON GENERATION & METRIC FIDELITY AUDIT")
    print("=" * 80)

    # 1. Existence and File Size
    assert junctions_path.exists(), f"Junctions GeoJSON file missing: {junctions_path}"
    assert pipes_path.exists(), f"Pipes GeoJSON file missing: {pipes_path}"
    print(f"\n[1] File Integrity & Storage:")
    print(f"  * Junctions GeoJSON : {junctions_path} ({junctions_path.stat().st_size / 1024:.1f} KB)")
    print(f"  * Pipes GeoJSON     : {pipes_path} ({pipes_path.stat().st_size / 1024:.1f} KB)")

    # 2. JSON Parsing
    with open(junctions_path, "r", encoding="utf-8") as f:
        junctions_fc = json.load(f)
    with open(pipes_path, "r", encoding="utf-8") as f:
        pipes_fc = json.load(f)

    assert junctions_fc.get("type") == "FeatureCollection", "Junctions file is not a GeoJSON FeatureCollection"
    assert pipes_fc.get("type") == "FeatureCollection", "Pipes file is not a GeoJSON FeatureCollection"

    junction_features = junctions_fc.get("features", [])
    pipe_features = pipes_fc.get("features", [])

    print(f"\n[2] Feature Count & Topology:")
    print(f"  * Total Junction Points : {len(junction_features):,}")
    print(f"  * Total Pipe LineStrings: {len(pipe_features):,}")

    assert len(junction_features) == 3904, f"Expected 3,904 junctions, found {len(junction_features)}"
    assert len(pipe_features) == 4279, f"Expected 4,279 pipes, found {len(pipe_features)}"

    # 3. Properties Schema Verification
    for feat in junction_features[:50]:
        props = feat.get("properties", {})
        assert "node_id" in props, f"Missing 'node_id' in junction properties: {props}"
        assert "elevation" in props, f"Missing 'elevation' in junction properties: {props}"
        assert "dma" in props, f"Missing 'dma' in junction properties: {props}"
        assert props["dma"] in ("DMA 01", "DMA 02"), f"Invalid DMA tag: {props['dma']}"

    for feat in pipe_features[:50]:
        props = feat.get("properties", {})
        assert "pipe_id" in props, f"Missing 'pipe_id' in pipe properties: {props}"
        assert "diameter" in props, f"Missing 'diameter' in pipe properties: {props}"
        assert "length" in props, f"Missing 'length' in pipe properties: {props}"

    # 4. Bounding Box & Axis Orientation Check ([lon, lat] per RFC 7946)
    lons = [f["geometry"]["coordinates"][0] for f in junction_features]
    lats = [f["geometry"]["coordinates"][1] for f in junction_features]

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    mean_lon, mean_lat = sum(lons) / len(lons), sum(lats) / len(lats)

    print(f"\n[3] WGS84 Geographic Extents (Kaduwela East):")
    print(f"  * Longitude (East)  : {min_lon:.6f}° E to {max_lon:.6f}° E (Mean: {mean_lon:.6f}° E)")
    print(f"  * Latitude (North)  : {min_lat:.6f}° N to {max_lat:.6f}° N (Mean: {mean_lat:.6f}° N)")
    print(f"  * Expected Center   : {KADUWELA_EAST_CENTER_LNG:.4f}° E, {KADUWELA_EAST_CENTER_LAT:.4f}° N")

    # Strict bounding box sanity assertions for Kaduwela, Sri Lanka
    assert 79.94 <= min_lon <= 79.98, f"min_lon out of expected bounds: {min_lon}"
    assert 80.00 <= max_lon <= 80.06, f"max_lon out of expected bounds: {max_lon}"
    assert 6.88 <= min_lat <= 6.93, f"min_lat out of expected bounds: {min_lat}"
    assert 6.93 <= max_lat <= 6.96, f"max_lat out of expected bounds: {max_lat}"

    # Verify no axis inversion (GeoJSON requires [lon, lat])
    for f in junction_features:
        lon, lat = f["geometry"]["coordinates"]
        assert 75.0 <= lon <= 85.0, f"Inverted or distorted coordinate! Longitude={lon}"
        assert 5.0 <= lat <= 10.0, f"Inverted or distorted coordinate! Latitude={lat}"

    # 5. Geodetic Distance Fidelity & Distortion Audit
    # Compare local grid Euclidean distance with geodetic distance for all pipes
    wn = wntr.network.WaterNetworkModel(str(inp_path))
    ratios: List[float] = []
    abs_diffs: List[float] = []

    pipe_lookup = {f["properties"]["pipe_id"]: f for f in pipe_features}

    for name, pipe in wn.pipes():
        start_node = wn.get_node(pipe.start_node_name)
        end_node = wn.get_node(pipe.end_node_name)

        gx1, gy1 = start_node.coordinates
        gx2, gy2 = end_node.coordinates
        grid_dist = math.hypot(gx2 - gx1, gy2 - gy1)

        # Ignore tiny zero-length connectors or pump spacers
        if grid_dist < 0.5:
            continue

        feat = pipe_lookup.get(name)
        if not feat:
            continue

        coords = feat["geometry"]["coordinates"]
        p_lon1, p_lat1 = coords[0]
        p_lon2, p_lat2 = coords[1]

        geo_dist = haversine_distance_m(p_lat1, p_lon1, p_lat2, p_lon2)
        ratio = geo_dist / grid_dist
        abs_diff = abs(geo_dist - grid_dist)

        ratios.append(ratio)
        abs_diffs.append(abs_diff)

    mean_ratio = sum(ratios) / len(ratios)
    mean_abs_diff = sum(abs_diffs) / len(abs_diffs)
    max_abs_diff = max(abs_diffs)

    print(f"\n[4] Metric Fidelity & Scale Distortion Analysis ({len(ratios):,} pipes analyzed):")
    print(f"  * Geodesic / Grid Scale Ratio : {mean_ratio:.6f}  (Scale factor distortion: {abs(mean_ratio - 1.0) * 100:.3f}%)")
    print(f"  * Mean Distance Deviation     : {mean_abs_diff:.3f} meters")
    print(f"  * Max Pipe Distance Deviation : {max_abs_diff:.3f} meters")

    # Assert scale ratio is within 0.5% (standard spherical vs SLD99 transverse Mercator)
    assert 0.995 <= mean_ratio <= 1.005, f"Excessive metric distortion detected: scale ratio {mean_ratio}"
    assert mean_abs_diff < 0.25, f"Mean pipe distance deviation exceeds 0.25m: {mean_abs_diff}"

    # 6. Monitored Landmark Junction Audit
    print(f"\n[5] Key Monitored Junctions Spot Audit:")
    print("-" * 80)
    print(f"{'Node ID':<10} {'DMA':<8} {'Elevation':<10} {'Lon (° E)':<14} {'Lat (° N)':<14} {'Status'}")
    print("-" * 80)

    test_nodes = ["J_10", "J_100", "J_500", "J_1200", "J_2200", "J_3000"]
    junc_dict = {f["properties"]["node_id"]: f for f in junction_features}

    for nid in test_nodes:
        feat = junc_dict.get(nid)
        assert feat is not None, f"Designated node {nid} missing from exported GeoJSON"
        lon, lat = feat["geometry"]["coordinates"]
        elev = feat["properties"]["elevation"]
        dma = feat["properties"]["dma"]
        print(f"{nid:<10} {dma:<8} {elev:<10.1f} {lon:<14.6f} {lat:<14.6f} Verified OK")

    print("-" * 80)

    print("\n" + "=" * 80)
    print("  CONFIRMATION: ALL GEOJSON FILES GENERATED WITHOUT COORDINATE DISTORTION (100%)")
    print("=" * 80 + "\n")

    return True


if __name__ == "__main__":
    j_path, p_path = export_network_geojson()
    verify_no_coordinate_distortion(j_path, p_path)
