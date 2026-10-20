"""
tests/test_benchmark_models.py
Unit and Integration Tests for Comparative Architecture Benchmark (src/benchmark_models.py)
Component 2: NWSDB Unauthorized Water Withdrawal & Physical Twin Surveillance Engine

Validates:
  1. Loading training features dataset.
  2. Generation of synthetic IWS refill transient surge evaluation set.
  3. Evaluation of Model A (Static Residual Threshold Baseline).
  4. Evaluation of Model B (Single-Stage SVM).
  5. Evaluation of Model C (3-Layer MLP).
  6. Evaluation of Model D (Proposed Two-Stage Architecture with Refill Dampening).
  7. Verification of >= 60.0% false alarm reduction during morning IWS refill.
  8. Output artifact generation: CSV table and 300 DPI publication figure.
"""

from pathlib import Path
import pytest
import pandas as pd
import numpy as np

from src.benchmark_models import (
    FEATURE_COLUMNS,
    load_training_dataset,
    build_refill_transient_eval_set,
    evaluate_model_a_rule_based,
    evaluate_model_b_svm,
    evaluate_model_c_mlp,
    evaluate_model_d_proposed_two_stage,
    run_full_benchmark,
    plot_benchmark_comparison,
    DEFAULT_FEATURES_CSV,
    DEFAULT_BENCHMARK_CSV,
    DEFAULT_BENCHMARK_PNG,
)


@pytest.fixture
def sample_dataset():
    """Provides the training features dataset."""
    df = load_training_dataset(DEFAULT_FEATURES_CSV)
    return df


def test_load_training_dataset(sample_dataset):
    """Asserts that training_features.csv loads with required columns and labels."""
    assert isinstance(sample_dataset, pd.DataFrame)
    assert len(sample_dataset) > 1000
    for col in FEATURE_COLUMNS:
        assert col in sample_dataset.columns
    assert "label" in sample_dataset.columns
    assert set(sample_dataset["label"].unique()) >= {"normal", "leak", "partial_bypass"}


def test_build_refill_transient_eval_set(sample_dataset):
    """Asserts that morning IWS refill transient evaluation set contains valid surge cases."""
    df_refill = build_refill_transient_eval_set(sample_dataset.iloc[:200], n_surge_events=20, random_seed=42)
    assert isinstance(df_refill, pd.DataFrame)
    assert len(df_refill) >= 20
    assert "hydraulic_residual" in df_refill.columns
    assert "hours_since_supply_start" in df_refill.columns
    # Check that surge samples have legitimate 'normal' ground truth
    assert (df_refill["label"] == "normal").all()


def test_model_a_static_rule_evaluation(sample_dataset):
    """Asserts that Model A executes and computes 5 metrics."""
    X = sample_dataset[FEATURE_COLUMNS].iloc[:300]
    y = sample_dataset["label"].iloc[:300]
    eval_refill = build_refill_transient_eval_set(sample_dataset.iloc[:100], n_surge_events=20)

    res_a = evaluate_model_a_rule_based(X, y, eval_refill, threshold_m=3.0)
    assert res_a["model_id"] == "Model A"
    assert "precision" in res_a
    assert "recall" in res_a
    assert "f1_score" in res_a
    assert "refill_transient_fpr" in res_a
    assert "avg_latency_ms" in res_a
    assert 0.0 <= res_a["precision"] <= 1.0
    assert 0.0 <= res_a["refill_transient_fpr"] <= 1.0


def test_model_b_svm_evaluation(sample_dataset):
    """Asserts that Model B executes multi-class SVM and computes 5 metrics."""
    from sklearn.model_selection import train_test_split
    train_df, test_df = train_test_split(
        sample_dataset, test_size=0.30, random_state=42, stratify=sample_dataset["label"]
    )
    eval_refill = build_refill_transient_eval_set(test_df, n_surge_events=15)

    res_b = evaluate_model_b_svm(
        train_df[FEATURE_COLUMNS],
        train_df["label"],
        test_df[FEATURE_COLUMNS],
        test_df["label"],
        eval_refill,
        random_state=42,
    )
    assert res_b["model_id"] == "Model B"
    assert "precision" in res_b
    assert "recall" in res_b
    assert "f1_score" in res_b
    assert res_b["avg_latency_ms"] > 0.0


def test_model_c_mlp_evaluation(sample_dataset):
    """Asserts that Model C executes 3-Layer MLP and computes 5 metrics."""
    from sklearn.model_selection import train_test_split
    train_df, test_df = train_test_split(
        sample_dataset, test_size=0.30, random_state=42, stratify=sample_dataset["label"]
    )
    eval_refill = build_refill_transient_eval_set(test_df, n_surge_events=15)

    res_c = evaluate_model_c_mlp(
        train_df[FEATURE_COLUMNS],
        train_df["label"],
        test_df[FEATURE_COLUMNS],
        test_df["label"],
        eval_refill,
        random_state=42,
    )
    assert res_c["model_id"] == "Model C"
    assert "precision" in res_c
    assert "f1_score" in res_c
    assert res_c["avg_latency_ms"] > 0.0


def test_model_d_proposed_two_stage_evaluation(sample_dataset):
    """Asserts that Model D executes two-stage pipeline with IWS refill dampening."""
    from sklearn.model_selection import train_test_split
    train_df, test_df = train_test_split(
        sample_dataset, test_size=0.30, random_state=42, stratify=sample_dataset["label"]
    )
    eval_refill = build_refill_transient_eval_set(test_df, n_surge_events=20)

    res_d = evaluate_model_d_proposed_two_stage(
        train_df[FEATURE_COLUMNS],
        train_df["label"],
        test_df[FEATURE_COLUMNS],
        test_df["label"],
        test_df,
        eval_refill,
        random_state=42,
    )
    assert res_d["model_id"] == "Model D"
    assert res_d["f1_score"] >= 0.0
    # Refill transient FPR must be dampened close to 0%
    assert res_d["refill_transient_fpr"] <= 0.20


def test_full_benchmark_and_reduction_target():
    """
    Validates end-to-end benchmark execution and confirms that Model D achieves
    >= 60.0% false alarm reduction during morning IWS refill compared to Model A.
    """
    benchmark_df, summary = run_full_benchmark(test_size=0.25, random_seed=42)

    assert isinstance(benchmark_df, pd.DataFrame)
    assert len(benchmark_df) == 4
    assert set(benchmark_df["Model ID"]) == {"Model A", "Model B", "Model C", "Model D"}

    # Assert that all 5 required quantitative metrics are present in columns
    expected_cols = [
        "Model ID",
        "Architecture",
        "Precision",
        "Recall",
        "F1-Score",
        "Refill Transient FPR (%)",
        "Avg Latency (ms)",
    ]
    for c in expected_cols:
        assert c in benchmark_df.columns

    # Check key false alarm reduction condition: >= 60.0%
    reduc = summary["false_alarm_reduction_pct"]
    assert reduc >= 60.0, f"Expected >= 60% false alarm reduction, but got {reduc:.2f}%"
    assert summary["target_met_ge_60"] is True


def test_plot_benchmark_comparison_artifact(tmp_path):
    """Validates that plot_benchmark_comparison generates a valid PNG file."""
    benchmark_df, summary = run_full_benchmark(test_size=0.15, random_seed=42)
    out_png = tmp_path / "test_benchmark.png"
    result_path = plot_benchmark_comparison(benchmark_df, summary, output_png=out_png)

    assert result_path.exists()
    assert result_path.stat().st_size > 50000  # High resolution image > 50 KB
