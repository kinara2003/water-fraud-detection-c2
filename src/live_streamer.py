"""
src/live_streamer.py
Continuous Live Pressure Telemetry Streamer with Interactive CLI Controls
Component 2: NWSDB Unauthorized Water Withdrawal & Physical Twin Surveillance Engine

Streams real-time pressure sensor telemetry into the FastAPI backend at:
  POST http://localhost:8000/api/v1/sensors/telemetry

Interactive Controls:
  [n] Stream Normal Baseline Data (All Green)
  [f] Inject Unauthorized Bypass at J_100 (drops pressure by 6.0m, triggers Red alert)
  [r] Inject Morning Refill Surge (shows transient filter in action)
  [1-6] Switch active sensor node (J_10, J_100, J_500, J_1200, J_2200, J_3000)
  [q] Quit streamer
"""

import argparse
import datetime
import json
import math
import os
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

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


# ==============================================================================
# ANSI Color & Formatting Utilities
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


# ==============================================================================
# Junction & Zone Metadata Configuration
# ==============================================================================
JUNCTION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "J_10": {
        "zone_id": "Zone 01",
        "dma_id": "DMA 01",
        "name": "Zone 01 — Town Central",
        "expected_pressure": 21.0,
        "landmark": "Town Central Primary Vault",
        "gps": "6.9350° N, 79.9830° E",
    },
    "J_100": {
        "zone_id": "Zone 04",
        "dma_id": "DMA 01",
        "name": "Zone 04 — Kaduwela East Industrial",
        "expected_pressure": 21.2,
        "landmark": "Kaduwela East Sector Road (Near Node J_100 Chamber)",
        "gps": "6.9354° N, 79.9842° E",
    },
    "J_500": {
        "zone_id": "Zone 03",
        "dma_id": "DMA 02",
        "name": "Zone 03 — Korathota Junction",
        "expected_pressure": 21.4,
        "landmark": "Korathota Junction Flow Chamber",
        "gps": "6.9360° N, 79.9855° E",
    },
    "J_1200": {
        "zone_id": "Zone 05",
        "dma_id": "DMA 02",
        "name": "Zone 05 — Welihinda Ridge",
        "expected_pressure": 20.5,
        "landmark": "Welihinda Elevated Ridge Chamber",
        "gps": "6.9340° N, 79.9820° E",
    },
    "J_2200": {
        "zone_id": "Zone 05",
        "dma_id": "DMA 02",
        "name": "Zone 05 — Eastern Suburban Ridge",
        "expected_pressure": 21.0,
        "landmark": "Suburban Ridge Sub-Distribution Vault",
        "gps": "6.9335° N, 79.9815° E",
    },
    "J_3000": {
        "zone_id": "Zone 06",
        "dma_id": "DMA 02",
        "name": "Zone 06 — Welivita Highway Exit",
        "expected_pressure": 21.2,
        "landmark": "Welivita Highway Interchange Chamber",
        "gps": "6.9320° N, 79.9860° E",
    },
}

NODE_KEYS_ORDER = ["J_10", "J_100", "J_500", "J_1200", "J_2200", "J_3000"]


