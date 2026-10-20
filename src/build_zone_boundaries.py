"""
src/build_zone_boundaries.py
Generates operational zone boundary polygons from network junction coordinates for Kaduwela East.

Loads junction coordinates from data/processed/kaduwela_nodes_geo.json (or extracts them
from data/networks/kaduwela_2dma_clean_East_side.inp using WNTR as fallback).

Groups junctions into the 6 operational sectors across Kaduwela East:
  - DMA 01:
      * Zone 01 - Kaduwela Town Central (sensor: J_10)
      * Zone 02 - Nawagamuwa North (sensor: J_20)
      * Zone 04 - Kaduwela East Industrial (sensor: J_100)
  - DMA 02:
      * Zone 03 - Korathota Junction (sensor: J_500)
      * Zone 05 - Welihinda Ridge (sensor: J_1200)
      * Zone 06 - Welivita Highway Exit (sensor: J_3000, J_2200)

Computes spatial boundary polygons using scipy.spatial.ConvexHull (or shapely.geometry.MultiPoint).
Adds an outward spatial buffer (20-30 meters, default 25m) so peripheral pipes are fully enclosed.
Exports valid RFC 7946 GeoJSON to frontend/public/data/kaduwela_zones.geojson with properties:
  zone_id, name, dma_id, sensor_node_id, and default_status: 'NORMAL'.
"""

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in Python module search path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from scipy.spatial import ConvexHull

from src.geo_converter import (
    DEFAULT_INP_PATH,
    find_nearest_sector,
    project_grid_to_wgs84,
)

# Optional shapely integration
try:
    import shapely.geometry as sgeom
    _SHAPELY_AVAILABLE = True
except ImportError:
    _SHAPELY_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_zone_boundaries")

# Default file paths
DEFAULT_NODES_GEOJSON = PROJECT_ROOT / "data" / "processed" / "kaduwela_nodes_geo.json"
DEFAULT_OUTPUT_GEOJSON = PROJECT_ROOT / "frontend" / "public" / "data" / "kaduwela_zones.geojson"

# Zone metadata configuration for the 6 operational sectors in Kaduwela East
ZONE_SPECIFICATIONS: List[Dict[str, Any]] = [
    {
        "zone_id": "zone-01",
        "name": "Zone 01 - Kaduwela Town Central",
        "dma_id": "DMA 01",
        "sensor_node_id": "J_10",
        "default_status": "NORMAL",
        "anchor_node": "J_10",
    },
    {
        "zone_id": "zone-02",
        "name": "Zone 02 - Nawagamuwa North",
        "dma_id": "DMA 01",
        "sensor_node_id": "J_20",
        "default_status": "NORMAL",
        "anchor_node": "J_20",
    },
    {
        "zone_id": "zone-04",
        "name": "Zone 04 - Kaduwela East Industrial",
        "dma_id": "DMA 01",
        "sensor_node_id": "J_100",
        "default_status": "NORMAL",
        "anchor_node": "J_100",
    },
    {
        "zone_id": "zone-03",
        "name": "Zone 03 - Korathota Junction",
        "dma_id": "DMA 02",
        "sensor_node_id": "J_500",
        "default_status": "NORMAL",
        "anchor_node": "J_500",
    },
    {
        "zone_id": "zone-05",
        "name": "Zone 05 - Welihinda Ridge",
        "dma_id": "DMA 02",
        "sensor_node_id": "J_1200",
        "default_status": "NORMAL",
        "anchor_node": "J_1200",
    },
    {
        "zone_id": "zone-06",
        "name": "Zone 06 - Welivita Highway Exit",
        "dma_id": "DMA 02",
        "sensor_node_id": "J_3000",
        "default_status": "NORMAL",
        "anchor_node": "J_3000",
        "secondary_nodes": ["J_2200"],
    },
]


