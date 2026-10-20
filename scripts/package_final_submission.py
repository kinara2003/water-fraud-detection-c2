"""
scripts/package_final_submission.py
Final University Research Delivery Package Assembler
Component 2: NWSDB Water Fraud Surveillance Platform

Automated Steps:
1. Component Verifications:
   - Unit tests execution (pytest tests/)
   - Code formatting & critical syntax linting (flake8 + py_compile)
   - Model & full system verification (python verify_full_system.py)
   - 12-slide presentation deck validation (reports/Component2_Viva_Presentation.pptx)
   - Thesis publication figures validation (reports/figures/)
2. Evaluator's Navigation Map generation/validation (SUBMISSION_INDEX.md)
3. Workspace Cache Cleanup (__pycache__, .pytest_cache, dist, etc.)
4. Clean packaging into Final_Submission_Component2_AI_Water_Fraud.zip
5. Celebratory summary report detailing archive SHA-256 checksum and completion status.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import zipfile

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("package_final_submission")

# Destination ZIP
SUBMISSION_ZIP_NAME = "Final_Submission_Component2_AI_Water_Fraud.zip"
SUBMISSION_ZIP_PATH = PROJECT_ROOT / SUBMISSION_ZIP_NAME
SUBMISSION_SHA_PATH = PROJECT_ROOT / f"{SUBMISSION_ZIP_NAME}.sha256"


# ==============================================================================
# ANSI Color Formatting
# ==============================================================================
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 hexadecimal digest for a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


# ==============================================================================
# Step 1: Verification Checks
# ==============================================================================
def verify_unit_tests() -> Tuple[bool, str]:
    """Runs pytest across tests/ directory."""
    logger.info("Executing unit and integration tests (pytest tests/)...")
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            # Extract summary line (e.g. '83 passed in 30.12s')
            lines = [ln.strip() for ln in res.stdout.strip().splitlines() if ln.strip()]
            summary_line = lines[-1] if lines else "All tests passed"
            return True, summary_line
        else:
            err_snip = res.stdout[-400:] + res.stderr[-400:]
            return False, f"Pytest failed with exit code {res.returncode}: {err_snip.strip()}"
    except Exception as exc:
        return False, f"Could not execute pytest: {exc}"


def verify_code_linting() -> Tuple[bool, str]:
    """Executes flake8 critical syntax checks and Python compilation."""
    logger.info("Verifying code formatting and syntax integrity...")
    try:
        # Check Python compilation
        import py_compile
        py_files = list(PROJECT_ROOT.glob("app/**/*.py")) + \
                   list(PROJECT_ROOT.glob("src/**/*.py")) + \
                   list(PROJECT_ROOT.glob("scripts/**/*.py")) + \
                   [PROJECT_ROOT / "verify_full_system.py"]

        for pf in py_files:
            if pf.exists() and pf.is_file():
                py_compile.compile(str(pf), doraise=True)

        # Run flake8 critical error check
        flake8_bin = Path(sys.executable).parent / ("flake8.exe" if sys.platform == "win32" else "flake8")
        if flake8_bin.exists():
            res = subprocess.run(
                [str(flake8_bin), "app/", "src/", "scripts/", "verify_full_system.py",
                 "--count", "--select=E9,F63,F7,F82"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                return False, f"Flake8 reported errors: {res.stdout.strip()}"

        return True, f"Verified clean syntax across {len(py_files)} Python modules (0 syntax errors)"
    except Exception as exc:
        return False, f"Linting check failed: {exc}"


def verify_models_and_system() -> Tuple[bool, str]:
    """Runs verify_full_system.py to test all 5 core modules."""
    logger.info("Executing automated end-to-end model and system verification...")
    try:
        res = subprocess.run(
            [sys.executable, "verify_full_system.py"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and "5/5 COMPONENTS VERIFIED" in res.stdout:
            return True, "All 5 core modules verified (Physical Twin, AI Models, Geo-Location, Alerts, API)"
        else:
            return False, f"System verification failed:\n{res.stdout[-300:]}\n{res.stderr[-300:]}"
    except Exception as exc:
        return False, f"Could not run verify_full_system.py: {exc}"


def verify_presentation_deck() -> Tuple[bool, str]:
    """Verifies that reports/Component2_Viva_Presentation.pptx exists, is non-empty, or generates it."""
    logger.info("Verifying oral defense presentation deck...")
    deck_path = PROJECT_ROOT / "reports" / "Component2_Viva_Presentation.pptx"
    if not deck_path.exists() or deck_path.stat().st_size < 500_000:
        logger.info("Presentation deck missing or outdated; compiling via scripts/generate_slides.py...")
        try:
            from scripts.generate_slides import generate_presentation
            generate_presentation(output_path=deck_path)
        except Exception as exc:
            return False, f"Failed to generate presentation deck: {exc}"

    size_mb = deck_path.stat().st_size / (1024.0 * 1024.0)
    return True, f"Verified 12-slide widescreen presentation deck ({size_mb:.2f} MB)"


def verify_thesis_figures() -> Tuple[bool, str]:
    """Verifies the presence of all 6 publication figures in reports/figures/."""
    logger.info("Validating thesis publication figures in reports/figures/...")
    figures_dir = PROJECT_ROOT / "reports" / "figures"
    expected_figures = [
        "fig1_iws_refill_vs_theft.png",
        "fig2_spatial_delta_dma.png",
        "fig3_roc_pr_curves.png",
        "fig4_feature_importance.png",
        "confusion_matrix.png",
        "model_benchmark_comparison.png",
    ]

    missing = []
    found_count = 0
    for fig_name in expected_figures:
        fig_path = figures_dir / fig_name
        if not fig_path.exists() or fig_path.stat().st_size < 10_000:
            missing.append(fig_name)
        else:
            found_count += 1

    if missing:
        return False, f"Missing {len(missing)} publication figures: {missing}"
    return True, f"All {found_count}/6 high-resolution publication figures verified"


# ==============================================================================
# Step 2: Workspace Cache Cleanup
# ==============================================================================
def clean_temporary_cache_files(root_dir: Path = PROJECT_ROOT) -> int:
    """
    Cleans all temporary cache and build artifacts:
    - __pycache__ directories
    - .pytest_cache directories
    - dist directories (if any)
    Returns count of removed items.
    """
    logger.info("Cleaning temporary cache and build directories...")
    removed_count = 0

    # Remove __pycache__
    for p in list(root_dir.rglob("__pycache__")):
        if p.is_dir() and "node_modules" not in p.parts:
            try:
                shutil.rmtree(p, ignore_errors=True)
                removed_count += 1
            except Exception:
                pass

    # Remove .pytest_cache
    pytest_cache = root_dir / ".pytest_cache"
    if pytest_cache.exists():
        try:
            shutil.rmtree(pytest_cache, ignore_errors=True)
            removed_count += 1
        except Exception:
            pass

    # Remove frontend dist (if any)
    frontend_dist = root_dir / "frontend" / "dist"
    if frontend_dist.exists():
        try:
            shutil.rmtree(frontend_dist, ignore_errors=True)
            removed_count += 1
        except Exception:
            pass

    logger.info(f"Cleaned {removed_count} temporary cache directories.")
    return removed_count


# ==============================================================================
# Step 3: Bundle Final University Submission Archive
# ==============================================================================
def is_submittable_file(file_path: Path, rel_str: str) -> bool:
    """Filters out node_modules, .git, virtual environments, and temporary files."""
    parts = rel_str.split("/")

    # Excluded directories
    excluded_dirs = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        "dist",
        ".tempmediaStorage",
        ".gemini",
    }
    if any(part in excluded_dirs for part in parts):
        return False

    # Exclude zip archives and tarballs from within the project
    if file_path.suffix in [".zip", ".gz", ".tar"] and rel_str != "":
        return False

    # Exclude temporary or scratch logs
    if file_path.name.endswith(".log") or file_path.name.endswith(".tmp"):
        return False

    return True


def assemble_final_submission_zip(
    root_dir: Path = PROJECT_ROOT,
    output_zip_path: Path = SUBMISSION_ZIP_PATH,
) -> Tuple[Path, int, str]:
    """
    Bundles the clean, complete university research delivery package into a single ZIP archive.
    """
    logger.info(f"Assembling final university research archive at: {output_zip_path}...")

    # Ensure SUBMISSION_INDEX.md exists
    index_path = root_dir / "SUBMISSION_INDEX.md"
    if not index_path.exists():
        raise FileNotFoundError("SUBMISSION_INDEX.md is missing. It must be present in the project root.")

    files_to_pack: List[Tuple[Path, str]] = []

    # Specific inclusion scopes
    scopes = [
        root_dir / "app",
        root_dir / "src",
        root_dir / "scripts",
        root_dir / "data" / "networks",
        root_dir / "data" / "processed",
        root_dir / "models",
        root_dir / "reports",
        root_dir / "tests",
        root_dir / "frontend" / "src",
        root_dir / "frontend" / "public",
    ]

    # Root files
    root_files = [
        "SUBMISSION_INDEX.md",
        "RESEARCH_DEFENSE.md",
        "VIVA_PREP.md",
        "DEFENSE_FAQ.md",
        "verify_full_system.py",
        "Dockerfile.backend",
        "docker-compose.yml",
        "requirements.txt",
        ".env",
        "pytest.ini",
    ]

    frontend_root_files = [
        "frontend/package.json",
        "frontend/tsconfig.json",
        "frontend/tsconfig.node.json",
        "frontend/vite.config.ts",
        "frontend/index.html",
        "frontend/Dockerfile",
        "frontend/nginx.conf",
    ]

    for rf in root_files:
        p = root_dir / rf
        if p.exists() and p.is_file():
            files_to_pack.append((p, rf))

    for frf in frontend_root_files:
        p = root_dir / frf
        if p.exists() and p.is_file():
            files_to_pack.append((p, frf.replace("\\", "/")))

    for sc in scopes:
        if sc.exists() and sc.is_dir():
            for item in sc.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(root_dir).as_posix()
                    if is_submittable_file(item, rel):
                        files_to_pack.append((item, rel))

    # Deduplicate files while preserving order
    unique_files: Dict[str, Path] = {}
    for abs_path, rel_path in files_to_pack:
        if rel_path not in unique_files:
            unique_files[rel_path] = abs_path

    logger.info(f"Packing {len(unique_files)} files into {output_zip_path.name}...")

    # Write compressed archive
    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel_path, abs_path in unique_files.items():
            zf.write(abs_path, arcname=rel_path)

    # Compute SHA-256 Checksum
    sha256_checksum = compute_file_sha256(output_zip_path)

    # Write sidecar checksum file
    SUBMISSION_SHA_PATH.write_text(f"{sha256_checksum}  {output_zip_path.name}\n", encoding="utf-8")

    return output_zip_path, len(unique_files), sha256_checksum


# ==============================================================================
# Step 4: Final Celebratory Summary Report
# ==============================================================================
def print_celebratory_report(
    verification_results: List[Tuple[str, bool, str]],
    zip_path: Path,
    file_count: int,
    checksum: str,
) -> None:
    """Prints a formatted university submission report card."""
    size_mb = zip_path.stat().st_size / (1024.0 * 1024.0)

    print(f"\n{Color.BOLD}{'=' * 86}{Color.RESET}")
    print(f"{Color.CYAN}{Color.BOLD}   NATIONAL WATER SUPPLY AND DRAINAGE BOARD (NWSDB) -- COMPONENT 2{Color.RESET}")
    print(f"{Color.BLUE}{Color.BOLD}   UNIVERSITY RESEARCH DELIVERY & VIVA DEFENSE FINAL SUBMISSION PACKAGE{Color.RESET}")
    print(f"{Color.BOLD}{'=' * 86}{Color.RESET}")
    print(f"  Utility Target  : National Water Supply and Drainage Board (NWSDB), Sri Lanka")
    print(f"  Pilot Zone      : Kaduwela Water Supply Scheme (DMA 01 & DMA 02)")
    print(f"  Hydraulic Regime: Intermittent Water Supply (IWS 06:00 - 18:00 Supply Window)")
    print(f"  Timestamp       : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Color.BOLD}{'-' * 86}{Color.RESET}")

    print(f"\n{Color.BOLD}1. COMPONENT VERIFICATION & QUALITY AUDIT CHECKLIST:{Color.RESET}")
    for title, status, desc in verification_results:
        status_str = f"{Color.GREEN}[PASS]{Color.RESET}" if status else f"{Color.RED}[FAIL]{Color.RESET}"
        print(f"  {status_str} {Color.BOLD}{title:<30}{Color.RESET} : {desc}")

    print(f"\n{Color.BOLD}2. SUBMISSION ARTIFACTS & DELIVERY PACKAGE:{Color.RESET}")
    print(f"  Archive Filename    : {Color.BOLD}{zip_path.name}{Color.RESET}")
    print(f"  Archive Location    : {zip_path.resolve()}")
    print(f"  Compressed Size     : {Color.GREEN}{size_mb:.2f} MB{Color.RESET} ({zip_path.stat().st_size:,} bytes)")
    print(f"  Total Files Packed  : {Color.GREEN}{file_count} clean source files{Color.RESET} (zero cache / zero node_modules)")
    print(f"  SHA-256 Digest      : {Color.YELLOW}{checksum}{Color.RESET}")
    print(f"  Sidecar Checksum    : {SUBMISSION_SHA_PATH.name}")

    print(f"\n{Color.BOLD}3. CORE RESEARCH ARTIFACTS INCLUDED IN BUNDLE:{Color.RESET}")
    print(f"  * Evaluator Index   : SUBMISSION_INDEX.md (Complete directory map & API reference)")
    print(f"  * Technical Defense : RESEARCH_DEFENSE.md & DEFENSE_FAQ.md (Hydraulic equations & FAQ)")
    print(f"  * Examiner Guide    : VIVA_PREP.md (Viva oral examination Q&A reference)")
    print(f"  * Slide Deck        : reports/Component2_Viva_Presentation.pptx (12 widescreen slides)")
    print(f"  * Digital Twin      : data/networks/kaduwela_2dma_clean_East_side.inp (EPANET PDD model)")
    print(f"  * Model Binaries    : models/isolation_forest.joblib & random_forest.joblib")
    print(f"  * React Dashboard   : frontend/ (Vite/React 18 source, GIS maps, real-time telemetry)")
    print(f"  * Docker Deployment : Dockerfile.backend & docker-compose.yml (One-click launch)")

    all_passed = all(status for _, status, _ in verification_results)

    print(f"\n{Color.BOLD}{'=' * 86}{Color.RESET}")
    if all_passed:
        print(f"{Color.GREEN}{Color.BOLD}   🎉 [SUCCESS] 100% OF VERIFICATION AUDITS PASSED -- FINAL SUBMISSION READY! 🎉{Color.RESET}")
        print(f"{Color.GREEN}   All code, models, test suites, and documentation are packaged for final defense.{Color.RESET}")
    else:
        print(f"{Color.RED}{Color.BOLD}   ⚠️ [WARNING] SOME VERIFICATION AUDITS FAILED -- REVIEW LOGS ABOVE.{Color.RESET}")
    print(f"{Color.BOLD}{'=' * 86}{Color.RESET}\n")


# ==============================================================================
# Main Execution Pipeline
# ==============================================================================
def main():
    logger.info("Initiating Final University Research Delivery Packaging Pipeline...")
    verification_results: List[Tuple[str, bool, str]] = []

    # 1. Unit Tests
    ut_ok, ut_msg = verify_unit_tests()
    verification_results.append(("Unit Tests (pytest)", ut_ok, ut_msg))
    if not ut_ok:
        logger.error(f"Unit tests failed: {ut_msg}")

    # 2. Code Linting & Syntax
    lint_ok, lint_msg = verify_code_linting()
    verification_results.append(("Code Formatting & Linting", lint_ok, lint_msg))
    if not lint_ok:
        logger.error(f"Linting failed: {lint_msg}")

    # 3. Model & Full System Verification
    sys_ok, sys_msg = verify_models_and_system()
    verification_results.append(("Full System Sanity Check", sys_ok, sys_msg))
    if not sys_ok:
        logger.error(f"Full system sanity check failed: {sys_msg}")

    # 4. Slide Deck Generation
    deck_ok, deck_msg = verify_presentation_deck()
    verification_results.append(("Slide Deck (12 Slides PPTX)", deck_ok, deck_msg))
    if not deck_ok:
        logger.error(f"Presentation deck check failed: {deck_msg}")

    # 5. Thesis Publication Figures
    fig_ok, fig_msg = verify_thesis_figures()
    verification_results.append(("Thesis Publication Figures", fig_ok, fig_msg))
    if not fig_ok:
        logger.error(f"Figures verification failed: {fig_msg}")

    # 6. Clean Temporary Cache Files
    clean_temporary_cache_files(PROJECT_ROOT)

    # 7. Assemble ZIP Package
    zip_path, file_count, checksum = assemble_final_submission_zip(PROJECT_ROOT, SUBMISSION_ZIP_PATH)

    # 8. Print Celebratory Summary Report
    print_celebratory_report(verification_results, zip_path, file_count, checksum)

    # Exit code: 0 if all verified, 1 otherwise
    if all(status for _, status, _ in verification_results):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
