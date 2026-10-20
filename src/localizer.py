"""
src/localizer.py
Hydraulic Anomaly Localization & Suspect Junction Pinpointing for Kaduwela East.

Features:
- Loads the WNTR EPANET hydraulic model (data/networks/kaduwela_2dma_clean_East_side.inp).
- Builds a topological & hydraulic sensitivity dictionary mapping monitored sensor nodes
  (J_10, J_100, J_500, J_1200, J_2200, J_3000) to surrounding junctions ranked by hydraulic influence.
- Implements localize_anomaly(zone_id, sensor_node_id, pressure_gap):
  * If pressure_gap < 2.0m: Returns None (normal hydraulic fluctuation).
  * If pressure_gap >= 2.0m:
      - Identifies suspect junction (e.g., J_100 for Zone 04).
      - Retrieves exact GPS coordinates (latitude, longitude) from src/geo_converter.py.
      - Defines a physical inspection corridor (radius_meters: 50).
      - Retrieves access landmark (e.g., 'Kaduwela East Main Road - Valve Box #4').
      - Generates a direct Google Maps inspection dispatch URL:
        https://www.google.com/maps/search/?api=1&query={lat},{lng}.
- Includes exported test function test_zone_04_localization() for automated validation.
"""

from pathlib import Path
import logging
import math
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure project root is available in module path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import networkx as nx
import wntr

from src.geo_converter import (
    DEFAULT_INP_PATH,
    get_junction_location,
    project_grid_to_wgs84,
)

logger = logging.getLogger("water_fraud.localizer")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [Localizer]: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Monitored sensors across Kaduwela DMAs
MONITORED_SENSOR_NODES: List[str] = [
    "J_10",
    "J_100",
    "J_500",
    "J_1200",
    "J_2200",
    "J_3000",
]

# Designated access landmarks for sensor nodes and primary suspect chambers
DESIGNATED_LANDMARKS: Dict[str, str] = {
    "J_100": "Kaduwela East Main Road - Valve Box #4",
    "J_10": "Kaduwela Town Central Main Road - Valve Box #1",
    "J_20": "Nawagamuwa North Devalaya Access - Valve Box #2",
    "J_500": "Korathota Junction / Welihinda Link - Valve Box #3",
    "J_1200": "Hewagama South Old Avissawella Corridor - Valve Box #5",
    "J_2200": "Ihala Bomiriya Highlands Access Road - Valve Box #6",
    "J_3000": "Outer Circular Expressway Service Road - Valve Box #7",
}

# Zone to sensor node default mapping
ZONE_TO_SENSOR: Dict[str, str] = {
    "01": "J_10",
    "zone-01": "J_10",
    "02": "J_20",
    "zone-02": "J_20",
    "03": "J_500",
    "zone-03": "J_500",
    "04": "J_100",
    "zone-04": "J_100",
    "05": "J_1200",
    "zone-05": "J_1200",
    "06": "J_3000",
    "zone-06": "J_3000",
}

# Sensor node to zone ID mapping
SENSOR_TO_ZONE: Dict[str, str] = {
    "J_10": "zone-01",
    "J_20": "zone-02",
    "J_500": "zone-03",
    "J_100": "zone-04",
    "J_1200": "zone-05",
    "J_2200": "zone-06",
    "J_3000": "zone-06",
}


