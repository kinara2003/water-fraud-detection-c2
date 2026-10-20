"""
demo_walkthrough.py
===================
End-to-End Automated Demonstration Walkthrough for the NWSDB Water Fraud
& Leak Detection System (Component 2 - Kaduwela DMAs 01 & 02).

Execution Steps:
1. Check that the FastAPI server (http://127.0.0.1:8000) is live and healthy.
2. Send a sequence of normal morning telemetry samples for DMA 01 and DMA 02
   (confirming Fraud Risk Score < 30 and no alerts dispatched).
3. Simulate an unauthorized partial-bypass event at node J_100:
   - Expected Pressure: 21.5 m
   - Actual Pressure:   14.2 m  (Delta P = 7.3 m drop)
   - Spatial Deviation:  7.1 m
4. Confirm that the Fraud Risk Score crosses 80%, triggering classification
   as 'partial_bypass'.
5. Verify that AuthorityNotifier automatically fires an alert to
   data/processed/dispatched_alerts.json.
6. Send inspector ground-truth feedback confirming the finding, and verify
   that the feedback logs update in data/processed/inspection_logs.csv.
7. Print a publication-quality formatted terminal summary confirming that
   all component requirements have passed.

Usage:
    python demo_walkthrough.py
"""

import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple
import requests

# Ensure stdout and stderr handle UTF-8 cleanly on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# Terminal formatting ANSI codes
class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_RED = "\033[41m"


BASE_URL = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parent
ALERTS_FILE = PROJECT_ROOT / "data" / "processed" / "dispatched_alerts.json"
INSPECTION_LOGS_FILE = PROJECT_ROOT / "data" / "processed" / "inspection_logs.csv"


def log_header(title: str) -> None:
    print(f"\n{Style.CYAN}{'=' * 76}{Style.RESET}")
    print(f"{Style.BOLD}{Style.WHITE}  {title}{Style.RESET}")
    print(f"{Style.CYAN}{'=' * 76}{Style.RESET}")


def log_step(step_num: int, title: str) -> None:
    print(f"\n{Style.BOLD}{Style.BLUE}[STEP {step_num}]{Style.RESET} {Style.BOLD}{title}{Style.RESET}")
    print(f"{Style.DIM}{'-' * 60}{Style.RESET}")


def log_success(msg: str) -> None:
    print(f"  {Style.GREEN}[PASS] {msg}{Style.RESET}")


def log_info(msg: str) -> None:
    print(f"  {Style.CYAN}[INFO] {msg}{Style.RESET}")


def log_warn(msg: str) -> None:
    print(f"  {Style.YELLOW}[WARN] {msg}{Style.RESET}")


def log_error(msg: str) -> None:
    print(f"  {Style.RED}[FAIL] {msg}{Style.RESET}")


# ==============================================================================
# Helper Functions
# ==============================================================================

def get_current_alerts_count() -> int:
    """Reads current count of alerts from dispatched_alerts.json."""
    if not ALERTS_FILE.exists():
        return 0
    try:
        data = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return len(data)
    except Exception:
        pass
    return 0


def read_dispatched_alerts() -> List[Dict[str, Any]]:
    """Reads all alerts from dispatched_alerts.json."""
    if not ALERTS_FILE.exists():
        return []
    try:
        data = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


# ==============================================================================
# Walkthrough Execution
# ==============================================================================

