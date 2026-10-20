"""
src/simulation.py
Generates synthetic training datasets for the Kaduwela water distribution network model
under Intermittent Water Supply (IWS) using Pressure-Dependent Demand (PDD).
"""

import os
from pathlib import Path
from typing import Optional, Any, cast
import numpy as np
import pandas as pd
import wntr


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INP_PATH = PROJECT_ROOT / "data" / "networks" / "kaduwela_2dma_clean_East_side.inp"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw_simulations"


def resolve_junction_name(wn, name):
    """
    Resolves junction name in the network, supporting formats like 'J100' or 'J_100'.
    """
    if name is None:
        return None
    if name in wn.junction_name_list:
        return name
    if name.startswith("J") and not name.startswith("J_"):
        alt_name = f"J_{name[1:]}"
        if alt_name in wn.junction_name_list:
            return alt_name
    alt_name = f"J_{name}"
    if alt_name in wn.junction_name_list:
        return alt_name
    raise KeyError(f"Junction '{name}' not found in water network model.")


def run_scenario(
    scenario_name: str,
    fault_type: str = "normal",
    target_junction: Optional[str] = None,
    fault_magnitude: Optional[float] = None,
    inp_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """
    Runs a 24-hour hydraulic simulation with 15-minute timesteps in Pressure-Dependent
    Demand (PDD) mode using WNTRSimulator.

    Parameters:
    -----------
    scenario_name : str
        Name of the scenario (used for exported CSV filename).
    fault_type : str
        Type of scenario: 'normal', 'leak', or 'partial_bypass'.
    target_junction : str, optional
        Junction ID where the fault is introduced (e.g. 'J100' or 'J_100').
    fault_magnitude : float, optional
        Magnitude of fault:
        - For 'normal': noise standard deviation or magnitude (0.0 for baseline reference).
        - For 'leak': leak area in m^2 (defaults to 0.0004).
        - For 'partial_bypass': withdrawal rate in LPS (defaults between 0.02 and 0.08 LPS).
    inp_path : str, optional
        Path to the network INP file.
    output_dir : str, optional
        Directory where {scenario_name}.csv will be saved.
    seed : int, optional
        Random seed for reproducibility.

    Returns:
    --------
    pd.DataFrame:
        Node pressure results over time.
    """
    if seed is not None:
        np.random.seed(seed)

    inp_file = Path(inp_path) if inp_path else DEFAULT_INP_PATH
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load water network model
    wn = wntr.network.WaterNetworkModel(str(inp_file))

    # 2. Configure Pressure-Dependent Demand (PDD)
    wn.options.hydraulic.demand_model = "PDD"
    wn.options.hydraulic.minimum_pressure = 3.5   # meters
    wn.options.hydraulic.required_pressure = 15.0  # meters

    # 3. Configure 24-hour duration with 15-minute timestep (900 s)
    wn.options.time.duration = 24 * 3600
    wn.options.time.hydraulic_timestep = 900
    wn.options.time.report_timestep = 900

    # 4. Implement scenario faults
    resolved_target = resolve_junction_name(wn, target_junction) if target_junction else None

    if fault_type == "normal":
        # Baseline reference has 0 noise; varied normal runs apply Gaussian noise (+-5%)
        is_baseline = (scenario_name == "baseline_normal") or (fault_magnitude is not None and fault_magnitude == 0.0)
        if not is_baseline:
            # Gaussian noise with std scaled so ~95% falls within +-5%
            noise_std = (fault_magnitude / 2.0) if (fault_magnitude is not None and fault_magnitude > 0) else (0.05 / 2.0)
            for _, junction in wn.junctions():
                for demand in junction.demand_timeseries_list:
                    noise = np.random.normal(loc=0.0, scale=noise_std)
                    factor = max(0.0, 1.0 + np.clip(noise, -0.05, 0.05))
                    demand.base_value *= factor

    elif fault_type == "leak":
        if not resolved_target:
            raise ValueError("A target_junction must be provided for 'leak' fault type.")
        leak_area = fault_magnitude if (fault_magnitude is not None and fault_magnitude > 0) else 0.0004
        target_node = wn.get_node(resolved_target)
        if target_node is None:
            raise KeyError(f"Junction '{resolved_target}' not found in water network model.")
        target_node.add_leak(
            wn=wn,
            area=leak_area,
            discharge_coeff=0.75,
            start_time=6 * 3600,
        )

    elif fault_type == "partial_bypass":
        if not resolved_target:
            raise ValueError("A target_junction must be provided for 'partial_bypass' fault type.")
        
        # Withdrawal rate in LPS (0.02 to 0.08 LPS)
        if fault_magnitude is not None and fault_magnitude > 0:
            withdrawal_lps = fault_magnitude
        else:
            withdrawal_lps = float(np.random.uniform(0.02, 0.08))

        # Convert LPS to m^3/s (1 LPS = 0.001 m^3/s)
        withdrawal_m3s = withdrawal_lps * 1e-3

        # Pattern active between hours 06:00 and 11:00 (hours 6, 7, 8, 9, 10)
        pattern_multipliers = [1.0 if 6 <= h < 11 else 0.0 for h in range(24)]
        pattern_name = f"bypass_pattern_{scenario_name}"
        wn.add_pattern(pattern_name, pattern_multipliers)

        target_node = wn.get_node(resolved_target)
        if target_node is None:
            raise KeyError(f"Junction '{resolved_target}' not found in water network model.")
        target_node.demand_timeseries_list.append((withdrawal_m3s, pattern_name, "bypass"))

    else:
        raise ValueError(f"Unknown fault_type '{fault_type}'. Choose from 'normal', 'leak', or 'partial_bypass'.")

    # 5. Run simulation using WNTRSimulator
    sim = wntr.sim.WNTRSimulator(wn)
    # Use robust convergence tolerance for large PDD network
    results = sim.run_sim(solver_options={"MAXITER": 50, "TOL": 1e-2})

    # 6. Extract node pressure DataFrame and export to CSV
    results_dict = cast(Any, results)
    df_pressure: pd.DataFrame = results_dict.node["pressure"]
    if df_pressure.index.name is None:
        df_pressure.index.name = "time"

    output_csv = out_dir / f"{scenario_name}.csv"
    df_pressure.to_csv(output_csv)
    print(f"[{scenario_name}] Saved pressure dataset: {output_csv} (shape: {df_pressure.shape})")

    return df_pressure


def main():
    print("=" * 70)
    print("Starting Synthetic Dataset Generation for Kaduwela Network (PDD / IWS)")
    print("=" * 70)

    # 1 baseline reference run
    print("\n--- Generating 1 Baseline Reference Run ---")
    run_scenario(
        scenario_name="baseline_normal",
        fault_type="normal",
        fault_magnitude=0.0,
        seed=42,
    )

    # 4 varied normal runs
    print("\n--- Generating 4 Varied Normal Runs (Gaussian noise +-5%) ---")
    for i in range(1, 5):
        run_scenario(
            scenario_name=f"normal_{i}",
            fault_type="normal",
            fault_magnitude=0.05,
            seed=100 + i,
        )

    # 4 leak runs at different junctions
    print("\n--- Generating 4 Leak Runs ---")
    leak_junctions = ["J100", "J500", "J1200", "J2200"]
    for j in leak_junctions:
        run_scenario(
            scenario_name=f"leak_{j}",
            fault_type="leak",
            target_junction=j,
            fault_magnitude=0.0004,
            seed=200,
        )

    # 4 partial bypass runs at different junctions (0.02 to 0.08 LPS)
    print("\n--- Generating 4 Partial Bypass Runs (0.02 to 0.08 LPS, 06:00 - 11:00) ---")
    bypass_configs = [
        ("bypass_J100", "J100", 0.03),
        ("bypass_J500", "J500", 0.05),
        ("bypass_J1200", "J1200", 0.07),
        ("bypass_J2200", "J2200", 0.04),
    ]
    for sc_name, j, mag in bypass_configs:
        run_scenario(
            scenario_name=sc_name,
            fault_type="partial_bypass",
            target_junction=j,
            fault_magnitude=mag,
            seed=300,
        )

    print("\n" + "=" * 70)
    print("Dataset generation completed successfully!")
    print(f"Generated 13 simulation runs in: {DEFAULT_OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