# ==============================================================================
# Simulation Data Handler (Raw CSV or Synthetic Fallback)
# ==============================================================================
class SimulationDataLoader:
    """
    Loads pressure timesteps from data/raw_simulations/ or computes synthetic
    hydraulic cycles based on EPANET diurnal baseline curves.
    """

    def __init__(self, raw_dir: Optional[Path] = None):
        self.raw_dir = raw_dir or (PROJECT_ROOT / "data" / "raw_simulations")
        self.baseline_csv = self.raw_dir / "baseline_normal.csv"
        self.bypass_csv = self.raw_dir / "bypass_J100.csv"
        self.baseline_rows: List[Dict[str, float]] = []
        self.bypass_rows: List[Dict[str, float]] = []
        self.has_csv = False

        self._load_csv_data()

    def _load_csv_data(self) -> None:
        try:
            if self.baseline_csv.exists():
                import pandas as pd
                df_base = pd.read_csv(self.baseline_csv, nrows=100)
                available_nodes = [n for n in NODE_KEYS_ORDER if n in df_base.columns]
                if available_nodes:
                    self.baseline_rows = df_base[available_nodes].to_dict(orient="records")
                    self.has_csv = True

            if self.bypass_csv.exists():
                import pandas as pd
                df_byp = pd.read_csv(self.bypass_csv, nrows=100)
                available_nodes = [n for n in NODE_KEYS_ORDER if n in df_byp.columns]
                if available_nodes:
                    self.bypass_rows = df_byp[available_nodes].to_dict(orient="records")
        except Exception as e:
            # Fall back transparently to synthetic generator
            self.has_csv = False

    def get_readings(
        self,
        node_id: str,
        mode: str,
        step: int,
    ) -> Tuple[float, float, str, Optional[float]]:
        """
        Returns (observed_pressure, expected_pressure, iso_timestamp, hours_since_supply_start).
        """
        cfg = JUNCTION_CONFIGS.get(node_id, JUNCTION_CONFIGS["J_100"])
        base_exp = cfg["expected_pressure"]

        # Diurnal wave variation (±0.3 m diurnal variation across steps)
        diurnal_delta = round(0.25 * math.sin((step % 48) * (2 * math.pi / 48)), 2)
        expected_p = round(base_exp + diurnal_delta, 2)

        now_utc = datetime.datetime.now(datetime.timezone.utc)

        # ----------------------------------------------------------------------
        # Mode: Bypass Anomaly [f]
        # ----------------------------------------------------------------------
        if mode == "f":
            if node_id == "J_100":
                # Drop pressure by 6.0m: canonical 15.2m vs 21.2m
                observed_p = round(expected_p - 6.0 + random.uniform(-0.04, 0.04), 2)
                if step == 0:
                    observed_p = 15.2
                    expected_p = 21.2
            else:
                observed_p = round(expected_p - 0.2 + random.uniform(-0.05, 0.05), 2)

            timestamp = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            return observed_p, expected_p, timestamp, None

        # ----------------------------------------------------------------------
        # Mode: Refill Surge Transient [r]
        # ----------------------------------------------------------------------
        elif mode == "r":
            # Supply opening at 06:00: transient refill drop (-4.5m)
            observed_p = round(expected_p - 4.5 + random.uniform(-0.08, 0.08), 2)
            # Timestamp formatted within morning 06:00-06:45 window
            morning_sec = (step * 2) % 60
            morning_dt = now_utc.replace(hour=6, minute=25, second=morning_sec)
            timestamp = morning_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            # 25 min elapsed since 06:00 supply opening = 0.42 hours
            hours_since_supply_start = 0.42
            return observed_p, expected_p, timestamp, hours_since_supply_start

        # ----------------------------------------------------------------------
        # Mode: Normal Baseline [n]
        # ----------------------------------------------------------------------
        else:
            # Nominal pressure conforms within ±0.2m digital twin tolerance
            observed_p = round(expected_p - 0.2 + random.uniform(-0.08, 0.08), 2)
            timestamp = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            return observed_p, expected_p, timestamp, None


# ==============================================================================
# Non-Blocking Keyboard Input Controller
# ==============================================================================
class KeyboardController:
    """
    Non-blocking keyboard listener that captures key events ('n', 'f', 'r', 'q')
    without blocking the continuous streaming loop.
    """

    def __init__(self):
        self._current_command: Optional[str] = None
        self._running = True
        self._lock = threading.Lock()

        # Start background input listener thread
        self._thread = threading.Thread(target=self._listen_keys, daemon=True)
        self._thread.start()

    def _listen_keys(self) -> None:
        if sys.platform == "win32":
            import msvcrt
            while self._running:
                try:
                    if msvcrt.kbhit():
                        ch = msvcrt.getch()
                        char_str = ch.decode("utf-8", errors="ignore").lower()
                        with self._lock:
                            self._current_command = char_str
                    time.sleep(0.05)
                except Exception:
                    time.sleep(0.1)
        else:
            # Posix fallback (stdin loop)
            import select
            while self._running:
                try:
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if rlist:
                        line = sys.stdin.readline().strip().lower()
                        if line:
                            with self._lock:
                                self._current_command = line[0]
                except Exception:
                    time.sleep(0.1)

    def pop_command(self) -> Optional[str]:
        with self._lock:
            cmd = self._current_command
            self._current_command = None
            return cmd

    def stop(self) -> None:
        self._running = False


