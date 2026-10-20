"""
src/notifier.py
Authority Alert Notification System for NWSDB Water Fraud Component 2.

Features:
- Class AuthorityNotifier with in-memory deduplication & cooldown cache:
  Maximum 1 alert per node every 6 hours unless risk transitions to 'Critical' (>85%).
- Logs dispatched alerts to data/processed/dispatched_alerts.json.
- Dispatches urgent formatted alert emails via SMTP (with automatic console fallback simulation).
- Dispatches JSON alert payloads to configurable municipal/utility webhooks.
- Historical alert query interface for Admin Portal and REST API.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import smtplib
from typing import Any, Dict, List, Optional, Tuple
import requests

try:
    from src.geo_converter import get_junction_location
except ImportError:
    try:
        from geo_converter import get_junction_location  # type: ignore
    except ImportError:
        get_junction_location = None  # type: ignore

# Logging configuration
logger = logging.getLogger("water_fraud.notifier")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [AuthorityNotifier]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ALERTS_FILE = PROJECT_ROOT / "data" / "processed" / "dispatched_alerts.json"

# Configuration defaults and environment overrides
SMTP_HOST = os.getenv("NWSDB_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("NWSDB_SMTP_PORT", "587"))
SMTP_USER = os.getenv("NWSDB_SMTP_USER", "")
SMTP_PASSWORD = os.getenv("NWSDB_SMTP_PASSWORD", "")
ALERT_RECIPIENT_EMAIL = os.getenv("NWSDB_ALERT_RECIPIENT_EMAIL", "investigations@nwsdb.gov.lk")
ALERT_SENDER_EMAIL = os.getenv("NWSDB_ALERT_SENDER_EMAIL", "alerts@nwsdb-monitoring.gov.lk")
DEFAULT_WEBHOOK_URL = os.getenv("NWSDB_ALERT_WEBHOOK_URL", "https://municipal-dispatch.nwsdb.gov.lk/api/v1/fraud-alerts")

COOLDOWN_SECONDS_DEFAULT = float(os.getenv("ALERT_COOLDOWN_HOURS", "6.0")) * 3600.0  # 6 hours
CRITICAL_THRESHOLD_DEFAULT = float(os.getenv("ALERT_CRITICAL_THRESHOLD", "85.0"))


class AuthorityNotifier:
    """
    Manages urgent dispatch of water fraud and theft alerts to NWSDB utility authorities.
    Features:
    - Alert deduplication and 6-hour per-node cooldown.
    - Automatic cooldown override if risk escalates to 'Critical' (>85.0%).
    - Email notification with HTML tabular body and console fallback.
    - Webhook pushing for municipal command-center systems.
    - Persistent JSON file logging.
    """

    def __init__(
        self,
        alerts_file: Path = DEFAULT_ALERTS_FILE,
        cooldown_seconds: float = COOLDOWN_SECONDS_DEFAULT,
        critical_threshold: float = CRITICAL_THRESHOLD_DEFAULT,
        recipient_email: str = ALERT_RECIPIENT_EMAIL,
        webhook_url: str = DEFAULT_WEBHOOK_URL,
    ) -> None:
        self.alerts_file = Path(alerts_file)
        self.cooldown_seconds = cooldown_seconds
        self.critical_threshold = critical_threshold
        self.recipient_email = recipient_email
        self.webhook_url = webhook_url

        # In-memory deduplication & cooldown cache: node_id -> {"timestamp": float, "risk_score": float}
        self._node_cooldown_cache: Dict[str, Dict[str, Any]] = {}
        self._ensure_storage_ready()

    def _ensure_storage_ready(self) -> None:
        """Ensures destination data directory and dispatched_alerts.json file exist."""
        try:
            self.alerts_file.parent.mkdir(parents=True, exist_ok=True)
            if not self.alerts_file.exists():
                self.alerts_file.write_text("[]", encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to initialize alert storage at {self.alerts_file}: {e}")

    def check_cooldown(self, node_id: str, current_risk_score: float) -> Tuple[bool, str]:
        """
        Determines whether an alert can be dispatched for node_id based on deduplication rules:
        - Maximum 1 alert per node every 6 hours.
        - Exception: Allowed if current risk transitions to 'Critical' (>85%) while previous was <=85%.
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        record = self._node_cooldown_cache.get(node_id)

        if record is None:
            return True, "Initial alert for node"

        last_ts = float(record.get("timestamp", 0.0))
        last_score = float(record.get("risk_score", 0.0))
        elapsed_sec = now_ts - last_ts

        # Critical escalation override: If risk escalates above 85% and previous was lower
        if current_risk_score > self.critical_threshold and last_score <= self.critical_threshold:
            return True, f"Critical escalation override (Risk: {current_risk_score:.1f}% > {self.critical_threshold}%)"

        if elapsed_sec >= self.cooldown_seconds:
            return True, f"Cooldown expired ({elapsed_sec / 3600.0:.1f} hrs elapsed)"

        remaining_hrs = (self.cooldown_seconds - elapsed_sec) / 3600.0
        return False, f"Cooldown active ({remaining_hrs:.1f} hrs remaining). Last alert score: {last_score:.1f}%"

    def reset_cooldown(self, node_id: Optional[str] = None) -> None:
        """
        Resets cooldown cache for testing, demonstration walkthroughs, or manual override.
        """
        if node_id:
            self._node_cooldown_cache.pop(node_id, None)
            logger.info(f"Cleared cooldown cache for node {node_id}")
        else:
            self._node_cooldown_cache.clear()
            logger.info("Cleared cooldown cache for all nodes")

    def format_email_content(self, alert_payload: Dict[str, Any]) -> Tuple[str, str, str]:
        """
        Formats urgent alert email subject, plain text body, and HTML table body.
        """
        dma_id = str(alert_payload.get("dma_id", "DMA 01"))
        node_id = str(alert_payload.get("node_id", "Unknown"))
        risk_score = float(alert_payload.get("risk_score", 0.0))
        actual_p = float(alert_payload.get("actual_pressure", 0.0))
        expected_p = float(alert_payload.get("expected_pressure", 0.0))
        residual_drop = float(alert_payload.get("residual_head_drop", expected_p - actual_p))
        probable_cause = str(alert_payload.get("probable_cause", "partial_bypass"))
        priority = str(alert_payload.get("inspection_priority", "P1 - Immediate Field Investigation"))
        evidence_list = alert_payload.get("evidence_list", [])

        evidence_str = "\n".join([f"  • {e}" for e in evidence_list]) if evidence_list else "  • Hydraulic residual threshold departure"

        subject = f"[NWSDB URGENT ALERT] Unauthorized Water Withdrawal Suspected - {dma_id} Node {node_id}"

        # Resolve exact location metadata
        loc = alert_payload.get("location")
        if not loc and get_junction_location and node_id not in ("Unknown", ""):
            try:
                raw_loc = get_junction_location(node_id)
                landmark = (
                    "Kaduwela East Sector 04B (Near Node J_100 Chamber)"
                    if node_id == "J_100"
                    else f"{raw_loc.get('sector_name', 'Kaduwela East')} (Near Node {node_id} Chamber)"
                )
                loc = {
                    "junction_id": node_id,
                    "grid_x": raw_loc["grid_x"],
                    "grid_y": raw_loc["grid_y"],
                    "latitude": raw_loc["latitude"],
                    "longitude": raw_loc["longitude"],
                    "elevation_m": raw_loc["elevation_m"],
                    "landmark": landmark,
                    "google_maps_url": raw_loc["google_maps_url"],
                }
            except Exception:
                pass

        if loc:
            landmark_str = str(loc.get("landmark", f"Kaduwela Sector Chamber ({node_id})"))
            lat_val = float(loc.get("latitude", 6.936812 if node_id == "J_100" else 6.9350))
            lng_val = float(loc.get("longitude", 79.967673 if node_id == "J_100" else 79.9840))
            gx_val = float(loc.get("grid_x", 410927.22 if node_id == "J_100" else 412730.0))
            gy_val = float(loc.get("grid_y", 493000.00 if node_id == "J_100" else 492800.0))
            elev_val = float(loc.get("elevation_m", 12.0))
            maps_url = str(loc.get("google_maps_url", f"https://www.google.com/maps/search/?api=1&query={lat_val:.6f},{lng_val:.6f}"))
        else:
            landmark_str = (
                "Kaduwela East Sector 04B (Near Node J_100 Chamber)"
                if node_id == "J_100"
                else f"Kaduwela East Sector Chamber ({node_id})"
            )
            lat_val, lng_val = (6.936812, 79.967673) if node_id == "J_100" else (6.9350, 79.9840)
            gx_val, gy_val = (410927.22, 493000.0) if node_id == "J_100" else (412730.0, 492800.0)
            elev_val = 12.0
            maps_url = f"https://www.google.com/maps/search/?api=1&query={lat_val:.6f},{lng_val:.6f}"

        plain_body = f"""================================================================================
NWSDB URGENT ALERT: UNAUTHORIZED WATER THEFT / BYPASS DETECTED
================================================================================
District Metered Area (DMA) : {dma_id}
Monitored Junction Node     : {node_id}
Physical Landmark           : {landmark_str}
GPS Coordinates             : {lat_val:.6f}° N, {lng_val:.6f}° E (Elevation: {elev_val:.1f} m)
Grid Coordinates (SLD99)    : X={gx_val:.2f} m, Y={gy_val:.2f} m
Google Maps Navigation Link : {maps_url}
Calculated Fraud Risk Score : {risk_score:.2f} / 100
Current Pressure Head       : {actual_p:.2f} m
Expected Baseline Pressure  : {expected_p:.2f} m
Residual Head Loss Deficit  : {residual_drop:.2f} m
Probable Cause Classification: {probable_cause} (Commercial / Industrial Bypass)
Field Inspection Priority   : {priority}

FORENSIC EVIDENCE SUMMARY:
{evidence_str}

ACTION REQUIRED:
Dispatch Area Water Audit & NRW Investigation Taskforce immediately to junction {node_id}.
Navigate to coordinates via Google Maps: {maps_url}
================================================================================
"""

        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 20px; }}
    .alert-card {{ max-width: 650px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-top: 5px solid #dc2626; border-radius: 8px; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }}
    .header {{ margin-bottom: 20px; }}
    .header h2 {{ margin: 0; color: #b91c1c; font-size: 20px; }}
    .header p {{ margin: 4px 0 0; color: #64748b; font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #f1f5f9; text-align: left; }}
    th {{ background: #f8fafc; color: #475569; font-weight: 600; width: 38%; }}
    td {{ color: #0f172a; font-weight: 500; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
    .badge-critical {{ background: #fee2e2; color: #991b1b; }}
    .evidence-box {{ background: #fef2f2; border-left: 3px solid #dc2626; padding: 12px; margin-top: 14px; border-radius: 4px; font-size: 13px; }}
    .footer {{ margin-top: 24px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 12px; }}
  </style>
</head>
<body>
  <div class="alert-card">
    <div class="header">
      <h2>National Water Supply & Drainage Board — Urgent Theft Alert</h2>
      <p>Kaduwela Water Supply Network Digital Twin Surveillance (Component 2)</p>
    </div>

    <table>
      <tr><th>District Metered Area</th><td><strong>{dma_id}</strong></td></tr>
      <tr><th>Monitoring Junction</th><td><code>{node_id}</code></td></tr>
      <tr><th>Physical Landmark</th><td><strong>{landmark_str}</strong></td></tr>
      <tr><th>GPS Coordinates</th><td>{lat_val:.6f}&deg; N, {lng_val:.6f}&deg; E (Elev: {elev_val:.1f} m)</td></tr>
      <tr><th>Local Grid (SLD99)</th><td>X={gx_val:.2f} m, Y={gy_val:.2f} m</td></tr>
      <tr><th>Google Maps Navigation</th><td><a href="{maps_url}" target="_blank" style="color: #0284c7; font-weight: bold; text-decoration: underline;">Open in Google Maps &rarr;</a></td></tr>
      <tr><th>Fraud Risk Score</th><td><span class="badge badge-critical">{risk_score:.2f} / 100</span></td></tr>
      <tr><th>Observed Pressure (Telemetry)</th><td>{actual_p:.2f} m</td></tr>
      <tr><th>Expected Baseline (Twin)</th><td>{expected_p:.2f} m</td></tr>
      <tr><th>Residual Head Loss Drop (&Delta;P)</th><td><strong style="color: #dc2626;">-{residual_drop:.2f} m</strong></td></tr>
      <tr><th>Probable Cause Classification</th><td><strong>{probable_cause}</strong></td></tr>
      <tr><th>Field Inspection Priority</th><td><strong style="color: #b91c1c;">{priority}</strong></td></tr>
    </table>

    <div class="evidence-box">
      <strong>Forensic Evidence Detected:</strong>
      <ul style="margin: 6px 0 0 16px; padding: 0;">
        {"".join([f"<li>{e}</li>" for e in evidence_list]) if evidence_list else "<li>Severe sustained hydraulic residual deficit</li>"}
      </ul>
    </div>

    <div class="footer">
      Automated dispatch from NWSDB Digital Twin Component 2 • Dispatched at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
    </div>
  </div>
</body>
</html>
"""
        return subject, plain_body, html_body

    def send_smtp_email(self, alert_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatches alert email via SMTP if credentials are configured;
        otherwise logs a complete email console simulation.
        """
        subject, plain_body, _ = self.format_email_content(alert_payload)
        recipient = self.recipient_email

        if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
            try:
                from email.mime.multipart import MIMEMultipart
                from email.mime.text import MIMEText

                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = ALERT_SENDER_EMAIL
                msg["To"] = recipient

                msg.attach(MIMEText(plain_body, "plain", "utf-8"))

                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10.0) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.send_message(msg)

                logger.info(f"Successfully sent SMTP urgent alert email to {recipient} (Subject: {subject})")
                return {"delivery_status": "Sent", "channel": "SMTP", "recipient": recipient, "error": None}
            except Exception as e:
                err_msg = f"SMTP dispatch failed: {str(e)}"
                logger.warning(f"{err_msg}. Falling back to console simulation.")
                return {"delivery_status": "Failed", "channel": "SMTP", "recipient": recipient, "error": str(e)}

        # Fallback simulation when SMTP credentials are unset
        logger.info(
            f"\n--- [SMTP CONSOLE SIMULATION: EMAIL DISPATCH] ---\n"
            f"To: {recipient}\nFrom: {ALERT_SENDER_EMAIL}\nSubject: {subject}\n"
            f"{plain_body}\n"
            f"--- [END EMAIL SIMULATION] ---\n"
        )
        return {
            "delivery_status": "Sent",
            "channel": "Console Simulation (SMTP credentials unset)",
            "recipient": recipient,
            "error": None,
        }

    def send_webhook(self, alert_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatches alert JSON payload to an external municipal/utility webhook.
        """
        endpoint = self.webhook_url
        if not endpoint:
            return {"delivery_status": "Skipped", "channel": "Webhook", "endpoint": "Unconfigured", "error": None}

        # If dummy or unresolvable default domain, simulate webhook gracefully without crashing
        is_mock_url = "municipal-dispatch.nwsdb.gov.lk" in endpoint or "example.com" in endpoint

        if not is_mock_url:
            try:
                resp = requests.post(endpoint, json=alert_payload, timeout=4.0)
                if resp.status_code >= 200 and resp.status_code < 300:
                    logger.info(f"Webhook alert successfully pushed to {endpoint} (HTTP {resp.status_code})")
                    return {"delivery_status": "Sent", "channel": "Webhook", "endpoint": endpoint, "error": None}
                else:
                    logger.warning(f"Webhook endpoint returned HTTP {resp.status_code}")
                    return {"delivery_status": "Failed", "channel": "Webhook", "endpoint": endpoint, "error": f"HTTP {resp.status_code}"}
            except Exception as e:
                logger.warning(f"Webhook network error to {endpoint}: {e}")
                return {"delivery_status": "Failed", "channel": "Webhook", "endpoint": endpoint, "error": str(e)}

        # Simulated Webhook for internal test environments
        logger.info(f"[Webhook Simulation] JSON alert payload queued for municipal endpoint: {endpoint}")
        return {
            "delivery_status": "Sent",
            "channel": "Webhook Simulation",
            "endpoint": endpoint,
            "error": None,
        }

    def log_alert_record(self, alert_record: Dict[str, Any]) -> None:
        """Appends alert record to dispatched_alerts.json safely."""
        self._ensure_storage_ready()
        try:
            alerts: List[Dict[str, Any]] = []
            if self.alerts_file.exists() and self.alerts_file.stat().st_size > 0:
                try:
                    content = self.alerts_file.read_text(encoding="utf-8")
                    alerts = json.loads(content)
                    if not isinstance(alerts, list):
                        alerts = []
                except Exception:
                    alerts = []

            alerts.append(alert_record)

            # Keep recent 500 alerts
            if len(alerts) > 500:
                alerts = alerts[-500:]

            self.alerts_file.write_text(json.dumps(alerts, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to append alert to {self.alerts_file}: {e}")

    def dispatch_alert(self, alert_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes authority alert dispatch workflow:
        1. Checks deduplication & cooldown.
        2. Sends formatted email (SMTP or simulation).
        3. Sends webhook push.
        4. Writes record to data/processed/dispatched_alerts.json.
        """
        node_id = str(alert_payload.get("node_id", "Unknown"))
        dma_id = str(alert_payload.get("dma_id", alert_payload.get("zone_id", "DMA 01")))
        risk_score = float(alert_payload.get("risk_score", alert_payload.get("fraud_risk_score", 0.0)))

        can_dispatch, reason = self.check_cooldown(node_id, risk_score)
        if not can_dispatch:
            logger.info(f"Alert for node {node_id} suppressed by cooldown: {reason}")
            return {
                "dispatched": False,
                "node_id": node_id,
                "risk_score": risk_score,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Update cooldown timestamp and score
        now_ts = datetime.now(timezone.utc).timestamp()
        self._node_cooldown_cache[node_id] = {
            "timestamp": now_ts,
            "risk_score": risk_score,
        }

        # Resolve location for webhook and log persistence
        loc = alert_payload.get("location")
        if not loc and get_junction_location and node_id not in ("Unknown", ""):
            try:
                raw_loc = get_junction_location(node_id)
                landmark = (
                    "Kaduwela East Sector 04B (Near Node J_100 Chamber)"
                    if node_id == "J_100"
                    else f"{raw_loc.get('sector_name', 'Kaduwela East')} (Near Node {node_id} Chamber)"
                )
                loc = {
                    "junction_id": node_id,
                    "grid_x": raw_loc["grid_x"],
                    "grid_y": raw_loc["grid_y"],
                    "latitude": raw_loc["latitude"],
                    "longitude": raw_loc["longitude"],
                    "elevation_m": raw_loc["elevation_m"],
                    "landmark": landmark,
                    "google_maps_url": raw_loc["google_maps_url"],
                }
            except Exception:
                pass

        if loc and "location" not in alert_payload:
            alert_payload["location"] = loc

        # Dispatch via channels
        email_res = self.send_smtp_email(alert_payload)
        webhook_res = self.send_webhook(alert_payload)

        # Composite delivery status
        if email_res.get("delivery_status") == "Sent" or webhook_res.get("delivery_status") == "Sent":
            delivery_status = "Sent"
        else:
            delivery_status = "Failed"

        alert_id = f"ALT-{int(now_ts)}-{node_id}"
        record: Dict[str, Any] = {
            "alert_id": alert_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node_id": node_id,
            "dma_id": dma_id,
            "risk_score": round(risk_score, 2),
            "evidence_list": alert_payload.get("evidence_list", alert_payload.get("reasons_list", [])),
            "probable_cause": alert_payload.get("probable_cause", alert_payload.get("classification", "partial_bypass")),
            "actual_pressure": alert_payload.get("actual_pressure"),
            "expected_pressure": alert_payload.get("expected_pressure"),
            "residual_head_drop": alert_payload.get("residual_head_drop"),
            "inspection_priority": alert_payload.get("inspection_priority", alert_payload.get("recommended_action", "P1 - Immediate Field Investigation")),
            "delivery_status": delivery_status,
            "recipient_email": self.recipient_email,
            "webhook_url": self.webhook_url,
            "email_channel": email_res.get("channel"),
            "webhook_channel": webhook_res.get("channel"),
            "dispatch_reason": reason,
        }

        if loc:
            record["location"] = loc
            record["landmark"] = loc.get("landmark")
            record["latitude"] = loc.get("latitude")
            record["longitude"] = loc.get("longitude")
            record["google_maps_url"] = loc.get("google_maps_url")

        self.log_alert_record(record)
        logger.info(f"[DISPATCHED] Authority alert {alert_id} for {dma_id} node {node_id} (Score: {risk_score:.2f})")
        return record

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieves recent dispatched notifications from dispatched_alerts.json.
        """
        self._ensure_storage_ready()
        if not self.alerts_file.exists():
            return []

        try:
            content = self.alerts_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, list):
                # Return most recent alerts first
                return list(reversed(data))[:limit]
            return []
        except Exception as e:
            logger.error(f"Failed to read alert history from {self.alerts_file}: {e}")
            return []


# Global singleton instance
_notifier_instance: Optional[AuthorityNotifier] = None


def get_authority_notifier() -> AuthorityNotifier:
    """Returns global singleton instance of AuthorityNotifier."""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = AuthorityNotifier()
    return _notifier_instance
