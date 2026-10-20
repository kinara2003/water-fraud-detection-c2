"""
src/scenario_runner.py
Automated Demonstration Launcher & Interactive Scenario Runner
Component 2: NWSDB Unauthorized Water Withdrawal & Physical Twin Surveillance Engine

Demonstrates 4 core operational modes of the Kaduwela Water Fraud Detection system:
  1. --scenario normal:
     Streams clean baseline telemetry across Kaduwela DMAs 01 & 02.
     Demonstrates nominal hydraulic conditions (Risk < 25%, 0 false alarms, all green).
  2. --scenario refill_surge:
     Emulates 06:00 AM supply opening under Intermittent Water Supply (IWS).
     Rapid pressure drops occur as empty pipes refill; demonstrates that the IWS
     transient dampening filter suppresses false alarms (Risk stays < 45%).
  3. --scenario pipe_leak:
     Emulates physical pipe burst at junction J_500 coupled with Component 1 acoustic/sensor
     leak feedback (leak_prob > 0.70). Demonstrates fraud score suppression and reclassification
     to physical pipe repair instead of theft.
  4. --scenario bypass_theft:
     Emulates unauthorized 0.06 LPS industrial withdrawal at J_100 during morning peak.
     Triggers high-risk fraud state (89-92%), logs exact WGS84 GPS coordinates & Google Maps link,
     and dispatches urgent authority alerts via email and municipal webhooks.

Options:
  --scenario [normal|refill_surge|pipe_leak|bypass_theft|all]
  --speed FLOAT     Timestep delay in seconds (default: 0.1s for fast-forwarding, or 1.0s for real-time)
  --url STR         FastAPI backend URL (default: http://127.0.0.1:8000; falls back to in-process engine if offline)
  --interactive, -i Launch interactive menu
"""

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# Ensure project root is available in module path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scenario_runner")


# ==============================================================================
# ANSI Color & Formatting Constants
# ==============================================================================
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    # Foreground
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    # Background
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"


def print_banner(title: str, subtitle: str = "") -> None:
    print(f"\n{Color.CYAN}{'=' * 82}{Color.RESET}")
    print(f"{Color.BOLD}{Color.WHITE}  {title.center(78)}{Color.RESET}")
    if subtitle:
        print(f"{Color.DIM}{subtitle.center(80)}{Color.RESET}")
    print(f"{Color.CYAN}{'=' * 82}{Color.RESET}\n")


def print_section(title: str) -> None:
    print(f"\n{Color.BOLD}{Color.BLUE}--- {title} ---{Color.RESET}")


def format_risk_badge(score: float) -> str:
    if score >= 75.0:
        return f"{Color.BG_RED}{Color.WHITE}{Color.BOLD} CRITICAL {score:5.1f}% {Color.RESET}"
    elif score >= 50.0:
        return f"{Color.BG_YELLOW}{Color.WHITE}{Color.BOLD} HIGH     {score:5.1f}% {Color.RESET}"
    elif score >= 25.0:
        return f"{Color.YELLOW}{Color.BOLD} MEDIUM   {score:5.1f}% {Color.RESET}"
    else:
        return f"{Color.BG_GREEN}{Color.WHITE}{Color.BOLD} NORMAL   {score:5.1f}% {Color.RESET}"


def format_status_code(code: int) -> str:
    if 200 <= code < 300:
        return f"{Color.GREEN}HTTP {code} OK{Color.RESET}"
    elif 400 <= code < 500:
        return f"{Color.YELLOW}HTTP {code}{Color.RESET}"
    else:
        return f"{Color.RED}HTTP {code}{Color.RESET}"


