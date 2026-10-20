"""
verify_full_system.py
Automated end-to-end sanity verification across all Component 2 modules:
1. Physical Twin: Verifies EPANET .inp network file exists and parses cleanly via WNTR.
2. Two-Stage AI: Verifies Isolation Forest & Random Forest models load and score.
3. API Service: Sends mock unauthorized bypass telemetry for Node J_100 to /api/v1/assess-risk.
4. Geo-Location: Verifies response contains fraud_risk_score >= 70, classification == 'partial_bypass',
   valid WGS84 GPS coordinates, and Google Maps navigation link.
5. Notifications: Confirms alert record is logged in data/processed/dispatched_alerts.json.
6. Prints formatted terminal checklist:
   [PASS] Physical Twin, [PASS] Two-Stage AI, [PASS] Geo-Location, [PASS] Notifications, [PASS] API Service.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import warnings

# Ensure project root is available in module path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# File paths
INP_NETWORK_PATH = PROJECT_ROOT / "data" / "networks" / "kaduwela_2dma_clean_East_side.inp"
MODELS_DIR = PROJECT_ROOT / "models"
ISO_FOREST_PATH = MODELS_DIR / "isolation_forest.joblib"
RANDOM_FOREST_PATH = MODELS_DIR / "random_forest.joblib"
DISPATCHED_ALERTS_PATH = PROJECT_ROOT / "data" / "processed" / "dispatched_alerts.json"

API_BASE_URL = "http://127.0.0.1:8000"
ASSESS_RISK_ENDPOINT = f"{API_BASE_URL}/api/v1/assess-risk"

# Standard mock telemetry payload exhibiting an unauthorized bypass drop at Node J_100
MOCK_BYPASS_TELEMETRY: Dict[str, Any] = {
    "zone_id": "DMA 01",
    "node_id": "J_100",
    "actual_pressure": 28.50,
    "expected_pressure": 34.70,
    "spatial_deviation": 5.80,
    "recurrence_count": 5,
    "pressure_change_rate": -0.05,
    "residual_rolling_mean": 6.10,
    "residual_rolling_std": 0.12,
    "hours_since_supply_start": 2.50,
}


def verify_physical_twin() -> Tuple[bool, str]:
    """
    1. Verify that data/networks/kaduwela_2dma_clean_East_side.inp exists and parses cleanly.
    """
    if not INP_NETWORK_PATH.exists():
        return False, f"Network file missing at {INP_NETWORK_PATH}"

    try:
        import wntr

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wn = wntr.network.WaterNetworkModel(str(INP_NETWORK_PATH))

        num_junctions = len(wn.junction_name_list)
        num_pipes = len(wn.pipe_name_list)
        num_reservoirs = len(wn.reservoir_name_list)

        if num_junctions == 0:
            return False, "Parsed network model contains 0 junctions."

        # Verify J_100 coordinates exist
        if "J_100" not in wn.junction_name_list:
            return False, "Target node J_100 not found in network junctions."

        coord = wn.get_node("J_100").coordinates
        return True, (
            f"WNTR parsed {num_junctions:,} junctions, {num_pipes:,} pipes, "
            f"{num_reservoirs} reservoirs (J_100 grid coords: {coord[0]:.2f}, {coord[1]:.2f})"
        )
    except Exception as exc:
        return False, f"Failed to parse EPANET .inp file: {exc}"


def verify_two_stage_ai() -> Tuple[bool, str]:
    """
    2. Verify that models/isolation_forest.joblib and models/random_forest.joblib are loaded and functional.
    """
    if not ISO_FOREST_PATH.exists():
        return False, f"Isolation Forest model missing at {ISO_FOREST_PATH}"
    if not RANDOM_FOREST_PATH.exists():
        return False, f"Random Forest model missing at {RANDOM_FOREST_PATH}"

    try:
        import joblib
        import numpy as np

        iso_model = joblib.load(ISO_FOREST_PATH)
        rf_model = joblib.load(RANDOM_FOREST_PATH)

        # Dummy feature vector matching the 6 canonical hydraulic features
        test_vector = np.array([[20.0, 1.2, 0.05, 1.1, 0.2, 0.4]])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            iso_pred = iso_model.predict(test_vector)
            iso_score = iso_model.score_samples(test_vector)
            rf_pred = rf_model.predict(test_vector)
            rf_proba = rf_model.predict_proba(test_vector)

        classes_list = [str(c) for c in getattr(rf_model, "classes_", [])]
        return True, (
            f"Stage 1 IsolationForest functional (score={iso_score[0]:.4f}); "
            f"Stage 2 RandomForest functional ({len(rf_model.estimators_)} trees, classes={classes_list})"
        )
    except Exception as exc:
        return False, f"Failed to execute two-stage AI model scoring: {exc}"


def send_telemetry_request() -> Tuple[bool, Dict[str, Any], str]:
    """
    3. Send mock telemetry reading for Node J_100 exhibiting an unauthorized bypass drop
       to http://127.0.0.1:8000/api/v1/assess-risk.
       Gracefully queries live HTTP service or falls back to in-process FastAPI TestClient.
    """
    # Attempt 1: Live HTTP endpoint via httpx
    try:
        import httpx

        response = httpx.post(ASSESS_RISK_ENDPOINT, json=MOCK_BYPASS_TELEMETRY, timeout=8.0)
        if response.status_code == 200:
            return True, response.json(), f"Live HTTP 200 OK from {ASSESS_RISK_ENDPOINT}"
        return False, {}, f"Live HTTP returned status {response.status_code}: {response.text}"
    except Exception:
        pass

    # Attempt 2: In-process TestClient fallback if live server process is starting
    try:
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.post("/api/v1/assess-risk", json=MOCK_BYPASS_TELEMETRY)
        if response.status_code == 200:
            return True, response.json(), "In-Process TestClient 200 OK (/api/v1/assess-risk)"
        return False, {}, f"TestClient returned status {response.status_code}: {response.text}"
    except Exception as exc:
        return False, {}, f"Failed to send telemetry reading: {exc}"


def verify_geo_and_classification(response_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    4. Verify that the response returns:
       - fraud_risk_score >= 70.0
       - classification == 'partial_bypass'
       - Valid location data containing real coordinates and a Google Maps link.
    """
    # 4a. Check fraud risk score
    fraud_score = float(response_data.get("fraud_risk_score", 0.0))
    if fraud_score < 70.0:
        return False, f"fraud_risk_score ({fraud_score:.2f}) is below threshold 70.0"

    # 4b. Check classification
    classification = str(response_data.get("classification", ""))
    if classification != "partial_bypass":
        return False, f"Expected classification 'partial_bypass', but got '{classification}'"

    # 4c. Check location metadata
    location = response_data.get("location")
    if not isinstance(location, dict):
        return False, f"Missing or invalid location object in response: {location}"

    lat = location.get("latitude")
    lng = location.get("longitude")
    gmaps_url = location.get("google_maps_url", "")
    landmark = location.get("landmark", "")

    if lat is None or lng is None:
        return False, f"Location lacks latitude or longitude: lat={lat}, lng={lng}"

    if not (6.0 <= float(lat) <= 8.0) or not (79.0 <= float(lng) <= 81.0):
        return False, f"Coordinates outside Sri Lanka / Kaduwela bounding box: ({lat}, {lng})"

    if not isinstance(gmaps_url, str) or not gmaps_url.startswith("https://www.google.com/maps/search/"):
        return False, f"Invalid Google Maps navigation link: {gmaps_url}"

    return True, (
        f"Score={fraud_score:.2f} (>=70.0), Class='{classification}', "
        f"GPS=({lat:.6f} N, {lng:.6f} E), Landmark='{landmark}', MapsURL='{gmaps_url}'"
    )