class AnomalyLocalizer:
    """
    Hydraulic network anomaly localizer and sensitivity engine.
    """

    def __init__(self, inp_path: Union[str, Path] = DEFAULT_INP_PATH):
        self.inp_path = Path(inp_path)
        self._wn: Optional[wntr.network.WaterNetworkModel] = None
        self._graph: Optional[nx.Graph] = None
        self._sensitivity_dict: Dict[str, List[Dict[str, Any]]] = {}
        self._is_loaded = False

    def load_network(self) -> None:
        """Loads EPANET network model into WNTR and builds weighted undirected pipe graph."""
        if self._is_loaded:
            return

        if not self.inp_path.exists():
            raise FileNotFoundError(f"EPANET network file not found at: {self.inp_path}")

        logger.info(f"Loading WNTR WaterNetworkModel from {self.inp_path}...")
        self._wn = wntr.network.WaterNetworkModel(str(self.inp_path))

        # Build undirected graph where edges represent physical pipe segments weighted by length
        G = nx.Graph()
        for name, link in self._wn.pipes():
            length = float(getattr(link, "length", 50.0))
            diam = float(getattr(link, "diameter", 0.1))
            G.add_edge(
                link.start_node_name,
                link.end_node_name,
                pipe_name=name,
                length=length,
                diameter=diam,
                weight=max(0.1, length),
            )

        self._graph = G
        self._is_loaded = True
        logger.info(f"Constructed pipe topology graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} pipe links.")

    def build_sensitivity_dictionary(
        self,
        cutoff_m: float = 600.0,
        d0: float = 150.0,
        top_k: int = 20,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Builds hydraulic sensitivity dictionary:
        For each monitored sensor node, maps surrounding junctions ordered by hydraulic influence.
        Sensitivity S(s, j) = exp(-d(s, j) / d0), where d(s, j) is the shortest pipe path distance in meters.

        Returns:
            Dict mapping sensor_node_id -> list of surrounding junctions with distances and scores.
        """
        self.load_network()
        if self._sensitivity_dict:
            return self._sensitivity_dict

        G = self._graph
        assert G is not None

        sensitivity_dict: Dict[str, List[Dict[str, Any]]] = {}

        for sensor in MONITORED_SENSOR_NODES:
            if sensor not in G:
                logger.warning(f"Sensor node {sensor} not found in hydraulic network graph.")
                sensitivity_dict[sensor] = []
                continue

            # Compute shortest path distances along network pipes
            lengths = nx.single_source_dijkstra_path_length(
                G, source=sensor, cutoff=cutoff_m, weight="weight"
            )

            sorted_entries = sorted(lengths.items(), key=lambda item: item[1])
            node_entries: List[Dict[str, Any]] = []

            for node_id, dist_m in sorted_entries[:top_k]:
                score = math.exp(-dist_m / d0)
                node_entries.append({
                    "junction": node_id,
                    "pipe_distance_m": round(float(dist_m), 2),
                    "hydraulic_sensitivity": round(float(score), 4),
                })

            sensitivity_dict[sensor] = node_entries

        self._sensitivity_dict = sensitivity_dict
        logger.info(f"Built hydraulic sensitivity dictionary for {len(sensitivity_dict)} monitored sensors.")
        return self._sensitivity_dict

    def get_suspect_junction(self, zone_id: str, sensor_node_id: str) -> str:
        """
        Identifies the primary suspect junction for the given zone and sensor.
        For example: Zone 04 -> J_100.
        """
        if sensor_node_id and sensor_node_id.strip():
            return sensor_node_id.strip()

        clean_zone = zone_id.lower().replace("zone-", "").replace("zone", "").strip()
        if clean_zone in ZONE_TO_SENSOR:
            return ZONE_TO_SENSOR[clean_zone]

        norm_zone = f"zone-{int(clean_zone):02d}" if clean_zone.isdigit() else clean_zone
        return ZONE_TO_SENSOR.get(norm_zone, "J_100")

    def localize_anomaly(
        self,
        zone_id: str,
        sensor_node_id: str,
        pressure_gap: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Localizes a suspected unauthorized extraction or pressure deficit:
          - If pressure_gap < 2.0m: Returns None (normal hydraulic variance).
          - If pressure_gap >= 2.0m:
              * Identifies suspect junction (e.g., J_100 for Zone 04).
              * Retrieves exact GPS coordinates (latitude, longitude) from src/geo_converter.py.
              * Defines physical inspection corridor: radius_meters: 50.
              * Retrieves access landmark (e.g., 'Kaduwela East Main Road - Valve Box #4').
              * Generates direct Google Maps URL: https://www.google.com/maps/search/?api=1&query={lat},{lng}.

        Returns:
            Dict containing suspect localization dossier, or None.
        """
        gap = float(pressure_gap)
        if gap < 2.0:
            logger.debug(f"Pressure gap {gap:.2f}m is below 2.0m threshold; no localization required.")
            return None

        suspect_junction = self.get_suspect_junction(zone_id, sensor_node_id)

        # Retrieve exact GPS coordinates and sector location metadata from src/geo_converter.py
        loc = get_junction_location(suspect_junction)
        lat = float(loc["latitude"])
        lng = float(loc["longitude"])

        # Physical inspection corridor specification
        inspection_radius_m = 50

        # Retrieve landmark
        landmark = DESIGNATED_LANDMARKS.get(
            suspect_junction,
            f"{loc.get('nearest_access_road', 'Kaduwela East Main Corridor')} - Valve Box #{suspect_junction}",
        )

        # Direct Google Maps URL with exact decimal coordinates
        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lng:.6f}"

        # Ensure sensitivity dictionary is available
        sens_dict = self.build_sensitivity_dictionary()
        sensitive_neighbors = sens_dict.get(suspect_junction, [])

        clean_zone = zone_id.lower().replace("zone-", "").replace("zone", "").strip()
        standard_zone_id = f"zone-{int(clean_zone):02d}" if clean_zone.isdigit() else zone_id

        return {
            "suspect_junction": suspect_junction,
            "node_id": suspect_junction,
            "junction_id": suspect_junction,
            "zone_id": standard_zone_id,
            "sensor_node_id": sensor_node_id or suspect_junction,
            "pressure_gap": round(gap, 2),
            "pressure_drop_m": round(gap, 2),
            "latitude": round(lat, 6),
            "longitude": round(lng, 6),
            "coordinates": (round(lat, 6), round(lng, 6)),
            "radius_meters": inspection_radius_m,
            "inspection_corridor": {
                "radius_meters": inspection_radius_m,
                "landmark": landmark,
                "corridor_type": "physical_inspection_radius",
            },
            "physical_inspection_corridor": {
                "radius_meters": inspection_radius_m,
                "landmark": landmark,
                "corridor_type": "physical_inspection_radius",
            },
            "access_landmark": landmark,
            "landmark": landmark,
            "google_maps_url": google_maps_url,
            "dma_id": loc.get("dma_id", "DMA 01"),
            "dma_boundary": loc.get("dma_boundary", ""),
            "nearest_access_road": loc.get("nearest_access_road", ""),
            "sensitive_surrounding_nodes": sensitive_neighbors[:10],
        }


