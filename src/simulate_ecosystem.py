"""
src/simulate_ecosystem.py
Multi-Component Cross-Talk Demonstration Script for Kaduwela Water Fraud Detection (Component 2).

Demonstrates live bi-directional and multi-component cross-talk via real HTTP API calls
to the running FastAPI service (http://127.0.0.1:8000):

Scenarios:
1. Scenario 1: Clean refill cycle in DMA 01 (C2 confirms normal, risk < 20%).
2. Scenario 2: Pipe break event: injects pressure drop at J_100, calls POST /api/v1/c1-leak-feedback
   with leak_probability: 0.85, and verifies that C2 suppresses fraud risk down to 18%.
3. Scenario 3: Theft event: pressure drops at J_100 with C1 reporting zero leak; C2 raises fraud
   score to 89%, dispatches an alert, and calls GET /api/v1/c3-water-loss/DMA_01 to show C3
   deducting 0.08 LPS from water security storage.
4. Scenario 4: Shared depressurization event: severe drop triggers C2 theft analysis while querying
   GET /api/v1/c4-pressure-drop-events to show C4 opening a microbial intrusion hazard window.

Features:
- Interactive terminal menu or non-interactive CLI flags (--scenario, --all).
- Pretty-printed, syntax-highlighted color-coded JSON payloads.
- Automated verification assertions for each component interaction.
"""

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests

# Enable ANSI terminal colors on Windows
try:
    import colorama
    colorama.init(autoreset=True)
except ImportError:
    pass

# ==============================================================================
# Configuration & Colors
# ==============================================================================

DEFAULT_API_BASE_URL = os.environ.get("C2_API_URL", "http://127.0.0.1:8000")

class Colors:
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

    # Component Badges
    BG_C1 = "\033[44m\033[97m\033[1m"    # Blue
    BG_C2 = "\033[46m\033[30m\033[1m"    # Cyan
    BG_C3 = "\033[43m\033[30m\033[1m"    # Yellow/Amber
    BG_C4 = "\033[41m\033[97m\033[1m"    # Red
    BG_PASS = "\033[42m\033[30m\033[1m"  # Green
    BG_FAIL = "\033[41m\033[97m\033[1m"  # Red


def colorize_json(data: Any) -> str:
    """
    Formats a dictionary or object as syntax-highlighted ANSI color JSON.
    """
    raw_str = json.dumps(data, indent=2)
    lines = []
    for line in raw_str.split("\n"):
        # Highlight keys
        line = re.sub(r'\"([a-zA-Z0-9_\-]+)\":', f'{Colors.CYAN}"\\1"{Colors.RESET}:', line)
        # Highlight string values
        line = re.sub(r': \"([^\"]*)\"', f': {Colors.GREEN}"\\1"{Colors.RESET}', line)
        # Highlight numeric values
        line = re.sub(r': (-?\d+\.?\d*)', f': {Colors.YELLOW}\\1{Colors.RESET}', line)
        # Highlight booleans & null
        line = re.sub(r': (true|false|null)', f': {Colors.MAGENTA}\\1{Colors.RESET}', line)
        lines.append(line)
    return "\n".join(lines)


def print_banner():
    """
    Renders top-level system banner.
    """
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.WHITE}   NWSDB WATERGUARD (COMPONENT 2) -- MULTI-COMPONENT ECOSYSTEM SIMULATOR{Colors.RESET}")
    print(f"{Colors.DIM}   Live Cross-Talk: C1 (Leaks) <-> C2 (Fraud) <-> C3 (Storage) <-> C4 (Intrusion){Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}")


