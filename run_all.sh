#!/usr/bin/env bash
# ==============================================================================
# run_all.sh - Linux & macOS Launch Script for NWSDB WATERGUARD (Component 2)
# ==============================================================================

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

BACKEND_PID=""
FRONTEND_PID=""

# ANSI Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

cleanup() {
    echo ""
    echo -e "${YELLOW}==============================================================================${NC}"
    echo -e "${YELLOW} Shutting down WATERGUARD services...${NC}"
    echo -e "${YELLOW}==============================================================================${NC}"
    
    # Terminate Frontend process
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo -e " [*] Stopping Vite dev server (PID: ${FRONTEND_PID})..."
        kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    fi

    # Terminate Backend process
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo -e " [*] Stopping FastAPI backend (PID: ${BACKEND_PID})..."
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
    fi

    sleep 1

    # Force cleanup any lingering processes bound to ports 8000 or 5173
    if command -v lsof >/dev/null 2>&1; then
        lsof -ti:8000 | xargs kill -9 2>/dev/null || true
        lsof -ti:5173 | xargs kill -9 2>/dev/null || true
    elif command -v fuser >/dev/null 2>&1; then
        fuser -k 8000/tcp 2>/dev/null || true
        fuser -k 5173/tcp 2>/dev/null || true
    fi

    echo -e "${GREEN} [*] All services terminated cleanly.${NC}"
    exit 0
}

# Trap termination signals
trap cleanup INT TERM EXIT

echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "${BOLD}   NWSDB WATERGUARD (COMPONENT 2) -- SERVICE LAUNCH ORCHESTRATOR${NC}"
echo -e "${CYAN}==============================================================================${NC}"
echo ""

# 1. Verify Virtual Environment
if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    echo -e "${GREEN}[*] Activating virtual environment (venv)...${NC}"
    source venv/bin/activate
elif [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
    echo -e "${GREEN}[*] Activating virtual environment (.venv)...${NC}"
    source .venv/bin/activate
else
    echo -e "${YELLOW}[!] Virtual environment not found. Creating new venv in ./venv...${NC}"
    python3 -m venv venv
    source venv/bin/activate
    if [ -f "requirements.txt" ]; then
        echo -e "${GREEN}[*] Installing dependencies from requirements.txt...${NC}"
        pip install --upgrade pip
        pip install -r requirements.txt
    fi
fi

# 2. Start FastAPI Backend on Port 8000 in Background
echo -e "${GREEN}[*] Starting FastAPI backend on port 8000 in the background...${NC}"
uvicorn app.main:app --port 8000 &
BACKEND_PID=$!
echo -e "    FastAPI process started with PID: ${BOLD}${BACKEND_PID}${NC}"

# Wait for backend health probe
echo -e "    Waiting for backend to bind port 8000..."
for i in {1..20}; do
    if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo -e "${GREEN}    [OK] FastAPI backend is ready and healthy.${NC}"
        break
    fi
    sleep 0.5
done

# 3. Navigate to frontend/ and check node_modules
cd "$PROJECT_ROOT/frontend"
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}[*] node_modules directory missing in frontend/. Running npm install...${NC}"
    npm install
fi

# 4. Start Vite Dev Server on Port 5173
echo -e "${GREEN}[*] Launching Vite frontend dev server on port 5173...${NC}"
npm run dev -- --port 5173 &
FRONTEND_PID=$!
echo -e "    Vite dev server started with PID: ${BOLD}${FRONTEND_PID}${NC}"

# 5. Open Default Browser
sleep 1.5
echo -e "${GREEN}[*] Opening http://localhost:5173 in default browser...${NC}"
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:5173" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
    open "http://localhost:5173" >/dev/null 2>&1 &
fi

# 6. Print Summary Instructions and Wait
echo ""
echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo -e "${BOLD} WATERGUARD (Component 2) SERVICES ACTIVE:${NC}"
echo -e "   - Frontend Dashboard: ${BOLD}${GREEN}http://localhost:5173${NC}"
echo -e "   - FastAPI Swagger UI: ${BOLD}${GREEN}http://127.0.0.1:8000/docs${NC}"
echo -e "   - Telemetry API:      ${BOLD}${GREEN}http://127.0.0.1:8000/api/v1/zones${NC}"
echo ""
echo -e " Press ${BOLD}${RED}[Ctrl+C]${NC} to gracefully stop both frontend and backend."
echo -e "${BOLD}${CYAN}==============================================================================${NC}"
echo ""

# Block until user interrupts with Ctrl+C
wait "$FRONTEND_PID"
