"""
app/routes/network_status.py
FastAPI router for real-time live network map state and bypass anomaly dispatch.

Provides endpoint:
  GET /api/v1/network/live-map-state
    Returns the current operational state of all 6 Kaduwela East zones:
    - Normal State:
        * active_incident: null
        * All zones have status: 'NORMAL', color: '#10b981' (green)
        * No junction pins or GPS coordinates are returned (clean, calm map)
    - Bypass Anomaly State (e.g. Zone 04 suspicion score >= 70%):
        * Flagged zone has status: 'FRAUD_ALERT', color: '#ef4444' (red)
        * active_incident contains suspect junction J_100, coordinates [6.93541, 79.98425],
          search_radius_m: 50, landmark, google_maps_url, and evidence reasons.
    - Supports query parameter override: ?state=normal or ?state=bypass
    - Supports dynamic simulation toggle via POST /api/v1/network/live-map-state/simulate
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/network", tags=["Network Live State"])

# Standard color tokens
COLOR_NORMAL = "#10b981"      # Emerald green
COLOR_CAUTION = "#f59e0b"     # Amber yellow
COLOR_FRAUD_ALERT = "#ef4444" # Ruby red

# Server-side simulation state (defaults to 'normal' or toggled to 'bypass')
_CURRENT_SIMULATION_STATE: str = "normal"


# ==============================================================================
# Pydantic Schemas
# ==============================================================================
class ActiveIncident(BaseModel):
    zone_id: str = Field(default="Zone 04", description="Affected operational zone ID")
    suspect_junction: str = Field(default="J_100", description="Pinpointed suspect junction node")
    coordinates: List[float] = Field(
        default=[6.93541, 79.98425],
        description="Target GPS coordinates [latitude, longitude]",
    )
    search_radius_m: int = Field(default=50, description="Inspection corridor radius in meters")
    landmark: str = Field(
        default="Kaduwela East Sector Road (Near Node J_100 Chamber)",
        description="Field navigation access landmark",
    )
    google_maps_url: str = Field(
        default="https://www.google.com/maps/search/?api=1&query=6.93541,79.98425",
        description="Direct Google Maps URL for field dispatch",
    )
    reasons: List[str] = Field(
        default=[
            "Missing 6.0m pressure",
            "Recurring 06:45–09:30 AM",
            "Acoustic leak check negative",
        ],
        description="Forensic evidentiary factors confirming unauthorized withdrawal",
    )
    detected_at: str = Field(default="06:45 AM", description="Anomaly onset timestamp")
    suspicion_score: float = Field(default=89.0, description="Fraud suspicion confidence percentage")


class ZoneLiveState(BaseModel):
    zone_id: str = Field(description="Operational zone identifier")
    name: str = Field(description="Descriptive zone name")
    dma_id: str = Field(description="DMA identifier (DMA 01 or DMA 02)")
    status: str = Field(description="State: 'NORMAL', 'CAUTION', or 'FRAUD_ALERT'")
    color: str = Field(description="Display color code: '#10b981', '#f59e0b', or '#ef4444'")
    sensor_node_id: str = Field(description="Monitoring sensor node ID")
    risk_score: float = Field(description="Suspicion percentage score (0-100%)")
    pressure_residual_m: float = Field(description="Pressure residual deficit in meters")


class LiveMapStateResponse(BaseModel):
    status: str = Field(default="success")
    simulation_state: str = Field(description="Active simulation mode ('normal' or 'bypass')")
    active_incident: Optional[ActiveIncident] = Field(
        default=None,
        description="Active fraud incident dossier (null when all zones are normal)",
    )
    zones: List[ZoneLiveState] = Field(description="Live status array for all 6 operational zones")
    total_zones: int = Field(default=6)
    incident_count: int = Field(default=0)


class SimulationToggleRequest(BaseModel):
    state: str = Field(
        default="bypass",
        description="Target simulation state: 'normal', 'bypass' / 'fraud_alert', or 'caution'",
    )


class TelemetryInput(BaseModel):
    zone_id: Optional[str] = Field(default="Zone 04", description="Operational zone ID")
    sensor_node_id: Optional[str] = Field(default="J_100", description="Sensor node ID")
    node_id: Optional[str] = Field(default="J_100", description="Alias for sensor node ID")
    observed_pressure: float = Field(default=21.0, description="Observed pressure head in meters")
    expected_pressure: float = Field(default=21.0, description="Expected pressure head in meters")
    delta_p: Optional[float] = Field(default=None, description="Pressure drop Delta P (e.g. -6.0m)")


# ==============================================================================
# Base Zone Definitions for the 6 Operational Zones
# ==============================================================================
BASE_OPERATIONAL_ZONES = [
    {
        "zone_id": "Zone 01",
        "name": "Zone 01 - Kaduwela Town Central",
        "dma_id": "DMA 01",
        "sensor_node_id": "J_10",
        "base_risk": 12.0,
        "base_residual": -0.2,
    },
    {
        "zone_id": "Zone 02",
        "name": "Zone 02 - Nawagamuwa North",
        "dma_id": "DMA 01",
        "sensor_node_id": "J_20",
        "base_risk": 18.0,
        "base_residual": -0.2,
    },
    {
        "zone_id": "Zone 03",
        "name": "Zone 03 - Korathota Junction",
        "dma_id": "DMA 02",
        "sensor_node_id": "J_500",
        "base_risk": 15.0,
        "base_residual": -0.1,
    },
    {
        "zone_id": "Zone 04",
        "name": "Zone 04 - Kaduwela East Industrial",
        "dma_id": "DMA 01",
        "sensor_node_id": "J_100",
        "base_risk": 14.0,
        "base_residual": -0.3,
        "bypass_risk": 89.0,
        "bypass_residual": -6.0,
    },
    {
        "zone_id": "Zone 05",
        "name": "Zone 05 - Welihinda Ridge",
        "dma_id": "DMA 02",
        "sensor_node_id": "J_1200",
        "base_risk": 22.0,
        "base_residual": -0.3,
    },
    {
        "zone_id": "Zone 06",
        "name": "Zone 06 - Welivita Highway Exit",
        "dma_id": "DMA 02",
        "sensor_node_id": "J_3000",
        "base_risk": 16.0,
        "base_residual": -0.1,
    },
]


def build_live_map_state(state: str) -> LiveMapStateResponse:
    """
    Builds the complete LiveMapStateResponse according to the requested state:
      - 'normal': active_incident = None, all 6 zones NORMAL with '#10b981', no GPS/pins.
      - 'bypass' / 'fraud_alert': Zone 04 is FRAUD_ALERT with '#ef4444', active_incident populated.
      - 'caution': Zone 04 is CAUTION with '#f59e0b', active_incident = None.
    """
    normalized_state = state.lower().strip()
    is_bypass = normalized_state in ("bypass", "fraud_alert", "alert", "anomaly", "theft")
    is_caution = normalized_state in ("caution", "warning")

    zones_output: List[ZoneLiveState] = []

    for z in BASE_OPERATIONAL_ZONES:
        zid = z["zone_id"]
        if zid == "Zone 04" and is_bypass:
            zone_status = "FRAUD_ALERT"
            zone_color = COLOR_FRAUD_ALERT
            risk = z.get("bypass_risk", 89.0)
            residual = z.get("bypass_residual", -6.0)
        elif zid == "Zone 04" and is_caution:
            zone_status = "CAUTION"
            zone_color = COLOR_CAUTION
            risk = 55.0
            residual = -2.5
        else:
            zone_status = "NORMAL"
            zone_color = COLOR_NORMAL
            risk = z["base_risk"]
            residual = z["base_residual"]

        zones_output.append(
            ZoneLiveState(
                zone_id=zid,
                name=z["name"],
                dma_id=z["dma_id"],
                status=zone_status,
                color=zone_color,
                sensor_node_id=z["sensor_node_id"],
                risk_score=risk,
                pressure_residual_m=residual,
            )
        )

    if is_bypass:
        active_inc = ActiveIncident(
            zone_id="Zone 04",
            suspect_junction="J_100",
            coordinates=[6.93541, 79.98425],
            search_radius_m=50,
            landmark="Kaduwela East Sector Road (Near Node J_100 Chamber)",
            google_maps_url="https://www.google.com/maps/search/?api=1&query=6.93541,79.98425",
            reasons=[
                "Missing 6.0m pressure",
                "Recurring 06:45–09:30 AM",
                "Acoustic leak check negative",
            ],
            detected_at="06:45 AM",
            suspicion_score=89.0,
        )
        incident_count = 1
        effective_mode = "bypass"
    else:
        active_inc = None
        incident_count = 0
        effective_mode = "caution" if is_caution else "normal"

    return LiveMapStateResponse(
        status="success",
        simulation_state=effective_mode,
        active_incident=active_inc,
        zones=zones_output,
        total_zones=len(zones_output),
        incident_count=incident_count,
    )


# ==============================================================================
# Endpoints
# ==============================================================================
@router.get(
    "/live-map-state",
    response_model=LiveMapStateResponse,
    summary="Get Live Operational Map State for all 6 Zones",
)
def get_live_map_state(
    state: Optional[str] = Query(
        default=None,
        description="Simulation state override: 'normal', 'bypass' (fraud alert), or 'caution'. "
                    "If omitted, uses the active server simulation state.",
    ),
    simulate_bypass: Optional[bool] = Query(
        default=None,
        description="Convenience boolean flag: true for bypass, false for normal.",
    ),
) -> LiveMapStateResponse:
    """
    Returns live map state for all 6 operational zones across Kaduwela East.

    - **Normal State**:
        * `active_incident`: `null`
        * All zones have `status: 'NORMAL'`, `color: '#10b981'` (green).
        * No junction pins or GPS coordinates are returned (clean, calm map).
    - **Bypass Anomaly State**:
        * Zone 04 has `status: 'FRAUD_ALERT'`, `color: '#ef4444'` (red).
        * `active_incident` populated with suspect junction `J_100`, coordinates `[6.93541, 79.98425]`,
          search radius `50m`, landmark, direct Google Maps URL, and evidence reasons.
    """
    if state is not None:
        effective_state = state
    elif simulate_bypass is not None:
        effective_state = "bypass" if simulate_bypass else "normal"
    else:
        effective_state = _CURRENT_SIMULATION_STATE

    return build_live_map_state(effective_state)


@router.post(
    "/live-map-state/simulate",
    response_model=LiveMapStateResponse,
    summary="Set Server Simulation State (normal vs bypass)",
)
def set_simulation_state(
    state: Optional[str] = Query(
        default=None,
        description="Target state query override ('normal' or 'bypass')",
    ),
    payload: Optional[SimulationToggleRequest] = Body(
        default=None,
        description="JSON body with target state",
    ),
) -> LiveMapStateResponse:
    """
    Dynamically switches the server-wide live map simulation state:
    - 'normal': All zones green, incident null.
    - 'bypass': Zone 04 red, active incident triggered with target J_100 coordinates.
    """
    global _CURRENT_SIMULATION_STATE

    target = "normal"
    if state is not None:
        target = state
    elif payload is not None and payload.state:
        target = payload.state

    _CURRENT_SIMULATION_STATE = target.lower().strip()
    return build_live_map_state(_CURRENT_SIMULATION_STATE)


@router.post(
    "/telemetry",
    response_model=LiveMapStateResponse,
    summary="Ingest Real-Time Sensor Telemetry and Update Operational Map State",
)
def ingest_telemetry(payload: TelemetryInput) -> LiveMapStateResponse:
    """
    Ingests sensor telemetry (observed pressure, expected baseline, or Delta P).
    - If observed pressure is normal (>= 20.0m or Delta P > -2.0m), map stays clean/green (normal).
    - If observed pressure drops (<= 18.0m or Delta P <= -2.0m, e.g. 15.0m vs 21.0m baseline),
      triggers FRAUD_ALERT and pinpoints suspect junction J_100.
    """
    global _CURRENT_SIMULATION_STATE

    if payload.delta_p is not None:
        drop = abs(payload.delta_p)
    else:
        drop = abs(payload.expected_pressure - payload.observed_pressure)

    if drop >= 2.0 or payload.observed_pressure <= 18.0:
        _CURRENT_SIMULATION_STATE = "bypass"
    else:
        _CURRENT_SIMULATION_STATE = "normal"

    return build_live_map_state(_CURRENT_SIMULATION_STATE)

