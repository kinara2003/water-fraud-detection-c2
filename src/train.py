"""
src/train.py
Trains a two-stage AI system for water network anomaly detection and fraud classification:
- Stage 1: IsolationForest for Anomaly Detection (trained on normal operating conditions).
- Stage 2: RandomForestClassifier for Root Cause Classification (leak vs. partial_bypass).
"""

from pathlib import Path
from typing import Any, Tuple, cast
import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_CSV_PATH = PROJECT_ROOT / "data" / "processed" / "training_features.csv"
MODELS_DIR = PROJECT_ROOT / "models"
ISO_FOREST_MODEL_PATH = MODELS_DIR / "isolation_forest.joblib"
RANDOM_FOREST_MODEL_PATH = MODELS_DIR / "random_forest.joblib"

# Model feature set
FEATURE_COLUMNS = [
    "actual_pressure",
    "hydraulic_residual",
    "pressure_change_rate",
    "residual_rolling_mean",
    "residual_rolling_std",
    "spatial_deviation",
]


def load_dataset(csv_path: Path = FEATURES_CSV_PATH) -> pd.DataFrame:
    """
    Loads training feature matrix and ensures required feature columns exist.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Feature dataset not found at {csv_path}. Run features.py first.")

    df = pd.read_csv(csv_path)

    # Column mapping fallback in case shorthand names are used
    column_aliases = {
        "P_actual": "actual_pressure",
        "residual": "hydraulic_residual",
        "dP_dt": "pressure_change_rate",
    }
    for old_col, new_col in column_aliases.items():
        if new_col not in df.columns and old_col in df.columns:
            df[new_col] = df[old_col]

    missing_cols = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing_cols:
        raise KeyError(f"Missing required feature columns in {csv_path}: {missing_cols}")

    if "label" not in df.columns:
        raise KeyError(f"Missing 'label' column in {csv_path}")

    return df


def train_stage1_anomaly_detector(
    df: pd.DataFrame,
    contamination: float = 0.03,
    random_state: int = 42,
    model_output_path: Path = ISO_FOREST_MODEL_PATH,
) -> IsolationForest:
    """
    Stage 1: Fits IsolationForest on normal operations for anomaly detection.
    """
    print("-" * 65)
    print("Stage 1: Training Anomaly Detection Model (Isolation Forest)")
    print("-" * 65)

    df_normal = df[df["label"] == "normal"]
    X_normal = df_normal[FEATURE_COLUMNS]
    print(f"Training samples (label == 'normal'): {X_normal.shape[0]}")
    print(f"Features used ({len(FEATURE_COLUMNS)}): {FEATURE_COLUMNS}")

    model = IsolationForest(
        contamination=cast(Any, contamination),
        random_state=random_state,
    )
    model.fit(X_normal)

    # Save model
    model_output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_output_path)
    print(f"Stage 1 model saved successfully to: {model_output_path}")

    return model


def train_stage2_root_cause_classifier(
    df: pd.DataFrame,
    n_estimators: int = 100,
    max_depth: int = 8,
    random_state: int = 42,
    model_output_path: Path = RANDOM_FOREST_MODEL_PATH,
) -> Tuple[RandomForestClassifier, str]:
    """
    Stage 2: Trains RandomForestClassifier on anomalous rows to classify root cause.
    """
    print("\n" + "-" * 65)
    print("Stage 2: Training Root Cause Classification Model (Random Forest)")
    print("-" * 65)

    df_anomalous = df[df["label"] != "normal"]
    X = pd.DataFrame(df_anomalous[FEATURE_COLUMNS])
    y = pd.Series(df_anomalous["label"])

    print(f"Total anomalous samples (label != 'normal'): {X.shape[0]}")
    print(f"Class distribution:\n{y.value_counts().to_string()}")

    # 70/30 Stratified train-test split
    split_res = train_test_split(
        X,
        y,
        test_size=0.3,
        stratify=y,
        random_state=random_state,
    )
    X_train = pd.DataFrame(split_res[0], columns=pd.Index(FEATURE_COLUMNS))
    X_test = pd.DataFrame(split_res[1], columns=pd.Index(FEATURE_COLUMNS))
    y_train = pd.Series(split_res[2])
    y_test = pd.Series(split_res[3])
    print(f"\nTrain split: {X_train.shape[0]} samples | Test split: {X_test.shape[0]} samples")

    # Fit RandomForestClassifier
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state,
    )
    model.fit(X_train, y_train)

    # Evaluate on test split
    y_pred = model.predict(X_test)
    report = str(classification_report(y_test, y_pred, digits=4))
    print("\nClassification Report (Test Split):")
    print(report)

    # Save model
    model_output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_output_path)
    print(f"Stage 2 model saved successfully to: {model_output_path}")

    return model, report


def main():
    print("=" * 65)
    print("Two-Stage AI Training Pipeline: Water Fraud & Leak Detection")
    print("=" * 65)

    # 1. Load feature dataset
    print(f"\nLoading dataset from: {FEATURES_CSV_PATH}")
    df = load_dataset(FEATURES_CSV_PATH)
    print(f"Dataset loaded: {df.shape[0]} total rows, {df.shape[1]} columns")

    # 2. Stage 1: Anomaly Detection
    train_stage1_anomaly_detector(df)

    # 3. Stage 2: Root Cause Classification
    train_stage2_root_cause_classifier(df)

    print("\n" + "=" * 65)
    print("Training pipeline completed successfully!")
    print(f"Artifacts saved in: {MODELS_DIR}")
    print("=" * 65)


if __name__ == "__main__":
    main()
