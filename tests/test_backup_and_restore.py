"""
tests/test_backup_and_restore.py
Unit and Integration Tests for Application State Backup and Restoration.

Validates:
1. Target collection: .env, data/networks/, data/processed/, models/*.joblib, reports/.
2. Backup archive generation (tar.gz) and SHA-256 sidecar manifest.
3. Archive integrity verification and corruption detection.
4. Security guard against directory traversal attacks.
5. Automated model integrity validation (pickle signatures and feature counts).
6. Non-destructive dry-run backup-restore cycle.
7. Wrapper scripts (.bat and .sh) existence and functionality.
"""

from pathlib import Path
import shutil
import tarfile
import tempfile
import pytest

from scripts.backup_and_restore import (
    collect_backup_targets,
    create_backup,
    restore_backup,
    validate_model_integrity,
    compute_file_sha256,
    PROJECT_ROOT,
    DEFAULT_BACKUP_DIR,
)


@pytest.fixture
def temp_backup_dir(tmp_path):
    """Provides an isolated directory for storing test backups."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def test_collect_backup_targets():
    """Asserts that all designated operational directories and files are identified."""
    targets = collect_backup_targets(PROJECT_ROOT)
    rel_paths = [t[1] for t in targets]

    # Verify key expected targets are in the collected list
    assert any(p == ".env" for p in rel_paths), "Missing .env target"
    assert any(p.startswith("data/networks/") for p in rel_paths), "Missing data/networks targets"
    assert any(p.startswith("data/processed/") for p in rel_paths), "Missing data/processed targets"
    assert any(p.startswith("models/") and p.endswith(".joblib") for p in rel_paths), "Missing models/*.joblib"
    assert any(p.startswith("reports/") for p in rel_paths), "Missing reports/ targets"


def test_create_backup_tarball_and_manifest(temp_backup_dir):
    """Asserts that --backup produces a valid gzip tarball and SHA-256 sidecar."""
    archive_path, manifest = create_backup(
        root_dir=PROJECT_ROOT,
        output_dir=temp_backup_dir,
        dry_run=False,
    )

    assert archive_path.exists(), "Tarball archive was not created"
    assert archive_path.stat().st_size > 500_000, "Archive size should exceed 500 KB"
    assert archive_path.name.startswith("backup_") and archive_path.name.endswith(".tar.gz")

    # Sidecar checksum
    sidecar_path = temp_backup_dir / f"{archive_path.name}.sha256"
    assert sidecar_path.exists(), "Sidecar .sha256 file was not created"
    expected_sha = compute_file_sha256(archive_path)
    sidecar_content = sidecar_path.read_text(encoding="utf-8")
    assert expected_sha in sidecar_content

    # Manifest verification
    assert manifest["total_files"] >= 20
    assert len(manifest["files"]) == manifest["total_files"]
    assert ".env" in manifest["files"]


def test_tarball_internal_structure_and_security(temp_backup_dir):
    """Asserts that the tarball contains valid members and no directory traversal paths."""
    archive_path, _ = create_backup(
        root_dir=PROJECT_ROOT,
        output_dir=temp_backup_dir,
        dry_run=False,
    )

    with tarfile.open(archive_path, "r:gz") as tar:
        member_names = tar.getnames()
        # Verify internal manifest
        assert ".backup_manifest.json" in member_names

        # Security check: no path traversal
        for m in member_names:
            assert not m.startswith("/"), f"Absolute path detected: {m}"
            assert ".." not in m, f"Path traversal detected: {m}"
            assert not m.startswith(".git/"), f"Git internal directory should not be in backup: {m}"


def test_restore_dry_run_validation(temp_backup_dir):
    """Asserts that --restore with --dry-run completes full verification without errors."""
    archive_path, _ = create_backup(
        root_dir=PROJECT_ROOT,
        output_dir=temp_backup_dir,
        dry_run=False,
    )

    result = restore_backup(
        tarball_path=archive_path,
        target_dir=PROJECT_ROOT,
        dry_run=True,
    )

    assert result["success"] is True
    assert result["sidecar_verified"] is True
    assert result["manifest_stats"]["matched"] == result["manifest_stats"]["total"]
    assert result["models_all_valid"] is True
    assert result["models_verified"] >= 2


def test_restore_tampered_archive_fails(temp_backup_dir):
    """Asserts that if the tarball is corrupted or tampered with, restore immediately aborts."""
    archive_path, _ = create_backup(
        root_dir=PROJECT_ROOT,
        output_dir=temp_backup_dir,
        dry_run=False,
    )

    # Tamper with archive content by appending junk bytes
    with open(archive_path, "ab") as f:
        f.write(b"CORRUPTED_BYTES_INJECTION")

    with pytest.raises(ValueError, match="Archive SHA-256 checksum mismatch"):
        restore_backup(
            tarball_path=archive_path,
            target_dir=PROJECT_ROOT,
            dry_run=True,
        )


def test_model_pickle_integrity_validation():
    """Asserts that existing models unpickle cleanly and satisfy estimator contracts."""
    models_dir = PROJECT_ROOT / "models"
    joblib_files = list(models_dir.glob("*.joblib"))
    assert len(joblib_files) >= 2, "Expected at least 2 model binaries in models/"

    for jf in joblib_files:
        valid, msg, details = validate_model_integrity(jf)
        assert valid is True, f"Failed model integrity check on {jf.name}: {msg}"
        assert details["n_features_in"] == 6, f"Expected 6 engineered features, got {details.get('n_features_in')}"
        assert "sklearn" in details["class"]


def test_model_pickle_corruption_detection(tmp_path):
    """Asserts that a corrupted .joblib file fails pickle signature validation."""
    fake_model = tmp_path / "corrupted_model.joblib"
    fake_model.write_bytes(b"NOT_A_VALID_PICKLE_STREAM_1234567890")

    valid, msg, details = validate_model_integrity(fake_model)
    assert valid is False
    assert "validation failed" in msg.lower()


def test_wrapper_scripts_presence_and_format():
    """Asserts that scripts/backup_and_restore.bat and scripts/backup_and_restore.sh exist and contain correct flags."""
    bat_file = PROJECT_ROOT / "scripts" / "backup_and_restore.bat"
    sh_file = PROJECT_ROOT / "scripts" / "backup_and_restore.sh"

    assert bat_file.exists(), "scripts/backup_and_restore.bat is missing"
    assert sh_file.exists(), "scripts/backup_and_restore.sh is missing"

    bat_content = bat_file.read_text(encoding="utf-8")
    assert "--backup" in bat_content
    assert "--restore" in bat_content
    assert "backup_and_restore.py" in bat_content

    sh_content = sh_file.read_text(encoding="utf-8")
    assert "--backup" in sh_content
    assert "--restore" in sh_content
    assert "backup_and_restore.py" in sh_content