def verify_notifications() -> Tuple[bool, str]:
    """
    5. Confirm that data/processed/dispatched_alerts.json records the alert entry.
    """
    if not DISPATCHED_ALERTS_PATH.exists():
        return False, f"Dispatched alerts log file missing at {DISPATCHED_ALERTS_PATH}"

    try:
        with open(DISPATCHED_ALERTS_PATH, "r", encoding="utf-8") as f:
            alerts = json.load(f)

        if not isinstance(alerts, list) or len(alerts) == 0:
            return False, "dispatched_alerts.json is empty or not a list."

        # Find matching alert for Node J_100 with partial_bypass classification
        matching_alerts = [
            a for a in alerts
            if a.get("node_id") == "J_100" and a.get("probable_cause") == "partial_bypass"
        ]

        if not matching_alerts:
            return False, "No alert entry for Node J_100 with probable_cause='partial_bypass' found in log."

        last_alert = matching_alerts[-1]
        alert_id = last_alert.get("alert_id", "N/A")
        risk_score = last_alert.get("risk_score", 0.0)
        status = last_alert.get("delivery_status", "N/A")
        return True, (
            f"Alert entry confirmed in dispatched_alerts.json ({len(alerts)} total logged): "
            f"ID={alert_id}, Node={last_alert.get('node_id')}, Risk={risk_score:.2f}, Delivery={status}"
        )
    except Exception as exc:
        return False, f"Failed to read or parse dispatched_alerts.json: {exc}"


