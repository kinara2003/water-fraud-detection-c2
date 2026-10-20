"""
src/scorer.py
Calculates Fraud Risk Scores based on two-stage AI outputs and hydraulic heuristics:
1. Stage 1 Anomaly presence (20 pts)
2. Hydraulic residual severity up to 10m head loss (up to 25 pts)
3. Temporal recurrence: min(15, recurrence_count * 3) (up to 15 pts)
4. Stage 2 Random Forest partial_bypass confidence (up to 25 pts)
5. Spatial deviation exceeding neighborhood average (15 pts)

IWS Transient Dampening Window:
During the first 45–60 minutes after supply opens, suppresses high-risk theft alerts
unless the residual persists AND spatial mismatch is confirmed across adjacent zones.
Total score is bounded between 0.0 and 100.0.
"""

from typing import Any, Dict, List, Optional, Tuple


# IWS Refill Transient parameters
DEFAULT_TRANSIENT_WINDOW_HOURS: float = 1.0  # 45–60 minutes window (up to 1.0 hr after supply opening)
MIN_PERSISTENCE_RECURRENCE: int = 1         # Minimum prior recurrence required to confirm persistence
SPATIAL_MISMATCH_THRESHOLD: float = 0.5     # Threshold (m) to confirm localized spatial mismatch across adjacent zones


def check_transient_dampening(
    hours_since_supply_start: Optional[float],
    residual: float,
    recurrence_count: int,
    spatial_deviation: float,
    transient_window_hours: float = DEFAULT_TRANSIENT_WINDOW_HOURS,
    spatial_mismatch_threshold: float = SPATIAL_MISMATCH_THRESHOLD,
    min_persistence: int = MIN_PERSISTENCE_RECURRENCE,
) -> Tuple[bool, bool, str]:
    """
    Evaluates whether IWS pipe refill transient dampening applies:
    During the first 45–60 minutes after supply opens, suppress high-risk theft alerts
    unless the residual persists AND spatial mismatch is confirmed across adjacent zones.

    Parameters:
    -----------
    hours_since_supply_start : Optional[float]
        Hours elapsed since active supply window opened.
    residual : float
        Hydraulic residual head loss (m).
    recurrence_count : int
        Number of prior persistent anomalous events.
    spatial_deviation : float
        Node residual minus neighborhood mean residual in meters.
    transient_window_hours : float
        Length of the transient dampening window (defaults to 1.0 hr = 60 min).
    spatial_mismatch_threshold : float
        Minimum spatial deviation (m) required to confirm localized anomaly.
    min_persistence : int
        Minimum recurrence count to confirm persistence.

    Returns:
    --------
    Tuple[bool, bool, str]:
        (is_in_transient_window, should_dampen, reason_note)
    """
    if hours_since_supply_start is None:
        return False, False, "Telemetry time relative to supply window not provided."

    hours_val = float(hours_since_supply_start)
    if not (0.0 <= hours_val <= float(transient_window_hours)):
        return False, False, f"Outside transient window ({hours_val:.2f}h > {transient_window_hours:.2f}h)."

    # We are inside the first 45-60 min transient refill window
    # Check if exceptions apply:
    # 1. Residual persists (recurring anomalous events confirmed)
    residual_persists = (int(recurrence_count) >= min_persistence) and (float(residual) > 0.0)
    # 2. Spatial mismatch is confirmed across adjacent zones
    spatial_mismatch_confirmed = float(spatial_deviation) >= float(spatial_mismatch_threshold)

    if residual_persists and spatial_mismatch_confirmed:
        # Override dampening: both persistence and spatial mismatch confirm genuine localized fault
        return True, False, (
            f"Override: Persistent residual ({recurrence_count} prior events) and confirmed "
            f"spatial mismatch ({spatial_deviation:.2f}m >= {spatial_mismatch_threshold:.2f}m) across adjacent zones."
        )
    else:
        # Suppress high-risk alerts: refill hydraulics likely caused the transient pressure drop
        missing = []
        if not residual_persists:
            missing.append(f"residual persistence unconfirmed (recurrence={recurrence_count} < {min_persistence})")
        if not spatial_mismatch_confirmed:
            missing.append(f"spatial mismatch unconfirmed ({spatial_deviation:.2f}m < {spatial_mismatch_threshold:.2f}m)")
        reason = f"Refill transient dampening active: {'; '.join(missing)}."
        return True, True, reason


