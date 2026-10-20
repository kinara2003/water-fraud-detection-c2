"""
src/evaluate.py
Evaluates the two-stage AI fraud and anomaly detection pipeline on held-out test scenarios
for Kaduwela DMA 01 & 02 under Intermittent Water Supply (IWS).

Stages evaluated:
- Stage 1: IsolationForest for Anomaly Detection (identifying departures from normal digital twin baseline).
- Stage 2: RandomForestClassifier for Root Cause Classification (leak vs. partial_bypass).
- End-to-End Pipeline: Multi-class assessment across normal, leak, and partial_bypass.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
import joblib
import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"

FEATURES_CSV_PATH = DATA_DIR / "training_features.csv"
ISO_FOREST_PATH = MODELS_DIR / "isolation_forest.joblib"
RANDOM_FOREST_PATH = MODELS_DIR / "random_forest.joblib"

CONFUSION_MATRIX_PNG = DATA_DIR / "confusion_matrix.png"
METRICS_CSV_PATH = DATA_DIR / "evaluation_metrics.csv"

FEATURE_COLUMNS: List[str] = [
    "actual_pressure",
    "hydraulic_residual",
    "pressure_change_rate",
    "residual_rolling_mean",
    "residual_rolling_std",
    "spatial_deviation",
]

SCENARIO_CLASSES: List[str] = ["normal", "leak", "partial_bypass"]


def load_data_and_models(
    features_csv: Path = FEATURES_CSV_PATH,
    iso_path: Path = ISO_FOREST_PATH,
    rf_path: Path = RANDOM_FOREST_PATH,
) -> Tuple[pd.DataFrame, Any, Any]:
    """
    Loads training feature matrix, IsolationForest model, and RandomForest model.
    """
    if not features_csv.exists():
        raise FileNotFoundError(f"Feature dataset not found: {features_csv}. Run features.py first.")
    if not iso_path.exists():
        raise FileNotFoundError(f"Stage 1 IsolationForest model not found: {iso_path}. Run train.py first.")
    if not rf_path.exists():
        raise FileNotFoundError(f"Stage 2 RandomForest model not found: {rf_path}. Run train.py first.")

    df: pd.DataFrame = pd.read_csv(features_csv)

    # Column aliases fallback
    column_aliases = {
        "P_actual": "actual_pressure",
        "residual": "hydraulic_residual",
        "dP_dt": "pressure_change_rate",
    }
    for old_col, new_col in column_aliases.items():
        if new_col not in df.columns and old_col in df.columns:
            df[new_col] = df[old_col]

    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required feature columns: {missing}")
    if "label" not in df.columns:
        raise KeyError("Missing 'label' column in feature dataset.")

    iso_model = joblib.load(iso_path)
    rf_model = joblib.load(rf_path)

    return df, iso_model, rf_model


def calibrate_anomaly_threshold(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    iso_model: Any,
) -> Tuple[float, str]:
    """
    Calibrates the Stage 1 anomaly detection threshold on the training split
    by maximizing the F1-score for anomaly classification (normal vs anomalous).
    """
    raw_scores = iso_model.decision_function(X_train)
    scores_train: np.ndarray = np.asarray(raw_scores, dtype=float)
    y_is_anomaly: np.ndarray = np.asarray(y_train != "normal", dtype=bool)

    best_thresh: float = 0.0
    best_f1: float = -1.0
    best_dir: str = "greater"

    # Search through candidate thresholds
    min_score = float(scores_train.min())
    max_score = float(scores_train.max())
    threshold_candidates: List[float] = [float(v) for v in np.linspace(min_score, max_score, 100)]

    for thresh in threshold_candidates:
        for direction in ["greater", "less"]:
            pred_anom = (scores_train > thresh) if direction == "greater" else (scores_train < thresh)
            tp = int(np.logical_and(pred_anom, y_is_anomaly).sum())
            fp = int(np.logical_and(pred_anom, ~y_is_anomaly).sum())
            fn = int(np.logical_and(~pred_anom, y_is_anomaly).sum())

            denom = 2 * tp + fp + fn
            f1 = float(2 * tp / denom) if denom > 0 else 0.0

            if f1 > best_f1:
                best_f1 = f1
                best_thresh = float(thresh)
                best_dir = direction

    return best_thresh, best_dir


def predict_two_stage_pipeline(
    X: pd.DataFrame,
    iso_model: Any,
    rf_model: Any,
    anomaly_threshold: float,
    threshold_dir: str = "greater",
) -> np.ndarray:
    """
    Executes two-stage inference:
    1. Stage 1 flags whether a sample is Normal or Anomaly.
    2. Stage 2 classifies root cause (leak or partial_bypass) for anomalies.
    """
    raw_scores = iso_model.decision_function(X)
    scores: np.ndarray = np.asarray(raw_scores, dtype=float)
    is_anomaly: np.ndarray = (scores > anomaly_threshold) if threshold_dir == "greater" else (scores < anomaly_threshold)

    predictions: np.ndarray = np.array(["normal"] * len(X), dtype=object)

    anom_count = int(np.sum(is_anomaly))
    if anom_count > 0:
        anom_indices = np.where(is_anomaly)[0]
        X_anom = X.iloc[anom_indices]
        rf_preds = np.asarray(rf_model.predict(X_anom), dtype=object)
        for idx, pred_label in zip(anom_indices, rf_preds):
            predictions[idx] = pred_label

    return predictions


def compute_metrics(
    y_true: pd.Series,
    y_pred: np.ndarray,
    classes: List[str] = SCENARIO_CLASSES,
) -> Tuple[np.ndarray, float, pd.DataFrame]:
    """
    Computes confusion matrix, False Positive Rate (FPR) on normal operations,
    and structured per-class summary metrics.
    """
    raw_cm = confusion_matrix(y_true, y_pred, labels=classes)
    cm: np.ndarray = np.asarray(raw_cm, dtype=int)

    # False Positive Rate (FPR) on normal operations:
    # Row 0 is actual 'normal'.
    # FP on normal = actual normal misclassified as leak or partial_bypass
    # TN on normal = actual normal correctly classified as normal
    normal_total = int(cm[0].sum())
    normal_tp = int(cm[0, 0])
    normal_fp = int(cm[0, 1:].sum())
    fpr_normal = float(normal_fp / normal_total) if normal_total > 0 else 0.0

    # Per-class precision, recall, f1, support
    p_arr, r_arr, f1_arr, sup_arr = precision_recall_fscore_support(  # type: ignore[call-overload]
        y_true, y_pred, labels=classes, zero_division=0  # type: ignore[arg-type]
    )
    precision = np.asarray(p_arr, dtype=float)
    recall = np.asarray(r_arr, dtype=float)
    f1 = np.asarray(f1_arr, dtype=float)
    support = np.asarray(sup_arr, dtype=int)

    rows: List[Dict[str, Any]] = []
    for i, cls_name in enumerate(classes):
        # Per-class FPR (FP / (FP + TN))
        fp_val = int(cm[:, i].sum() - cm[i, i])
        tn_val = int(cm.sum() - (cm[i, :].sum() + cm[:, i].sum() - cm[i, i]))
        denom = fp_val + tn_val
        cls_fpr = float(fp_val / denom) if denom > 0 else 0.0

        rows.append(
            {
                "class": cls_name,
                "precision": round(float(precision[i]), 4),
                "recall": round(float(recall[i]), 4),
                "f1_score": round(float(f1[i]), 4),
                "support": int(support[i]),
                "false_positive_rate": round(float(cls_fpr), 4),
            }
        )

    # Macro & Weighted Averages
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(  # type: ignore[call-overload]
        y_true, y_pred, average="macro", zero_division=0  # type: ignore[arg-type]
    )
    weighted_p, weighted_r, weighted_f1, _ = precision_recall_fscore_support(  # type: ignore[call-overload]
        y_true, y_pred, average="weighted", zero_division=0  # type: ignore[arg-type]
    )
    overall_acc = float(accuracy_score(y_true, y_pred))

    rows.append(
        {
            "class": "macro_avg",
            "precision": round(float(macro_p), 4),
            "recall": round(float(macro_r), 4),
            "f1_score": round(float(macro_f1), 4),
            "support": int(len(y_true)),
            "false_positive_rate": np.nan,
        }
    )
    rows.append(
        {
            "class": "weighted_avg",
            "precision": round(float(weighted_p), 4),
            "recall": round(float(weighted_r), 4),
            "f1_score": round(float(weighted_f1), 4),
            "support": int(len(y_true)),
            "false_positive_rate": np.nan,
        }
    )
    rows.append(
        {
            "class": "overall_accuracy",
            "precision": round(overall_acc, 4),
            "recall": round(overall_acc, 4),
            "f1_score": round(overall_acc, 4),
            "support": int(len(y_true)),
            "false_positive_rate": np.nan,
        }
    )
    rows.append(
        {
            "class": "normal_operations_fpr",
            "precision": np.nan,
            "recall": np.nan,
            "f1_score": np.nan,
            "support": int(normal_total),
            "false_positive_rate": round(fpr_normal, 4),
        }
    )

    metrics_df = pd.DataFrame(rows)
    return cm, fpr_normal, metrics_df


def render_and_save_confusion_matrix(
    cm: np.ndarray,
    classes: List[str] = SCENARIO_CLASSES,
    output_png: Path = CONFUSION_MATRIX_PNG,
    overall_accuracy: Optional[float] = None,
    fpr_normal: Optional[float] = None,
) -> None:
    """
    Renders and saves a publication-quality Confusion Matrix heatmap using matplotlib.
    """
    output_png.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 6.5), dpi=300)

    # Use elegant Blue colormap
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(labelsize=10)
    cbar.set_label("Sample Count", fontsize=11, fontweight="bold", labelpad=10)

    # Labels
    formatted_labels = [c.replace("_", " ").title() for c in classes]
    ax.set_xticks(list(range(len(classes))))
    ax.set_yticks(list(range(len(classes))))
    ax.set_xticklabels(formatted_labels, fontsize=11, fontweight="bold")
    ax.set_yticklabels(formatted_labels, fontsize=11, fontweight="bold")

    ax.set_xlabel("Predicted Scenario Label", fontsize=12, fontweight="bold", labelpad=12)
    ax.set_ylabel("Actual Scenario Label", fontsize=12, fontweight="bold", labelpad=12)

    title = "Kaduwela DMA 01 & 02: Water Fraud & Leak Detection\nConfusion Matrix (Held-out 30% Test Set)"
    ax.set_title(title, fontsize=13, fontweight="bold", pad=15)

    # Annotate cell counts and row-wise recall percentage
    max_cm_val = float(np.max(cm))
    threshold = max_cm_val / 2.0
    for i in range(cm.shape[0]):
        row_sum = int(cm[i].sum())
        for j in range(cm.shape[1]):
            val = int(cm[i, j])
            pct = (val / row_sum * 100.0) if row_sum > 0 else 0.0
            color = "white" if val > threshold else "#1e293b"
            text = f"{val:,}\n({pct:.1f}%)"
            ax.text(
                j,
                i,
                text,
                ha="center",
                va="center",
                color=color,
                fontsize=11,
                fontweight="bold",
            )

    # Add subtitle summary box
    subtitle_lines: List[str] = []
    if overall_accuracy is not None:
        subtitle_lines.append(f"Accuracy: {overall_accuracy * 100:.2f}%")
    if fpr_normal is not None:
        subtitle_lines.append(f"Normal Operations FPR: {fpr_normal * 100:.2f}%")

    if subtitle_lines:
        info_text = " | ".join(subtitle_lines)
        ax.text(
            0.5,
            -0.18,
            info_text,
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=10,
            fontweight="semibold",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#f1f5f9", edgecolor="#cbd5e1"),
        )

    plt.tight_layout()
    fig.savefig(output_png, bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"\n[Artifact Saved] Confusion Matrix rendered to: {output_png}")


def export_metrics_table(metrics_df: pd.DataFrame, output_csv: Path = METRICS_CSV_PATH) -> None:
    """
    Exports summary metrics table to CSV.
    """
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    metrics_df.to_csv(output_csv, index=False)
    print(f"[Artifact Saved] Evaluation metrics summary exported to: {output_csv}")


def print_summary_console(
    cm: np.ndarray,
    fpr_normal: float,
    metrics_df: pd.DataFrame,
    classes: List[str] = SCENARIO_CLASSES,
) -> None:
    """
    Prints a clean, formatted evaluation report and tables to the console.
    """
    print("\n" + "=" * 78)
    print("   AI WATER FRAUD & ANOMALY DETECTION EVALUATION (HELD-OUT TEST SET)")
    print("=" * 78)

    # 1. Confusion Matrix Table
    print("\n" + "-" * 78)
    print("1. CONFUSION MATRIX (Actual vs. Predicted)")
    print("-" * 78)
    row_labels = [f"Actual: {c.replace('_', ' ').title()}" for c in classes]
    col_labels = [f"Pred: {c.replace('_', ' ').title()}" for c in classes]
    cm_df = pd.DataFrame(
        cm,
        index=pd.Index(row_labels),
        columns=pd.Index(col_labels),
    )
    print(cm_df.to_string())

    # 2. Operational False Positive Rate
    print("\n" + "-" * 78)
    print("2. OPERATIONAL RELIABILITY & FALSE ALARMS")
    print("-" * 78)
    normal_total = int(cm[0].sum())
    normal_tp = int(cm[0, 0])
    normal_fp = int(cm[0, 1:].sum())
    print(f"Total Normal Operations in Test Set : {normal_total:,}")
    print(f"Correctly Classified as Normal      : {normal_tp:,} ({normal_tp / normal_total * 100:.2f}%)")
    print(f"False Alarms (Misclassified)        : {normal_fp:,} ({normal_fp / normal_total * 100:.2f}%)")
    print(f"False Positive Rate (FPR) on Normal : {fpr_normal:.4f} ({fpr_normal * 100:.2f}%)")

    # 3. Summary Metrics Table
    print("\n" + "-" * 78)
    print("3. CLASSIFICATION METRICS SUMMARY TABLE")
    print("-" * 78)
    formatted_df = metrics_df.copy()
    for col in ["precision", "recall", "f1_score", "false_positive_rate"]:
        formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:.4f}" if pd.notnull(x) else "-")
    print(formatted_df.to_string(index=False))

    print("\n" + "=" * 78)
    print("Evaluation complete! All artifacts generated successfully.")
    print("=" * 78 + "\n")


def evaluate() -> Tuple[pd.DataFrame, np.ndarray, float]:
    """
    Main evaluation pipeline.
    """
    print("=" * 78)
    print("Loading models and held-out test features...")
    print("=" * 78)

    df, iso_model, rf_model = load_data_and_models()

    X = cast(pd.DataFrame, df[FEATURE_COLUMNS])
    y = cast(pd.Series, df["label"])

    print(f"Total dataset: {X.shape[0]} rows, {X.shape[1]} features")
    print(f"Scenario distribution:\n{y.value_counts().to_string()}")

    # 70/30 Stratified train-test split
    raw_splits = train_test_split(
        X,
        y,
        test_size=0.30,
        stratify=y,
        random_state=42,
    )
    X_train = cast(pd.DataFrame, raw_splits[0])
    X_test = cast(pd.DataFrame, raw_splits[1])
    y_train = cast(pd.Series, raw_splits[2])
    y_test = cast(pd.Series, raw_splits[3])

    print(f"\nTrain set: {X_train.shape[0]} samples (70%)")
    print(f"Test set : {X_test.shape[0]} samples (30% held-out)")

    # Calibrate Stage 1 anomaly threshold strictly on the training set
    print("\nCalibrating Stage 1 Anomaly Detection Threshold on training partition...")
    thresh, direction = calibrate_anomaly_threshold(X_train, y_train, iso_model)
    print(f"Optimal Anomaly Threshold: {thresh:.4f} (Direction: {direction})")

    # Perform Two-Stage Inference on held-out test set
    print("\nExecuting Two-Stage inference on held-out test split...")
    y_pred: np.ndarray = predict_two_stage_pipeline(
        X_test,
        iso_model=iso_model,
        rf_model=rf_model,
        anomaly_threshold=thresh,
        threshold_dir=direction,
    )

    # Compute metrics
    cm, fpr_normal, metrics_df = compute_metrics(y_test, y_pred, classes=SCENARIO_CLASSES)
    overall_acc = float(accuracy_score(y_test, y_pred))

    # Render & save artifacts
    render_and_save_confusion_matrix(
        cm=cm,
        classes=SCENARIO_CLASSES,
        output_png=CONFUSION_MATRIX_PNG,
        overall_accuracy=overall_acc,
        fpr_normal=fpr_normal,
    )
    export_metrics_table(metrics_df, output_csv=METRICS_CSV_PATH)

    # Print summary to console
    print_summary_console(cm, fpr_normal, metrics_df, classes=SCENARIO_CLASSES)

    return metrics_df, cm, fpr_normal


if __name__ == "__main__":
    evaluate()