def load_junction_nodes(
    nodes_geo_path: Optional[Path] = None,
    inp_path: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Loads all junction coordinates from data/processed/kaduwela_nodes_geo.json.
    If not available, falls back to parsing data/networks/kaduwela_2dma_clean_East_side.inp
    using WNTR and calculating coordinates.

    Returns:
        Dict mapping node_id -> dict with grid_x, grid_y, latitude, longitude, dma_id, etc.
    """
    geo_path = nodes_geo_path or DEFAULT_NODES_GEOJSON
    network_path = inp_path or DEFAULT_INP_PATH

    if geo_path.exists():
        logger.info(f"Loading junction nodes from processed JSON: {geo_path}")
        with open(geo_path, "r", encoding="utf-8") as f:
            nodes_data = json.load(f)
        logger.info(f"Loaded {len(nodes_data)} junctions from {geo_path.name}")
        return nodes_data

    # Fallback to WNTR INP extraction
    logger.info(f"Processed nodes file not found at {geo_path}. Extracting from INP: {network_path}")
    import wntr

    wn = wntr.network.WaterNetworkModel(str(network_path))
    nodes_data: Dict[str, Dict[str, Any]] = {}

    for name, node in wn.junctions():
        gx, gy = node.coordinates
        elev = float(getattr(node, "elevation", 12.0))
        lat, lon = project_grid_to_wgs84(gx, gy)
        sec = find_nearest_sector(gx, gy, node_id=str(name))
        dma_id = str(sec.get("dma_id", "DMA 01"))

        nodes_data[str(name)] = {
            "node_id": str(name),
            "grid_x": float(gx),
            "grid_y": float(gy),
            "elevation_m": elev,
            "latitude": lat,
            "longitude": lon,
            "dma_id": dma_id,
            "sector_name": sec.get("sector_name", ""),
        }

    logger.info(f"Extracted {len(nodes_data)} junctions from EPANET model {network_path.name}")
    return nodes_data


def group_nodes_by_operational_zones(
    nodes_data: Dict[str, Dict[str, Any]]
) -> Dict[str, List[str]]:
    """
    Groups all network junctions into their corresponding operational zones in Kaduwela East:
      - DMA 01: Zone 01, Zone 02, Zone 04
      - DMA 02: Zone 03, Zone 05, Zone 06

    Ensures key monitoring sensors:
      - J_10 is in Zone 01
      - J_20 is in Zone 02
      - J_100 is in Zone 04
      - J_500 is in Zone 03
      - J_1200 is in Zone 05
      - J_3000 and J_2200 are in Zone 06

    Returns:
        Dict mapping zone_id -> list of node IDs.
    """
    groups: Dict[str, List[str]] = {spec["zone_id"]: [] for spec in ZONE_SPECIFICATIONS}

    # Reference coordinates for zone anchors
    anchor_coords: Dict[str, Tuple[float, float]] = {}
    for spec in ZONE_SPECIFICATIONS:
        zid = spec["zone_id"]
        anode = spec["anchor_node"]
        if anode in nodes_data:
            anchor_coords[zid] = (nodes_data[anode]["grid_x"], nodes_data[anode]["grid_y"])
        else:
            # Fallback to mean coordinates if anchor missing
            anchor_coords[zid] = (412730.0, 492800.0)

    # Optional secondary anchor points (e.g. J_2200 for Zone 06)
    secondary_coords: Dict[str, List[Tuple[float, float]]] = {}
    for spec in ZONE_SPECIFICATIONS:
        zid = spec["zone_id"]
        secondary_coords[zid] = []
        for snode in spec.get("secondary_nodes", []):
            if snode in nodes_data:
                secondary_coords[zid].append(
                    (nodes_data[snode]["grid_x"], nodes_data[snode]["grid_y"])
                )

    dma1_zones = ["zone-01", "zone-02", "zone-04"]
    dma2_zones = ["zone-03", "zone-05", "zone-06"]

    # Priority pinned overrides
    pinned_assignments = {
        "J_10": "zone-01",
        "J_20": "zone-02",
        "J_100": "zone-04",
        "J_500": "zone-03",
        "J_1200": "zone-05",
        "J_2200": "zone-06",
        "J_3000": "zone-06",
    }

    for nid, node in nodes_data.items():
        if nid in pinned_assignments:
            groups[pinned_assignments[nid]].append(nid)
            continue

        gx = node["grid_x"]
        gy = node["grid_y"]
        dma = node.get("dma_id", "DMA 01")

        candidates = dma1_zones if dma == "DMA 01" else dma2_zones

        best_zone = candidates[0]
        min_dist = float("inf")

        for zid in candidates:
            ax, ay = anchor_coords[zid]
            d = math.hypot(gx - ax, gy - ay)

            # Check secondary anchors if any
            for sx, sy in secondary_coords.get(zid, []):
                sd = math.hypot(gx - sx, gy - sy)
                if sd < d:
                    d = sd

            if d < min_dist:
                min_dist = d
                best_zone = zid

        groups[best_zone].append(nid)

    for zid, nids in sorted(groups.items()):
        logger.info(f"Zone {zid}: assigned {len(nids)} junctions")

    return groups


def buffer_convex_hull(
    points_meters: np.ndarray,
    buffer_m: float = 25.0,
    arc_segments: int = 8,
) -> np.ndarray:
    """
    Computes a buffered outer boundary (Minkowski sum with circular disk of radius buffer_m)
    for a 2D point cloud in metric coordinates (e.g. SLD99 grid meters).

    If shapely is available, utilizes shapely.geometry.MultiPoint(points).convex_hull.buffer.
    Otherwise, applies an exact Minkowski sum on scipy.spatial.ConvexHull vertices.

    Returns:
        np.ndarray of shape (M, 2) of CCW-ordered polygon boundary vertices in meters.
    """
    pts = np.asarray(points_meters, dtype=float)
    if len(pts) < 3:
        raise ValueError(f"At least 3 points are required to compute a convex hull polygon. Got {len(pts)}.")

    if _SHAPELY_AVAILABLE:
        try:
            mp = sgeom.MultiPoint(pts)
            hull = mp.convex_hull
            buffered = hull.buffer(buffer_m, quad_segs=arc_segments)
            if hasattr(buffered, "exterior") and buffered.exterior is not None:
                coords = np.array(buffered.exterior.coords)
                # Omit trailing duplicate if present
                if len(coords) > 1 and np.allclose(coords[0], coords[-1]):
                    coords = coords[:-1]
                return coords
        except Exception as e:
            logger.warning(f"Shapely buffering encountered error: {e}. Falling back to SciPy implementation.")

    # Native SciPy ConvexHull + Minkowski circular arc expansion
    base_hull = ConvexHull(pts)
    hull_pts = pts[base_hull.vertices]
    n = len(hull_pts)

    # Compute outward unit normals for each edge
    normals = []
    for i in range(n):
        p1 = hull_pts[i]
        p2 = hull_pts[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length == 0:
            normals.append((0.0, 1.0))
        else:
            normals.append((dy / length, -dx / length))

    # Add circular arcs around each hull vertex
    buffered_pts = []
    for i in range(n):
        v = hull_pts[i]
        n_prev = normals[(i - 1) % n]
        n_curr = normals[i]

        theta_prev = math.atan2(n_prev[1], n_prev[0])
        theta_curr = math.atan2(n_curr[1], n_curr[0])

        # Angular difference in counter-clockwise direction
        d_theta = (theta_curr - theta_prev) % (2.0 * math.pi)
        steps = max(2, int(arc_segments * (d_theta / (math.pi / 2.0))))

        for step in range(steps + 1):
            theta = theta_prev + d_theta * (step / steps)
            ox = v[0] + buffer_m * math.cos(theta)
            oy = v[1] + buffer_m * math.sin(theta)
            buffered_pts.append([ox, oy])

    buf_array = np.array(buffered_pts)
    buf_hull = ConvexHull(buf_array)
    return buf_array[buf_hull.vertices]


def build_kaduwela_zones_geojson(
    nodes_geo_path: Optional[Path] = None,
    inp_path: Optional[Path] = None,
    buffer_m: float = 25.0,
) -> Dict[str, Any]:
    """
    Executes the full pipeline to generate GeoJSON zone boundaries:
      1. Loads junction nodes.
      2. Groups nodes by operational zones.
      3. Computes spatial convex hull with outward metric buffer (20-30m).
      4. Projects boundaries to WGS84 GPS decimal degrees [longitude, latitude].
      5. Constructs FeatureCollection with standardized properties.

    Returns:
        GeoJSON FeatureCollection dict.
    """
    nodes_data = load_junction_nodes(nodes_geo_path, inp_path)
    groups = group_nodes_by_operational_zones(nodes_data)

    spec_by_id = {spec["zone_id"]: spec for spec in ZONE_SPECIFICATIONS}
    features: List[Dict[str, Any]] = []

    for zid in sorted(groups.keys()):
        spec = spec_by_id[zid]
        node_ids = groups[zid]

        coords_metric = np.array(
            [[nodes_data[nid]["grid_x"], nodes_data[nid]["grid_y"]] for nid in node_ids],
            dtype=float,
        )

        buffered_metric = buffer_convex_hull(coords_metric, buffer_m=buffer_m)

        # Project boundary vertices from SLD99 grid meters to WGS84 GPS [longitude, latitude]
        gps_ring: List[List[float]] = []
        for pt in buffered_metric:
            lat, lon = project_grid_to_wgs84(pt[0], pt[1])
            gps_ring.append([lon, lat])

        # RFC 7946 Polygon LinearRing must be closed (first coordinate equals last)
        if gps_ring and gps_ring[0] != gps_ring[-1]:
            gps_ring.append(list(gps_ring[0]))

        # Approximate area calculation in square meters (Shoelace formula on metric polygon)
        x = buffered_metric[:, 0]
        y = buffered_metric[:, 1]
        area_m2 = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))

        feature = {
            "type": "Feature",
            "id": zid,
            "geometry": {
                "type": "Polygon",
                "coordinates": [gps_ring],
            },
            "properties": {
                "zone_id": spec["zone_id"],
                "name": spec["name"],
                "dma_id": spec["dma_id"],
                "sensor_node_id": spec["sensor_node_id"],
                "default_status": spec["default_status"],
                "node_count": len(node_ids),
                "area_sq_m": round(float(area_m2), 1),
                "buffer_applied_m": buffer_m,
            },
        }
        features.append(feature)

    feature_collection = {
        "type": "FeatureCollection",
        "name": "kaduwela_zones",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }

    return feature_collection


def export_zone_boundaries_geojson(
    output_path: Optional[Path] = None,
    nodes_geo_path: Optional[Path] = None,
    inp_path: Optional[Path] = None,
    buffer_m: float = 25.0,
) -> Path:
    """
    Generates and exports kaduwela_zones.geojson to disk.

    Returns:
        Path of written GeoJSON file.
    """
    out_file = output_path or DEFAULT_OUTPUT_GEOJSON
    out_file.parent.mkdir(parents=True, exist_ok=True)

    geojson_data = build_kaduwela_zones_geojson(
        nodes_geo_path=nodes_geo_path,
        inp_path=inp_path,
        buffer_m=buffer_m,
    )

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2)

    logger.info(f"Successfully exported {len(geojson_data['features'])} zone polygons to: {out_file}")
    logger.info(f"File size: {out_file.stat().st_size:,} bytes")
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build operational zone boundaries GeoJSON for Kaduwela East water supply network."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_GEOJSON,
        help=f"Destination GeoJSON path (default: {DEFAULT_OUTPUT_GEOJSON})",
    )
    parser.add_argument(
        "--nodes-json",
        type=Path,
        default=DEFAULT_NODES_GEOJSON,
        help=f"Path to processed nodes JSON (default: {DEFAULT_NODES_GEOJSON})",
    )
    parser.add_argument(
        "--inp",
        type=Path,
        default=DEFAULT_INP_PATH,
        help=f"Path to EPANET .inp file fallback (default: {DEFAULT_INP_PATH})",
    )
    parser.add_argument(
        "--buffer",
        "-b",
        type=float,
        default=25.0,
        help="Spatial buffer distance in meters around outer boundary (default: 25.0m)",
    )

    args = parser.parse_args()

    out_path = export_zone_boundaries_geojson(
        output_path=args.output,
        nodes_geo_path=args.nodes_json,
        inp_path=args.inp,
        buffer_m=args.buffer,
    )
    print(f"\n[OK] Operational zone boundaries written to: {out_path}")
    print(f"     Buffer: {args.buffer} meters")


if __name__ == "__main__":
    main()