# ==============================================================================
# Terminal Presentation Functions
# ==============================================================================
def print_banner(active_mode: str, active_node: str, endpoint: str, is_auto: bool = False) -> None:
    mode_titles = {
        "n": f"{Color.GREEN}NORMAL BASELINE (All Green - Safe){Color.RESET}",
        "f": f"{Color.RED}UNAUTHORIZED BYPASS AT J_100 (Red Alert -6.0m){Color.RESET}",
        "r": f"{Color.YELLOW}MORNING REFILL SURGE (Transient Filter Active){Color.RESET}",
        "auto": f"{Color.MAGENTA}AUTOMATED SCENARIO CYCLE (Normal -> Bypass -> Refill Surge){Color.RESET}",
    }
    mode_label = mode_titles.get("auto" if is_auto else active_mode, active_mode)

    print(f"\n{Color.CYAN}{'=' * 84}{Color.RESET}")
    print(f"{Color.BOLD}{Color.WHITE}   NWSDB KADUWELA EAST — REAL-TIME PRESSURE TELEMETRY STREAMER{Color.RESET}")
    print(f"{Color.CYAN}{'=' * 84}{Color.RESET}")
    print(f"  Target Endpoint : {Color.BOLD}{endpoint}{Color.RESET}")
    print(f"  Active Node     : {Color.BOLD}{active_node}{Color.RESET} ({JUNCTION_CONFIGS[active_node]['name']})")
    print(f"  Streaming State : {mode_label}")
    print(f"  Stream Interval : {Color.BOLD}2.0 seconds{Color.RESET}")
    print(f"{Color.CYAN}{'-' * 84}{Color.RESET}")
    print(f"  {Color.BOLD}INTERACTIVE CONTROLS:{Color.RESET}")
    print(f"    Press {Color.BOLD}[n]{Color.RESET} : Stream Normal Baseline Data (All Green)")
    print(f"    Press {Color.BOLD}[f]{Color.RESET} : Inject Unauthorized Bypass at J_100 (-6.0m Drop -> Red Alert)")
    print(f"    Press {Color.BOLD}[r]{Color.RESET} : Inject Morning Refill Surge (Tests Refill Transient Filter)")
    print(f"    Press {Color.BOLD}[a]{Color.RESET} : Resume Automated Demo Cycle (Normal -> Bypass -> Refill)")
    print(f"    Press {Color.BOLD}[1-6]{Color.RESET}: Switch Node (1: J_10, 2: J_100, 3: J_500, 4: J_1200, 5: J_2200, 6: J_3000)")
    print(f"    Press {Color.BOLD}[q]{Color.RESET} : Quit Streamer")
    print(f"{Color.CYAN}{'=' * 84}{Color.RESET}\n")


