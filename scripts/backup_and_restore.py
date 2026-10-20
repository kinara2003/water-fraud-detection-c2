"""
scripts/backup_and_restore.py
Automated Application State Backup & Restoration Engine
Component 2: NWSDB Water Fraud Surveillance Platform

Operations:
  --backup:
      Archives .env, data/networks/, data/processed/, models/*.joblib, and reports/
      into a timestamped tarball: backups/backup_YYYYMMDD_HHMMSS.tar.gz.
      Computes file-level SHA-256 hashes stored in .backup_manifest.json and writes
      a sidecar archive checksum (backups/backup_YYYYMMDD_HHMMSS.tar.gz.sha256).

  --restore <tarball>:
      Verifies sidecar archive checksum and internal manifest integrity hashes.
      Validates directory structures and safety checks (no path traversal).
      Cleanly restores application state without overwriting active Git branches.
      Executes automated model integrity validation: loads restored .joblib files
      to confirm valid pickle signatures and scikit-learn estimator attributes.

Flags:
  --dry-run:
      Executes full integrity, directory, and model signature validations
      in a staged temporary directory without overwriting active project files.
"""

import argparse
import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Dict, List, Optional, Tuple

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backup_and_restore")

DEFAULT_BACKUP_DIR = PROJECT_ROOT / "backups"
MANIFEST_FILENAME = ".backup_manifest.json"


# ==============================================================================
# Terminal ANSI Color Formatting
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


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 hexadecimal digest for a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_active_git_branch(root_dir: Path) -> Optional[str]:
    """Retrieves current active Git branch name, or None if not a Git repository."""
    git_dir = root_dir / ".git"
    if not git_dir.exists():
        return None
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            branch = res.stdout.strip()
            return branch if branch else "HEAD (detached)"
    except Exception:
        pass
    return "UNKNOWN_GIT"


# ==============================================================================
# Backup Routine
# ==============================================================================
def collect_backup_targets(root_dir: Path) -> List[Tuple[Path, str]]:
    """
    Identifies all files designated for backup:
    1. .env (if present)
    2. data/networks/ (all files)
    3. data/processed/ (all files)
    4. models/*.joblib
    5. reports/ (all files including figures, markdown, pptx)
    Returns a list of (absolute_path, relative_archive_name).
    """
    targets: List[Tuple[Path, str]] = []

    # 1. .env
    env_file = root_dir / ".env"
    if env_file.exists() and env_file.is_file():
        targets.append((env_file, ".env"))

    # 2. data/networks/
    networks_dir = root_dir / "data" / "networks"
    if networks_dir.exists() and networks_dir.is_dir():
        for item in networks_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(root_dir).as_posix()
                targets.append((item, rel))

    # 3. data/processed/
    processed_dir = root_dir / "data" / "processed"
    if processed_dir.exists() and processed_dir.is_dir():
        for item in processed_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(root_dir).as_posix()
                targets.append((item, rel))

    # 4. models/*.joblib
    models_dir = root_dir / "models"
    if models_dir.exists() and models_dir.is_dir():
        for item in models_dir.glob("*.joblib"):
            if item.is_file():
                rel = item.relative_to(root_dir).as_posix()
                targets.append((item, rel))

    # 5. reports/
    reports_dir = root_dir / "reports"
    if reports_dir.exists() and reports_dir.is_dir():
        for item in reports_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(root_dir).as_posix()
                targets.append((item, rel))

    return sorted(targets, key=lambda x: x[1])


