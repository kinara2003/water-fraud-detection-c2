#!/usr/bin/env bash
# ==============================================================================
# scripts/backup_and_restore.sh
# NWSDB Water Fraud Platform Backup & Restore POSIX Wrapper
# Component 2: Application State Preservation & Model Integrity Validation
# ==============================================================================

set -euo pipefail

# Resolve script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Usage banner
show_usage() {
    cat << EOF
Usage:
  ./scripts/backup_and_restore.sh --backup [--dry-run]
  ./scripts/backup_and_restore.sh --restore <tarball> [--dry-run]

Operations:
  --backup              Archive .env, data/, models/*.joblib, and reports/ into backups/
  --restore <tarball>   Verify checksums, validate directory structure, restore state,
                        and run automated model pickle signature validations
  --dry-run             Perform simulation and validation without modifying target files
  -h, --help            Show this help message
EOF
}

if [[ $# -eq 0 ]]; then
    show_usage
    exit 1
fi

# Locate Python 3 binary (prefer project virtual environment)
PYTHON_BIN=""
if [[ -f "${PROJECT_ROOT}/venv/bin/python" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/venv/bin/python"
elif [[ -f "${PROJECT_ROOT}/venv/Scripts/python.exe" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/venv/Scripts/python.exe"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
else
    echo "[ERROR] Python 3 not found in virtual environment or system PATH." >&2
    exit 1
fi

# Translate script path if invoking a Windows .exe python from WSL or Git Bash
TARGET_SCRIPT="${SCRIPT_DIR}/backup_and_restore.py"
if [[ "${PYTHON_BIN}" == *.exe ]]; then
    if command -v cygpath &>/dev/null; then
        TARGET_SCRIPT="$(cygpath -w "${TARGET_SCRIPT}")"
    elif command -v wslpath &>/dev/null; then
        TARGET_SCRIPT="$(wslpath -w "${TARGET_SCRIPT}")"
    fi
fi

# Execute Python engine with passed arguments
exec "${PYTHON_BIN}" "${TARGET_SCRIPT}" "$@"