def log_packet_transmission(
    seq: int,
    payload: Dict[str, Any],
    mode: str,
    resp: Optional[requests.Response] = None,
    error: Optional[str] = None,
    elapsed_ms: float = 0.0,
) -> None:
    node_id = payload.get("node_id", "J_100")
    cfg = JUNCTION_CONFIGS.get(node_id, JUNCTION_CONFIGS["J_100"])
    obs_p = payload.get("observed_pressure", 0.0)
    exp_p = payload.get("expected_pressure", 0.0)
    delta_p = round(obs_p - exp_p, 2)
    timestamp = payload.get("timestamp", "")
    hours_open = payload.get("hours_since_supply_start")

    # Mode badge
    if mode == "f":
        mode_badge = f"{Color.BG_RED}{Color.WHITE}{Color.BOLD} [MODE: BYPASS THEFT] {Color.RESET}"
    elif mode == "r":
        mode_badge = f"{Color.BG_YELLOW}{Color.WHITE}{Color.BOLD} [MODE: REFILL SURGE] {Color.RESET}"
    else:
        mode_badge = f"{Color.BG_GREEN}{Color.WHITE}{Color.BOLD} [MODE: NORMAL BASELINE] {Color.RESET}"

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"{Color.CYAN}{'-' * 84}{Color.RESET}")
    print(f"[{now_str}] {Color.BOLD}OUTGOING PACKET #{seq}{Color.RESET} {mode_badge}")
    print(f"  Payload Structure:")
    print(f"    node_id           : {Color.BOLD}{node_id}{Color.RESET} ({cfg['zone_id']} | {cfg['name']})")
    print(f"    observed_pressure : {Color.BOLD}{obs_p:.2f} m{Color.RESET} (Expected: {exp_p:.2f} m | Delta P: {Color.RED if delta_p < -1.0 else Color.GREEN}{delta_p:+.2f} m{Color.RESET})")
    print(f"    timestamp         : {timestamp}" + (f" (Hours since supply start: {hours_open}h)" if hours_open else ""))

    if error:
        print(f"\n  {Color.RED}FastAPI Response [CONNECTION ERROR]:{Color.RESET}")
        print(f"    Error Details     : {error}")
        print(f"    Hint              : Ensure FastAPI server is running (e.g. uvicorn app.main:app --port 8000)")
        return

    if resp is not None:
        status_code = resp.status_code
        status_color = Color.GREEN if status_code == 200 else Color.RED
        print(f"\n  FastAPI Response [{status_color}HTTP {status_code} {resp.reason}{Color.RESET}] ({elapsed_ms:.1f} ms):")

        try:
            data = resp.json()
            score = data.get("fraud_risk_score", 0.0)
            classification = data.get("classification", "unknown")
            is_transient = data.get("transient_dampening_active", False)
            action = data.get("recommended_action", "None")
            location = data.get("location") or {}

            # Score color coding
            if score >= 70.0:
                score_str = f"{Color.RED}{Color.BOLD}{score:.1f}% [CRITICAL FRAUD ALERT - DISPATCH]{Color.RESET}"
            elif score >= 40.0:
                score_str = f"{Color.YELLOW}{Color.BOLD}{score:.1f}% [CAUTION / WARNING]{Color.RESET}"
            else:
                score_str = f"{Color.GREEN}{Color.BOLD}{score:.1f}% [NOMINAL / SAFE]{Color.RESET}"

            print(f"    Fraud Risk Score  : {score_str}")
            print(f"    Classification    : {Color.BOLD}{classification}{Color.RESET}")
            print(f"    Refill Transient  : {Color.YELLOW if is_transient else Color.DIM}{'ACTIVE (False Alarm Suppressed)' if is_transient else 'Inactive (Normal Window)'}{Color.RESET}")
            print(f"    Field Action      : {action}")
            if location.get("latitude") and location.get("longitude"):
                print(f"    GPS Target Coord  : [{location.get('latitude'):.5f}, {location.get('longitude'):.5f}] ({location.get('landmark', '')})")
        except Exception:
            print(f"    Body: {resp.text[:120]}")