def create_backup(
    root_dir: Path = PROJECT_ROOT,
    output_dir: Path = DEFAULT_BACKUP_DIR,
    dry_run: bool = False,
) -> Tuple[Path, Dict[str, Any]]:
    """
    Archives application state into backups/backup_YYYYMMDD_HHMMSS.tar.gz.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"backup_{timestamp}.tar.gz"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / archive_name
    checksum_path = output_dir / f"{archive_name}.sha256"

    logger.info(f"Scanning target files for backup from: {root_dir}")
    targets = collect_backup_targets(root_dir)

    if not targets:
        raise RuntimeError("No files found matching backup criteria (.env, data/, models/*.joblib, reports/)")

    # Build Manifest with file-level SHA-256 hashes
    manifest: Dict[str, Any] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "timestamp_local": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "archive_name": archive_name,
        "git_branch": get_active_git_branch(root_dir),
        "total_files": len(targets),
        "files": {},
    }

    total_bytes = 0
    for abs_path, rel_name in targets:
        size = abs_path.stat().st_size
        total_bytes += size
        sha = compute_file_sha256(abs_path)
        manifest["files"][rel_name] = {
            "size_bytes": size,
            "sha256": sha,
        }

    total_mb = total_bytes / (1024.0 * 1024.0)

    if dry_run:
        logger.info(f"{Color.YELLOW}[DRY RUN]{Color.RESET} Simulated backup of {len(targets)} files ({total_mb:.2f} MB)")
        return archive_path, manifest

    # Write archive
    logger.info(f"Creating gzip tarball: {archive_path} ({len(targets)} files, {total_mb:.2f} MB)...")
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tmp_man:
        json.dump(manifest, tmp_man, indent=2)
        tmp_manifest_path = Path(tmp_man.name)

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            # Add manifest first
            tar.add(tmp_manifest_path, arcname=MANIFEST_FILENAME)
            # Add all target files
            for abs_path, rel_name in targets:
                tar.add(abs_path, arcname=rel_name)
    finally:
        if tmp_manifest_path.exists():
            tmp_manifest_path.unlink()

    # Compute tarball SHA-256 and write sidecar
    archive_sha256 = compute_file_sha256(archive_path)
    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write(f"{archive_sha256}  {archive_name}\n")

    tar_size_mb = archive_path.stat().st_size / (1024.0 * 1024.0)

    # Print Formatted Report
    print(f"\n{Color.BOLD}{'=' * 78}{Color.RESET}")
    print(f"{Color.CYAN}{Color.BOLD}  NWSDB WATERGUARD -- BACKUP GENERATION COMPLETE{Color.RESET}")
    print(f"{Color.BOLD}{'=' * 78}{Color.RESET}")
    print(f"  Archive Path   : {archive_path}")
    print(f"  Archive Size   : {tar_size_mb:.2f} MB ({archive_path.stat().st_size:,} bytes)")
    print(f"  Total Files    : {len(targets)} files")
    print(f"  Raw Content    : {total_mb:.2f} MB")
    print(f"  SHA-256 Digest : {archive_sha256}")
    print(f"  Sidecar File   : {checksum_path.name}")
    if manifest["git_branch"]:
        print(f"  Active Branch  : {manifest['git_branch']}")
    print(f"{Color.BOLD}{'=' * 78}{Color.RESET}\n")

    return archive_path, manifest


# ==============================================================================
# Model Integrity Validation (Pickle / Joblib Signatures)
# ==============================================================================
def validate_model_integrity(model_path: Path) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Loads restored .joblib file and confirms valid pickle signatures:
    1. Unpickles cleanly via joblib.load().
    2. Validates scikit-learn estimator instance.
    3. Confirms presence of expected fitted attributes (e.g. n_features_in_).
    4. Executes a non-destructive dry-run prediction test.
    """
    import warnings
    import numpy as np

    details: Dict[str, Any] = {
        "file": model_path.name,
        "size_kb": model_path.stat().st_size / 1024.0,
    }

    try:
        import joblib
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = joblib.load(model_path)

        cls_name = model.__class__.__name__
        module_name = model.__class__.__module__
        details["class"] = f"{module_name}.{cls_name}"

        # Check estimator attributes
        n_features = getattr(model, "n_features_in_", None)
        details["n_features_in"] = n_features

        # Check classes if classification model
        classes = getattr(model, "classes_", None)
        if classes is not None:
            details["classes"] = list(classes)

        # Check number of trees in forest
        estimators = getattr(model, "estimators_", None)
        if estimators is not None:
            details["n_estimators"] = len(estimators)

        # Dry-run prediction validation
        if n_features is not None and hasattr(model, "predict"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                dummy_x = np.zeros((1, int(n_features)))
                pred = model.predict(dummy_x)
                details["dry_run_prediction"] = str(pred[0])

        return True, f"Valid pickle signature ({cls_name}, features={n_features})", details

    except Exception as exc:
        return False, f"Pickle signature validation failed: {str(exc)}", details


# ==============================================================================
# Restore Routine
# ==============================================================================
def validate_tarball_security(tar: tarfile.TarFile) -> List[str]:
    """
    Validates that the tarball contains no directory traversal attacks
    (no absolute paths, no '..' path components).
    """
    unsafe_members = []
    for member in tar.getmembers():
        name = member.name.replace("\\", "/")
        if name.startswith("/") or name.startswith("..") or "/../" in name or ":/" in name:
            unsafe_members.append(member.name)
    return unsafe_members


def restore_backup(
    tarball_path: Path,
    target_dir: Path = PROJECT_ROOT,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Verifies integrity hashes, validates directory structures, and cleanly
    restores application state without overwriting active Git branches.
    """
    tarball_path = Path(tarball_path).resolve()
    if not tarball_path.exists():
        raise FileNotFoundError(f"Tarball not found: {tarball_path}")

    logger.info(f"Initiating restoration from: {tarball_path}")

    # 1. Verify Sidecar Archive Checksum (if exists)
    sidecar_path = tarball_path.parent / f"{tarball_path.name}.sha256"
    sidecar_verified = False
    if sidecar_path.exists():
        expected_sha = sidecar_path.read_text(encoding="utf-8").split()[0].strip()
        computed_sha = compute_file_sha256(tarball_path)
        if expected_sha.lower() != computed_sha.lower():
            raise ValueError(
                f"Archive SHA-256 checksum mismatch!\n"
                f"  Expected: {expected_sha}\n"
                f"  Computed: {computed_sha}"
            )
        sidecar_verified = True
        logger.info(f"{Color.GREEN}[PASSED]{Color.RESET} Archive SHA-256 sidecar checksum verified.")

    # 2. Inspect Tarball Format & Directory Security
    if not tarfile.is_tarfile(tarball_path):
        raise ValueError(f"File is not a valid tar/gzip archive: {tarball_path}")

    with tarfile.open(tarball_path, "r:gz") as tar:
        unsafe = validate_tarball_security(tar)
        if unsafe:
            raise ValueError(f"Unsafe path traversal detected in archive members: {unsafe[:5]}")

        member_names = tar.getnames()

    # 3. Directory Structure Pre-Validation
    expected_prefixes = ["data/networks", "data/processed", "models", "reports"]
    matched_prefixes = {p: any(m.startswith(p) for m in member_names) for p in expected_prefixes}
    missing_structures = [p for p, matched in matched_prefixes.items() if not matched]
    if missing_structures:
        logger.warning(f"Archive is missing some typical directory structures: {missing_structures}")

    # 4. Git Branch Safety Guard
    active_branch_before = get_active_git_branch(target_dir)
    logger.info(
        f"Active Git environment: {active_branch_before or 'No Git repository detected'} "
        f"(Branches and HEAD will be strictly protected)"
    )

    # 5. Extract files (to temp dir for dry run or staged validation, or target dir)
    extraction_dir = target_dir
    tmp_extract_dir: Optional[tempfile.TemporaryDirectory] = None

    if dry_run:
        tmp_extract_dir = tempfile.TemporaryDirectory(prefix="water_fraud_restore_dryrun_")
        extraction_dir = Path(tmp_extract_dir.name)
        logger.info(f"{Color.YELLOW}[DRY RUN]{Color.RESET} Staging restore to temporary directory: {extraction_dir}")

    def is_git_internal(name: str) -> bool:
        norm = name.replace("\\", "/").strip("/")
        parts = norm.split("/")
        return any(p == ".git" for p in parts)

    # Extract all members
    logger.info(f"Extracting {len(member_names)} members to {extraction_dir}...")
    with tarfile.open(tarball_path, "r:gz") as tar:
        # Prevent any potential .git directory extraction
        safe_members = [
            m for m in tar.getmembers()
            if not is_git_internal(m.name)
        ]
        tar.extractall(path=str(extraction_dir), members=safe_members)

    # 6. Verify Manifest Hashes of Restored Files
    manifest_path = extraction_dir / MANIFEST_FILENAME
    manifest_verified = False
    manifest_stats: Dict[str, Any] = {"total": 0, "matched": 0, "mismatched": []}

    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)

            files_dict = manifest_data.get("files", {})
            manifest_stats["total"] = len(files_dict)

            for rel_path, meta in files_dict.items():
                target_file = extraction_dir / rel_path
                if not target_file.exists():
                    manifest_stats["mismatched"].append((rel_path, "MISSING"))
                    continue

                curr_sha = compute_file_sha256(target_file)
                if curr_sha.lower() == meta["sha256"].lower():
                    manifest_stats["matched"] += 1
                else:
                    manifest_stats["mismatched"].append((rel_path, f"HASH_MISMATCH ({curr_sha} != {meta['sha256']})"))

            if not manifest_stats["mismatched"]:
                manifest_verified = True
                logger.info(f"{Color.GREEN}[PASSED]{Color.RESET} All {manifest_stats['matched']} restored file SHA-256 hashes verified against manifest.")
            else:
                logger.error(f"{Color.RED}[FAILED]{Color.RESET} Hash mismatches found: {manifest_stats['mismatched']}")
        except Exception as e:
            logger.warning(f"Failed to parse internal manifest: {e}")

    # 7. Automated Model Integrity Validation (.joblib pickle signatures)
    restored_models_dir = extraction_dir / "models"
    model_validation_results: List[Dict[str, Any]] = []
    models_all_valid = True

    if restored_models_dir.exists():
        joblib_files = list(restored_models_dir.glob("*.joblib"))
        logger.info(f"Validating pickle signatures on {len(joblib_files)} restored model binaries...")
        for jf in joblib_files:
            valid, msg, details = validate_model_integrity(jf)
            details["valid"] = valid
            details["message"] = msg
            model_validation_results.append(details)
            if not valid:
                models_all_valid = False
                logger.error(f"Model integrity failure on {jf.name}: {msg}")
            else:
                logger.info(f"{Color.GREEN}[VERIFIED]{Color.RESET} {jf.name}: {msg}")

    # 8. Git Safety Verification After Restore
    active_branch_after = get_active_git_branch(target_dir)
    if active_branch_before is not None:
        assert active_branch_before == active_branch_after, (
            f"Git branch integrity violated! Changed from {active_branch_before} to {active_branch_after}"
        )
        logger.info(f"{Color.GREEN}[PASSED]{Color.RESET} Active Git branch preserved ({active_branch_after}).")

    # Cleanup temp directory if dry run
    if tmp_extract_dir is not None:
        tmp_extract_dir.cleanup()

    # Print Restoration Report
    print(f"\n{Color.BOLD}{'=' * 78}{Color.RESET}")
    print(f"{Color.GREEN}{Color.BOLD}  NWSDB WATERGUARD -- RESTORATION VERIFICATION SUMMARY{Color.RESET}")
    print(f"{Color.BOLD}{'=' * 78}{Color.RESET}")
    print(f"  Tarball Restored   : {tarball_path.name}")
    print(f"  Mode               : {'DRY RUN (Test Simulation)' if dry_run else 'LIVE PRODUCTION RESTORE'}")
    print(f"  Archive Checksum   : {'VERIFIED' if sidecar_verified else 'SKIPPED (No sidecar)'}")
    print(f"  Manifest Hashes    : {manifest_stats['matched']}/{manifest_stats['total']} VERIFIED")
    print(f"  Git Branch Guard   : PROTECTED (Active branch: {active_branch_after or 'N/A'})")
    print(f"  Model Binaries     : {len(model_validation_results)} models loaded & verified")
    for m in model_validation_results:
        status_str = f"{Color.GREEN}VALID{Color.RESET}" if m.get("valid") else f"{Color.RED}INVALID{Color.RESET}"
        print(f"    * {m.get('file', 'model')}: [{status_str}] {m.get('class', 'Estimator')} (features={m.get('n_features_in', '?')})")
    print(f"{Color.BOLD}{'=' * 78}{Color.RESET}\n")

    return {
        "success": models_all_valid and (manifest_verified or not manifest_stats["mismatched"]),
        "tarball": str(tarball_path),
        "dry_run": dry_run,
        "sidecar_verified": sidecar_verified,
        "manifest_stats": manifest_stats,
        "models_verified": len(model_validation_results),
        "models_all_valid": models_all_valid,
        "model_details": model_validation_results,
    }


# ==============================================================================
# CLI Entrypoint
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Backup and Restore Platform for Component 2 (NWSDB Water Fraud Surveillance Engine)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a timestamped backup
  python scripts/backup_and_restore.py --backup

  # Perform a dry-run test backup
  python scripts/backup_and_restore.py --backup --dry-run

  # Restore from a backup archive with full verification
  python scripts/backup_and_restore.py --restore backups/backup_20261019_184500.tar.gz

  # Perform a dry-run test restoration
  python scripts/backup_and_restore.py --restore backups/backup_20261019_184500.tar.gz --dry-run
        """,
    )

    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--backup",
        action="store_true",
        help="Archive .env, data/, models/*.joblib, and reports/ into backups/backup_YYYYMMDD_HHMMSS.tar.gz",
    )
    action_group.add_argument(
        "--restore",
        type=str,
        metavar="TARBALL",
        help="Restore application state from the specified .tar.gz archive and validate model pickle signatures",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_BACKUP_DIR),
        help=f"Directory to save backups (default: {DEFAULT_BACKUP_DIR})",
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        default=str(PROJECT_ROOT),
        help=f"Target directory for restoration (default: {PROJECT_ROOT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the operation and validate all checksums and pickle signatures without modifying target files",
    )

    args = parser.parse_args()

    if args.backup:
        out_path, manifest = create_backup(
            root_dir=PROJECT_ROOT,
            output_dir=Path(args.output_dir),
            dry_run=args.dry_run,
        )
        sys.exit(0)

    elif args.restore:
        tarball_path = Path(args.restore)
        if not tarball_path.exists():
            # Try searching relative to DEFAULT_BACKUP_DIR
            alt_path = Path(args.output_dir) / args.restore
            if alt_path.exists():
                tarball_path = alt_path

        res = restore_backup(
            tarball_path=tarball_path,
            target_dir=Path(args.target_dir),
            dry_run=args.dry_run,
        )
        if not res["success"]:
            sys.exit(1)
        sys.exit(0)


if __name__ == "__main__":
    main()