def check_api_health(base_url: str) -> bool:
    """
    Verifies that the FastAPI backend server is alive and reachable.
    """
    try:
        resp = requests.get(f"{base_url}/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def print_http_call(
    method: str,
    url: str,
    component: str,
    req_body: Optional[Dict] = None,
    resp_body: Optional[Dict] = None,
    status_code: int = 200,
    latency_ms: float = 0.0,
):
    """
    Displays a formatted HTTP request/response exchange.
    """
    status_color = Colors.GREEN if 200 <= status_code < 300 else Colors.RED
    badge = f"{Colors.BG_C2} C2 API {Colors.RESET}"
    if component == "C1":
        badge = f"{Colors.BG_C1} C1 LEAK DETECTION {Colors.RESET}"
    elif component == "C3":
        badge = f"{Colors.BG_C3} C3 STORAGE FORECAST {Colors.RESET}"
    elif component == "C4":
        badge = f"{Colors.BG_C4} C4 INTRUSION HAZARD {Colors.RESET}"

    print(f"\n{Colors.DIM}{'-' * 80}{Colors.RESET}")
    print(f" {badge}  {Colors.BOLD}{method} {url}{Colors.RESET}")
    print(f" Status: {status_color}{status_code} OK{Colors.RESET}  |  Latency: {Colors.YELLOW}{latency_ms:.1f}ms{Colors.RESET}")

    if req_body is not None:
        print(f"\n {Colors.BOLD}{Colors.CYAN}[>] Outgoing Request Payload:{Colors.RESET}")
        print(colorize_json(req_body))

    if resp_body is not None:
        print(f"\n {Colors.BOLD}{Colors.GREEN}[<] Incoming Response Payload:{Colors.RESET}")
        print(colorize_json(resp_body))
    print(f"{Colors.DIM}{'-' * 80}{Colors.RESET}")


def print_verdict(scenario_num: int, title: str, passed: bool, notes: List[str]):
    """
    Prints a clear pass/fail status box with highlighted verification checklist.
    """
    badge = f"{Colors.BG_PASS} VERIFIED [OK] {Colors.RESET}" if passed else f"{Colors.BG_FAIL} FAILED [X] {Colors.RESET}"
    print(f"\n{Colors.BOLD}Scenario {scenario_num} Result:{Colors.RESET} {badge} {Colors.BOLD}{title}{Colors.RESET}")
    for n in notes:
        prefix = f"{Colors.GREEN}[OK]{Colors.RESET}" if passed else f"{Colors.RED}[X]{Colors.RESET}"
        print(f"   {prefix} {n}")
    print()


# ==============================================================================
# Scenario 1: Clean Refill Cycle in DMA 01
# ==============================================================================

def run_scenario_1(base_url: str = DEFAULT_API_BASE_URL) -> bool:
    """
    Scenario 1: Clean refill cycle in DMA 01 (C2 confirms normal, risk < 20%).
    
    Narrative:
    The intermittent water supply (IWS) morning refill window opens at 06:00 in DMA 01.
    Water rushes through empty pipelines to refill local distribution mains, causing a
    temporary hydraulic head drop and transient pressure surge. C2 evaluates telemetry
    at node J_10 at t = 30 minutes into the supply opening. The pipe-filling refill transient
    dampening rule suppresses false theft alarms, keeping the calculated fraud risk < 20%.
    """
    print(f"\n{Colors.BOLD}{Colors.CYAN}+==============================================================================+{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}| SCENARIO 1: Clean Refill Cycle in DMA 01 (C2 Confirms Normal, Risk < 20%)    |{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}+==============================================================================+{Colors.RESET}")
    print(f"{Colors.DIM}Context: Supply opening refill transient at 06:30 (elapsed = 0.50h). Empty pipe filling.{Colors.RESET}")

    payload = {
        "zone_id": "DMA 01",
        "node_id": "J_10",
        "actual_pressure": 34.5,
        "expected_pressure": 34.7,
        "spatial_deviation": 0.1,
        "recurrence_count": 0,
        "hours_since_supply_start": 0.5,
        "pressure_change_rate": 0.0,
        "residual_rolling_mean": 0.2,
        "residual_rolling_std": 0.05,
    }

    t0 = time.time()
    try:
        resp = requests.post(f"{base_url}/api/v1/assess-risk", json=payload, timeout=5.0)
        latency = (time.time() - t0) * 1000.0
        data = resp.json()
    except Exception as e:
        print(f"{Colors.RED}API Call failed: {e}{Colors.RESET}")
        return False

    print_http_call(
        method="POST",
        url=f"{base_url}/api/v1/assess-risk",
        component="C2",
        req_body=payload,
        resp_body=data,
        status_code=resp.status_code,
        latency_ms=latency,
    )

    risk_score = float(data.get("fraud_risk_score", 100.0))
    classification = str(data.get("classification", ""))
    is_transient = bool(data.get("transient_dampening_active", False))

    passed = (risk_score < 20.0) and (classification == "normal") and is_transient
    print_verdict(
        scenario_num=1,
        title="Clean Refill Cycle Suppresses False Theft Alarms",
        passed=passed,
        notes=[
            f"Calculated Fraud Risk: {Colors.BOLD}{risk_score:.2f}%{Colors.RESET} (Expected < 20.0%).",
            f"Event Classification: '{Colors.BOLD}{classification}{Colors.RESET}' (Expected 'normal').",
            f"IWS Refill Transient Dampening Active: {Colors.BOLD}{is_transient}{Colors.RESET}.",
            f"Recommended Action: {Colors.DIM}{data.get('recommended_action')}{Colors.RESET}",
        ],
    )
    return passed


