"""
src/features.py
Transforms raw simulation pressure CSVs into a training feature matrix
for AI-based water fraud and leak detection on Kaduwela DMA 01 & 02.
"""

from pathlib import Path
from typing import List, Tuple
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_SIM_DIR = PROJECT_ROOT / "data" / "raw_simulations"
BASELINE_PATH = RAW_SIM_DIR / "baseline_normal.csv"
OUTPUT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_FEATURES_CSV = OUTPUT_PROCESSED_DIR / "training_features.csv"
OUTPUT_FEATURES_WIDE_CSV = OUTPUT_PROCESSED_DIR / "training_features_wide.csv"

# Candidate sensor junctions across Kaduwela DMA 01 & 02
CANDIDATE_SENSORS: List[str] = ["J_10", "J_100", "J_500", "J_1200", "J_2200", "J_3000"]

# Active IWS supply window schedule:
# Kaduwela DMA 01 & 02 morning distribution cycle opens at 06:00 (6.0 hours, 21,600s)
DEFAULT_SUPPLY_WINDOW_START_HOUR: float = 6.0


def compute_hours_since_supply_start(
    time_seconds: float,
    supply_window_start_hour: float = DEFAULT_SUPPLY_WINDOW_START_HOUR,
    cycle_hours: float = 24.0,
) -> float:
    """
    Computes hours elapsed since the active IWS supply window opened.

    Parameters:
    -----------
    time_seconds : float
        Simulation or telemetry timestamp in seconds.
    supply_window_start_hour : float
        Hour of day (0-24) when the active supply window opens (default 6.0 for 06:00).
    cycle_hours : float
        Total duration of operational supply cycle (default 24.0 hours).

    Returns:
    --------
    float:
        Hours elapsed since supply window start (0.0 to cycle_hours).
    """
    time_hours = (float(time_seconds) / 3600.0) % cycle_hours
    elapsed = (time_hours - float(supply_window_start_hour)) % cycle_hours
    return round(float(elapsed), 4)


def get_scenario_label(filename_or_stem: str) -> str:
    """
    Extracts scenario label ('normal', 'leak', or 'partial_bypass') from scenario name.
    """
    stem = Path(filename_or_stem).stem.lower()
    if stem.startswith("baseline_normal") or stem.startswith("normal"):
        return "normal"
    elif stem.startswith("leak"):
        return "leak"
    elif stem.startswith("bypass") or stem.startswith("partial_bypass"):
        return "partial_bypass"
    else:
        raise ValueError(f"Unrecognized scenario type in filename: {filename_or_stem}")