def main() -> int:
    divider = "=" * 80
    subdivider = "-" * 80

    print("\n" + divider)
    print("NWSDB COMPONENT 2: FULL SYSTEM AUTOMATED SANITY VERIFICATION")
    print(divider)

    checklist: List[Tuple[str, str, bool, str]] = []

    # 1. Physical Twin Verification
    ok_twin, msg_twin = verify_physical_twin()
    checklist.append(("Physical Twin", "kaduwela_2dma_clean_East_side.inp", ok_twin, msg_twin))

    # 2. Two-Stage AI Verification
    ok_ai, msg_ai = verify_two_stage_ai()
    checklist.append(("Two-Stage AI", "Isolation Forest & Random Forest", ok_ai, msg_ai))

    # 3. API Service & Mock Telemetry
    ok_api, resp_data, msg_api = send_telemetry_request()
    checklist.append(("API Service", "POST /api/v1/assess-risk", ok_api, msg_api))

    # 4. Geo-Location & Risk Assessment Response
    if ok_api and resp_data:
        ok_geo, msg_geo = verify_geo_and_classification(resp_data)
    else:
        ok_geo, msg_geo = False, "Skipped due to API service failure"
    checklist.append(("Geo-Location", "Node J_100 GPS & Triage", ok_geo, msg_geo))

    # 5. Notifications Verification
    ok_notif, msg_notif = verify_notifications()
    checklist.append(("Notifications", "dispatched_alerts.json", ok_notif, msg_notif))

    # Print Detailed Execution Trace
    print("\nDETAILED VERIFICATION LOGS:")
    print(subdivider)
    for title, subtitle, passed, details in checklist:
        tag = "[PASS]" if passed else "[FAIL]"
        print(f"* {title:<16s} ({subtitle}):")
        print(f"  Result : {tag}")
        print(f"  Details: {details}\n")

    # Print Formatted Terminal Checklist exactly as requested:
    # [PASS] Physical Twin, [PASS] Two-Stage AI, [PASS] Geo-Location, [PASS] Notifications, [PASS] API Service
    print(divider)
    print("FORMATTED COMPONENT CHECKLIST:")
    print(subdivider)
    
    status_map = {item[0]: ("[PASS]" if item[2] else "[FAIL]") for item in checklist}
    
    print(
        f"{status_map['Physical Twin']} Physical Twin\n"
        f"{status_map['Two-Stage AI']} Two-Stage AI\n"
        f"{status_map['Geo-Location']} Geo-Location\n"
        f"{status_map['Notifications']} Notifications\n"
        f"{status_map['API Service']} API Service"
    )

    all_passed = all(item[2] for item in checklist)
    print(divider)
    if all_passed:
        print("OVERALL VERDICT: [PASS] FULL SYSTEM SANITY CHECK PASSED (5/5 COMPONENTS VERIFIED)")
    else:
        print("OVERALL VERDICT: [FAIL] ONE OR MORE COMPONENTS FAILED SANITY CHECK")
    print(divider + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