# ==============================================================================
# Scenario 2: Pipe Break Event (C1 Feedback Suppresses Fraud Risk to 18%)
# ==============================================================================

def run_scenario_2(base_url: str = DEFAULT_API_BASE_URL) -> bool:
    """
    Scenario 2: Pipe break event: injects pressure drop at J_100, calls POST /api/v1/c1-leak-feedback
    with leak_probability: 0.85, and verifies that C2 suppresses fraud risk down to 18%.
    
    Narrative:
    A physical pipe burst / fracture occurs near node J_100, causing a sharp hydraulic pressure
    drop (25.0m vs 34.7m). Without cross-component intelligence, C2 might initially mistake this
    for a high-volume theft bypass. Component 1 (Physical Leak Detection) performs acoustic and
    transient correlator cross-validation, confirming a leak probability of 85.0%.
    Component 1 invokes POST /api/v1/c1-leak-feedback. C2 absorbs this signal, suppresses the fraud
    risk down to 18%, reclassifies the incident as 'physical_leak', and routes it to repair technicians.
    """
    print(f"\n{Colors.BOLD}{Colors.CYAN}+==============================================================================+{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}| SCENARIO 2: Pipe Break Event (C1 Feedback Suppresses Fraud Risk to 18%)       |{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}+==============================================================================+{Colors.RESET}")
    print(f"{Colors.DIM}Step 1: Inject severe pressure drop at J_100 (Unadjusted initial anomaly).{Colors.RESET}")

    # Step 1: Telemetry injection
    step1_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 25.0,
        "expected_pressure": 34.7,
        "spatial_deviation": 3.8,
        "recurrence_count": 0,
        "hours_since_supply_start": 2.0,
        "pressure_change_rate": -3.5,
        "residual_rolling_mean": 9.7,
        "residual_rolling_std": 1.2,
    }

    t0 = time.time()
    try:
        resp1 = requests.post(f"{base_url}/api/v1/assess-risk", json=step1_payload, timeout=5.0)
        latency1 = (time.time() - t0) * 1000.0
        data1 = resp1.json()
    except Exception as e:
        print(f"{Colors.RED}Step 1 API Call failed: {e}{Colors.RESET}")
        return False

    print_http_call(
        method="POST",
        url=f"{base_url}/api/v1/assess-risk",
        component="C2",
        req_body=step1_payload,
        resp_body=data1,
        status_code=resp1.status_code,
        latency_ms=latency1,
    )
    initial_score = float(data1.get("fraud_risk_score", 0.0))
    print(f" {Colors.YELLOW}[!] Initial unvalidated C2 alert: Score = {initial_score:.1f}% ({data1.get('classification')}){Colors.RESET}")

    # Step 2: Component 1 acoustic leak confirmation
    print(f"\n{Colors.DIM}Step 2: Component 1 cross-talk injection: POST /api/v1/c1-leak-feedback (leak_probability: 0.85).{Colors.RESET}")
    c1_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "leak_probability": 0.85,
    }

    t1 = time.time()
    try:
        resp2 = requests.post(f"{base_url}/api/v1/c1-leak-feedback", json=c1_payload, timeout=5.0)
        latency2 = (time.time() - t1) * 1000.0
        data2 = resp2.json()
    except Exception as e:
        print(f"{Colors.RED}Step 2 API Call failed: {e}{Colors.RESET}")
        return False

    print_http_call(
        method="POST",
        url=f"{base_url}/api/v1/c1-leak-feedback",
        component="C1",
        req_body=c1_payload,
        resp_body=data2,
        status_code=resp2.status_code,
        latency_ms=latency2,
    )

    # Step 3: Re-query C2 risk assessment to verify suppressed state
    print(f"\n{Colors.DIM}Step 3: Verify C2 now evaluates node J_100 with suppressed risk score (<= 18.0%).{Colors.RESET}")
    t2 = time.time()
    try:
        resp3 = requests.post(f"{base_url}/api/v1/assess-risk", json=step1_payload, timeout=5.0)
        latency3 = (time.time() - t2) * 1000.0
        data3 = resp3.json()
    except Exception as e:
        print(f"{Colors.RED}Step 3 API Call failed: {e}{Colors.RESET}")
        return False

    print_http_call(
        method="POST",
        url=f"{base_url}/api/v1/assess-risk",
        component="C2",
        req_body=step1_payload,
        resp_body=data3,
        status_code=resp3.status_code,
        latency_ms=latency3,
    )

    adj_feedback_score = float(data2.get("adjusted_fraud_risk_score", 100.0))
    feedback_applied = bool(data2.get("leak_feedback_applied", False))
    reclassified_cause = str(data2.get("adjusted_classification", ""))
    subsequent_score = float(data3.get("fraud_risk_score", 100.0))

    passed = (
        feedback_applied
        and (adj_feedback_score <= 18.0)
        and (reclassified_cause == "physical_leak")
        and (subsequent_score <= 18.0)
    )

    print_verdict(
        scenario_num=2,
        title="Component 1 Leak Cross-Validation Suppresses Theft Risk",
        passed=passed,
        notes=[
            f"Component 1 Acoustic Leak Probability: {Colors.BOLD}{c1_payload['leak_probability']*100:.1f}%{Colors.RESET}.",
            f"C1 Feedback Response Adjusted Score: {Colors.BOLD}{adj_feedback_score:.2f}%{Colors.RESET} (Target: 18.0%).",
            f"Event Reclassification: '{Colors.BOLD}{reclassified_cause}{Colors.RESET}' (Expected 'physical_leak').",
            f"Subsequent Telemetry Score: {Colors.BOLD}{subsequent_score:.2f}%{Colors.RESET} (Suppressed down to 18%).",
            f"Workorder Dispatch: {Colors.DIM}{data2.get('recommended_action')}{Colors.RESET}",
        ],
    )
    return passed