def process_simulation_features(
    sim_csv_path: Path,
    df_expected: pd.DataFrame,
    sensors: List[str] = CANDIDATE_SENSORS,
    supply_window_start_hour: float = DEFAULT_SUPPLY_WINDOW_START_HOUR,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Computes hydraulic features for a single simulation CSV relative to expected digital twin baseline.

    Features computed per sensor:
    - P_actual: actual pressure
    - P_expected: expected pressure from baseline digital twin
    - residual: P_expected - P_actual
    - dP_dt: rate of pressure change P_actual(t) - P_actual(t-1)
    - residual_rolling_mean: 4-timestep rolling mean of residual
    - residual_rolling_std: 4-timestep rolling standard deviation of residual
    - spatial_deviation: sensor residual minus mean residual across all other sensors
    - hours_since_supply_start: temporal feature measuring hours elapsed since active supply window opened

    Returns:
    --------
    Tuple[pd.DataFrame, pd.DataFrame]:
        (long_features_df, wide_features_df)
    """
    scenario_name = sim_csv_path.stem
    label = get_scenario_label(scenario_name)

    # Load actual pressures for candidate sensors
    df_actual = pd.read_csv(sim_csv_path, index_col=0)
    P_actual = df_actual[sensors].copy()
    P_exp = df_expected[sensors].copy()

    # Align indexes
    P_actual.index = P_actual.index.astype(int)
    P_exp.index = P_exp.index.astype(int)

    # 1. Hydraulic Residual = P_expected - P_actual
    residual = P_exp - P_actual

    # 2. Rate of change: dP/dt = P_actual(t) - P_actual(t-1)
    dp_dt = P_actual.diff().fillna(0.0)

    # 3. 4-timestep rolling mean and std of the residual (min_periods=1 preserves early timesteps)
    rolling_mean = residual.rolling(window=4, min_periods=1).mean()
    rolling_std = residual.rolling(window=4, min_periods=1).std().fillna(0.0)

    # 4. Spatial deviation: sensor residual minus mean residual across all other sensors
    spatial_deviation = pd.DataFrame(index=residual.index, columns=pd.Index(sensors), dtype=float)
    for s in sensors:
        other_sensors = [o for o in sensors if o != s]
        mean_others = residual[other_sensors].mean(axis=1)
        spatial_deviation[s] = residual[s] - mean_others

    # Construct Long Format (per sensor observation per timestep)
    long_rows = []
    for t in residual.index:
        elapsed_supply_hours = compute_hours_since_supply_start(
            time_seconds=float(t),
            supply_window_start_hour=supply_window_start_hour,
        )
        for s in sensors:
            long_rows.append(
                {
                    "scenario": scenario_name,
                    "time": t,
                    "sensor_id": s,
                    # Temporal supply schedule feature
                    "hours_since_supply_start": elapsed_supply_hours,
                    # Feature names matching Stage 1 & Stage 2 requirements
                    "actual_pressure": float(P_actual.loc[t, s]),
                    "hydraulic_residual": float(residual.loc[t, s]),
                    "pressure_change_rate": float(dp_dt.loc[t, s]),
                    "residual_rolling_mean": float(rolling_mean.loc[t, s]),
                    "residual_rolling_std": float(rolling_std.loc[t, s]),
                    "spatial_deviation": float(spatial_deviation.loc[t, s]),
                    # Compatibility aliases
                    "P_actual": float(P_actual.loc[t, s]),
                    "P_expected": float(P_exp.loc[t, s]),
                    "residual": float(residual.loc[t, s]),
                    "dP_dt": float(dp_dt.loc[t, s]),
                    "label": label,
                }
            )
    long_df = pd.DataFrame(long_rows)

    # Construct Wide Format (network-level features per timestep)
    wide_data = {
        "scenario": scenario_name,
        "time": residual.index,
        "hours_since_supply_start": [
            compute_hours_since_supply_start(float(t), supply_window_start_hour=supply_window_start_hour)
            for t in residual.index
        ],
    }
    for s in sensors:
        wide_data[f"{s}_P_actual"] = np.asarray(P_actual[s])
        wide_data[f"{s}_P_expected"] = np.asarray(P_exp[s])
        wide_data[f"{s}_residual"] = np.asarray(residual[s])
        wide_data[f"{s}_dP_dt"] = np.asarray(dp_dt[s])
        wide_data[f"{s}_residual_rolling_mean"] = np.asarray(rolling_mean[s])
        wide_data[f"{s}_residual_rolling_std"] = np.asarray(rolling_std[s])
        wide_data[f"{s}_spatial_deviation"] = np.asarray(spatial_deviation[s])
    wide_data["label"] = label
    wide_df = pd.DataFrame(wide_data)

    return long_df, wide_df


def generate_training_matrix(
    raw_sim_dir: Path = RAW_SIM_DIR,
    baseline_csv: Path = BASELINE_PATH,
    output_csv: Path = OUTPUT_FEATURES_CSV,
    output_wide_csv: Path = OUTPUT_FEATURES_WIDE_CSV,
    sensors: List[str] = CANDIDATE_SENSORS,
    supply_window_start_hour: float = DEFAULT_SUPPLY_WINDOW_START_HOUR,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Transforms all simulation CSVs into training feature matrices and saves them.
    """
    print(f"Loading digital twin baseline reference: {baseline_csv}")
    if not baseline_csv.exists():
        raise FileNotFoundError(f"Baseline CSV not found at {baseline_csv}. Run simulation.py first.")

    df_expected = pd.read_csv(baseline_csv, index_col=0)
    for s in sensors:
        if s not in df_expected.columns:
            raise KeyError(f"Candidate sensor '{s}' not present in {baseline_csv}")

    # Only include training simulation files (ignore evaluation test scenarios like dma_theft_test_scenario)
    sim_files = [
        f for f in sorted(list(raw_sim_dir.glob("*.csv")))
        if not f.stem.startswith("dma_theft") and not f.stem.startswith("test_")
    ]
    if not sim_files:
        raise FileNotFoundError(f"No simulation CSVs found in {raw_sim_dir}")

    print(f"Found {len(sim_files)} simulation CSVs to process across candidate sensors: {sensors}")

    all_long_dfs = []
    all_wide_dfs = []

    for sim_file in sim_files:
        long_df, wide_df = process_simulation_features(
            sim_file,
            df_expected,
            sensors=sensors,
            supply_window_start_hour=supply_window_start_hour,
        )
        all_long_dfs.append(long_df)
        all_wide_dfs.append(wide_df)
        print(f"  Processed [{sim_file.name}]: label={long_df['label'].iloc[0]}, long_shape={long_df.shape}")

    # Concatenate all rows
    final_long_df = pd.concat(all_long_dfs, ignore_index=True)
    final_wide_df = pd.concat(all_wide_dfs, ignore_index=True)

    # Save to data/processed/
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    final_long_df.to_csv(output_csv, index=False)
    print(f"\nSaved training features (primary matrix): {output_csv}")
    print(f"  Shape: {final_long_df.shape}")
    print(f"  Label distribution:\n{final_long_df['label'].value_counts().to_string()}")

    if output_wide_csv:
        final_wide_df.to_csv(output_wide_csv, index=False)
        print(f"\nSaved wide network training features: {output_wide_csv} (shape: {final_wide_df.shape})")

    return final_long_df, final_wide_df


def main():
    print("=" * 70)
    print("Extracting Hydraulic Features from Raw Simulations for Model Training")
    print("=" * 70)
    generate_training_matrix()
    print("=" * 70)
    print("Feature generation completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
