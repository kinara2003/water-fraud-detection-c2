"""
tests/test_viva_package.py
Tests for scripts/prepare_viva_package.py:
Validates prerequisites checking, markdown compilation, and zip package integrity.
"""

from pathlib import Path
import zipfile
import pytest

from scripts.prepare_viva_package import (
    validate_prerequisites,
    compile_executive_summary,
    create_defense_package_zip,
    SUMMARY_MD_PATH,
    ZIP_OUTPUT_PATH,
)


def test_validate_prerequisites():
    """Asserts that all prerequisites are verified and valid."""
    all_valid, results = validate_prerequisites()
    assert all_valid is True
    assert len(results["models"]) >= 2
    assert len(results["figures"]) >= 5
    assert len(results["evaluation_data"]) >= 2
    assert len(results["documentation"]) >= 2
    assert len(results["geojson_layers"]) >= 2


def test_compile_executive_summary():
    """Asserts that the executive summary markdown is generated with required sections."""
    summary_path = compile_executive_summary()
    assert summary_path.exists()
    assert summary_path.stat().st_size > 3000

    text = summary_path.read_text(encoding="utf-8")
    assert "Methodology" in text
    assert "Quantitative Evaluation Results" in text
    assert "Multi-Component Interlock & Data Contracts" in text
    assert "Component 1" in text
    assert "Component 3" in text
    assert "Component 4" in text
    assert "Partial Bypass" in text


def test_create_defense_package_zip():
    """Asserts that the zip package is generated with proper files and non-empty size."""
    all_valid, results = validate_prerequisites()
    summary_path = compile_executive_summary()
    zip_path, count, checksum = create_defense_package_zip(results, summary_path)

    assert zip_path.exists()
    assert zip_path.stat().st_size > 1_000_000  # Over 1 MB
    assert count >= 15
    assert len(checksum) == 64

    # Verify zip content integrity
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert "models/isolation_forest.joblib" in namelist
        assert "models/random_forest.joblib" in namelist
        assert "reports/EXECUTIVE_DEFENSE_SUMMARY.md" in namelist
        assert "data/processed/evaluation_metrics.csv" in namelist
        assert "data/processed/kaduwela_nodes_geo.json" in namelist
        assert "frontend/public/data/kaduwela_junctions.geojson" in namelist
        assert "frontend/public/data/kaduwela_pipes.geojson" in namelist
        assert "documentation/RESEARCH_DEFENSE.md" in namelist
        assert "documentation/VIVA_PREP.md" in namelist