# ==============================================================================
# Scenario 3: Unauthorized Theft Event (C1 Zero Leak -> C2 89% -> C3 0.08 LPS)
# ==============================================================================

def run_scenario_3(base_url: str = DEFAULT_API_BASE_URL) -> bool:
    """
    Scenario 3: Theft event: pressure drops at J_100 with C1 reporting zero leak; C2 raises fraud
    score to 89%, dispatches an alert, and calls GET /api/v1/c3-water-loss/DMA_01 to show C3
    deducting 0.08 LPS from water security storage.
    
    Narrative:
    An illicit commercial facility activates a high-volume partial bypass tap at node J_100 in DMA 01.
    Sustained pressure drop is observed across multiple consecutive days (recurrence = 5).
    Component 1 acoustic cross-check reports zero physical leak (leak_prob = 0.0).
    C2 affirms an authentic unauthorized withdrawal, raises the fraud risk to ~89%, and dispatches
    a high-priority alert. Component 3 (Storage Forecasting Engine) queries GET /api/v1/c3-water-loss/DMA_01
    and deducts 0.08 LPS (0.288 m3/hr, 6.91 m3/day) from the distribution tank water balance inventory.
    """
    print(f"\n{Colors.BOLD}{Colors.CYAN}+==============================================================================+{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}| SCENARIO 3: Theft Event (C1 Zero Leak -> C2 Risk 89% -> C3 Deducts 0.08 LPS)   |{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}+==============================================================================+{Colors.RESET}")
    print(f"{Colors.DIM}Step 1: Component 1 acoustic cross-check returns 0.0% physical leak probability.{Colors.RESET}")

    # Step 1: C1 confirms zero leak (resets any previous leak overrides)
    c1_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "leak_probability": 0.0,
        "current_fraud_score": 88.6,
    }

    t0 = time.time()
    try:
        resp_c1 = requests.post(f"{base_url}/api/v1/c1-leak-feedback", json=c1_payload, timeout=5.0)
        latency_c1 = (time.time() - t0) * 1000.0
        data_c1 = resp_c1.json()
    except Exception as e:
        print(f"{Colors.RED}Step 1 C1 API Call failed: {e}{Colors.RESET}")
        return False

    print_http_call(
        method="POST",
        url=f"{base_url}/api/v1/c1-leak-feedback",
        component="C1",
        req_body=c1_payload,
        resp_body=data_c1,
        status_code=resp_c1.status_code,
        latency_ms=latency_c1,
    )

    # Step 2: C2 Telemetry assessment for persistent recurring bypass
    print(f"\n{Colors.DIM}Step 2: C2 analyzes sustained head drop (recurrence = 5, residual = 6.0m).{Colors.RESET}")
    theft_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 15.2,
        "expected_pressure": 21.2,
        "spatial_deviation": 5.8,
        "recurrence_count": 5,
        "hours_since_supply_start": 2.5,
        "pressure_change_rate": -0.2,
        "residual_rolling_mean": 6.0,
        "residual_rolling_std": 0.3,
    }

    t1 = time.time()
    try:
        resp_c2 = requests.post(f"{base_url}/api/v1/assess-risk", json=theft_payload, timeout=5.0)
        latency_c2 = (time.time() - t1) * 1000.0
        data_c2 = resp_c2.json()
    except Exception as e:
        print(f"{Colors.RED}Step 2 C2 API Call failed: {e}{Colors.RESET}")
        return False

    print_http_call(
        method="POST",
        url=f"{base_url}/api/v1/assess-risk",
        component="C2",
        req_body=theft_payload,
        resp_body=data_c2,
        status_code=resp_c2.status_code,
        latency_ms=latency_c2,
    )

    # Step 3: Query Component 3 Water Loss Forecast
    print(f"\n{Colors.DIM}Step 3: Component 3 queries GET /api/v1/c3-water-loss/DMA_01 for storage penalty.{Colors.RESET}")
    t2 = time.time()
    try:
        resp_c3 = requests.get(f"{base_url}/api/v1/c3-water-loss/DMA_01", timeout=5.0)
        latency_c3 = (time.time() - t2) * 1000.0
        data_c3 = resp_c3.json()
    except Exception as e:
        print(f"{Colors.RED}Step 3 C3 API Call failed: {e}{Colors.RESET}")
        return False

    print_http_call(
        method="GET",
        url=f"{base_url}/api/v1/c3-water-loss/DMA_01",
        component="C3",
        req_body=None,
        resp_body=data_c3,
        status_code=resp_c3.status_code,
        latency_ms=latency_c3,
    )

    c2_risk_score = float(data_c2.get("fraud_risk_score", 0.0))
    c2_classification = str(data_c2.get("classification", ""))
    c3_loss_lps = float(data_c3.get("estimated_unmetered_water_loss_lps", 0.0))
    c3_hourly_loss = float(data_c3.get("estimated_hourly_loss_m3", 0.0))
    c3_daily_loss = float(data_c3.get("estimated_daily_loss_m3", 0.0))

    passed = (
        (c2_risk_score >= 80.0)
        and (c2_classification == "partial_bypass")
        and (c3_loss_lps >= 0.05)
    )

    print_verdict(
        scenario_num=3,
        title="Theft Event Escalation & Component 3 Storage Deduction",
        passed=passed,
        notes=[
            f"Component 1 Cross-Check: Acoustic leak probability {Colors.BOLD}0.0%{Colors.RESET} (Confirmed non-leak).",
            f"C2 Fraud Risk Score: {Colors.BOLD}{c2_risk_score:.1f}%{Colors.RESET} (~89% Critical Severity).",
            f"C2 Probable Cause: '{Colors.BOLD}{c2_classification}{Colors.RESET}' (Partial Bypass Unauthorized Withdrawal).",
            f"C3 Storage Deduction Rate: {Colors.BOLD}{c3_loss_lps:.2f} LPS{Colors.RESET} ({c3_hourly_loss:.3f} m³/hr, {c3_daily_loss:.2f} m³/day).",
            f"C3 Impact Statement: {Colors.DIM}{data_c3.get('storage_forecast_impact')}{Colors.RESET}",
        ],
    )
    return passed