def run_demo() -> bool:
    start_time = time.time()
    all_passed = True
    summary_results: List[Tuple[str, str, str]] = []

    print("\n" + f"{Style.BOLD}{Style.BG_BLUE}{Style.WHITE}  NWSDB WATER FRAUD DETECTION & RESPONSE PLATFORM -- DEMO WALKTHROUGH  {Style.RESET}\n")
    print(f"  Target Server: {Style.BOLD}{BASE_URL}{Style.RESET}")
    print(f"  Alerts Storage: {Style.DIM}{ALERTS_FILE}{Style.RESET}")
    print(f"  Inspections Log: {Style.DIM}{INSPECTION_LOGS_FILE}{Style.RESET}")

    # --------------------------------------------------------------------------
    # Step 1: Health & Server Connectivity Check
    # --------------------------------------------------------------------------
    log_step(1, "Check FastAPI Server Connectivity & Model Readiness")
    try:
        health_resp = requests.get(f"{BASE_URL}/health", timeout=5.0)
        if health_resp.status_code == 200:
            health_data = health_resp.json()
            stage1 = health_data.get("stage1_model", "Unknown")
            stage2 = health_data.get("stage2_model", "Unknown")
            log_success(f"FastAPI Server is ONLINE (HTTP 200 OK)")
            log_info(f"Stage 1 Anomaly Model: {Style.BOLD}{stage1}{Style.RESET}")
            log_info(f"Stage 2 Fault Classifier: {Style.BOLD}{stage2}{Style.RESET}")
            summary_results.append(("Step 1: Server & Models Online", "PASS", f"Stage 1: {stage1}, Stage 2: {stage2}"))
        else:
            log_error(f"Health check failed with HTTP {health_resp.status_code}: {health_resp.text}")
            return False
    except requests.exceptions.ConnectionError:
        log_error(f"Could not connect to {BASE_URL}. Ensure uvicorn is running:")
        print(f"     {Style.YELLOW}uvicorn app.main:app --host 127.0.0.1 --port 8000{Style.RESET}")
        return False
    except Exception as e:
        log_error(f"Unexpected connection error: {e}")
        return False

    # Reset cooldown cache on the server to guarantee clean deterministic execution
    try:
        requests.post(f"{BASE_URL}/api/v1/notifications/reset-cooldown", timeout=3.0)
        log_info("Alert notification cooldown cache cleared for clean test pass.")
    except Exception:
        pass

    initial_alerts_count = get_current_alerts_count()
    log_info(f"Baseline alerts count in storage: {initial_alerts_count}")

    # --------------------------------------------------------------------------
    # Step 2: Normal Morning Telemetry Samples for DMA 01 & DMA 02
    # --------------------------------------------------------------------------
    log_step(2, "Stream Normal Morning Telemetry Samples (DMA 01 & DMA 02)")
    normal_samples = [
        {
            "desc": "DMA 01 - Junction J_10 (Morning Supply Stabilized)",
            "payload": {
                "zone_id": "DMA 01",
                "node_id": "J_10",
                "actual_pressure": 35.08,
                "expected_pressure": 35.10,
                "spatial_deviation": 0.02,
                "recurrence_count": 0,
                "pressure_change_rate": 0.01,
                "residual_rolling_mean": 0.02,
                "residual_rolling_std": 0.01,
                "hours_since_supply_start": 2.5,
            },
        },
        {
            "desc": "DMA 01 - Junction J_500 (Morning Nominal Flow)",
            "payload": {
                "zone_id": "DMA 01",
                "node_id": "J_500",
                "actual_pressure": 34.78,
                "expected_pressure": 34.80,
                "spatial_deviation": 0.03,
                "recurrence_count": 0,
                "pressure_change_rate": 0.00,
                "residual_rolling_mean": 0.02,
                "residual_rolling_std": 0.01,
                "hours_since_supply_start": 2.5,
            },
        },
        {
            "desc": "DMA 02 - Junction J_1200 (Baseline Reference Node)",
            "payload": {
                "zone_id": "DMA 02",
                "node_id": "J_1200",
                "actual_pressure": 35.19,
                "expected_pressure": 35.20,
                "spatial_deviation": 0.01,
                "recurrence_count": 0,
                "pressure_change_rate": -0.01,
                "residual_rolling_mean": 0.01,
                "residual_rolling_std": 0.01,
                "hours_since_supply_start": 2.5,
            },
        },
        {
            "desc": "DMA 02 - Junction J_2200 (Stable Distribution)",
            "payload": {
                "zone_id": "DMA 02",
                "node_id": "J_2200",
                "actual_pressure": 34.89,
                "expected_pressure": 34.90,
                "spatial_deviation": 0.02,
                "recurrence_count": 0,
                "pressure_change_rate": 0.00,
                "residual_rolling_mean": 0.01,
                "residual_rolling_std": 0.01,
                "hours_since_supply_start": 2.5,
            },
        },
    ]

    step2_passed = True
    max_normal_score = 0.0

    for idx, item in enumerate(normal_samples, start=1):
        desc = item["desc"]
        payload = item["payload"]
        resp = requests.post(f"{BASE_URL}/api/v1/assess-risk", json=payload, timeout=5.0)

        if resp.status_code != 200:
            log_error(f"Sample {idx} failed with HTTP {resp.status_code}: {resp.text}")
            step2_passed = False
            continue

        res_json = resp.json()
        score = float(res_json.get("fraud_risk_score", 99.0))
        classification = str(res_json.get("classification", ""))
        rec_action = str(res_json.get("recommended_action", ""))
        max_normal_score = max(max_normal_score, score)

        if score < 30.0 and classification == "normal":
            log_success(
                f"{desc} -> Risk Score: {Style.BOLD}{score:.2f}/100{Style.RESET} | "
                f"Class: {Style.GREEN}{classification}{Style.RESET} | Action: {rec_action}"
            )
        else:
            log_error(
                f"{desc} -> UNEXPECTED high score {score:.2f} or class {classification}"
            )
            step2_passed = False

    time.sleep(0.5)
    alerts_after_normal = get_current_alerts_count()
    new_alerts_normal = alerts_after_normal - initial_alerts_count

    if new_alerts_normal == 0:
        log_success(f"Zero false alarms triggered (Alerts dispatched: {new_alerts_normal})")
    else:
        log_error(f"Expected 0 alerts for normal operations, but {new_alerts_normal} were fired!")
        step2_passed = False

    if step2_passed:
        summary_results.append((
            "Step 2: Normal Telemetry (DMA 01 & 02)",
            "PASS",
            f"All Risk Scores < 30 (Peak: {max_normal_score:.2f}), 0 False Alarms",
        ))
    else:
        summary_results.append(("Step 2: Normal Telemetry", "FAIL", "Elevated score or false alarm"))
        all_passed = False

    # --------------------------------------------------------------------------
    # Step 3 & 4: Simulate Unauthorized Partial-Bypass Event at Node J_100
    # --------------------------------------------------------------------------
    log_step(3, "Simulate Unauthorized Partial-Bypass Theft Event at J_100")
    print(f"  Target Node:        {Style.BOLD}J_100 (DMA 01){Style.RESET}")
    print(f"  Expected Baseline:  {Style.BOLD}21.50 m{Style.RESET}")
    print(f"  Observed Pressure:  {Style.BOLD}14.20 m{Style.RESET} (Severe Head Drop Delta P = 7.30 m)")
    print(f"  Spatial Deviation:  {Style.BOLD}7.10 m{Style.RESET} (Significant localized divergence)")
    print(f"  Supply Window:      {Style.BOLD}4.0 hours elapsed{Style.RESET} (Outside refill transient window)")

    theft_payload = {
        "zone_id": "DMA 01",
        "node_id": "J_100",
        "actual_pressure": 14.20,
        "expected_pressure": 21.50,
        "spatial_deviation": 7.10,
        "recurrence_count": 5,
        "pressure_change_rate": -0.45,
        "residual_rolling_mean": 7.20,
        "residual_rolling_std": 0.15,
        "hours_since_supply_start": 4.0,
    }

    resp_theft = requests.post(f"{BASE_URL}/api/v1/assess-risk", json=theft_payload, timeout=5.0)
    theft_data = resp_theft.json()

    theft_score = float(theft_data.get("fraud_risk_score", 0.0))
    theft_class = str(theft_data.get("classification", ""))
    theft_reasons = theft_data.get("reasons_list", [])
    theft_action = theft_data.get("recommended_action", "")

    log_step(4, "Evaluate Fraud Risk Score & Root-Cause Classification")
    log_info(f"Computed Fraud Risk Score: {Style.BOLD}{Style.RED}{theft_score:.2f} / 100{Style.RESET}")
    log_info(f"AI Root-Cause Classification: {Style.BOLD}{Style.RED}{theft_class}{Style.RESET}")
    log_info(f"Recommended Field Action: {theft_action}")
    print(f"  {Style.DIM}Evidence Checklist:{Style.RESET}")
    for reason in theft_reasons:
        print(f"    * {reason}")

    step3_passed = True
    if theft_score > 80.0:
        log_success(f"Fraud Risk Score crossed threshold: {theft_score:.2f}% > 80.0%")
    else:
        log_error(f"Fraud Risk Score {theft_score:.2f}% did NOT cross 80.0% threshold!")
        step3_passed = False

    if theft_class == "partial_bypass":
        log_success(f"Root-cause classified accurately as 'partial_bypass'")
    else:
        log_error(f"Expected classification 'partial_bypass', but got '{theft_class}'")
        step3_passed = False

    if step3_passed:
        summary_results.append((
            "Steps 3 & 4: Theft Detection & Classification",
            "PASS",
            f"Risk Score: {theft_score:.2f}% (>80%), Class: {theft_class}",
        ))
    else:
        summary_results.append(("Steps 3 & 4: Theft Classification", "FAIL", f"Score: {theft_score:.2f}%"))
        all_passed = False

    # --------------------------------------------------------------------------
    # Step 5: Verify AuthorityNotifier Dispatched Alert
    # --------------------------------------------------------------------------
    log_step(5, "Verify AuthorityNotifier Automatic Dispatch to dispatched_alerts.json")
    # Allow background task up to 2 seconds to complete writing
    time.sleep(1.0)

    alerts_list = read_dispatched_alerts()
    matching_j100_alerts = [a for a in alerts_list if a.get("node_id") == "J_100"]

    step5_passed = False
    latest_alert: Dict[str, Any] = {}

    if matching_j100_alerts:
        latest_alert = matching_j100_alerts[-1]
        alert_id = latest_alert.get("alert_id", "")
        alert_score = float(latest_alert.get("risk_score", 0.0))
        deliv_status = latest_alert.get("delivery_status", "")
        email_channel = latest_alert.get("email_channel", "")
        webhook_channel = latest_alert.get("webhook_channel", "")
        recip_email = latest_alert.get("recipient_email", "")

        log_success(f"Authority Alert found in storage: {Style.BOLD}{alert_id}{Style.RESET}")
        log_info(f"Target DMA / Junction: {latest_alert.get('dma_id')} / {latest_alert.get('node_id')}")
        log_info(f"Logged Risk Score: {Style.BOLD}{alert_score:.2f}%{Style.RESET}")
        log_info(f"Delivery Status: {Style.GREEN}{deliv_status}{Style.RESET}")
        log_info(f"Email Dispatch: {email_channel} -> {recip_email}")
        log_info(f"Webhook Dispatch: {webhook_channel}")

        if alert_score >= 80.0 and deliv_status == "Sent":
            step5_passed = True
    else:
        log_error(f"No alert for node J_100 found in {ALERTS_FILE}!")

    if step5_passed:
        summary_results.append((
            "Step 5: Authority Alert Dispatch",
            "PASS",
            f"Alert ID: {latest_alert.get('alert_id')}, Status: {latest_alert.get('delivery_status')}",
        ))
    else:
        summary_results.append(("Step 5: Authority Alert Dispatch", "FAIL", "Alert not dispatched or not found"))
        all_passed = False

    # --------------------------------------------------------------------------
    # Step 6: Send Inspector Feedback & Verify Feedback Logs Update
    # --------------------------------------------------------------------------
    log_step(6, "Send Inspector Field Feedback & Verify Continuous Learning Logs")
    feedback_payload = {
        "node_id": "J_100",
        "actual_finding": "partial_bypass",
        "notes": "Field investigation team dispatched. Located unauthorized 50mm PVC bypass branch tapped directly before bulk customer meter.",
    }

    fb_resp = requests.post(f"{BASE_URL}/api/v1/inspections/logs", json=feedback_payload, timeout=5.0)
    step6_passed = False

    if fb_resp.status_code == 200:
        fb_data = fb_resp.json()
        log_id = fb_data.get("log_id", "")
        log_status = fb_data.get("status", "")
        unprocessed = fb_data.get("total_unprocessed_logs", 0)

        log_success(f"Inspector feedback recorded successfully: {Style.BOLD}{log_id}{Style.RESET}")
        log_info(f"Ground Truth Finding: {Style.BOLD}{fb_data.get('actual_finding')}{Style.RESET}")
        log_info(f"Total Unprocessed Verification Logs: {unprocessed}")

        # Verify via GET endpoint
        time.sleep(0.5)
        get_logs_resp = requests.get(f"{BASE_URL}/api/v1/inspections/logs?limit=5", timeout=5.0)
        if get_logs_resp.status_code == 200:
            recent_logs = get_logs_resp.json()
            if any(l.get("log_id") == log_id for l in recent_logs):
                log_success(f"Verified new entry persisted into {INSPECTION_LOGS_FILE.name}")
                step6_passed = True
            else:
                log_error("Recorded log ID not found in GET /api/v1/inspections/logs")
        else:
            log_error(f"Failed to fetch logs: HTTP {get_logs_resp.status_code}")
    else:
        log_error(f"Failed to record inspection log: HTTP {fb_resp.status_code}: {fb_resp.text}")

    if step6_passed:
        summary_results.append((
            "Step 6: Inspector Feedback Logging",
            "PASS",
            f"Log ID: {fb_data.get('log_id')}, Ground Truth: partial_bypass",
        ))
    else:
        summary_results.append(("Step 6: Inspector Feedback", "FAIL", "Log persistence failed"))
        all_passed = False

    # --------------------------------------------------------------------------
    # Step 7: Formatted Terminal Summary
    # --------------------------------------------------------------------------
    elapsed = time.time() - start_time
    log_header("END-TO-END DEMO WALKTHROUGH EXECUTION SUMMARY")

    print(f"\n{'+' + '-' * 42}+{'-' * 10}+{'-' * 42}+")
    print(f"| {'Requirement / Test Phase':<40} | {'Status':<8} | {'Forensic Details':<40} |")
    print(f"{'+' + '=' * 42}+{ '=' * 10}+{ '=' * 42}+")

    for req_name, status, details in summary_results:
        color = Style.GREEN if status == "PASS" else Style.RED
        print(f"| {req_name:<40} | {color}{Style.BOLD}{status:<8}{Style.RESET} | {details:<40} |")

    print(f"{'+' + '-' * 42}+{'-' * 10}+{'-' * 42}+\n")

    if all_passed:
        print(f"  {Style.BOLD}{Style.BG_GREEN}{Style.WHITE}  ALL 6 COMPONENT INTEGRATION REQUIREMENTS PASSED SUCCESSFULLY  {Style.RESET}")
        print(f"  Total Walkthrough Execution Time: {Style.BOLD}{elapsed:.2f} seconds{Style.RESET}\n")
        return True
    else:
        print(f"  {Style.BOLD}{Style.BG_RED}{Style.WHITE}  ONE OR MORE REQUIREMENTS FAILED - REVIEW TERMINAL OUTPUT ABOVE  {Style.RESET}\n")
        return False


if __name__ == "__main__":
    success = run_demo()
    sys.exit(0 if success else 1)
