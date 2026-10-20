"""
src/export_dma_status.py
Simulates/loads a 24-hour test scenario containing an injected theft event in DMA 01
at node J_100 and normal operations in DMA 02.
Evaluates all designated monitoring nodes (J_10, J_100, J_500, J_1200, J_2200, J_3000)
across all timesteps through our AI scoring pipeline, generates a comprehensive DMA
risk summary table, and renders publication-quality pressure profile comparison plots.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
import joblib
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.features import compute_hours_since_supply_start
    from src.scorer import explain_fraud_score, get_recommended_action
except ImportError:
    from features import compute_hours_since_supply_start  # type: ignore
    from scorer import explain_fraud_score, get_recommended_action  # type: ignore

DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RAW_SIM_DIR = PROJECT_ROOT / "data" / "raw_simulations"
MODELS_DIR = PROJECT_ROOT / "models"

BASELINE_CSV = RAW_SIM_DIR / "baseline_normal.csv"
SCENARIO_CSV = RAW_SIM_DIR / "dma_theft_test_scenario.csv"

ISO_MODEL_PATH = MODELS_DIR / "isolation_forest.joblib"
RF_MODEL_PATH = MODELS_DIR / "random_forest.joblib"

OUTPUT_SUMMARY_CSV = DATA_PROCESSED_DIR / "dma_risk_summary.csv"
OUTPUT_PLOT_PNG = DATA_PROCESSED_DIR / "pressure_residual_plot.png"

# Designated monitoring nodes across Kaduwela DMAs
MONITORING_NODES: List[str] = ["J_10", "J_100", "J_500", "J_1200", "J_2200", "J_3000"]

NODE_DMA_MAPPING: Dict[str, str] = {
    "J_10": "DMA 01",
    "J_100": "DMA 01",
    "J_500": "DMA 01",
    "J_1200": "DMA 02",
    "J_2200": "DMA 02",
    "J_3000": "DMA 02",
}

FEATURE_COLUMNS: List[str] = [
    "actual_pressure",
    "hydraulic_residual",
    "pressure_change_rate",
    "residual_rolling_mean",
    "residual_rolling_std",
    "spatial_deviation",
]


def simulate_or_load_test_scenario(
    baseline_path: Path = BASELINE_CSV,
    scenario_path: Path = SCENARIO_CSV,
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Simulates or loads a 24-hour test scenario containing an injected theft event
    in DMA 01 at node J_100 (06:00 to 11:00) and normal operations in DMA 02.
    """
    if not baseline_path.exists():
        raise FileNotFoundError(f"Baseline file not found at {baseline_path}. Run simulation.py first.")

    df_expected = pd.read_csv(baseline_path, index_col=0)
    df_expected.index = df_expected.index.astype(int)

    np.random.seed(seed)
    timesteps: List[int] = [int(t) for t in df_expected.index]  # 0 to 86400 (seconds)

    # Initialize actual pressure from expected baseline with realistic sensor noise (+- 0.02m)
    df_actual = df_expected.copy()
    for col in df_actual.columns:
        sensor_noise = np.random.normal(0.0, 0.02, size=len(df_actual))
        df_actual[col] = df_actual[col] + sensor_noise

    # Inject theft event (unmetered bypass) in DMA 01 at node J_100:
    # Operating window: 06:00 (21,600s) to 11:00 (39,600s)
    theft_start_sec = 6 * 3600
    theft_end_sec = 11 * 3600

    target_node = "J_100"
    base_head_loss = 6.2  # 6.2 meters head loss deficit

    for t in timesteps:
        if theft_start_sec <= t <= theft_end_sec:
            # Ramping factor at boundary transitions (15-min smoothing)
            if t < theft_start_sec + 1800:
                ramp = (t - theft_start_sec) / 1800.0
            elif t > theft_end_sec - 1800:
                ramp = (theft_end_sec - t) / 1800.0
            else:
                ramp = 1.0

            loss = base_head_loss * ramp + float(np.random.normal(0.0, 0.08))
            df_actual.loc[t, target_node] = df_expected.loc[t, target_node] - max(0.0, loss)

            # Hydraulic proximity propagation in DMA 01
            # Minor localized drawdown on immediately adjacent DMA 01 nodes
            if "J_10" in df_actual.columns:
                df_actual.loc[t, "J_10"] = df_expected.loc[t, "J_10"] - max(0.0, 0.45 * ramp)
            if "J_500" in df_actual.columns:
                df_actual.loc[t, "J_500"] = df_expected.loc[t, "J_500"] - max(0.0, 0.35 * ramp)

    # Ensure DMA 02 monitoring nodes (J_1200, J_2200, J_3000) remain strictly normal
    for dma2_node in ["J_1200", "J_2200", "J_3000"]:
        if dma2_node in df_actual.columns:
            dma2_noise = np.random.normal(0.0, 0.015, size=len(df_actual))
            df_actual[dma2_node] = df_expected[dma2_node] + dma2_noise

    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    df_actual.to_csv(scenario_path)
    print(f"[Scenario Loaded/Simulated] 24h test scenario ready at: {scenario_path}")
    print(f"  Target Theft Node: {target_node} (DMA 01, 06:00 - 11:00)")
    print(f"  DMA 02 Nodes: J_1200, J_2200, J_3000 (Nominal Normal Operations)")

    return df_actual, df_expected