# ==============================================================================
# Scenario 4: Shared Depressurization Event (C2 Severe Theft -> C4 Intrusion)
# ==============================================================================

def run_scenario_4(base_url: str = DEFAULT_API_BASE_URL) -> bool:
    """
    Scenario 4: Shared depressurization event: severe drop triggers C2 theft analysis while querying
    GET /api/v1/c4-pressure-drop-events to show C4 opening a microbial intrusion hazard window.
    
    Narrative:
    When a commercial theft bypass draws massive flow from the distribution main, local pressure
    collapses below the critical 5.0m threshold (Delta P > 5.0m). Beyond water revenue loss (C2),
    severe negative pressure differentials compromise pipe joint integrity, creating suction that
    can draw external groundwater contaminants into the potable water network.
    Component 4 (Water Quality / Intrusion Risk) queries GET /api/v1/c4-pressure-drop-events to
    open a microbial intrusion hazard alert window.
    """
    print(f"\n{Colors.BOLD}{Colors.CYAN}+==============================================================================+{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}| SCENARIO 4: Shared Depressurization Event (C2 Theft -> C4 Intrusion Hazard)   |{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}+==============================================================================+{Colors.RESET}")
    # Clear any prior physical leak override so C2 evaluates pure theft depressurization
    try:
        requests.post(
            f"{base_url}/api/v1/c1-leak-feedback",
            json={"zone_id": "DMA 01", "node_id": "J_100", "leak_probability": 0.0},
            timeout=3.0,
        )
    except Exception:
        pass

    # Step 1: Telemetry assessment
    severe_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 15.2,
        "expected_pressure": 21.2,
        "spatial_deviation": 6.15,
        "recurrence_count": 5,
        "hours_since_supply_start": 3.0,
        "pressure_change_rate": -0.5,
        "residual_rolling_mean": 6.0,
        "residual_rolling_std": 0.4,
    }

    t0 = time.time()
    try:
        resp_c2 = requests.post(f"{base_url}/api/v1/assess-risk", json=severe_payload, timeout=5.0)
        latency_c2 = (time.time() - t0) * 1000.0
        data_c2 = resp_c2.json()
    except Exception as e:
        print(f"{Colors.RED}Step 1 C2 API Call failed: {e}{Colors.RESET}")
        return False

    print_http_call(
        method="POST",
        url=f"{base_url}/api/v1/assess-risk",
        component="C2",
        req_body=severe_payload,
        resp_body=data_c2,
        status_code=resp_c2.status_code,
        latency_ms=latency_c2,
    )

    # Step 2: Component 4 queries depressurization events
    print(f"\n{Colors.DIM}Step 2: Component 4 queries GET /api/v1/c4-pressure-drop-events?threshold_m=5.0.{Colors.RESET}")
    t1 = time.time()
    try:
        resp_c4 = requests.get(f"{base_url}/api/v1/c4-pressure-drop-events?threshold_m=5.0", timeout=5.0)
        latency_c4 = (time.time() - t1) * 1000.0
        data_c4 = resp_c4.json()
    except Exception as e:
        print(f"{Colors.RED}Step 2 C4 API Call failed: {e}{Colors.RESET}")
        return False

    print_http_call(
        method="GET",
        url=f"{base_url}/api/v1/c4-pressure-drop-events?threshold_m=5.0",
        component="C4",
        req_body=None,
        resp_body=data_c4,
        status_code=resp_c4.status_code,
        latency_ms=latency_c4,
    )

    total_events = int(data_c4.get("total_severe_events_count", 0))
    affected_nodes = data_c4.get("affected_nodes", [])
    recommendation = str(data_c4.get("recommendation", ""))

    passed = (total_events > 0) and ("J_100" in affected_nodes)

    print_verdict(
        scenario_num=4,
        title="Severe Theft Depressurization Triggers Component 4 Intrusion Warning",
        passed=passed,
        notes=[
            f"C2 Pressure Deficit: {Colors.BOLD}{severe_payload['expected_pressure'] - severe_payload['actual_pressure']:.2f}m{Colors.RESET} (Exceeds 5.0m critical threshold).",
            f"Component 4 Severe Events Count: {Colors.BOLD}{total_events}{Colors.RESET} timesteps.",
            f"Component 4 Compromised Nodes: {Colors.BOLD}{affected_nodes}{Colors.RESET}.",
            f"Component 4 Health Directive: {Colors.DIM}{recommendation}{Colors.RESET}",
        ],
    )
    return passed