def calculate_fraud_score(
    is_anomaly: bool,
    rf_probabilities: Dict[str, float],
    residual: float,
    recurrence_count: int,
    spatial_deviation: float = 0.0,
    hours_since_supply_start: Optional[float] = None,
    transient_window_hours: float = DEFAULT_TRANSIENT_WINDOW_HOURS,
    spatial_mismatch_threshold: float = SPATIAL_MISMATCH_THRESHOLD,
    min_persistence: int = MIN_PERSISTENCE_RECURRENCE,
) -> float:
    """
    Computes Fraud Risk Score (0.0 to 100.0).

    Weight Points (max 100):
    ------------------------
    - Anomaly presence from Stage 1: 20 pts
    - Hydraulic residual severity: up to 25 pts (scales with head loss up to 10m)
    - Temporal recurrence: min(15, recurrence_count * 3) pts
    - Random Forest bypass confidence: rf_probabilities.get('partial_bypass', 0.0) * 25 pts
    - Spatial deviation: 15 pts if residual exceeds neighborhood average (spatial_deviation > 0)

    Transient Dampening:
    --------------------
    During the first 45–60 minutes after supply opens, suppresses high-risk theft alerts
    (dampens score below high-risk thresholds) unless residual persists and spatial mismatch
    is confirmed across adjacent zones.

    Returns:
    --------
    float:
        Score bounded between 0.0 and 100.0.
    """
    # 1. Anomaly presence from Stage 1 (20 pts)
    anomaly_pts = 20.0 if bool(is_anomaly) else 0.0

    # 2. Hydraulic residual severity: scales with head loss up to 10m (up to 25 pts)
    effective_residual = max(0.0, float(residual))
    residual_pts = min(25.0, (effective_residual / 10.0) * 25.0)

    # 3. Temporal recurrence: min(15, recurrence_count * 3) pts
    recurrence_pts = float(min(15.0, max(0, int(recurrence_count) * 3)))

    # 4. Random Forest bypass confidence: rf_probabilities.get('partial_bypass', 0.0) * 25 pts
    if spatial_deviation == 0.0 and "spatial_deviation" in rf_probabilities:
        spatial_deviation = float(rf_probabilities["spatial_deviation"])

    bypass_prob = float(rf_probabilities.get("partial_bypass", 0.0))
    bypass_pts = min(25.0, max(0.0, bypass_prob * 25.0))

    # 5. Spatial deviation: 15 pts if residual exceeds neighborhood average
    spatial_pts = 15.0 if float(spatial_deviation) > 0.0 else 0.0

    # Total unadjusted score
    raw_score = anomaly_pts + residual_pts + recurrence_pts + bypass_pts + spatial_pts

    # Check transient dampening window
    _, should_dampen, _ = check_transient_dampening(
        hours_since_supply_start=hours_since_supply_start,
        residual=effective_residual,
        recurrence_count=recurrence_count,
        spatial_deviation=spatial_deviation,
        transient_window_hours=transient_window_hours,
        spatial_mismatch_threshold=spatial_mismatch_threshold,
        min_persistence=min_persistence,
    )

    if should_dampen:
        # Suppress high-risk theft alerts by scaling down and capping below high-risk threshold (<= 40.0 pts)
        dampened_score = min(40.0, raw_score * 0.5)
        return round(max(0.0, dampened_score), 2)

    bounded_score = round(max(0.0, min(100.0, raw_score)), 2)
    return bounded_score