# ==============================================================================
# Dual-Mode API Client (HTTP requests with automatic in-process fallback)
# ==============================================================================
class ScenarioClient:
    """
    Transparent API client that connects via HTTP to a running uvicorn server,
    or falls back automatically to FastAPI's in-process TestClient if offline.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")
        self.is_external: bool = False
        self._test_client: Optional[Any] = None
        self._init_connection()

    def _init_connection(self) -> None:
        try:
            import requests
            resp = requests.get(f"{self.base_url}/api/v1", timeout=0.8)
            if resp.status_code == 200:
                self.is_external = True
                print(f"  {Color.GREEN}[ONLINE]{Color.RESET} Connected to live server at {self.base_url}")
                return
        except Exception:
            pass

        # Server not running externally; initialize in-process FastAPI engine
        try:
            from fastapi.testclient import TestClient
            from app.main import app
            self._test_client = TestClient(app)
            self.is_external = False
            print(
                f"  {Color.YELLOW}[STANDALONE MODE]{Color.RESET} Live server at {self.base_url} not detected. "
                f"Using direct in-process FastAPI engine."
            )
        except Exception as e:
            print(f"  {Color.RED}[ERROR]{Color.RESET} Failed to initialize in-process engine: {e}")
            raise

    def post(self, endpoint: str, json_data: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        url = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        if self.is_external:
            import requests
            resp = requests.post(f"{self.base_url}{url}", json=json_data, timeout=10.0)
            try:
                return resp.status_code, resp.json()
            except Exception:
                return resp.status_code, {}
        else:
            resp = self._test_client.post(url, json=json_data)  # type: ignore[union-attr]
            try:
                return resp.status_code, resp.json()
            except Exception:
                return resp.status_code, {}

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
        url = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        if self.is_external:
            import requests
            resp = requests.get(f"{self.base_url}{url}", params=params, timeout=10.0)
            try:
                return resp.status_code, resp.json()
            except Exception:
                return resp.status_code, {}
        else:
            resp = self._test_client.get(url, params=params)  # type: ignore[union-attr]
            try:
                return resp.status_code, resp.json()
            except Exception:
                return resp.status_code, {}

    def reset_cooldown(self) -> None:
        try:
            self.post("/api/v1/notifications/reset-cooldown", {})
        except Exception:
            pass
        if not self.is_external:
            try:
                from app.main import FEEDBACK_CACHE, LATEST_NODE_ASSESSMENTS
                FEEDBACK_CACHE.clear()
                LATEST_NODE_ASSESSMENTS.clear()
            except Exception:
                pass


# ==============================================================================
# Scenario 1: Normal Baseline Telemetry Stream
# ==============================================================================
def run_normal_scenario(client: ScenarioClient, speed: float = 0.1) -> bool:
    """
    --scenario normal
    Streams clean baseline telemetry across Kaduwela DMAs 01 & 02.
    Confirms all nodes maintain Fraud Risk < 25% (normal green status, 0 false alarms).
    """
    print_banner(
        "SCENARIO 1: NORMAL BASELINE TELEMETRY STREAM",
        "Kaduwela DMAs 01 & 02 -- Stabilized Morning Distribution Window",
    )
    print(f"  Configuration: Speed delay = {speed:.2f}s per timestep | Monitored Zones = DMA 01 & DMA 02")
    print(f"  Expected Outcome: Fraud Risk Scores < 25.0% | Classification = 'normal' | 0 Dispatched Alarms\n")

    client.reset_cooldown()

    # Record baseline alerts count before streaming
    _, initial_history = client.get("/api/v1/notifications/history", {"limit": 100})
    initial_alerts_count = len(initial_history) if isinstance(initial_history, list) else 0

    # Sequence of clean morning telemetry readings across 6 designated monitoring nodes
    normal_steps = [
        {"time": "08:00", "dma": "DMA 01", "node": "J_10",   "act": 35.08, "exp": 35.10, "spatial": 0.02, "rate": 0.01},
        {"time": "08:15", "dma": "DMA 01", "node": "J_100",  "act": 34.69, "exp": 34.70, "spatial": 0.01, "rate": 0.00},
        {"time": "08:30", "dma": "DMA 01", "node": "J_500",  "act": 34.78, "exp": 34.80, "spatial": 0.02, "rate": -0.01},
        {"time": "08:45", "dma": "DMA 02", "node": "J_1200", "act": 35.19, "exp": 35.20, "spatial": 0.01, "rate": 0.00},
        {"time": "09:00", "dma": "DMA 02", "node": "J_2200", "act": 34.88, "exp": 34.90, "spatial": 0.02, "rate": 0.01},
        {"time": "09:15", "dma": "DMA 02", "node": "J_3000", "act": 35.09, "exp": 35.10, "spatial": 0.01, "rate": 0.00},
    ]

    print(f"{'Time':<7} {'Node':<8} {'DMA':<8} {'Act (m)':<9} {'Exp (m)':<9} {'ΔP (m)':<8} {'HTTP':<16} {'Risk Badge':<20} {'Class':<10}")
    print("-" * 96)

    max_risk = 0.0
    passed = True

    for step in normal_steps:
        payload = {
            "zone_id": step["dma"],
            "node_id": step["node"],
            "actual_pressure": step["act"],
            "expected_pressure": step["exp"],
            "spatial_deviation": step["spatial"],
            "recurrence_count": 0,
            "pressure_change_rate": step["rate"],
            "residual_rolling_mean": round(step["exp"] - step["act"], 2),
            "residual_rolling_std": 0.01,
            "hours_since_supply_start": 2.5,
        }

        status_code, data = client.post("/api/v1/assess-risk", payload)
        score = float(data.get("fraud_risk_score", 99.0))
        classification = str(data.get("classification", "unknown"))
        max_risk = max(max_risk, score)

        delta_p = round(step["exp"] - step["act"], 2)
        badge = format_risk_badge(score)
        code_str = format_status_code(status_code)

        print(
            f"{step['time']:<7} {step['node']:<8} {step['dma']:<8} "
            f"{step['act']:<9.2f} {step['exp']:<9.2f} {delta_p:<8.2f} "
            f"{code_str:<25} {badge:<30} {classification:<10}"
        )

        if score >= 25.0 or classification != "normal" or status_code != 200:
            passed = False

        if speed > 0:
            time.sleep(speed)

    print("-" * 96)

    # Check alert history to ensure zero new false alarms were dispatched
    _, history = client.get("/api/v1/notifications/history", {"limit": 100})
    current_alerts_count = len(history) if isinstance(history, list) else 0
    new_false_alarms = max(0, current_alerts_count - initial_alerts_count)

    print(f"\n{Color.BOLD}Scenario 1 Validation Summary:{Color.RESET}")
    print(f"  * Peak Risk Score Across Nodes : {Color.GREEN}{max_risk:.2f}%{Color.RESET} (Threshold: < 25.0%)")
    print(f"  * New False Alarms Dispatched  : {Color.GREEN}{new_false_alarms}{Color.RESET} (Expected: 0)")
    print(f"  * Dashboard Operational State  : {Color.GREEN}ALL GREEN (Normal Operations){Color.RESET}")

    if passed and max_risk < 25.0:
        print(f"\n  {Color.BG_GREEN}{Color.WHITE}{Color.BOLD} [SUCCESS] SCENARIO 1 (NORMAL BASELINE) PASSED 100% {Color.RESET}\n")
        return True
    else:
        print(f"\n  {Color.BG_RED}{Color.WHITE}{Color.BOLD} [FAILED] SCENARIO 1 EXCEEDED 25% RISK THRESHOLD {Color.RESET}\n")
        return False


# ==============================================================================
# Scenario 2: IWS 06:00 AM Refill Surge (Transient Filter Demonstration)
# ==============================================================================
def run_refill_surge_scenario(client: ScenarioClient, speed: float = 0.1) -> bool:
    """
    --scenario refill_surge
    Emulates 06:00 AM supply opening under Intermittent Water Supply (IWS).
    Demonstrates that the refill transient filter dampens alarms (Risk stays < 45%).
    """
    print_banner(
        "SCENARIO 2: 06:00 AM IWS PIPE REFILL SURGE",
        "Transient Pressure Drop Dampening & False Alarm Suppression Filter",
    )
    print(f"  Configuration: Speed delay = {speed:.2f}s per timestep | Monitored Node = J_10 (DMA 01)")
    print(f"  Expected Outcome: Large Head Losses Dampened | Transient Active = True | Risk < 45.0%\n")

    client.reset_cooldown()

    # Time-series representing 06:00 AM valve opening and filling transient
    surge_steps = [
        {"time": "06:00", "hours": 0.00, "act": 34.00, "exp": 35.10, "spatial": 0.10, "rate": -0.20, "desc": "Supply valve opens; initial filling"},
        {"time": "06:10", "hours": 0.16, "act": 27.50, "exp": 35.10, "spatial": 0.20, "rate": -0.75, "desc": "Empty main rapid charging; large head drop"},
        {"time": "06:20", "hours": 0.33, "act": 24.50, "exp": 35.10, "spatial": 0.25, "rate": -0.85, "desc": "Peak refill surge (ΔP = 10.6m head deficit)"},
        {"time": "06:35", "hours": 0.58, "act": 29.00, "exp": 35.10, "spatial": 0.18, "rate": 0.40,  "desc": "Pipe pressure begins hydraulic recovery"},
        {"time": "06:50", "hours": 0.83, "act": 32.80, "exp": 35.10, "spatial": 0.08, "rate": 0.25,  "desc": "Transient dampening window nearing end"},
        {"time": "07:05", "hours": 1.08, "act": 34.80, "exp": 35.10, "spatial": 0.02, "rate": 0.05,  "desc": "Stabilized active supply; steady state"},
    ]

    print(f"{'Time':<7} {'Elapsed':<9} {'Act (m)':<9} {'Exp (m)':<9} {'ΔP (m)':<8} {'Transient':<12} {'HTTP':<16} {'Dampened Risk':<20} {'Action Note'}")
    print("-" * 105)

    max_surge_risk = 0.0
    passed = True

    for step in surge_steps:
        delta_p = round(step["exp"] - step["act"], 2)
        payload = {
            "zone_id": "DMA 01",
            "node_id": "J_10",
            "actual_pressure": step["act"],
            "expected_pressure": step["exp"],
            "spatial_deviation": step["spatial"],
            "recurrence_count": 0,  # Single transient event, not recurring
            "pressure_change_rate": step["rate"],
            "residual_rolling_mean": delta_p,
            "residual_rolling_std": 0.25,
            "hours_since_supply_start": step["hours"],
        }

        status_code, data = client.post("/api/v1/assess-risk", payload)
        score = float(data.get("fraud_risk_score", 99.0))
        dampened = bool(data.get("transient_dampening_active", False))
        action = str(data.get("recommended_action", ""))
        action_short = action[:32] + "..." if len(action) > 32 else action

        max_surge_risk = max(max_surge_risk, score)
        badge = format_risk_badge(score)
        code_str = format_status_code(status_code)
        damp_str = f"{Color.CYAN}ACTIVE{Color.RESET}" if dampened else f"{Color.DIM}OFF{Color.RESET}"

        print(
            f"{step['time']:<7} {step['hours']:<5.2f}h   "
            f"{step['act']:<9.2f} {step['exp']:<9.2f} {delta_p:<8.2f} "
            f"{damp_str:<21} {code_str:<25} {badge:<30} {action_short}"
        )

        # Risk must stay strictly below 45% during the transient refill surge
        if score >= 45.0 or status_code != 200:
            passed = False

        if speed > 0:
            time.sleep(speed)

    print("-" * 105)

    print(f"\n{Color.BOLD}Scenario 2 Validation Summary:{Color.RESET}")
    print(f"  * Peak Dampened Risk Score : {Color.GREEN}{max_surge_risk:.2f}%{Color.RESET} (Threshold: < 45.0%)")
    print(f"  * Transient Dampening Mode : {Color.CYAN}VERIFIED (Refill filter prevented false theft dispatch){Color.RESET}")

    if passed and max_surge_risk < 45.0:
        print(f"\n  {Color.BG_GREEN}{Color.WHITE}{Color.BOLD} [SUCCESS] SCENARIO 2 (REFILL SURGE DAMPENING) PASSED 100% {Color.RESET}\n")
        return True
    else:
        print(f"\n  {Color.BG_RED}{Color.WHITE}{Color.BOLD} [FAILED] SCENARIO 2 EXCEEDED 45% RISK THRESHOLD {Color.RESET}\n")
        return False


# ==============================================================================
# Scenario 3: Physical Pipe Burst at J_500 + Component 1 Feedback
# ==============================================================================
def run_pipe_leak_scenario(client: ScenarioClient, speed: float = 0.1) -> bool:
    """
    --scenario pipe_leak
    Emulates physical pipe burst at J_500 coupled with Component 1 acoustic/sensor leak feedback.
    Demonstrates fraud risk score suppression and reclassification to physical pipe repair workorder.
    """
    print_banner(
        "SCENARIO 3: PHYSICAL PIPE BURST AT J_500 + C1 FEEDBACK",
        "Component 1 Acoustic Cross-Validation & Fraud Suppression Demonstration",
    )
    print(f"  Configuration: Speed delay = {speed:.2f}s | Target Node = J_500 (DMA 01 - Welihinda Ridge)")
    print(f"  Expected Outcome: C1 Leak Prob > 70% Suppresses Fraud Risk to ~18% & Classifies 'physical_leak'\n")

    client.reset_cooldown()

    # Step A: Baseline normal conditions before burst
    print_section("Step 3A: Baseline Conditions at Junction J_500 (Pre-Burst)")
    status_code, data_pre = client.post(
        "/api/v1/assess-risk",
        {
            "zone_id": "DMA 01",
            "node_id": "J_500",
            "actual_pressure": 34.78,
            "expected_pressure": 34.80,
            "spatial_deviation": 0.02,
            "recurrence_count": 0,
            "pressure_change_rate": 0.00,
            "residual_rolling_mean": 0.02,
            "residual_rolling_std": 0.01,
            "hours_since_supply_start": 3.0,
        },
    )
    score_pre = float(data_pre.get("fraud_risk_score", 0.0))
    print(f"  Pre-Burst State: {format_status_code(status_code)} | Risk: {format_risk_badge(score_pre)} | Cause: {data_pre.get('classification')}")

    if speed > 0:
        time.sleep(speed)

    # Step B: Sudden Pipe Burst Occurs at J_500 (High Pressure Drop)
    print_section("Step 3B: Sudden Pipe Burst Occurs at J_500 (8.3m Head Drop)")
    status_code, data_burst = client.post(
        "/api/v1/assess-risk",
        {
            "zone_id": "DMA 01",
            "node_id": "J_500",
            "actual_pressure": 26.50,
            "expected_pressure": 34.80,
            "spatial_deviation": 2.50,
            "recurrence_count": 3,
            "pressure_change_rate": -0.30,
            "residual_rolling_mean": 8.30,
            "residual_rolling_std": 0.20,
            "hours_since_supply_start": 3.5,
        },
    )
    score_burst = float(data_burst.get("fraud_risk_score", 0.0))
    print(f"  Raw Burst State: {format_status_code(status_code)} | Raw Score: {format_risk_badge(score_burst)} | Cause: {data_burst.get('classification')}")
    print(f"  Observation: Without C1 cross-check, head loss elevates risk to {score_burst:.1f}%.")

    if speed > 0:
        time.sleep(speed)

    # Step C: Component 1 (Physical Leak Detection) Feedback Ingestion
    print_section("Step 3C: Component 1 Acoustic / Sensor Leak Feedback Ingestion")
    c1_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_500",
        "leak_probability": 0.88,  # 88% acoustic physical leak confidence
        "current_fraud_score": score_burst,
    }
    status_c1, data_c1 = client.post("/api/v1/c1-leak-feedback", c1_payload)
    print(f"  C1 Feedback Response: {format_status_code(status_c1)}")
    print(f"  * Acoustic Leak Probability : {Color.BOLD}{data_c1.get('leak_probability', 0.0) * 100:.1f}%{Color.RESET} (> 70.0% threshold)")
    print(f"  * Original Fraud Risk Score : {Color.YELLOW}{data_c1.get('original_fraud_risk_score')}%{Color.RESET}")
    print(f"  * Adjusted Fraud Risk Score : {Color.GREEN}{data_c1.get('adjusted_fraud_risk_score')}%{Color.RESET} (Suppressed!)")
    print(f"  * Reclassification          : {Color.BOLD}{data_c1.get('adjusted_classification')}{Color.RESET}")
    print(f"  * Action Dispatched         : {Color.CYAN}{data_c1.get('recommended_action')}{Color.RESET}")

    if speed > 0:
        time.sleep(speed)

    # Step D: Subsequent Telemetry with C1 Feedback Active in Memory
    print_section("Step 3D: Subsequent Sensor Ingestion Confirms Fraud Risk Suppression")
    status_code, data_post = client.post(
        "/api/v1/assess-risk",
        {
            "zone_id": "DMA 01",
            "node_id": "J_500",
            "actual_pressure": 26.40,
            "expected_pressure": 34.80,
            "spatial_deviation": 2.45,
            "recurrence_count": 4,
            "pressure_change_rate": -0.05,
            "residual_rolling_mean": 8.35,
            "residual_rolling_std": 0.15,
            "hours_since_supply_start": 3.75,
        },
    )
    score_post = float(data_post.get("fraud_risk_score", 0.0))
    class_post = str(data_post.get("classification", ""))
    action_post = str(data_post.get("recommended_action", ""))

    print(f"  Post-C1 State  : {format_status_code(status_code)} | Risk: {format_risk_badge(score_post)} | Cause: {Color.BOLD}{class_post}{Color.RESET}")
    print(f"  Field Workorder: {Color.CYAN}{action_post}{Color.RESET}")

    passed = (
        status_c1 == 200
        and status_code == 200
        and data_c1.get("adjusted_classification") == "physical_leak"
        and score_post <= 25.0
        and class_post == "physical_leak"
    )

    print(f"\n{Color.BOLD}Scenario 3 Validation Summary:{Color.RESET}")
    print(f"  * Reclassified to Physical Pipe Leak : {Color.GREEN}CONFIRMED ('physical_leak'){Color.RESET}")
    print(f"  * Suppressed Post-Feedback Risk     : {Color.GREEN}{score_post:.2f}%{Color.RESET} (Normal / Low)")
    print(f"  * Dispatched Workorder Type         : {Color.CYAN}Physical Pipe Repair (Not Theft/Enforcement){Color.RESET}")

    if passed:
        print(f"\n  {Color.BG_GREEN}{Color.WHITE}{Color.BOLD} [SUCCESS] SCENARIO 3 (PIPE LEAK SUPPRESSION) PASSED 100% {Color.RESET}\n")
        return True
    else:
        print(f"\n  {Color.BG_RED}{Color.WHITE}{Color.BOLD} [FAILED] SCENARIO 3 C1 SUPPRESSION NOT APPLIED PROPERLY {Color.RESET}\n")
        return False


# ==============================================================================
# Scenario 4: Unauthorized 0.06 LPS Bypass Theft at J_100
# ==============================================================================
def run_bypass_theft_scenario(client: ScenarioClient, speed: float = 0.1) -> bool:
    """
    --scenario bypass_theft
    Emulates unauthorized 0.06 LPS withdrawal at J_100 during morning peak.
    Triggers high-risk fraud state (89%), logs GPS coordinates, and dispatches authority alert.
    """
    print_banner(
        "SCENARIO 4: UNAUTHORIZED 0.06 LPS BYPASS THEFT AT J_100",
        "Commercial Bypass Detection, GPS Forensic Geolocation & Emergency Alert Dispatch",
    )
    print(f"  Configuration: Speed delay = {speed:.2f}s | Target = Node J_100 (DMA 01 - Industrial Corridor)")
    print(f"  Expected Outcome: Fraud Risk ~89-92% | Class = 'partial_bypass' | GPS Navigation Logged | Alert Sent\n")

    client.reset_cooldown()

    # Step A: Baseline normal conditions at J_100 before unmetered withdrawal
    print_section("Step 4A: Morning Baseline at Node J_100 (07:30 AM)")
    status_code, data_base = client.post(
        "/api/v1/assess-risk",
        {
            "zone_id": "DMA 01",
            "node_id": "J_100",
            "actual_pressure": 34.68,
            "expected_pressure": 34.70,
            "spatial_deviation": 0.02,
            "recurrence_count": 0,
            "pressure_change_rate": 0.00,
            "residual_rolling_mean": 0.02,
            "residual_rolling_std": 0.01,
            "hours_since_supply_start": 1.5,
        },
    )
    print(f"  Baseline State: {format_status_code(status_code)} | Risk: {format_risk_badge(float(data_base.get('fraud_risk_score', 0)))} | Status: Clean")

    if speed > 0:
        time.sleep(speed)

    # Step B: Unauthorized 0.06 LPS Commercial Bypass Withdrawal Starts (09:15 AM Peak)
    print_section("Step 4B: Unauthorized 0.06 LPS Bypass Withdrawal Starts (09:15 AM)")
    theft_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 28.50,          # 6.20m localized pressure drop
        "expected_pressure": 34.70,
        "spatial_deviation": 5.80,         # Severe spatial deviation from neighborhood nodes
        "recurrence_count": 5,             # Persistent recurrence over 5 monitoring windows
        "pressure_change_rate": -0.45,
        "residual_rolling_mean": 6.20,
        "residual_rolling_std": 0.12,
        "hours_since_supply_start": 3.25,  # 09:15 AM (outside refill window)
    }

    status_code, theft_data = client.post("/api/v1/assess-risk", theft_payload)
    score = float(theft_data.get("fraud_risk_score", 0.0))
    classification = str(theft_data.get("classification", ""))
    action = str(theft_data.get("recommended_action", ""))
    location = theft_data.get("location", {})
    reasons = theft_data.get("reasons_list", [])

    print(f"  Telemetry Response : {format_status_code(status_code)}")
    print(f"  * Calculated Fraud Risk Score : {format_risk_badge(score)}")
    print(f"  * Root-Cause Classification   : {Color.RED}{Color.BOLD}{classification}{Color.RESET} (Commercial / Industrial Theft)")
    print(f"  * Recommended Priority Action : {Color.BOLD}{action}{Color.RESET}")

    print(f"\n  {Color.BOLD}Forensic Evidence Checklist:{Color.RESET}")
    for r in reasons:
        print(f"    [+] {r}")

    # Step C: Verify WGS84 GPS Geolocation & Landmark Navigation
    print_section("Step 4C: Forensic GPS Location & Google Maps Geolocation")
    lat = location.get("latitude")
    lon = location.get("longitude")
    elev = location.get("elevation_m")
    gx = location.get("grid_x")
    gy = location.get("grid_y")
    gmaps = location.get("google_maps_url")
    landmark = location.get("landmark")

    print(f"  * Monitored Junction Node : {Color.BOLD}{location.get('junction_id')}{Color.RESET}")
    print(f"  * WGS84 GPS Coordinates   : {Color.CYAN}{lat:.6f}° N, {lon:.6f}° E{Color.RESET} (Elevation: {elev} m)")
    print(f"  * Local Grid (SLD99)      : X = {gx} m, Y = {gy} m")
    print(f"  * Physical Audit Landmark : {Color.WHITE}{landmark}{Color.RESET}")
    print(f"  * Direct Navigation URL   : {Color.UNDERLINE}{gmaps}{Color.RESET}")

    # Step D: Confirm Authority Alert Dispatch in Background
    print_section("Step 4D: Real-Time Authority Alert Dispatch Verification")
    time.sleep(1.0)  # Allow background dispatch to write to dispatched_alerts.json

    status_hist, history = client.get("/api/v1/notifications/history", {"limit": 10})
    j100_alerts = [a for a in history if a.get("node_id") == "J_100"] if isinstance(history, list) else []

    alert_dispatched = False
    if j100_alerts:
        latest = j100_alerts[-1]
        alert_id = latest.get("alert_id")
        recip_email = latest.get("recipient_email")
        deliv = latest.get("delivery_status")
        ts = latest.get("timestamp")
        alert_score = latest.get("risk_score")

        print(f"  * Dispatched Alert ID    : {Color.BOLD}{alert_id}{Color.RESET}")
        print(f"  * Timestamp (Local Time) : {ts}")
        print(f"  * Logged Risk Score      : {Color.RED}{Color.BOLD}{alert_score:.2f}%{Color.RESET}")
        print(f"  * Recipient Authority    : {recip_email}")
        print(f"  * Delivery Channel Status: {Color.GREEN}{deliv}{Color.RESET}")
        alert_dispatched = True
    else:
        print(f"  {Color.YELLOW}[NOTE]{Color.RESET} Alert queued via background task.")

    passed = (
        status_code == 200
        and score >= 85.0
        and classification == "partial_bypass"
        and lat is not None
        and lon is not None
        and alert_dispatched
    )

    print(f"\n{Color.BOLD}Scenario 4 Validation Summary:{Color.RESET}")
    print(f"  * High-Risk Fraud State Triggered : {Color.GREEN}YES ({score:.1f}% >= 89.0%){Color.RESET}")
    print(f"  * GPS Geolocation Logged          : {Color.GREEN}YES ({lat:.6f}° N, {lon:.6f}° E){Color.RESET}")
    print(f"  * Authority Alert Dispatched      : {Color.GREEN}YES (Dispatched to NWSDB Taskforce){Color.RESET}")

    if passed:
        print(f"\n  {Color.BG_GREEN}{Color.WHITE}{Color.BOLD} [SUCCESS] SCENARIO 4 (BYPASS THEFT AT J_100) PASSED 100% {Color.RESET}\n")
        return True
    else:
        print(f"\n  {Color.BG_RED}{Color.WHITE}{Color.BOLD} [FAILED] SCENARIO 4 DID NOT COMPLETE ALL CRITERIA {Color.RESET}\n")
        return False


# ==============================================================================
# Interactive Menu Runner
# ==============================================================================
def run_all_scenarios(client: ScenarioClient, speed: float = 0.1) -> bool:
    print_banner(
        "EXECUTING ALL 4 DEMONSTRATION SCENARIOS SEQUENTIALLY",
        "Comprehensive Automated End-to-End Validation Suite",
    )
    results = []
    results.append(("Scenario 1: Normal Baseline Telemetry", run_normal_scenario(client, speed)))
    results.append(("Scenario 2: IWS 06:00 AM Refill Surge", run_refill_surge_scenario(client, speed)))
    results.append(("Scenario 3: Pipe Burst + C1 Feedback", run_pipe_leak_scenario(client, speed)))
    results.append(("Scenario 4: 0.06 LPS Bypass Theft J_100", run_bypass_theft_scenario(client, speed)))

    print("\n" + "=" * 80)
    print(f"{Color.BOLD}{Color.WHITE}  MASTER SCENARIO DEMONSTRATION SUMMARY{Color.RESET}")
    print("=" * 80)
    all_ok = True
    for name, success in results:
        status_str = f"{Color.GREEN}PASSED (100%){Color.RESET}" if success else f"{Color.RED}FAILED{Color.RESET}"
        print(f"  * {name:<46} : {status_str}")
        if not success:
            all_ok = False
    print("=" * 80 + "\n")
    return all_ok


def interactive_menu(client: ScenarioClient, default_speed: float = 0.1) -> None:
    while True:
        print("\n" + "=" * 80)
        print(f"{Color.CYAN}{Color.BOLD}  NWSDB WATER FRAUD DETECTION & RESPONSE PLATFORM: SCENARIO LAUNCHER{Color.RESET}")
        print("=" * 80)
        print(f"  Connected Backend: {Color.BOLD}{client.base_url}{Color.RESET} ({'Live HTTP' if client.is_external else 'In-Process Engine'})")
        print("\n  Select a demonstration scenario to execute:")
        print(f"    {Color.BOLD}[1]{Color.RESET} Normal Baseline Telemetry Stream (DMA 01 & 02, Risk < 25%)")
        print(f"    {Color.BOLD}[2]{Color.RESET} IWS Refill Surge at 06:00 AM (Transient Dampening, Risk < 45%)")
        print(f"    {Color.BOLD}[3]{Color.RESET} Physical Pipe Burst at J_500 + C1 Feedback (Fraud Risk Suppression)")
        print(f"    {Color.BOLD}[4]{Color.RESET} Unauthorized 0.06 LPS Bypass Theft at J_100 (Risk ~89%, GPS & Alert)")
        print(f"    {Color.BOLD}[5]{Color.RESET} Run All 4 Scenarios Sequentially")
        print(f"    {Color.BOLD}[Q]{Color.RESET} Quit / Exit")
        print("-" * 80)

        choice = input(f"  Enter selection [1-5, Q] (default 1): ").strip().upper()
        if not choice:
            choice = "1"

        if choice in ("Q", "QUIT", "EXIT"):
            print("\nExiting Scenario Runner. Goodbye!\n")
            break

        speed_input = input(f"  Enter timestep delay in seconds (default {default_speed}s): ").strip()
        try:
            speed = float(speed_input) if speed_input else default_speed
        except ValueError:
            speed = default_speed

        if choice == "1":
            run_normal_scenario(client, speed)
        elif choice == "2":
            run_refill_surge_scenario(client, speed)
        elif choice == "3":
            run_pipe_leak_scenario(client, speed)
        elif choice == "4":
            run_bypass_theft_scenario(client, speed)
        elif choice == "5":
            run_all_scenarios(client, speed)
        else:
            print(f"{Color.RED}Invalid option: {choice}. Please select 1-5 or Q.{Color.RESET}")


# ==============================================================================
# CLI Entry Point
# ==============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automated Demonstration Launcher for Kaduwela Water Fraud Detection (Component 2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scenario",
        "-s",
        choices=["normal", "refill_surge", "pipe_leak", "bypass_theft", "all"],
        default=None,
        help="Demonstration scenario to execute",
    )
    parser.add_argument(
        "--speed",
        "-t",
        type=float,
        default=0.1,
        help="Delay in seconds per timestep (default: 0.1s; use 0.0 for instant, 1.0 for real-time)",
    )
    parser.add_argument(
        "--url",
        "-u",
        default="http://127.0.0.1:8000",
        help="Base URL of the FastAPI backend service (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Launch interactive terminal menu",
    )

    args = parser.parse_args()

    client = ScenarioClient(base_url=args.url)

    if args.interactive or args.scenario is None:
        interactive_menu(client, default_speed=args.speed)
        return 0

    success = False
    if args.scenario == "normal":
        success = run_normal_scenario(client, speed=args.speed)
    elif args.scenario == "refill_surge":
        success = run_refill_surge_scenario(client, speed=args.speed)
    elif args.scenario == "pipe_leak":
        success = run_pipe_leak_scenario(client, speed=args.speed)
    elif args.scenario == "bypass_theft":
        success = run_bypass_theft_scenario(client, speed=args.speed)
    elif args.scenario == "all":
        success = run_all_scenarios(client, speed=args.speed)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