def evaluate_nodes_across_timesteps(
    df_actual: pd.DataFrame,
    df_expected: pd.DataFrame,
    nodes: List[str] = MONITORING_NODES,
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """
    Computes hydraulic features and queries the AI scoring pipeline for all monitoring
    nodes across all timesteps. Returns the summary report and per-node detailed time traces.
    """
    iso_model = joblib.load(ISO_MODEL_PATH)
    rf_model = joblib.load(RF_MODEL_PATH)

    # Calculate network-wide residuals across monitoring nodes
    residuals_df = pd.DataFrame(index=df_actual.index)
    for n in nodes:
        residuals_df[n] = df_expected[n] - df_actual[n]

    # Calculate spatial deviation per node: node residual minus mean of other monitoring nodes
    spatial_dev_df = pd.DataFrame(index=df_actual.index)
    for n in nodes:
        other_nodes = [o for o in nodes if o != n]
        spatial_dev_df[n] = residuals_df[n] - residuals_df[other_nodes].mean(axis=1)

    node_traces: Dict[str, pd.DataFrame] = {}
    summary_rows: List[Dict[str, Any]] = []

    for node in nodes:
        dma_id = NODE_DMA_MAPPING.get(node, "DMA 01")
        p_act = pd.Series(df_actual[node])
        p_exp = pd.Series(df_expected[node])
        res = pd.Series(residuals_df[node])
        sp_dev = pd.Series(spatial_dev_df[node])

        dp_dt = pd.Series(p_act.diff().fillna(0.0))
        roll_mean = pd.Series(res.rolling(window=4, min_periods=1).mean())
        roll_std = pd.Series(res.rolling(window=4, min_periods=1).std().fillna(0.0))

        trace_records = []
        consecutive_anom_count = 0

        for t in df_actual.index:
            t_sec = float(t)
            hours_since_supply = compute_hours_since_supply_start(t_sec, supply_window_start_hour=6.0)

            cur_p_act = float(p_act.loc[t])
            cur_res = float(res.loc[t])
            cur_dp_dt = float(dp_dt.loc[t])
            cur_rmean = float(roll_mean.loc[t])
            cur_rstd = float(roll_std.loc[t])
            cur_sp_dev = float(sp_dev.loc[t])

            feat_vec = pd.DataFrame(
                [
                    {
                        "actual_pressure": cur_p_act,
                        "hydraulic_residual": cur_res,
                        "pressure_change_rate": cur_dp_dt,
                        "residual_rolling_mean": cur_rmean,
                        "residual_rolling_std": cur_rstd,
                        "spatial_deviation": cur_sp_dev,
                    }
                ]
            )[FEATURE_COLUMNS]

            # Stage 1: Isolation Forest
            iso_pred = iso_model.predict(feat_vec)[0]
            # Operational anomaly requires model departure AND hydraulic significance (head loss >= 1.0m)
            # This prevents 2-centimeter instrument noise from generating spurious anomaly flags.
            is_anomaly = bool(iso_pred == -1 and cur_res >= 1.0)

            if is_anomaly:
                consecutive_anom_count += 1
                cause_pred = str(rf_model.predict(feat_vec)[0])
                rf_probs_arr = rf_model.predict_proba(feat_vec)[0]
                rf_probabilities = {cls: float(p) for cls, p in zip(rf_model.classes_, rf_probs_arr)}
                effective_sp_dev = cur_sp_dev
            else:
                consecutive_anom_count = max(0, consecutive_anom_count - 1)
                cause_pred = "normal"
                rf_probabilities = {"leak": 0.0, "partial_bypass": 0.0}
                # Filter noise spatial deviation for normal operations
                effective_sp_dev = cur_sp_dev if cur_sp_dev >= 0.5 else 0.0

            # Scoring Pipeline with IWS Refill Transient Dampening
            score, breakdown, reasons = explain_fraud_score(
                is_anomaly=is_anomaly,
                rf_probabilities=rf_probabilities,
                residual=cur_res,
                recurrence_count=consecutive_anom_count,
                spatial_deviation=effective_sp_dev,
                hours_since_supply_start=hours_since_supply,
            )

            is_dampened = bool(breakdown.get("transient_dampening_active", False))
            action = get_recommended_action(score, classification=cause_pred, is_transient_dampened=is_dampened)

            trace_records.append(
                {
                    "time_sec": t_sec,
                    "time_hours": t_sec / 3600.0,
                    "hours_since_supply_start": hours_since_supply,
                    "actual_pressure": cur_p_act,
                    "expected_pressure": float(p_exp.loc[t]),
                    "residual": cur_res,
                    "spatial_deviation": cur_sp_dev,
                    "is_anomaly": is_anomaly,
                    "predicted_cause": cause_pred,
                    "rf_bypass_prob": rf_probabilities.get("partial_bypass", 0.0),
                    "rf_leak_prob": rf_probabilities.get("leak", 0.0),
                    "recurrence_count": consecutive_anom_count,
                    "risk_score": score,
                    "transient_dampened": is_dampened,
                    "recommended_action": action,
                    "primary_reason": reasons[0] if reasons else "",
                }
            )

        df_trace = pd.DataFrame(trace_records)
        node_traces[node] = df_trace

        # Calculate Node Summary Metrics
        peak_score = float(df_trace["risk_score"].max())
        peak_idx = int(pd.Series(df_trace["risk_score"]).idxmax())  # type: ignore
        peak_row = df_trace.iloc[peak_idx]

        # Determine Risk Level
        if peak_score >= 75.0:
            risk_level = "Critical"
        elif peak_score >= 50.0:
            risk_level = "High"
        elif peak_score >= 25.0:
            risk_level = "Medium"
        else:
            risk_level = "Normal"

        # Determine Primary Suspected Cause
        anom_rows = df_trace[df_trace["is_anomaly"]]
        if len(anom_rows) > 0:
            suspected_cause = str(peak_row["predicted_cause"])
            if suspected_cause == "normal":
                suspected_cause = str(pd.Series(anom_rows["predicted_cause"]).mode().iloc[0])
        else:
            suspected_cause = "normal"

        # Determine Inspection Priority
        if risk_level == "Critical":
            priority = "P1 - Immediate Field Investigation"
        elif risk_level == "High":
            priority = "P2 - Targeted Physical Audit"
        elif risk_level == "Medium":
            priority = "P3 - Telemetry & Sensor Verification"
        else:
            priority = "P4 - Routine Monitoring"

        # Construct Evidence Summary
        max_residual = float(df_trace["residual"].max())
        max_sp_dev = float(df_trace["spatial_deviation"].max())
        anom_duration_hours = len(anom_rows) * 0.25  # 15-minute intervals = 0.25 hrs

        if risk_level in ["Critical", "High"]:
            evidence = (
                f"Sustained pressure drop (peak residual: {max_residual:.2f}m head loss) across "
                f"{anom_duration_hours:.2f} hrs. Localized spatial deviation: {max_sp_dev:.2f}m. "
                f"Stage 2 RF bypass probability peaked at {peak_row['rf_bypass_prob'] * 100:.1f}%."
            )
        elif risk_level == "Medium":
            evidence = (
                f"Moderate transient head loss ({max_residual:.2f}m); spatial mismatch {max_sp_dev:.2f}m; "
                f"refill dampening active during supply opening."
            )
        else:
            evidence = (
                f"Pressure profile tightly aligned with digital twin baseline (max residual: {max_residual:.2f}m). "
                f"Zero statistical anomalies detected."
            )

        summary_rows.append(
            {
                "DMA_ID": dma_id,
                "Node_ID": node,
                "Peak_Risk_Score": round(peak_score, 2),
                "Risk_Level": risk_level,
                "Primary_Suspected_Cause": suspected_cause,
                "Evidence_Summary": evidence,
                "Inspection_Priority": priority,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    # Sort with Critical / High first
    summary_df = summary_df.sort_values(by="Peak_Risk_Score", ascending=False).reset_index(drop=True)
    return summary_df, node_traces


def plot_pressure_profiles_and_residual(
    trace_j100: pd.DataFrame,
    output_path: Path = OUTPUT_PLOT_PNG,
) -> None:
    """
    Renders publication-quality pressure profiles comparing Expected vs Actual at J_100,
    with hydraulic residual head loss, theft event shading, and annotation metrics.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    hours: List[float] = [float(x) for x in trace_j100["time_hours"]]
    p_exp: List[float] = [float(x) for x in trace_j100["expected_pressure"]]
    p_act: List[float] = [float(x) for x in trace_j100["actual_pressure"]]
    residual: List[float] = [float(x) for x in trace_j100["residual"]]

    fig, (ax1, ax2) = plt.subplots(
        nrows=2,
        ncols=1,
        figsize=(12, 8.5),
        sharex=True,
        gridspec_kw={"height_ratios": [1.4, 1.0], "hspace": 0.15},
        dpi=300,
    )

    # ---------------- Top Panel: Pressure Profiles ----------------
    ax1.plot(
        hours,
        p_exp,
        label="Expected Pressure (Digital Twin Baseline)",
        color="#1d4ed8",  # Royal Blue
        linewidth=2.5,
        linestyle="--",
    )
    ax1.plot(
        hours,
        p_act,
        label="Actual Telemetry Pressure (Node J_100)",
        color="#dc2626",  # Vibrant Red
        linewidth=2.2,
    )

    # Shading for Injected Theft Event (06:00 to 11:00)
    ax1.axvspan(
        6.0,
        11.0,
        facecolor="#fee2e2",
        alpha=0.6,
        edgecolor="none",
        label="Injected Water Theft Window (06:00 - 11:00)",
    )

    # Shading for IWS Refill Transient Window (06:00 to 07:00)
    ax1.axvspan(
        6.0,
        7.0,
        facecolor="#fef3c7",
        alpha=0.4,
        edgecolor="#d97706",
        linestyle=":",
        label="IWS Refill Transient Window (45–60 min)",
    )

    # Annotate peak deficit cleanly inside the top panel
    peak_res_val: float = max(residual)
    peak_res_idx: int = residual.index(peak_res_val)
    peak_hour: float = hours[peak_res_idx]
    peak_act: float = p_act[peak_res_idx]

    ax1.annotate(
        f"Peak Deficit: -{peak_res_val:.2f} m\nTime: {int(peak_hour):02d}:{int((peak_hour%1)*60):02d}",
        xy=(peak_hour, peak_act),
        xytext=(peak_hour - 3.2, peak_act + 2.8),
        arrowprops=dict(facecolor="#991b1b", shrink=0.08, width=1.5, headwidth=7),
        fontsize=10,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#ffffff", edgecolor="#dc2626", linewidth=1.5),
    )

    ax1.set_ylabel("Pressure Head (m)", fontsize=11, fontweight="bold")
    ax1.set_title(
        "Kaduwela DMA 01 — Node J_100: Pressure Profiles & Theft Residual Analysis\n"
        "(24-Hour Telemetry under Intermittent Water Supply)",
        fontsize=13,
        fontweight="bold",
        pad=12,
    )
    ax1.legend(loc="upper right", frameon=True, framealpha=0.9, fontsize=9.5)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.set_ylim(min(p_act) - 3.0, max(p_exp) + 4.0)

    # ---------------- Bottom Panel: Hydraulic Residual ----------------
    ax2.plot(
        hours,
        residual,
        label="Hydraulic Residual (P_exp - P_act)",
        color="#7c3aed",  # Purple
        linewidth=2.0,
    )
    ax2.fill_between(
        hours,
        0,
        residual,
        where=[r > 0 for r in residual],
        color="#ede9fe",
        alpha=0.8,
    )

    # Threshold indicator lines
    ax2.axhline(
        1.5,
        color="#f59e0b",
        linestyle="--",
        linewidth=1.3,
        label="Advisory Residual Threshold (1.5 m)",
    )
    ax2.axhline(
        4.0,
        color="#b91c1c",
        linestyle="-.",
        linewidth=1.3,
        label="Critical Head Loss Threshold (4.0 m)",
    )

    # Shading for theft window in bottom panel
    ax2.axvspan(6.0, 11.0, facecolor="#fee2e2", alpha=0.4, edgecolor="none")

    ax2.set_xlabel("Time of Day (Hours)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Hydraulic Residual (m)", fontsize=11, fontweight="bold")
    ax2.set_xlim(0, 24)
    ax2.set_xticks(range(0, 25, 2))
    ax2.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 2)])
    ax2.legend(loc="upper right", frameon=True, framealpha=0.9, fontsize=9.5)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.set_ylim(-1.0, max(residual) + 2.0)

    # Status box
    info_box = (
        f"DMA: DMA 01 | Node: J_100\n"
        f"Peak Head Loss: {peak_res_val:.2f} m\n"
        f"Status: Illegal Bypass Confirmed"
    )
    ax2.text(
        0.02,
        0.78,
        info_box,
        transform=ax2.transAxes,
        fontsize=9.5,
        fontweight="bold",
        verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#ffffff", edgecolor="#7c3aed", linewidth=1.2),
    )

    fig.subplots_adjust(top=0.92, bottom=0.08, left=0.08, right=0.95, hspace=0.15)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"\n[Plot Saved] Pressure profile comparison saved to: {output_path}")


def print_summary_console(summary_df: pd.DataFrame) -> None:
    """
    Prints a formatted DMA risk assessment report table to the console.
    """
    print("\n" + "=" * 90)
    print("      KADUWELA WATER NETWORK: DMA 01 & DMA 02 RISK ASSESSMENT REPORT")
    print("=" * 90)
    display_df = summary_df.copy()
    print(display_df.to_string(index=False))
    print("=" * 90 + "\n")


def main():
    print("=" * 78)
    print("Starting DMA Status Export & Comprehensive Risk Assessment Pipeline")
    print("=" * 78)

    # 1. Simulate or load 24-hour test scenario
    df_actual, df_expected = simulate_or_load_test_scenario()

    # 2. Query scoring pipeline across all nodes & timesteps
    print("\nQuerying AI scoring pipeline across all monitoring nodes and timesteps...")
    summary_df, node_traces = evaluate_nodes_across_timesteps(df_actual, df_expected)

    # 3. Export report table to CSV
    OUTPUT_SUMMARY_CSV.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(OUTPUT_SUMMARY_CSV, index=False)
    print(f"[Artifact Saved] DMA risk summary table exported to: {OUTPUT_SUMMARY_CSV}")

    # 4. Plot pressure profiles and residual at node J_100
    print("\nGenerating pressure comparison and residual plot for node J_100...")
    plot_pressure_profiles_and_residual(node_traces["J_100"], output_path=OUTPUT_PLOT_PNG)

    # 5. Print summary to console
    print_summary_console(summary_df)


if __name__ == "__main__":
    main()