def explain_fraud_score(
    is_anomaly: bool,
    rf_probabilities: Dict[str, float],
    residual: float,
    recurrence_count: int,
    spatial_deviation: float = 0.0,
    hours_since_supply_start: Optional[float] = None,
    transient_window_hours: float = DEFAULT_TRANSIENT_WINDOW_HOURS,
    spatial_mismatch_threshold: float = SPATIAL_MISMATCH_THRESHOLD,
    min_persistence: int = MIN_PERSISTENCE_RECURRENCE,
) -> Tuple[float, Dict[str, Any], List[str]]:
    """
    Computes Fraud Risk Score and returns detailed breakdown and explanatory reasons list.
    Applies IWS refill transient dampening during first 45–60 min after supply opens.

    Returns:
    --------
    Tuple[float, Dict[str, Any], List[str]]:
        (fraud_score, points_breakdown, reasons_list)
    """
    anomaly_pts = 20.0 if bool(is_anomaly) else 0.0
    effective_residual = max(0.0, float(residual))
    residual_pts = min(25.0, (effective_residual / 10.0) * 25.0)
    recurrence_pts = float(min(15.0, max(0, int(recurrence_count) * 3)))
    bypass_prob = float(rf_probabilities.get("partial_bypass", 0.0))
    bypass_pts = min(25.0, max(0.0, bypass_prob * 25.0))
    spatial_pts = 15.0 if float(spatial_deviation) > 0.0 else 0.0

    raw_score = round(max(0.0, min(100.0, anomaly_pts + residual_pts + recurrence_pts + bypass_pts + spatial_pts)), 2)

    is_in_transient, should_dampen, transient_note = check_transient_dampening(
        hours_since_supply_start=hours_since_supply_start,
        residual=effective_residual,
        recurrence_count=recurrence_count,
        spatial_deviation=spatial_deviation,
        transient_window_hours=transient_window_hours,
        spatial_mismatch_threshold=spatial_mismatch_threshold,
        min_persistence=min_persistence,
    )

    if should_dampen:
        final_score = round(min(40.0, raw_score * 0.5), 2)
    else:
        final_score = raw_score

    breakdown: Dict[str, Any] = {
        "anomaly_presence_pts": anomaly_pts,
        "hydraulic_residual_pts": round(residual_pts, 2),
        "temporal_recurrence_pts": recurrence_pts,
        "rf_bypass_confidence_pts": round(bypass_pts, 2),
        "spatial_deviation_pts": spatial_pts,
        "raw_score": raw_score,
        "hours_since_supply_start": hours_since_supply_start,
        "is_transient_window": is_in_transient,
        "transient_dampening_active": should_dampen,
    }

    reasons: List[str] = []
    if is_anomaly:
        reasons.append("Stage 1 Anomaly: Statistical outlier detected relative to normal hydraulic digital twin (+20.0 pts)")
    else:
        reasons.append("Stage 1 Normal: Pressure profile conforms within digital twin bounds (0.0 pts)")

    if effective_residual > 0.0:
        reasons.append(f"Hydraulic severity: {effective_residual:.2f} m head loss observed (+{residual_pts:.2f} pts)")
    else:
        reasons.append("Hydraulic severity: No pressure deficit below expected baseline (0.0 pts)")

    if recurrence_count > 0:
        reasons.append(f"Temporal recurrence: {recurrence_count} prior persistent events logged (+{recurrence_pts:.1f} pts)")

    if bypass_prob > 0.0:
        reasons.append(f"RF Classifier Confidence: {bypass_prob * 100:.1f}% probability of unmetered bypass (+{bypass_pts:.2f} pts)")

    if spatial_deviation > 0.0:
        reasons.append(f"Spatial anomaly: Node pressure drop exceeds local DMA neighborhood average by {spatial_deviation:.2f} m (+15.0 pts)")

    # Transient window explanations
    if is_in_transient:
        if should_dampen:
            reasons.append(
                f"IWS Refill Transient (first 45–60 min after supply opens, elapsed={hours_since_supply_start:.2f}h): "
                f"High-risk alert suppressed due to pipe-filling refill hydraulics ({transient_note})."
            )
        else:
            reasons.append(
                f"IWS Refill Transient Override (elapsed={hours_since_supply_start:.2f}h): "
                f"High-risk alert maintained during refill window ({transient_note})."
            )

    return final_score, breakdown, reasons


def get_recommended_action(
    score: float,
    classification: Optional[str] = None,
    is_transient_dampened: bool = False,
) -> str:
    """
    Returns recommended field action based on Fraud Risk Score.
    Suppresses high-risk field inspections/audits during IWS refill transient windows.
    """
    if is_transient_dampened:
        return "Increased Telemetry Monitoring (Refill Transient - High-Risk Alert Suppressed)"
    if score > 70.0:
        return "Field Inspection Recommended"
    elif score > 45.0:
        return "Targeted Meter Audit & Verification"
    elif score > 25.0:
        return "Increased Telemetry Monitoring"
    else:
        return "Routine Monitoring"