# ==============================================================================
# Full Test Suite Orchestrator
# ==============================================================================

def run_all_scenarios(base_url: str = DEFAULT_API_BASE_URL):
    """
    Executes all 4 multi-component cross-talk scenarios sequentially
    and prints a consolidated executive summary table.
    """
    print(f"\n{Colors.BOLD}{Colors.WHITE}Starting Full Multi-Component Cross-Talk Demonstration Suite...{Colors.RESET}\n")
    results = []

    # Scenario 1
    s1 = run_scenario_1(base_url)
    results.append(("Scenario 1: Clean Refill Cycle (C2 Risk < 20%)", s1))
    time.sleep(0.5)

    # Scenario 2
    s2 = run_scenario_2(base_url)
    results.append(("Scenario 2: Pipe Break Event (C1 Suppresses Risk to 18%)", s2))
    time.sleep(0.5)

    # Scenario 3
    s3 = run_scenario_3(base_url)
    results.append(("Scenario 3: Theft Event (C1 Zero Leak -> C2 89% -> C3 0.08 LPS)", s3))
    time.sleep(0.5)

    # Scenario 4
    s4 = run_scenario_4(base_url)
    results.append(("Scenario 4: Shared Depressurization (C2 Theft -> C4 Intrusion)", s4))

    # Consolidated Executive Summary Table
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.WHITE}   MULTI-COMPONENT ECOSYSTEM DEMONSTRATION -- EXECUTIVE SUMMARY{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print(f" {'Scenario':<62} | {'Status':<12}")
    print(f" {'-' * 62}-+-{'-' * 12}")

    all_passed = True
    for title, status in results:
        status_text = f"{Colors.GREEN}VERIFIED [OK]{Colors.RESET}" if status else f"{Colors.RED}FAILED [X]{Colors.RESET}"
        print(f" {title:<62} | {status_text}")
        if not status:
            all_passed = False

    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    if all_passed:
        print(f"{Colors.BOLD}{Colors.GREEN}[OK] All 4 Multi-Component Cross-Talk Scenarios Passed Successfully!{Colors.RESET}\n")
    else:
        print(f"{Colors.BOLD}{Colors.RED}[X] Some scenarios encountered unexpected responses. Review API logs.{Colors.RESET}\n")


# ==============================================================================
# Interactive Terminal Menu
# ==============================================================================

def interactive_menu(base_url: str = DEFAULT_API_BASE_URL):
    """
    Displays the interactive terminal menu for selecting and running test scenarios.
    """
    while True:
        print_banner()
        print(f" Target Backend: {Colors.BOLD}{Colors.GREEN}{base_url}{Colors.RESET}")
        
        # Check backend connectivity
        is_alive = check_api_health(base_url)
        if is_alive:
            print(f" Backend Status: {Colors.BOLD}{Colors.GREEN}[*] FastAPI Online & Responding{Colors.RESET}\n")
        else:
            print(f" Backend Status: {Colors.BOLD}{Colors.RED}[!] Unreachable! Ensure uvicorn is running on {base_url}{Colors.RESET}\n")

        print(f" {Colors.BOLD}Select an Ecosystem Scenario to Demonstrate:{Colors.RESET}")
        print(f"   {Colors.CYAN}[1]{Colors.RESET} Scenario 1: Clean refill cycle in DMA 01 (C2 confirms normal, risk < 20%)")
        print(f"   {Colors.CYAN}[2]{Colors.RESET} Scenario 2: Pipe break event (C1 feedback suppresses fraud risk to 18%)")
        print(f"   {Colors.CYAN}[3]{Colors.RESET} Scenario 3: Theft event (C1 zero leak -> C2 risk 89% -> C3 deducts 0.08 LPS)")
        print(f"   {Colors.CYAN}[4]{Colors.RESET} Scenario 4: Shared depressurization event (C2 theft -> C4 intrusion hazard)")
        print(f"   {Colors.GREEN}[A]{Colors.RESET} Run All Scenarios (Full Demonstration Suite)")
        print(f"   {Colors.YELLOW}[H]{Colors.RESET} Re-check Health & Route Registry")
        print(f"   {Colors.RED}[Q]{Colors.RESET} Quit Simulator")

        print(f"\n{Colors.DIM}{'-' * 80}{Colors.RESET}")
        try:
            choice = input(f"{Colors.BOLD}Enter selection [1-4, A, H, Q]: {Colors.RESET}").strip().upper()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Colors.YELLOW}Exiting simulation...{Colors.RESET}")
            break

        if choice == "1":
            run_scenario_1(base_url)
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "2":
            run_scenario_2(base_url)
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "3":
            run_scenario_3(base_url)
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "4":
            run_scenario_4(base_url)
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "A":
            run_all_scenarios(base_url)
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice == "H":
            print(f"\n{Colors.BOLD}Testing Backend Health & Registry...{Colors.RESET}")
            try:
                res_h = requests.get(f"{base_url}/health", timeout=3.0)
                print(f"Health Response ({res_h.status_code}):\n{colorize_json(res_h.json())}")
                res_meta = requests.get(f"{base_url}/api/v1", timeout=3.0)
                print(f"\nRoute Registry ({res_meta.status_code}):\n{colorize_json(res_meta.json())}")
            except Exception as e:
                print(f"{Colors.RED}Health check failed: {e}{Colors.RESET}")
            input(f"\n{Colors.DIM}Press Enter to return to menu...{Colors.RESET}")
        elif choice in ("Q", "QUIT", "EXIT"):
            print(f"\n{Colors.GREEN}Ecosystem simulator terminated. Goodbye!{Colors.RESET}\n")
            break
        else:
            print(f"\n{Colors.RED}Invalid selection '{choice}'. Please select 1, 2, 3, 4, A, H, or Q.{Colors.RESET}")
            time.sleep(1.0)


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="NWSDB Component 2 Multi-Component Ecosystem Cross-Talk Simulator"
    )
    parser.add_argument(
        "--scenario",
        "-s",
        type=int,
        choices=[1, 2, 3, 4],
        help="Run a specific scenario (1, 2, 3, or 4)",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Run all 4 scenarios sequentially",
    )
    parser.add_argument(
        "--url",
        "-u",
        default=DEFAULT_API_BASE_URL,
        help=f"FastAPI backend base URL (default: {DEFAULT_API_BASE_URL})",
    )

    args = parser.parse_args()

    # Pre-flight check
    if not check_api_health(args.url):
        print(f"\n{Colors.RED}{Colors.BOLD}WARNING: Backend at {args.url} is not responding!{Colors.RESET}")
        print(f"{Colors.YELLOW}Please ensure FastAPI is running via:{Colors.RESET}")
        print(f"  .\\venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --port 8000\n")

    if args.scenario:
        print_banner()
        if args.scenario == 1:
            run_scenario_1(args.url)
        elif args.scenario == 2:
            run_scenario_2(args.url)
        elif args.scenario == 3:
            run_scenario_3(args.url)
        elif args.scenario == 4:
            run_scenario_4(args.url)
    elif args.all:
        print_banner()
        run_all_scenarios(args.url)
    else:
        interactive_menu(args.url)


if __name__ == "__main__":
    main()