# ==============================================================================
# Core Live Streaming Engine
# ==============================================================================
def run_live_streamer(
    url: str = "http://localhost:8000/api/v1/sensors/telemetry",
    interval: float = 2.0,
    initial_mode: str = "n",
    initial_node: str = "J_100",
    max_count: Optional[int] = None,
) -> None:
    """
    Main telemetry streaming loop.
    Sends a telemetry payload every `interval` seconds, while continuously
    checking for keyboard input controls ('n', 'f', 'r', 'a', 'q').
    Supports automated cyclic demonstration mode ('auto' or 'a').
    """
    data_loader = SimulationDataLoader()
    keyboard = KeyboardController()

    raw_mode = initial_mode.lower()
    is_auto = raw_mode in ("auto", "a")
    mode = "n" if is_auto else raw_mode
    active_node = initial_node
    step = 0
    seq = 0
    auto_step = 0

    print_banner(mode, active_node, url, is_auto=is_auto)

    node_shortcuts = {
        "1": "J_10",
        "2": "J_100",
        "3": "J_500",
        "4": "J_1200",
        "5": "J_2200",
        "6": "J_3000",
    }

    try:
        while True:
            # 1. Process any pending interactive key presses
            cmd = keyboard.pop_command()
            while cmd:
                if cmd == "a":
                    is_auto = True
                    auto_step = 0
                    print(f"\n{Color.BG_BLUE}{Color.WHITE}{Color.BOLD} >>> [CONTROL: 'a'] RESUMED AUTOMATED DEMO CYCLE (Normal -> Bypass -> Refill) <<< {Color.RESET}\n")
                elif cmd == "n":
                    is_auto = False
                    mode = "n"
                    print(f"\n{Color.BG_GREEN}{Color.WHITE}{Color.BOLD} >>> [CONTROL: 'n'] SWITCHED TO MANUAL NORMAL BASELINE (All Green) <<< {Color.RESET}\n")
                elif cmd == "f":
                    is_auto = False
                    mode = "f"
                    active_node = "J_100"  # Focus on J_100 bypass
                    print(f"\n{Color.BG_RED}{Color.WHITE}{Color.BOLD} >>> [CONTROL: 'f'] INJECTED MANUAL BYPASS AT J_100 (-6.0m Drop) <<< {Color.RESET}\n")
                elif cmd == "r":
                    is_auto = False
                    mode = "r"
                    print(f"\n{Color.BG_YELLOW}{Color.WHITE}{Color.BOLD} >>> [CONTROL: 'r'] INJECTED MANUAL MORNING REFILL SURGE (Transient Active) <<< {Color.RESET}\n")
                elif cmd in node_shortcuts:
                    active_node = node_shortcuts[cmd]
                    print(f"\n{Color.BLUE}{Color.BOLD} >>> [SWITCHED NODE] Active sensor node is now: {active_node} ({JUNCTION_CONFIGS[active_node]['name']}) <<< {Color.RESET}\n")
                elif cmd == "q":
                    print(f"\n{Color.BOLD}Exiting live telemetry streamer. Goodbye!{Color.RESET}")
                    return
                cmd = keyboard.pop_command()

            # Handle automatic cycling progression if in auto mode
            if is_auto:
                auto_step += 1
                cycle_pos = ((auto_step - 1) % 17) + 1  # 1..17 loop
                if cycle_pos == 1:
                    mode = "n"
                    print(f"\n{Color.BG_GREEN}{Color.WHITE}{Color.BOLD} >>> [AUTO PHASE 1/3] NORMAL BASELINE TELEMETRY (All Green Zones) <<< {Color.RESET}\n")
                elif cycle_pos == 6:
                    mode = "f"
                    active_node = "J_100"
                    print(f"\n{Color.BG_RED}{Color.WHITE}{Color.BOLD} >>> [AUTO PHASE 2/3] INJECTING BYPASS AT J_100 (-6.0m -> Red Alert Triggered) <<< {Color.RESET}\n")
                elif cycle_pos == 13:
                    mode = "r"
                    print(f"\n{Color.BG_YELLOW}{Color.WHITE}{Color.BOLD} >>> [AUTO PHASE 3/3] MORNING REFILL SURGE (Dampening False Alarms) <<< {Color.RESET}\n")

            seq += 1
            step += 1

            # 2. Build payload structure
            obs_p, exp_p, timestamp, hours_open = data_loader.get_readings(active_node, mode, step)
            cfg = JUNCTION_CONFIGS.get(active_node, JUNCTION_CONFIGS["J_100"])

            payload: Dict[str, Any] = {
                "node_id": active_node,
                "zone_id": cfg["zone_id"],
                "observed_pressure": obs_p,
                "expected_pressure": exp_p,
                "timestamp": timestamp,
            }
            if hours_open is not None:
                payload["hours_since_supply_start"] = hours_open

            # 3. Transmit HTTP POST to FastAPI
            t_start = time.perf_counter()
            resp: Optional[requests.Response] = None
            err_msg: Optional[str] = None
            try:
                resp = requests.post(url, json=payload, timeout=5.0)
            except Exception as e:
                err_msg = str(e)
            t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

            # 4. Print clean terminal logs
            log_packet_transmission(
                seq=seq,
                payload=payload,
                mode=mode,
                resp=resp,
                error=err_msg,
                elapsed_ms=t_elapsed_ms,
            )

            # Check if execution count limit reached (for automated testing)
            if max_count is not None and seq >= max_count:
                break

            # 5. Sleep with periodic key check (every 100ms up to interval)
            elapsed_sleep = 0.0
            sleep_step = 0.1
            while elapsed_sleep < interval:
                time.sleep(sleep_step)
                elapsed_sleep += sleep_step
                cmd = keyboard.pop_command()
                if cmd:
                    if cmd == "a":
                        is_auto = True
                        auto_step = 0
                        print(f"\n{Color.BG_BLUE}{Color.WHITE}{Color.BOLD} >>> [CONTROL: 'a'] RESUMED AUTOMATED DEMO CYCLE (Normal -> Bypass -> Refill) <<< {Color.RESET}\n")
                    elif cmd == "n":
                        is_auto = False
                        mode = "n"
                        print(f"\n{Color.BG_GREEN}{Color.WHITE}{Color.BOLD} >>> [CONTROL: 'n'] SWITCHED TO MANUAL NORMAL BASELINE (All Green) <<< {Color.RESET}\n")
                    elif cmd == "f":
                        is_auto = False
                        mode = "f"
                        active_node = "J_100"
                        print(f"\n{Color.BG_RED}{Color.WHITE}{Color.BOLD} >>> [CONTROL: 'f'] INJECTED MANUAL BYPASS AT J_100 (-6.0m Drop) <<< {Color.RESET}\n")
                    elif cmd == "r":
                        is_auto = False
                        mode = "r"
                        print(f"\n{Color.BG_YELLOW}{Color.WHITE}{Color.BOLD} >>> [CONTROL: 'r'] INJECTED MANUAL MORNING REFILL SURGE (Transient Active) <<< {Color.RESET}\n")
                    elif cmd in node_shortcuts:
                        active_node = node_shortcuts[cmd]
                        print(f"\n{Color.BLUE}{Color.BOLD} >>> [SWITCHED NODE] Active sensor node is now: {active_node} ({JUNCTION_CONFIGS[active_node]['name']}) <<< {Color.RESET}\n")
                    elif cmd == "q":
                        print(f"\n{Color.BOLD}Exiting live telemetry streamer. Goodbye!{Color.RESET}")
                        return
                    break

    except KeyboardInterrupt:
        print(f"\n{Color.BOLD}Streamer interrupted by user. Exiting cleanly...{Color.RESET}")
    finally:
        keyboard.stop()


# ==============================================================================
# CLI Entrypoint
# ==============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Continuous Live Pressure Telemetry Streamer for Kaduwela DMAs"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/api/v1/sensors/telemetry",
        help="FastAPI telemetry ingestion endpoint (default: http://localhost:8000/api/v1/sensors/telemetry)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Streaming interval in seconds between outgoing packets (default: 2.0)",
    )
    parser.add_argument(
        "--mode",
        choices=["n", "f", "r", "auto", "a"],
        default="n",
        help="Initial streaming mode: 'auto' (automatic cycle), 'n' (normal baseline), 'f' (bypass theft at J_100), 'r' (refill surge)",
    )
    parser.add_argument(
        "--node",
        choices=NODE_KEYS_ORDER,
        default="J_100",
        help="Initial active sensor node ID (default: J_100)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Optional maximum number of packets to stream before terminating (useful for automated testing)",
    )

    args = parser.parse_args()

    run_live_streamer(
        url=args.url,
        interval=args.interval,
        initial_mode=args.mode,
        initial_node=args.node,
        max_count=args.count,
    )


if __name__ == "__main__":
    main()
