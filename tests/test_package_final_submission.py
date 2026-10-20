"""
tests/test_package_final_submission.py
Unit and Integration Tests for scripts/package_final_submission.py.

Validates:
1. Verification functions (linting, presentation deck, publication figures).
2. Evaluator navigation index (SUBMISSION_INDEX.md) presence and structure.
3. Temporary cache cleaner (__pycache__, .pytest_cache).
4. Submittable file filtering (excluding node_modules, .git, virtual environments).
5. Generation of Final_Submission_Component2_AI_Water_Fraud.zip.
"""

from pathlib import Path
import tempfile
import zipfile
import pytest

from scripts.package_final_submission import (
    verify_code_linting,
    verify_presentation_deck,
    verify_thesis_figures,
    clean_temporary_cache_files,
    is_submittable_file,
    assemble_final_submission_zip,
    PROJECT_ROOT,
)


def test_submission_index_structure():
    """Asserts that SUBMISSION_INDEX.md exists and contains required evaluator sections."""
    index_path = PROJECT_ROOT / "SUBMISSION_INDEX.md"
    assert index_path.exists(), "SUBMISSION_INDEX.md is missing from project root"
    text = index_path.read_text(encoding="utf-8")

    assert "Navigation Map" in text
    assert "FastAPI Backend" in text
    assert "Two-Stage" in text
    assert "Component 1" in text
    assert "Component 3" in text
    assert "Component 4" in text
    assert "Quickstart" in text


def test_verify_code_linting():
    """Asserts that code formatting and syntax verification passes."""
    ok, msg = verify_code_linting()
    assert ok is True, f"Code linting failed: {msg}"
    assert "0 syntax errors" in msg


def test_verify_presentation_deck():
    """Asserts that the 12-slide presentation deck is validated."""
    ok, msg = verify_presentation_deck()
    assert ok is True, f"Presentation deck check failed: {msg}"
    assert "presentation deck" in msg.lower()


def test_verify_thesis_figures():
    """Asserts that all 6 publication figures are verified in reports/figures/."""
    ok, msg = verify_thesis_figures()
    assert ok is True, f"Thesis figures verification failed: {msg}"
    assert "6/6" in msg


def test_clean_temporary_cache_files(tmp_path):
    """Asserts that __pycache__ and temporary cache folders are cleanly removed."""
    fake_pycache = tmp_path / "app" / "__pycache__"
    fake_pycache.mkdir(parents=True, exist_ok=True)
    (fake_pycache / "test.cpython-310.pyc").write_bytes(b"dummy")

    assert fake_pycache.exists()
    removed = clean_temporary_cache_files(root_dir=tmp_path)
    assert removed >= 1
    assert not fake_pycache.exists()


def test_submittable_file_filtering():
    """Asserts that excluded directories (node_modules, .git, venv) are rejected."""
    # Should be rejected
    assert not is_submittable_file(Path("frontend/node_modules/vite/package.json"), "frontend/node_modules/vite/package.json")
    assert not is_submittable_file(Path(".git/HEAD"), ".git/HEAD")
    assert not is_submittable_file(Path("venv/lib/site.py"), "venv/lib/site.py")
    assert not is_submittable_file(Path(".pytest_cache/v/cache"), ".pytest_cache/v/cache")
    assert not is_submittable_file(Path("app/__pycache__/main.cpython-310.pyc"), "app/__pycache__/main.cpython-310.pyc")
    assert not is_submittable_file(Path("test.zip"), "test.zip")

    # Should be accepted
    assert is_submittable_file(Path("app/main.py"), "app/main.py")
    assert is_submittable_file(Path("src/scorer.py"), "src/scorer.py")
    assert is_submittable_file(Path("SUBMISSION_INDEX.md"), "SUBMISSION_INDEX.md")
    assert is_submittable_file(Path("frontend/src/App.tsx"), "frontend/src/App.tsx")


def test_assemble_submission_zip_in_temp_dir(tmp_path):
    """Asserts that the submission zip is created with all essential research artifacts."""
    target_zip = tmp_path / "Test_Submission.zip"
    zip_path, file_count, checksum = assemble_final_submission_zip(
        root_dir=PROJECT_ROOT,
        output_zip_path=target_zip,
    )

    assert zip_path.exists()
    assert zip_path.stat().st_size > 2_000_000  # Over 2 MB
    assert file_count >= 40
    assert len(checksum) == 64

    # Verify key members in zip
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert "SUBMISSION_INDEX.md" in namelist
        assert "RESEARCH_DEFENSE.md" in namelist
        assert "DEFENSE_FAQ.md" in namelist
        assert "app/main.py" in namelist
        assert "src/scorer.py" in namelist
        assert "data/networks/kaduwela_2dma_clean_East_side.inp" in namelist
        assert "models/isolation_forest.joblib" in namelist
        assert "reports/Component2_Viva_Presentation.pptx" in namelist
        assert "reports/figures/model_benchmark_comparison.png" in namelist

        # Assert no forbidden directories were packed
        assert not any("node_modules" in n for n in namelist)
        assert not any("__pycache__" in n for n in namelist)
        assert not any(".git/" in n for n in namelist)
