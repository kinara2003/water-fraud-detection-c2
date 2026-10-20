#!/usr/bin/env bash
# ==============================================================================
# run_live_system.sh
# NWSDB Water Fraud Platform — Automated Full-System Launcher (Linux/macOS)
# Component 2: Hydraulic Loss Pinpointing & Real-Time Edge Analytics
# ==============================================================================

# Exit immediately if an unhandled error occurs outside cleanup
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

BACKEND_PID=""
FRONTEND_PID=""
STREAMER_PID=""

# ------------------------------------------------------------------------------
# Clean Shutdown Handler
# Catches Ctrl+C (SIGINT), SIGTERM, and EXIT to terminate all 3 sub-processes
# simultaneously without leaving orphan or zombie server processes.
# ------------------------------------------------------------------------------
cleanup() {
    # Disable strict error checking during cleanup to allow full process sweeping
    set +e
    echo ""
    echo "======================================================================"
    echo " [SHUTDOWN] Terminating all sub-processes simultaneously..."
    echo "======================================================================"

    # Disable traps to avoid duplicate execution
    trap - INT TERM EXIT

    # 1. Terminate Telemetry Streamer
    if [[ -n "${STREAMER_PID:-}" ]] && kill -0 "$STREAMER_PID" 2>/dev/null; then
        echo " - Stopping Telemetry Streamer (PID: $STREAMER_PID)..."
        kill -TERM "$STREAMER_PID" 2>/dev/null || true
    fi

    # 2. Terminate React Frontend Dev Server
    if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo " - Stopping React Frontend (PID: $FRONTEND_PID)..."
        kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    fi

    # 3. Terminate FastAPI Backend Server
    if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo " - Stopping FastAPI Backend (PID: $BACKEND_PID)..."
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
    fi

    # 4. Port-based cleanup fallback to prevent port collisions on next launch
    if command -v lsof &>/dev/null; then
        for port in 8000 5173; do
            lingering_pids=$(lsof -ti :"$port" 2>/dev/null || true)
            if [[ -n "$lingering_pids" ]]; then
                echo "$lingering_pids" | xargs kill -9 2>/dev/null || true
            fi
        done
    elif command -v fuser &>/dev/null; then
        fuser -k 8000/tcp 2>/dev/null || true
        fuser -k 5173/tcp 2>/dev/null || true
    fi

    # 5. Process group termination
    kill 0 2>/dev/null || true

    echo "[OK] All sub-processes terminated cleanly."
    exit 0
}

# Register signal traps for clean multi-process shutdown
trap cleanup INT TERM EXIT

echo "======================================================================"
echo "   NWSDB KADUWELA EAST — WATER FRAUD DETECTION PLATFORM LAUNCHER"
echo "======================================================================"

# ------------------------------------------------------------------------------
# 1. Activate Python Environment
# ------------------------------------------------------------------------------
echo "[1/4] Activating Python virtual environment..."
PYTHON_BIN="python3"
if [[ -f "${PROJECT_ROOT}/venv/bin/activate" ]]; then
    source "${PROJECT_ROOT}/venv/bin/activate"
    PYTHON_BIN="${PROJECT_ROOT}/venv/bin/python"
elif [[ -f "${PROJECT_ROOT}/venv/Scripts/activate" ]]; then
    source "${PROJECT_ROOT}/venv/Scripts/activate"
    PYTHON_BIN="${PROJECT_ROOT}/venv/Scripts/python"
elif [[ -f "${PROJECT_ROOT}/.venv/bin/activate" ]]; then
    source "${PROJECT_ROOT}/.venv/bin/activate"
    PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
fi

UVICORN_BIN="uvicorn"
if [[ -f "${PROJECT_ROOT}/venv/bin/uvicorn" ]]; then
    UVICORN_BIN="${PROJECT_ROOT}/venv/bin/uvicorn"
elif [[ -f "${PROJECT_ROOT}/venv/Scripts/uvicorn.exe" ]]; then
    UVICORN_BIN="${PROJECT_ROOT}/venv/Scripts/uvicorn.exe"
fi

# ------------------------------------------------------------------------------
# 2. Launch FastAPI Backend
# ------------------------------------------------------------------------------
echo "[2/4] Starting FastAPI backend on http://localhost:8000..."
"$UVICORN_BIN" app.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "      FastAPI backend started with PID: $BACKEND_PID"

# ------------------------------------------------------------------------------
# 3. Launch React Frontend
# ------------------------------------------------------------------------------
echo "[3/4] Starting React frontend dev server on http://localhost:5173..."
(
    cd "${PROJECT_ROOT}/frontend"
    npm run dev
) &
FRONTEND_PID=$!
echo "      React frontend started with PID: $FRONTEND_PID"

# ------------------------------------------------------------------------------
# 4. Wait 4 seconds for servers to initialize
# ------------------------------------------------------------------------------
echo "[4/4] Waiting 4 seconds for servers to initialize..."
sleep 4

# ------------------------------------------------------------------------------
# 5. Open Default Web Browser directly to http://localhost:5173
# ------------------------------------------------------------------------------
echo "Opening default web browser to http://localhost:5173..."
if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:5173" >/dev/null 2>&1 &
elif command -v open &>/dev/null; then
    open "http://localhost:5173" >/dev/null 2>&1 &
elif command -v wslview &>/dev/null; then
    wslview "http://localhost:5173" >/dev/null 2>&1 &
else
    "$PYTHON_BIN" -m webbrowser "http://localhost:5173" >/dev/null 2>&1 &
fi

# ------------------------------------------------------------------------------
# 6. Launch Telemetry Streamer in Automated Demo Mode
# ------------------------------------------------------------------------------
echo ""
echo "======================================================================"
echo " Launching Telemetry Streamer in Automated Mode (--mode auto)"
echo " Streaming to: http://localhost:8000/api/v1/sensors/telemetry"
echo " Interactive keys: [n] Normal | [f] Bypass | [r] Refill | [a] Auto | [q] Quit"
echo " Press Ctrl+C at any time to shut down all processes."
echo "======================================================================"
echo ""

"$PYTHON_BIN" "${PROJECT_ROOT}/src/live_streamer.py" --mode auto &
STREAMER_PID=$!

# Wait for telemetry streamer; trap handles Ctrl+C and exit
wait "$STREAMER_PID"