# ==============================================================================
# Module-Level Singleton & Convenience Wrappers
# ==============================================================================
_LOCALIZER_INSTANCE: Optional[AnomalyLocalizer] = None


def get_localizer(inp_path: Union[str, Path] = DEFAULT_INP_PATH) -> AnomalyLocalizer:
    """Returns singleton AnomalyLocalizer instance."""
    global _LOCALIZER_INSTANCE
    if _LOCALIZER_INSTANCE is None:
        _LOCALIZER_INSTANCE = AnomalyLocalizer(inp_path=inp_path)
    return _LOCALIZER_INSTANCE


def build_sensitivity_dictionary(
    cutoff_m: float = 600.0,
    d0: float = 150.0,
) -> Dict[str, List[Dict[str, Any]]]:
    """Public helper to retrieve sensitivity dictionary."""
    return get_localizer().build_sensitivity_dictionary(cutoff_m=cutoff_m, d0=d0)


def localize_anomaly(
    zone_id: str,
    sensor_node_id: str,
    pressure_gap: float,
) -> Optional[Dict[str, Any]]:
    """
    Public entry point to localize anomalous pressure residuals:
      - Returns None if pressure_gap < 2.0m.
      - Returns complete inspection dossier if pressure_gap >= 2.0m.
    """
    return get_localizer().localize_anomaly(
        zone_id=zone_id,
        sensor_node_id=sensor_node_id,
        pressure_gap=pressure_gap,
    )


def test_zone_04_localization() -> bool:
    """
    Exported verification function:
    Asserts that passing an anomaly in Zone 04 returns the target coordinates for J_100.
    """
    # 1. Below threshold returns None
    normal_res = localize_anomaly(zone_id="zone-04", sensor_node_id="J_100", pressure_gap=1.5)
    assert normal_res is None, f"Expected None for pressure_gap < 2.0m, got: {normal_res}"

    # 2. Above threshold returns dossier for J_100
    anomaly_res = localize_anomaly(zone_id="zone-04", sensor_node_id="J_100", pressure_gap=6.0)
    assert anomaly_res is not None, "Expected localization result for Zone 04 anomaly, got None"
    assert anomaly_res["suspect_junction"] == "J_100"
    assert anomaly_res["zone_id"] == "zone-04"
    assert anomaly_res["radius_meters"] == 50
    assert anomaly_res["access_landmark"] == "Kaduwela East Main Road - Valve Box #4"

    # Coordinates verification for J_100
    assert abs(anomaly_res["latitude"] - 6.936812) < 0.001, f"Latitude mismatch: {anomaly_res['latitude']}"
    assert abs(anomaly_res["longitude"] - 79.967673) < 0.001, f"Longitude mismatch: {anomaly_res['longitude']}"

    # Google Maps URL verification
    expected_url = "https://www.google.com/maps/search/?api=1&query=6.936812,79.967673"
    assert anomaly_res["google_maps_url"] == expected_url, f"URL mismatch: {anomaly_res['google_maps_url']}"

    print("[PASS] test_zone_04_localization: Suspect J_100 localized accurately with target coordinates and landmark.")
    return True


if __name__ == "__main__":
    print("=" * 80)
    print("  KADUWELA WATER NETWORK: ANOMALY LOCALIZER & SENSITIVITY ENGINE")
    print("=" * 80)

    localizer = get_localizer()
    localizer.load_network()
    sens = localizer.build_sensitivity_dictionary()

    print("\n[Sensitivity Dictionary Summary]")
    for s_id in MONITORED_SENSOR_NODES:
        top_nodes = sens.get(s_id, [])[:3]
        top_str = ", ".join([f"{n['junction']} ({n['pipe_distance_m']}m, S={n['hydraulic_sensitivity']})" for n in top_nodes])
        print(f"  Sensor {s_id:6s} -> Top Influencing Nodes: {top_str}")

    print("\n[Running Zone 04 Localization Test]")
    test_zone_04_localization()
