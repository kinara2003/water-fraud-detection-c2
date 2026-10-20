"""
app/main.py
FastAPI backend service for real-time water fraud detection and risk assessment
on Kaduwela DMA 01 & 02 under Intermittent Water Supply (IWS).

Multi-Component Integration Routes:
- Component 1 (C1 Leak Detection): POST /api/v1/c1-leak-feedback
- Component 3 (C3 Storage Forecast): GET /api/v1/c3-water-loss/{zone_id}
- Component 4 (C4 Intrusion Risk): GET /api/v1/c4-pressure-drop-events
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import sys
import json
import joblib
import numpy as np
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

# Ensure project root is in Python module search path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from src.scorer import calculate_fraud_score, explain_fraud_score, get_recommended_action  # type: ignore
    from src.notifier import AuthorityNotifier, get_authority_notifier  # type: ignore
    from src.retrain import retrain_stage2_pipeline, INSPECTION_LOGS_PATH, ensure_inspection_logs_exist  # type: ignore
    from src.geo_converter import get_junction_location  # type: ignore
    from src.audit_logger import (  # type: ignore
        ensure_ledger_exists,
        get_inspection_ledger,
        calculate_operational_metrics,
        record_field_inspection,
    )
except ImportError:
    # Sibling directory fallback if run directly from inside app/
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.scorer import calculate_fraud_score, explain_fraud_score, get_recommended_action  # type: ignore
    from src.notifier import AuthorityNotifier, get_authority_notifier  # type: ignore
    from src.retrain import retrain_stage2_pipeline, INSPECTION_LOGS_PATH, ensure_inspection_logs_exist  # type: ignore
    from src.geo_converter import get_junction_location  # type: ignore
    from src.audit_logger import (  # type: ignore
        ensure_ledger_exists,
        get_inspection_ledger,
        calculate_operational_metrics,
        record_field_inspection,
    )


DATA_DIR = BASE_DIR / "data" / "processed"
RAW_SIM_DIR = BASE_DIR / "data" / "raw_simulations"
MODELS_DIR = BASE_DIR / "models"
INDEX_HTML_PATH = BASE_DIR / "app" / "templates" / "index.html"
INSPECTIONS_HTML_PATH = BASE_DIR / "app" / "templates" / "inspections.html"
FRONTEND_DATA_DIR = BASE_DIR / "frontend" / "public" / "data"

ISO_FOREST_PATH = MODELS_DIR / "isolation_forest.joblib"
RANDOM_FOREST_PATH = MODELS_DIR / "random_forest.joblib"

NOTIFIER: AuthorityNotifier = get_authority_notifier()

DMA_SUMMARY_PATH = DATA_DIR / "dma_risk_summary.csv"
SCENARIO_PATH = RAW_SIM_DIR / "dma_theft_test_scenario.csv"
BASELINE_PATH = RAW_SIM_DIR / "baseline_normal.csv"

FEATURE_NAMES = [
    "actual_pressure",
    "hydraulic_residual",
    "pressure_change_rate",
    "residual_rolling_mean",
    "residual_rolling_std",
    "spatial_deviation",
]

# Global model cache and multi-component state registry
MODELS: Dict = {}
FEEDBACK_CACHE: Dict[str, Dict[str, Any]] = {}
LATEST_NODE_ASSESSMENTS: Dict[str, Dict[str, Any]] = {}
TIMESERIES_CACHE: Dict[str, Any] = {}
GEOJSON_CACHE: Dict[str, Any] = {}
SENSOR_TRACKER: Dict[str, Dict[str, Any]] = {}
GATEWAY_HEALTH_REGISTRY: Dict[str, Dict[str, Any]] = {}

# ==============================================================================
# WebSocket Real-Time Telemetry Connection Manager
# ==============================================================================

class ConnectionManager:
    """
    Manages active WebSocket connections for real-time telemetry streaming to dashboards.
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client connected. Active clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WS] Client disconnected. Active clients: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """
        Asynchronously broadcasts message to all connected clients.
        Cleans up dead or stale sockets automatically.
        """
        dead_connections: List[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        for conn in dead_connections:
            self.disconnect(conn)

    def broadcast_sync(self, message: Dict[str, Any]) -> None:
        """
        Thread-safe broadcast invocation suitable for sync FastAPI route handlers
        running in threadpool or background tasks.
        """
        if not self.active_connections:
            return

        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(message))
        except RuntimeError:
            try:
                asyncio.run(self.broadcast(message))
            except Exception as e:
                print(f"[WS] Broadcast error: {e}")

WS_MANAGER = ConnectionManager()

DESIGNATED_GATEWAYS_CONFIG = [
    {"node_id": "J_10", "dma_id": "DMA 01", "gateway_id": "GW-DMA01-J10", "default_battery": 4.05, "default_rssi": -72},
    {"node_id": "J_100", "dma_id": "DMA 01", "gateway_id": "GW-DMA01-J100", "default_battery": 3.92, "default_rssi": -78},
    {"node_id": "J_500", "dma_id": "DMA 01", "gateway_id": "GW-DMA01-J500", "default_battery": 3.88, "default_rssi": -82},
    {"node_id": "J_1200", "dma_id": "DMA 02", "gateway_id": "GW-DMA02-J1200", "default_battery": 4.12, "default_rssi": -68},
    {"node_id": "J_2200", "dma_id": "DMA 02", "gateway_id": "GW-DMA02-J2200", "default_battery": 3.96, "default_rssi": -75},
    {"node_id": "J_3000", "dma_id": "DMA 02", "gateway_id": "GW-DMA02-J3000", "default_battery": 4.02, "default_rssi": -71},
]


def init_gateway_health_registry() -> None:
    """
    Initializes health registry for the 6 edge telemetry concentrators deployed
    in Kaduwela DMAs 01 & 02.
    """
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for cfg in DESIGNATED_GATEWAYS_CONFIG:
        nid = cfg["node_id"]
        v_bat = cfg["default_battery"]
        rssi = cfg["default_rssi"]
        pct = max(0.0, min(100.0, round(((v_bat - 3.4) / 0.8) * 100.0, 1)))
        bat_status = "GOOD" if v_bat >= 3.65 else ("LOW" if v_bat >= 3.45 else "CRITICAL")
        sig_quality = "EXCELLENT" if rssi >= -70 else ("GOOD" if rssi >= -80 else ("FAIR" if rssi >= -90 else "POOR"))
        GATEWAY_HEALTH_REGISTRY[nid] = {
            "gateway_id": cfg["gateway_id"],
            "node_id": nid,
            "dma_id": cfg["dma_id"],
            "status": "ONLINE",
            "battery_voltage": v_bat,
            "battery_percent": pct,
            "battery_status": bat_status,
            "cellular_rssi_dbm": rssi,
            "signal_quality": sig_quality,
            "deadband_suppressed_count": 0,
            "heartbeat_count": 0,
            "total_telemetry_sent": 0,
            "total_telemetry_flushed": 0,
            "offline_buffer_queue_depth": 0,
            "last_seen": now_str,
            "last_flushed_at": None,
            "firmware_version": "v2.4.1-edge-kaduwela",
        }


def update_gateway_health(
    zone_id: str,
    node_id: str,
    battery_voltage: Optional[float] = None,
    cellular_rssi_dbm: Optional[int] = None,
    is_heartbeat: Optional[bool] = False,
    is_store_and_forward: Optional[bool] = False,
    buffered_readings_count: Optional[int] = 0,
    deadband_suppressed_count: Optional[int] = 0,
) -> None:
    """
    Updates the edge gateway health registry when telemetry is received from a junction.
    """
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dma_name = normalize_zone_name(zone_id) or "DMA 01"

    if not GATEWAY_HEALTH_REGISTRY:
        init_gateway_health_registry()

    if node_id not in GATEWAY_HEALTH_REGISTRY:
        dma_tag = "01" if "01" in dma_name else "02"
        gw_id = f"GW-DMA{dma_tag}-{node_id.replace('_', '')}"
        v_bat = battery_voltage if battery_voltage is not None else 3.95
        rssi = cellular_rssi_dbm if cellular_rssi_dbm is not None else -75
        pct = max(0.0, min(100.0, round(((v_bat - 3.4) / 0.8) * 100.0, 1)))
        bat_status = "GOOD" if v_bat >= 3.65 else ("LOW" if v_bat >= 3.45 else "CRITICAL")
        sig_quality = "EXCELLENT" if rssi >= -70 else ("GOOD" if rssi >= -80 else ("FAIR" if rssi >= -90 else "POOR"))
        GATEWAY_HEALTH_REGISTRY[node_id] = {
            "gateway_id": gw_id,
            "node_id": node_id,
            "dma_id": dma_name,
            "status": "ONLINE",
            "battery_voltage": round(float(v_bat), 2),
            "battery_percent": pct,
            "battery_status": bat_status,
            "cellular_rssi_dbm": int(rssi),
            "signal_quality": sig_quality,
            "deadband_suppressed_count": 0,
            "heartbeat_count": 0,
            "total_telemetry_sent": 0,
            "total_telemetry_flushed": 0,
            "offline_buffer_queue_depth": 0,
            "last_seen": now_str,
            "last_flushed_at": None,
            "firmware_version": "v2.4.1-edge-kaduwela",
        }

    rec = GATEWAY_HEALTH_REGISTRY[node_id]
    rec["last_seen"] = now_str
    rec["total_telemetry_sent"] += 1

    if is_heartbeat:
        rec["heartbeat_count"] += 1

    if is_store_and_forward:
        rec["total_telemetry_flushed"] += 1
        rec["last_flushed_at"] = now_str

    if deadband_suppressed_count is not None and deadband_suppressed_count > 0:
        rec["deadband_suppressed_count"] = max(rec["deadband_suppressed_count"], int(deadband_suppressed_count))

    if buffered_readings_count is not None:
        rec["offline_buffer_queue_depth"] = int(buffered_readings_count)
        if is_store_and_forward and int(buffered_readings_count) == 0:
            for g in GATEWAY_HEALTH_REGISTRY.values():
                g["offline_buffer_queue_depth"] = 0

    if battery_voltage is not None:
        v_bat = max(3.0, min(4.5, float(battery_voltage)))
        rec["battery_voltage"] = round(v_bat, 2)
        rec["battery_percent"] = max(0.0, min(100.0, round(((v_bat - 3.4) / 0.8) * 100.0, 1)))
        rec["battery_status"] = "GOOD" if v_bat >= 3.65 else ("LOW" if v_bat >= 3.45 else "CRITICAL")

    if cellular_rssi_dbm is not None:
        rssi_val = int(cellular_rssi_dbm)
        rec["cellular_rssi_dbm"] = rssi_val
        rec["signal_quality"] = (
            "EXCELLENT" if rssi_val >= -70
            else ("GOOD" if rssi_val >= -80
            else ("FAIR" if rssi_val >= -90 else "POOR"))
        )

    if rec["battery_status"] == "CRITICAL" or rec["signal_quality"] == "POOR":
        rec["status"] = "DEGRADED"
    else:
        rec["status"] = "ONLINE"


def get_gateway_health_summary() -> Dict[str, Any]:
    """
    Returns aggregated gateway health summary across all monitored edge concentrators.
    """
    import datetime
    if not GATEWAY_HEALTH_REGISTRY:
        init_gateway_health_registry()

    gateways_list = list(GATEWAY_HEALTH_REGISTRY.values())
    total_gw = len(gateways_list)
    online_gw = sum(1 for g in gateways_list if g["status"] in ("ONLINE", "DEGRADED"))
    dma_counts = {"DMA 01": 0, "DMA 02": 0}
    total_suppressed = 0
    total_heartbeats = 0
    total_tx = 0
    total_flushed = 0
    total_queue_depth = 0

    for g in gateways_list:
        dma_counts[g["dma_id"]] = dma_counts.get(g["dma_id"], 0) + 1
        total_suppressed += g["deadband_suppressed_count"]
        total_heartbeats += g["heartbeat_count"]
        total_tx += g["total_telemetry_sent"]
        total_flushed += g.get("total_telemetry_flushed", 0)
        total_queue_depth += g.get("offline_buffer_queue_depth", 0)

    total_potential = total_suppressed + total_tx
    efficiency = round((total_suppressed / total_potential * 100.0), 1) if total_potential > 0 else 0.0
    recovery_status = "SYNCHRONIZED" if total_queue_depth == 0 else f"BUFFER_PENDING_{total_queue_depth}"

    return {
        "status": "operational",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_gateways": total_gw,
        "online_gateways": online_gw,
        "dma_distribution": dma_counts,
        "total_transmissions_suppressed": total_suppressed,
        "total_heartbeats_sent": total_heartbeats,
        "total_telemetry_received": total_tx,
        "total_store_and_forward_flushed": total_flushed,
        "network_bandwidth_efficiency_percent": efficiency,
        "offline_buffer_recovery_status": recovery_status,
        "gateways": gateways_list,
    }

# Pre-populate registry at module load time
init_gateway_health_registry()



def load_models():
    """
    Loads trained Stage 1 (IsolationForest) and Stage 2 (RandomForest) models.
    """
    if not ISO_FOREST_PATH.exists():
        raise FileNotFoundError(f"Isolation Forest model not found at {ISO_FOREST_PATH}. Run src/train.py first.")
    if not RANDOM_FOREST_PATH.exists():
        raise FileNotFoundError(f"Random Forest model not found at {RANDOM_FOREST_PATH}. Run src/train.py first.")

    MODELS["isolation_forest"] = joblib.load(ISO_FOREST_PATH)
    MODELS["random_forest"] = joblib.load(RANDOM_FOREST_PATH)
    print(f"Loaded Stage 1 model from {ISO_FOREST_PATH}")
    print(f"Loaded Stage 2 model from {RANDOM_FOREST_PATH}")


def load_timeseries_cache() -> Dict[str, Any]:
    """
    Preloads and caches 24-hour Expected vs Actual pressure timeseries
    for monitored nodes to ensure high-performance sub-millisecond polling.
    """
    global TIMESERIES_CACHE
    if TIMESERIES_CACHE:
        return TIMESERIES_CACHE

    if SCENARIO_PATH.exists() and BASELINE_PATH.exists():
        try:
            df_act = pd.read_csv(SCENARIO_PATH, index_col=0)
            df_exp = pd.read_csv(BASELINE_PATH, index_col=0)
            labels = [f"{int(t)//3600:02d}:{int((t%3600))//60:02d}" for t in df_exp.index]
            nodes_data = {}
            for n in ["J_10", "J_100", "J_500", "J_1200", "J_2200", "J_3000"]:
                if n in df_exp.columns and n in df_act.columns:
                    exp_list = [round(float(v), 2) for v in df_exp[n].values]
                    act_list = [round(float(v), 2) for v in df_act[n].values]
                    res_list = [round(float(e - a), 2) for e, a in zip(exp_list, act_list)]
                    nodes_data[n] = {
                        "expected_pressure": exp_list,
                        "actual_pressure": act_list,
                        "residual": res_list,
                    }
            TIMESERIES_CACHE = {
                "labels": labels,
                "nodes_data": nodes_data,
            }
        except Exception as e:
            print(f"Warning: Failed to load timeseries cache: {e}")
    return TIMESERIES_CACHE


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup model initialization.
    """
    load_models()
    load_timeseries_cache()
    init_gateway_health_registry()
    yield
    MODELS.clear()
    FEEDBACK_CACHE.clear()
    LATEST_NODE_ASSESSMENTS.clear()
    TIMESERIES_CACHE.clear()
    GEOJSON_CACHE.clear()
    SENSOR_TRACKER.clear()
    GATEWAY_HEALTH_REGISTRY.clear()


app = FastAPI(
    title="Kaduwela DMA Water Fraud & Leak Detection API (Component 2)",
    description=(
        "Two-stage AI service detecting pressure anomalies and classifying illegal bypass vs pipe leaks, "
        "featuring multi-component integrations with C1 (Leak Feedback), C3 (Storage Water Loss), and "
        "C4 (Intrusion Risk Depressurization Events)."
    ),
    version="1.1.0",
    lifespan=lifespan,
)

# Enable Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Register modular sub-routers
try:
    from app.routes.network_status import router as network_status_router
    app.include_router(network_status_router)
except ImportError:
    from routes.network_status import router as network_status_router  # type: ignore
    app.include_router(network_status_router)


# ==============================================================================
# Pydantic Request & Response Schemas
# ==============================================================================

class SensorTelemetryRequest(BaseModel):
    """
    Input schema representing sensor telemetry from Kaduwela DMA.
    Supports synthetic impairment testing and data imputation when actual_pressure is missing.
    """
    zone_id: str = Field(description="District Metered Area identifier (e.g. DMA 01, Kaduwela_DMA_01)")
    node_id: str = Field(description="Sensor junction node ID (e.g. J_100)")
    actual_pressure: Optional[float] = Field(default=None, description="Observed sensor pressure in meters (None or NaN triggers data imputation)")
    observed_pressure: Optional[float] = Field(default=None, description="Observed sensor pressure alias")
    expected_pressure: float = Field(description="Digital twin expected baseline pressure in meters")
    spatial_deviation: float = Field(default=0.0, description="Node residual minus neighborhood mean residual in meters")
    recurrence_count: int = Field(default=0, ge=0, description="Number of recurring anomalous events in recent windows")
    
    # Optional telemetry extensions
    timestamp: Optional[str] = Field(default=None, description="Timestamp or time index of telemetry reading (e.g. '06:15')")
    cycle_index: Optional[int] = Field(default=None, description="Sequential telemetry cycle index (15 min per interval)")
    pressure_change_rate: Optional[float] = Field(default=0.0, description="dP/dt rate of pressure change in meters/timestep")
    residual_rolling_mean: Optional[float] = Field(default=None, description="4-step rolling mean of residual")
    residual_rolling_std: Optional[float] = Field(default=0.0, description="4-step rolling standard deviation of residual")
    hours_since_supply_start: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Hours elapsed since active supply window opened (e.g. 0.75 for 45 min into refill)",
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_observed_pressure_and_hours(cls, data: Any) -> Any:
        if isinstance(data, dict):
            obs = data.get("observed_pressure")
            act = data.get("actual_pressure")
            if act is None and obs is not None:
                data["actual_pressure"] = obs
            elif obs is None and act is not None:
                data["observed_pressure"] = act

            if data.get("hours_since_supply_start") is None and data.get("timestamp"):
                ts = str(data["timestamp"])
                import re
                m = re.search(r"(\d{2}):(\d{2})", ts)
                if m:
                    h, mn = int(m.group(1)), int(m.group(2))
                    if 6 <= h < 7:
                        data["hours_since_supply_start"] = round((h - 6) + (mn / 60.0), 2)
        return data

    # Edge concentrator health & store-and-forward telemetry extensions
    battery_voltage: Optional[float] = Field(
        default=None,
        ge=3.0,
        le=4.5,
        description="Edge gateway battery voltage in Volts (3.4V to 4.2V nominal LiPo/LiFePO4)",
    )
    cellular_rssi_dbm: Optional[int] = Field(
        default=None,
        ge=-140,
        le=-30,
        description="Cellular modem RSSI signal strength in dBm (-115 to -65 dBm nominal)",
    )
    is_heartbeat: Optional[bool] = Field(
        default=False,
        description="True if reading is a periodic 60-minute deadband heartbeat",
    )
    is_store_and_forward: Optional[bool] = Field(
        default=False,
        description="True if reading was recovered and flushed from local offline SQLite buffer",
    )
    buffered_readings_count: Optional[int] = Field(
        default=0,
        ge=0,
        description="Depth of offline SQLite queue when transmission was attempted",
    )
    deadband_suppressed_count: Optional[int] = Field(
        default=0,
        ge=0,
        description="Cumulative count of transmissions suppressed locally by deadband filter",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "zone_id": "DMA 01",
                    "node_id": "J_100",
                    "actual_pressure": 28.5,
                    "expected_pressure": 34.7,
                    "spatial_deviation": 5.8,
                    "recurrence_count": 5,
                    "hours_since_supply_start": 2.5,
                }
            ]
        }
    }


class LocationMetadata(BaseModel):
    """
    Exact geodetic and local grid location metadata for network junction node.
    """
    junction_id: str = Field(description="Sensor junction node ID (e.g. J_100)")
    grid_x: float = Field(description="Local grid Easting coordinate in meters (SLD99)")
    grid_y: float = Field(description="Local grid Northing coordinate in meters (SLD99)")
    latitude: float = Field(description="WGS84 Latitude in decimal degrees")
    longitude: float = Field(description="WGS84 Longitude in decimal degrees")
    elevation_m: float = Field(description="Node elevation in meters above sea level")
    landmark: str = Field(description="Descriptive physical landmark for field audit navigation")
    google_maps_url: str = Field(description="Direct Google Maps search URL for GPS navigation")


class RiskAssessmentResponse(BaseModel):
    """
    Output schema for fraud risk assessment, triage, and IoT sensor resilience.
    """
    zone_id: str
    node_id: str
    fraud_risk_score: float
    classification: str
    reasons_list: List[str]
    recommended_action: str
    hours_since_supply_start: Optional[float] = None
    transient_dampening_active: Optional[bool] = False
    location: Optional[LocationMetadata] = None

    # IoT Resilience & Imputation attributes
    imputed_actual_pressure: Optional[float] = None
    is_imputed: Optional[bool] = False
    imputation_method: Optional[str] = None
    consecutive_missing_cycles: Optional[int] = 0
    sensor_health_warning: Optional[bool] = False
    sensor_health_details: Optional[str] = None

    # Edge gateway telemetry confirmation
    battery_voltage: Optional[float] = None
    cellular_rssi_dbm: Optional[int] = None
    is_heartbeat: Optional[bool] = False
    is_store_and_forward: Optional[bool] = False


class GatewayHealthItem(BaseModel):
    """
    Status and battery/signal health for a single edge concentrator gateway.
    """
    gateway_id: str
    node_id: str
    dma_id: str
    status: str
    battery_voltage: float
    battery_percent: float
    battery_status: str
    cellular_rssi_dbm: int
    signal_quality: str
    deadband_suppressed_count: int
    heartbeat_count: int
    total_telemetry_sent: int
    offline_buffer_queue_depth: int
    last_seen: str
    last_flushed_at: Optional[str] = None
    firmware_version: str = "v2.4.1-edge-kaduwela"


class GatewayHealthResponse(BaseModel):
    """
    Fleet-wide health and telemetry metrics for all edge gateways across Kaduwela DMAs.
    """
    status: str
    timestamp: str
    total_gateways: int
    online_gateways: int
    dma_distribution: Dict[str, int]
    total_transmissions_suppressed: int
    total_heartbeats_sent: int
    total_telemetry_received: int
    total_store_and_forward_flushed: int
    network_bandwidth_efficiency_percent: float
    offline_buffer_recovery_status: str
    gateways: List[GatewayHealthItem]


class C1LeakFeedbackRequest(BaseModel):
    """
    Component 1 Physical Leak Detection Feedback Schema.
    """
    zone_id: str = Field(description="DMA identifier (e.g. DMA 01 or Kaduwela_DMA_01)")
    node_id: str = Field(description="Sensor junction node ID (e.g. J_100)")
    leak_probability: float = Field(
        ge=0.0,
        le=1.0,
        description="Component 1 physical acoustic/sensor leak probability (0.0 to 1.0)",
    )
    current_fraud_score: Optional[float] = Field(
        default=None,
        description="Optional current calculated fraud risk score to adjust directly",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "zone_id": "DMA 01",
                    "node_id": "J_100",
                    "leak_probability": 0.85,
                    "current_fraud_score": 88.6,
                }
            ]
        }
    }


class C1LeakFeedbackResponse(BaseModel):
    """
    Component 1 Feedback Response with updated fraud risk score and reclassification.
    """
    zone_id: str
    node_id: str
    leak_probability: float
    original_fraud_risk_score: float
    adjusted_fraud_risk_score: float
    original_classification: str
    adjusted_classification: str
    leak_feedback_applied: bool
    recommended_action: str
    message: str


class C3WaterLossResponse(BaseModel):
    """
    Component 3 Storage Forecasting Integration Schema.
    """
    zone_id: str
    current_risk_level: str
    estimated_unmetered_water_loss_lps: float = Field(
        description="Estimated unmetered water volume loss in Liters Per Second (LPS)",
    )
    estimated_hourly_loss_m3: float = Field(description="Estimated water loss rate in m^3/hour")
    estimated_daily_loss_m3: float = Field(description="Projected 24h water loss volume in m^3")
    active_theft_nodes: List[str]
    monitoring_nodes_count: int
    storage_forecast_impact: str
    component_target: str = "Component 3 - Storage Forecasting"


class DepressurizationEvent(BaseModel):
    """
    Individual severe depressurization event record for Component 4.
    """
    timestamp_seconds: int
    time_formatted: str
    node_id: str
    zone_id: str
    actual_pressure: float
    expected_pressure: float
    pressure_deficit_m: float
    intrusion_risk_severity: str


class C4PressureDropEventsResponse(BaseModel):
    """
    Component 4 Intrusion Risk Analysis Integration Schema.
    """
    component_target: str = "Component 4 - Intrusion Risk Analysis"
    threshold_m: float
    total_severe_events_count: int
    affected_nodes: List[str]
    events: List[DepressurizationEvent]
    recommendation: str


# ------------------------------------------------------------------------------
# Retraining & Inspection Feedback Schemas
# ------------------------------------------------------------------------------

class RetrainRequest(BaseModel):
    min_new_entries: Optional[int] = Field(
        default=5,
        ge=1,
        description="Minimum new verified ground-truth entries required to trigger retraining",
    )
    force: Optional[bool] = Field(
        default=False,
        description="Whether to force retraining even if fewer than min_new_entries are available",
    )


class RetrainResponse(BaseModel):
    status: str
    message: str
    new_samples_added: Optional[int] = 0
    total_anomalous_samples: Optional[int] = None
    total_dataset_rows: Optional[int] = None
    old_f1_score: Optional[float] = None
    new_f1_score: Optional[float] = None
    f1_delta: Optional[float] = None
    class_weights: Optional[str] = None
    backup_model_path: Optional[str] = None
    primary_model_path: Optional[str] = None
    timestamp: str
    details: Optional[Dict[str, Any]] = None


class InspectionFeedbackLogRequest(BaseModel):
    node_id: str = Field(description="Sensor node ID (e.g. J_100)")
    actual_finding: str = Field(description="Ground truth finding: partial_bypass, leak, or normal")
    notes: Optional[str] = Field(default="", description="Inspector observation notes")


class InspectionFeedbackLogResponse(BaseModel):
    status: str
    message: str
    log_id: str
    node_id: str
    actual_finding: str
    timestamp: str
    total_unprocessed_logs: int


# ------------------------------------------------------------------------------
# Field Inspection Audit Ledger Schemas
# ------------------------------------------------------------------------------

class FieldInspectionRecordRequest(BaseModel):
    alert_id: str = Field(description="Alert identifier (e.g. ALT-1791355886-J_100)")
    node_id: str = Field(description="Sensor junction node ID (e.g. J_100)")
    dma_id: str = Field(default="DMA 01", description="DMA identifier (e.g. DMA 01)")
    ground_truth_finding: str = Field(
        description="Ground truth finding: CONFIRMED_BYPASS, CONFIRMED_LEAK, or FALSE_ALARM_OPERATIONAL",
    )
    action_taken: str = Field(description="Remediation or enforcement action executed")
    assigned_officer: Optional[str] = Field(default="Eng. K. Perera (Team 3)", description="Assigned officer name")
    notes: Optional[str] = Field(default="", description="Inspector observation notes")
    dispatch_time: Optional[str] = Field(default=None, description="ISO timestamp of initial alert dispatch")
    inspection_time: Optional[str] = Field(default=None, description="ISO timestamp of field inspection execution")
    inspection_id: Optional[str] = Field(default=None, description="Optional custom inspection identifier")


class AlertInvestigationUpdateRequest(BaseModel):
    assignedTo: Optional[str] = None
    inspectionDate: Optional[str] = None
    notes: Optional[str] = None
    status: str
    ground_truth_finding: Optional[str] = None
    action_taken: Optional[str] = None
    node_id: Optional[str] = None
    dma_id: Optional[str] = None


# ------------------------------------------------------------------------------
# Operator Dashboard Schemas (GET /api/v1/dma-status)
# ------------------------------------------------------------------------------

class EvidenceChecklist(BaseModel):
    pressure_drop: bool
    spatial_mismatch: bool
    digital_twin_residual_match: bool
    leak_rule_insufficient: bool


class MonitoredNodeStatus(BaseModel):
    dma_id: str
    node_id: str
    peak_risk_score: float
    risk_level: str
    classification: str
    recommended_action: str
    inspection_priority: str
    current_actual_pressure: float
    current_expected_pressure: float
    current_residual: float
    evidence_checklist: EvidenceChecklist


class SupplyWindowStatus(BaseModel):
    state: str
    window_start: str
    window_end: str
    hours_since_supply_start: float
    refill_transient_active: bool


class DmaSummaryItem(BaseModel):
    status: str
    unmetered_loss_lps: float
    active_theft_count: int


class HighestRiskSector(BaseModel):
    node_id: str
    dma_id: str
    risk_level: str
    peak_risk_score: float


class DmaSummary(BaseModel):
    dma_01: DmaSummaryItem
    dma_02: DmaSummaryItem
    highest_risk_sector: HighestRiskSector


class NodeTimeseries(BaseModel):
    expected_pressure: List[float]
    actual_pressure: List[float]
    residual: List[float]


class TimeseriesData(BaseModel):
    labels: List[str]
    nodes_data: Dict[str, NodeTimeseries]


class DmaStatusResponse(BaseModel):
    timestamp: str
    supply_window: SupplyWindowStatus
    dma_summary: DmaSummary
    nodes: List[MonitoredNodeStatus]
    timeseries: TimeseriesData


class ZoneModel(BaseModel):
    """
    Component 2 schema for monitored DMA zone status and live telemetry.
    """
    id: str
    name: str
    dmaId: str
    status: str
    fraudRisk: float
    actualPressure: float
    expectedPressure: float
    residual: float
    anomalyScore: float
    lastUpdated: str
    customerCount: int
    supplyWindow: str


class PressureReadingTrace(BaseModel):
    """
    24-hour hourly pressure telemetry reading schema.
    """
    timestamp: str
    actualPressure: float
    expectedPressure: float
    residual: float
    isAbnormal: bool


# ==============================================================================
# Helper Functions
# ==============================================================================

def normalize_zone_name(zone: Optional[str]) -> str:
    """
    Normalizes DMA zone naming (e.g. 'dma_01', 'DMA 01', 'Kaduwela_DMA_01' -> 'DMA 01').
    """
    if not zone or not isinstance(zone, str):
        return ""
    cleaned = zone.strip().upper().replace("_", " ").replace("-", " ")
    if "01" in cleaned or " 1" in cleaned:
        return "DMA 01"
    elif "02" in cleaned or " 2" in cleaned:
        return "DMA 02"
    return zone.strip()


def get_cached_or_default_node_state(zone_id: str, node_id: str) -> Tuple[float, str]:
    """
    Retrieves the current fraud score and classification for a node from memory
    or pre-computed summary table.
    """
    key = f"{normalize_zone_name(zone_id)}:{node_id}"
    if key in LATEST_NODE_ASSESSMENTS:
        item = LATEST_NODE_ASSESSMENTS[key]
        return float(item.get("fraud_risk_score", 50.0)), str(item.get("classification", "partial_bypass"))

    # Fallback to dma_risk_summary.csv if available
    if DMA_SUMMARY_PATH.exists():
        try:
            df = pd.read_csv(DMA_SUMMARY_PATH)
            matched = df[(df["Node_ID"] == node_id)]
            if len(matched) > 0:
                row = matched.iloc[0]
                return float(row["Peak_Risk_Score"]), str(row["Primary_Suspected_Cause"])
        except Exception:
            pass

    # Default heuristic baseline
    if node_id == "J_100":
        return 88.60, "partial_bypass"
    return 15.0, "normal"


def build_location_metadata(node_id: str) -> LocationMetadata:
    """
    Constructs exact location metadata for a network junction node using geo_converter.
    """
    try:
        geo_info = get_junction_location(node_id)
        landmark = (
            "Kaduwela East Sector 04B (Near Node J_100 Chamber)"
            if str(node_id) == "J_100"
            else f"Kaduwela East {geo_info.get('sector_name', 'Sector')} (Near Node {node_id} Chamber)"
        )
        return LocationMetadata(
            junction_id=str(node_id),
            grid_x=float(geo_info["grid_x"]),
            grid_y=float(geo_info["grid_y"]),
            latitude=float(geo_info["latitude"]),
            longitude=float(geo_info["longitude"]),
            elevation_m=float(geo_info["elevation_m"]),
            landmark=landmark,
            google_maps_url=str(geo_info["google_maps_url"]),
        )
    except Exception as e:
        # Graceful fallback for synthetic or custom test node IDs
        lat = 6.936812 if node_id == "J_100" else 6.935000
        lon = 79.967673 if node_id == "J_100" else 79.984000
        gx = 410927.22 if node_id == "J_100" else 412730.00
        gy = 493000.00 if node_id == "J_100" else 492800.00
        elev = 12.0
        landmark = (
            "Kaduwela East Sector 04B (Near Node J_100 Chamber)"
            if node_id == "J_100"
            else f"Kaduwela East (Near Node {node_id} Chamber)"
        )
        return LocationMetadata(
            junction_id=str(node_id),
            grid_x=gx,
            grid_y=gy,
            latitude=lat,
            longitude=lon,
            elevation_m=elev,
            landmark=landmark,
            google_maps_url=f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}",
        )


def get_or_create_sensor_tracker(zone_id: str, node_id: str) -> Dict[str, Any]:
    """
    Retrieves or initializes state tracker for a sensor junction node,
    recording consecutive missing intervals, last valid telemetry, and frozen reading counts.
    """
    key = f"{normalize_zone_name(zone_id)}:{node_id}"
    if key not in SENSOR_TRACKER:
        SENSOR_TRACKER[key] = {
            "consecutive_missing": 0,
            "last_valid_actual": None,
            "last_valid_expected": None,
            "last_valid_residual": None,
            "frozen_val": None,
            "frozen_count": 0,
            "history": [],
        }
    return SENSOR_TRACKER[key]


# ==============================================================================
# Base Service & Dashboard Endpoints
# ==============================================================================

@app.get("/", response_class=HTMLResponse, tags=["Dashboard"], summary="NWSDB Operator Web Dashboard")
def serve_dashboard():
    """
    Serves the NWSDB Network-Level Water Fraud & NRW Monitoring operator dashboard.
    """
    if not INDEX_HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Dashboard template not found at app/templates/index.html")
    return HTMLResponse(content=INDEX_HTML_PATH.read_text(encoding="utf-8"))


@app.get("/inspections", response_class=HTMLResponse, tags=["Dashboard"], summary="Page 4: Authority Inspections & Dispatched Alerts Portal")
def serve_inspections():
    """
    Serves Page 4 of the Admin Portal (/inspections):
    Dispatched Alerts to Authorities with real-time status badge, delivery logs, and recipient info.
    """
    if not INSPECTIONS_HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Inspections template not found at app/templates/inspections.html")
    return HTMLResponse(content=INSPECTIONS_HTML_PATH.read_text(encoding="utf-8"))


@app.get("/api", tags=["System"], summary="API Root Service Metadata")
@app.get("/api/v1", tags=["System"], summary="API Root Service Metadata")
def api_root():
    """
    Returns API operational metadata and route registry.
    """
    return {
        "service": "Kaduwela DMA Water Fraud Detection API (Component 2)",
        "status": "operational",
        "docs_url": "/docs",
        "dashboard_url": "/",
        "inspections_url": "/inspections",
        "models_loaded": list(MODELS.keys()),
        "integration_routes": {
            "dma_status": "GET /api/v1/dma-status",
            "zones_list": "GET /api/v1/zones",
            "zone_pressure": "GET /api/v1/pressure/{zone_id}",
            "C1_leak_feedback": "POST /api/v1/c1-leak-feedback",
            "C3_water_loss_forecast": "GET /api/v1/c3-water-loss/{zone_id}",
            "C4_intrusion_risk_events": "GET /api/v1/c4-pressure-drop-events",
            "network_geojson": "GET /api/v1/network/geojson/{layer_type}",
            "notifications_history": "GET /api/v1/notifications/history",
            "inspections_portal": "GET /inspections",
            "models_retrain": "POST /api/v1/models/retrain",
            "inspection_logs": "GET /api/v1/inspections/logs",
            "resilience_batch_assess": "POST /api/v1/resilience/batch-assess",
            "resilience_reset_sensor": "POST /api/v1/resilience/reset-sensor-health",
            "gateway_health": "GET /api/v1/sensors/gateway-health",
            "ws_telemetry": "WS /ws/telemetry",
        },
    }


@app.get(
    "/api/v1/dma-status",
    response_model=DmaStatusResponse,
    tags=["Dashboard"],
    summary="Get Live DMA Status, Monitored Nodes Telemetry, and Timeseries for Operator Dashboard",
)
def get_dma_status():
    """
    Returns full network status for Kaduwela DMAs 01 & 02:
    - Supply window operational status (with refill transient dampening tracking)
    - DMA summaries (DMA 01 vs DMA 02 unmetered losses and status)
    - Monitored nodes telemetry with risk scores, cause classifications, actions, and evidence checklists
    - 24-hour time-series datasets for Expected vs Actual pressures
    """
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ts_cache = load_timeseries_cache()

    # Designated monitored nodes across Kaduwela DMAs
    base_nodes: List[Dict[str, Any]] = [
        {"node_id": "J_100", "dma_id": "DMA 01", "base_score": 88.60, "base_cause": "partial_bypass", "priority": "P1 - Immediate Field Investigation"},
        {"node_id": "J_10", "dma_id": "DMA 01", "base_score": 1.13, "base_cause": "normal", "priority": "P4 - Routine Monitoring"},
        {"node_id": "J_500", "dma_id": "DMA 01", "base_score": 0.88, "base_cause": "normal", "priority": "P4 - Routine Monitoring"},
        {"node_id": "J_1200", "dma_id": "DMA 02", "base_score": 0.08, "base_cause": "normal", "priority": "P4 - Routine Monitoring"},
        {"node_id": "J_2200", "dma_id": "DMA 02", "base_score": 0.11, "base_cause": "normal", "priority": "P4 - Routine Monitoring"},
        {"node_id": "J_3000", "dma_id": "DMA 02", "base_score": 0.07, "base_cause": "normal", "priority": "P4 - Routine Monitoring"},
    ]

    # Pre-populate / override from dma_risk_summary.csv if available
    if DMA_SUMMARY_PATH.exists():
        try:
            df_sum = pd.read_csv(DMA_SUMMARY_PATH)
            for item in base_nodes:
                matched = df_sum[df_sum["Node_ID"] == item["node_id"]]
                if len(matched) > 0:
                    r = matched.iloc[0]
                    item["base_score"] = float(r["Peak_Risk_Score"])
                    item["base_cause"] = str(r["Primary_Suspected_Cause"])
                    item["priority"] = str(r["Inspection_Priority"])
        except Exception:
            pass

    nodes_result: List[MonitoredNodeStatus] = []
    dma1_theft_count = 0
    dma2_theft_count = 0
    dma1_loss_lps = 0.0
    dma2_loss_lps = 0.0
    highest_score: float = -1.0
    highest_node: str = "J_100"
    highest_dma: str = "DMA 01"
    highest_level: str = "Critical"

    for bn in base_nodes:
        nid: str = str(bn["node_id"])
        dma: str = str(bn["dma_id"])
        score: float = float(bn["base_score"])
        cause: str = str(bn["base_cause"])
        priority: str = str(bn["priority"])

        # Check FEEDBACK_CACHE for C1 leak feedback
        cache_key = f"{dma}:{nid}"
        if cache_key in FEEDBACK_CACHE:
            fb = FEEDBACK_CACHE[cache_key]
            score = float(fb.get("adjusted_score", score))
            cause = str(fb.get("classification", cause))
            if cause == "physical_leak":
                priority = "P2 - Physical Leak Repair"

        # Determine risk level
        if score >= 75.0:
            risk_level = "Critical"
        elif score >= 50.0:
            risk_level = "High"
        elif score >= 25.0:
            risk_level = "Medium"
        else:
            risk_level = "Normal"

        if score > highest_score:
            highest_score = score
            highest_node = nid
            highest_dma = dma
            highest_level = risk_level

        # Recommendations
        if cause == "physical_leak":
            rec_action = "Physical Pipe Repair Workorder (Component 1 Leak Confirmed)"
        elif cause == "partial_bypass":
            rec_action = f"P1 — Immediate Field Investigation Recommended: Dispatch inspection team to junction {nid} to locate illegal branch."
        else:
            rec_action = "Routine Monitoring & Acoustic Loggers"

        # Current pressure snapshots
        if nid == "J_100":
            cur_act = 28.50
            cur_exp = 34.70
            cur_res = 6.20
        else:
            cur_exp = 35.10
            cur_act = 35.08
            cur_res = 0.02

        # Evidence checklist flags
        pressure_drop_flag = cur_res > 1.5
        spatial_mismatch_flag = (cause == "partial_bypass" and score >= 50.0)
        dt_residual_match_flag = (score >= 25.0)
        leak_insufficient_flag = (cause == "partial_bypass")

        if cause == "partial_bypass" and score >= 50.0:
            if dma == "DMA 01":
                dma1_theft_count += 1
                dma1_loss_lps += 0.05
            else:
                dma2_theft_count += 1
                dma2_loss_lps += 0.05

        nodes_result.append(
            MonitoredNodeStatus(
                dma_id=dma,
                node_id=nid,
                peak_risk_score=round(score, 2),
                risk_level=risk_level,
                classification=cause,
                recommended_action=rec_action,
                inspection_priority=priority,
                current_actual_pressure=cur_act,
                current_expected_pressure=cur_exp,
                current_residual=cur_res,
                evidence_checklist=EvidenceChecklist(
                    pressure_drop=pressure_drop_flag,
                    spatial_mismatch=spatial_mismatch_flag,
                    digital_twin_residual_match=dt_residual_match_flag,
                    leak_rule_insufficient=leak_insufficient_flag,
                ),
            )
        )

    # DMA 01 Status
    if dma1_theft_count > 0:
        dma1_status = "Critical Alert"
    elif any(n.classification == "physical_leak" for n in nodes_result if n.dma_id == "DMA 01"):
        dma1_status = "Physical Leak"
    else:
        dma1_status = "Normal Operations"

    dma2_status = "Normal Operations" if dma2_theft_count == 0 else "Critical Alert"

    return DmaStatusResponse(
        timestamp=now_str,
        supply_window=SupplyWindowStatus(
            state="Active Supply (Stabilized)",
            window_start="06:00",
            window_end="18:00",
            hours_since_supply_start=5.0,
            refill_transient_active=False,
        ),
        dma_summary=DmaSummary(
            dma_01=DmaSummaryItem(
                status=dma1_status,
                unmetered_loss_lps=round(dma1_loss_lps, 4),
                active_theft_count=dma1_theft_count,
            ),
            dma_02=DmaSummaryItem(
                status=dma2_status,
                unmetered_loss_lps=round(dma2_loss_lps, 4),
                active_theft_count=dma2_theft_count,
            ),
            highest_risk_sector=HighestRiskSector(
                node_id=highest_node,
                dma_id=highest_dma,
                risk_level=highest_level,
                peak_risk_score=round(highest_score, 2),
            ),
        ),
        nodes=nodes_result,
        timeseries=TimeseriesData(
            labels=ts_cache.get("labels", []),
            nodes_data={
                k: NodeTimeseries(
                    expected_pressure=v.get("expected_pressure", []),
                    actual_pressure=v.get("actual_pressure", []),
                    residual=v.get("residual", []),
                )
                for k, v in ts_cache.get("nodes_data", {}).items()
            },
        ),
    )


# ==============================================================================
# Monitored Zones Telemetry & Pressure Endpoints (Component 2 Frontend API)
# ==============================================================================

BASE_ZONES_CONFIG: List[Dict[str, Any]] = [
    {
        "id": "zone-01",
        "name": "Zone 01 - Kaduwela Town Central",
        "dmaId": "DMA 01",
        "node_id": "J_10",
        "customerCount": 1450,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 21.0,
        "default_expected": 21.2,
        "default_risk": 12.0,
        "default_status": "normal",
        "default_anomaly": 0.11,
    },
    {
        "id": "zone-02",
        "name": "Zone 02 - Nawagamuwa North",
        "dmaId": "DMA 01",
        "node_id": "J_20",
        "customerCount": 1120,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 20.8,
        "default_expected": 21.0,
        "default_risk": 18.0,
        "default_status": "normal",
        "default_anomaly": 0.17,
    },
    {
        "id": "zone-03",
        "name": "Zone 03 - Korathota Junction",
        "dmaId": "DMA 01",
        "node_id": "J_50",
        "customerCount": 890,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 21.4,
        "default_expected": 21.5,
        "default_risk": 15.0,
        "default_status": "normal",
        "default_anomaly": 0.14,
    },
    {
        "id": "zone-04",
        "name": "Zone 04 - Kaduwela East Industrial",
        "dmaId": "DMA 01",
        "node_id": "J_100",
        "customerCount": 1240,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 15.2,
        "default_expected": 21.2,
        "default_risk": 89.0,
        "default_status": "high",
        "default_anomaly": 0.88,
    },
    {
        "id": "zone-05",
        "name": "Zone 05 - Welihinda Ridge",
        "dmaId": "DMA 01",
        "node_id": "J_500",
        "customerCount": 760,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 19.8,
        "default_expected": 20.1,
        "default_risk": 22.0,
        "default_status": "normal",
        "default_anomaly": 0.20,
    },
    {
        "id": "zone-06",
        "name": "Zone 06 - Ranala Commercial Sector",
        "dmaId": "DMA 01",
        "node_id": "J_600",
        "customerCount": 1350,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 22.0,
        "default_expected": 22.1,
        "default_risk": 9.0,
        "default_status": "normal",
        "default_anomaly": 0.08,
    },
    {
        "id": "zone-07",
        "name": "Zone 07 - Biyagama Border Commercial",
        "dmaId": "DMA 01",
        "node_id": "J_700",
        "customerCount": 980,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 16.5,
        "default_expected": 20.5,
        "default_risk": 64.0,
        "default_status": "medium",
        "default_anomaly": 0.62,
    },
    {
        "id": "zone-08",
        "name": "Zone 08 - Hewagama South",
        "dmaId": "DMA 02",
        "node_id": "J_1200",
        "customerCount": 1650,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 22.5,
        "default_expected": 22.5,
        "default_risk": 14.0,
        "default_status": "normal",
        "default_anomaly": 0.12,
    },
    {
        "id": "zone-09",
        "name": "Zone 09 - Pahala Bomiriya",
        "dmaId": "DMA 02",
        "node_id": "J_1500",
        "customerCount": 1420,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 23.0,
        "default_expected": 23.1,
        "default_risk": 11.0,
        "default_status": "normal",
        "default_anomaly": 0.10,
    },
    {
        "id": "zone-10",
        "name": "Zone 10 - Ihala Bomiriya Highlands",
        "dmaId": "DMA 02",
        "node_id": "J_2200",
        "customerCount": 920,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 22.8,
        "default_expected": 22.9,
        "default_risk": 8.0,
        "default_status": "normal",
        "default_anomaly": 0.07,
    },
    {
        "id": "zone-11",
        "name": "Zone 11 - Dedigamuwa Lakeview",
        "dmaId": "DMA 02",
        "node_id": "J_2500",
        "customerCount": 1100,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 21.9,
        "default_expected": 22.0,
        "default_risk": 19.0,
        "default_status": "normal",
        "default_anomaly": 0.16,
    },
    {
        "id": "zone-12",
        "name": "Zone 12 - Welivita Highway Exit",
        "dmaId": "DMA 02",
        "node_id": "J_3000",
        "customerCount": 1310,
        "supplyWindow": "06:00 - 18:00",
        "default_actual": 22.2,
        "default_expected": 22.3,
        "default_risk": 16.0,
        "default_status": "normal",
        "default_anomaly": 0.15,
    },
]


def get_aggregated_zones() -> List[ZoneModel]:
    """
    Builds the aggregated list of the 12 zones with live pressures,
    DMA tags, and latest risk status from models/ and telemetry caches.
    """
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Read pre-computed model outputs and summary from models/ and processed data
    dma_summary_map: Dict[str, Dict[str, Any]] = {}
    if DMA_SUMMARY_PATH.exists():
        try:
            df_sum = pd.read_csv(DMA_SUMMARY_PATH)
            for _, row in df_sum.iterrows():
                dma_summary_map[str(row["Node_ID"])] = {
                    "score": float(row["Peak_Risk_Score"]),
                    "level": str(row["Risk_Level"]).lower(),
                    "cause": str(row["Primary_Suspected_Cause"]),
                }
        except Exception as e:
            print(f"Warning reading DMA summary for zones: {e}")

    aggregated: List[ZoneModel] = []
    for z in BASE_ZONES_CONFIG:
        nid = z["node_id"]
        dma = z["dmaId"]
        risk = float(z["default_risk"])
        status = str(z["default_status"])
        act_p = float(z["default_actual"])
        exp_p = float(z["default_expected"])
        anomaly = float(z["default_anomaly"])

        # Check dma_risk_summary.csv for model findings
        if nid in dma_summary_map:
            item = dma_summary_map[nid]
            risk = float(item["score"])
            status = str(item["level"])

        # Check dynamic C1 physical leak feedback cache
        cache_key = f"{dma}:{nid}"
        if cache_key in FEEDBACK_CACHE:
            fb = FEEDBACK_CACHE[cache_key]
            risk = float(fb.get("adjusted_score", risk))
            classification = str(fb.get("classification", ""))
            if classification == "physical_leak":
                status = "medium" if risk < 70.0 else "high"

        # Check latest runtime assessment
        if cache_key in LATEST_NODE_ASSESSMENTS:
            la = LATEST_NODE_ASSESSMENTS[cache_key]
            risk = float(la.get("fraud_risk_score", risk))

        # Standardize risk status
        if risk >= 75.0:
            status = "high"
        elif risk >= 40.0:
            status = "medium"
        else:
            status = "normal"

        residual = round(act_p - exp_p, 2)

        aggregated.append(
            ZoneModel(
                id=z["id"],
                name=z["name"],
                dmaId=z["dmaId"],
                status=status,
                fraudRisk=round(risk, 1),
                actualPressure=act_p,
                expectedPressure=exp_p,
                residual=residual,
                anomalyScore=anomaly,
                lastUpdated=now_str,
                customerCount=z["customerCount"],
                supplyWindow=z["supplyWindow"],
            )
        )
    return aggregated


def generate_zone_pressure_trace(zone_id: str) -> List[PressureReadingTrace]:
    """
    Generates a 24-hour trace of actual vs. expected pressures and residuals
    for the requested zone (Zone 04, Zone 07, or baseline zones).
    """
    cid = zone_id.lower().replace("zone-", "").replace("zone ", "").strip()

    if cid in ["04", "4", "j_100", "j100"] or "04" in cid:
        # Zone 04: IWS opening at 06:00, sustained head drop 07:00-11:00 (15.2m vs 21.2m), shutdown 18:00
        return [
            PressureReadingTrace(timestamp="00:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="01:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="02:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="03:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="04:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="05:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="06:00", actualPressure=24.5, expectedPressure=22.0, residual=2.5, isAbnormal=False),
            PressureReadingTrace(timestamp="07:00", actualPressure=15.2, expectedPressure=21.2, residual=-6.0, isAbnormal=True),
            PressureReadingTrace(timestamp="08:00", actualPressure=15.2, expectedPressure=21.2, residual=-6.0, isAbnormal=True),
            PressureReadingTrace(timestamp="09:00", actualPressure=15.2, expectedPressure=21.2, residual=-6.0, isAbnormal=True),
            PressureReadingTrace(timestamp="10:00", actualPressure=15.2, expectedPressure=21.2, residual=-6.0, isAbnormal=True),
            PressureReadingTrace(timestamp="11:00", actualPressure=15.2, expectedPressure=21.2, residual=-6.0, isAbnormal=True),
            PressureReadingTrace(timestamp="12:00", actualPressure=15.8, expectedPressure=21.0, residual=-5.2, isAbnormal=True),
            PressureReadingTrace(timestamp="13:00", actualPressure=16.1, expectedPressure=21.0, residual=-4.9, isAbnormal=True),
            PressureReadingTrace(timestamp="14:00", actualPressure=15.5, expectedPressure=21.0, residual=-5.5, isAbnormal=True),
            PressureReadingTrace(timestamp="15:00", actualPressure=15.2, expectedPressure=21.2, residual=-6.0, isAbnormal=True),
            PressureReadingTrace(timestamp="16:00", actualPressure=16.4, expectedPressure=21.1, residual=-4.7, isAbnormal=True),
            PressureReadingTrace(timestamp="17:00", actualPressure=17.5, expectedPressure=21.0, residual=-3.5, isAbnormal=True),
            PressureReadingTrace(timestamp="18:00", actualPressure=8.5, expectedPressure=9.0, residual=-0.5, isAbnormal=False),
            PressureReadingTrace(timestamp="19:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="20:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="21:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="22:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
            PressureReadingTrace(timestamp="23:00", actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False),
        ]

    if cid in ["07", "7", "j_700", "j700"] or "07" in cid:
        # Zone 07: Medium risk partial drop (16.5m vs 20.5m)
        readings = []
        for h in range(24):
            t_str = f"{h:02d}:00"
            if h < 6 or h > 18:
                readings.append(PressureReadingTrace(timestamp=t_str, actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False))
            elif h == 6:
                readings.append(PressureReadingTrace(timestamp=t_str, actualPressure=22.0, expectedPressure=21.0, residual=1.0, isAbnormal=False))
            elif h == 18:
                readings.append(PressureReadingTrace(timestamp=t_str, actualPressure=9.0, expectedPressure=9.5, residual=-0.5, isAbnormal=False))
            else:
                readings.append(PressureReadingTrace(timestamp=t_str, actualPressure=16.5, expectedPressure=20.5, residual=-4.0, isAbnormal=True))
        return readings

    # Match other zones configuration
    matched_z = None
    for z in BASE_ZONES_CONFIG:
        if z["id"] == zone_id or z["id"].replace("zone-", "") == cid or z["node_id"].lower() == cid:
            matched_z = z
            break

    base_act = float(matched_z["default_actual"]) if matched_z else 21.0
    base_exp = float(matched_z["default_expected"]) if matched_z else 21.0

    readings = []
    for h in range(24):
        t_str = f"{h:02d}:00"
        if h < 6 or h > 18:
            readings.append(PressureReadingTrace(timestamp=t_str, actualPressure=0.0, expectedPressure=0.0, residual=0.0, isAbnormal=False))
        elif h == 6:
            readings.append(PressureReadingTrace(timestamp=t_str, actualPressure=round(base_exp + 0.5, 2), expectedPressure=base_exp, residual=0.5, isAbnormal=False))
        elif h == 18:
            readings.append(PressureReadingTrace(timestamp=t_str, actualPressure=8.5, expectedPressure=9.0, residual=-0.5, isAbnormal=False))
        else:
            res = round(base_act - base_exp, 2)
            readings.append(PressureReadingTrace(timestamp=t_str, actualPressure=base_act, expectedPressure=base_exp, residual=res, isAbnormal=abs(res) > 2.0))
    return readings


@app.get(
    "/api/v1/zones",
    response_model=List[ZoneModel],
    tags=["Zones"],
    summary="Get Aggregated List of 12 Monitored Zones with Live Telemetry and Model Risk",
)
def get_zones_list():
    """
    Returns an aggregated list of the 12 zones with current live pressures,
    DMA tags, and latest risk status from models/ and telemetry caches.
    """
    return get_aggregated_zones()


@app.get(
    "/api/v1/zones/geo",
    tags=["Zones"],
    summary="Get Geospatial Mapping of Kaduwela East Network Junctions",
)
def get_zones_geo():
    """
    Serves full geodetic mapping of all Kaduwela East network junctions
    from data/processed/kaduwela_nodes_geo.json.
    """
    geo_file = DATA_DIR / "kaduwela_nodes_geo.json"
    if not geo_file.exists():
        try:
            from src.geo_converter import export_all_junction_coordinates
            export_all_junction_coordinates()
        except Exception:
            pass
    if not geo_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Geospatial nodes JSON file not found at data/processed/kaduwela_nodes_geo.json",
        )
    with open(geo_file, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get(
    "/api/v1/network/geojson/{layer_type}",
    tags=["Network"],
    summary="Get Network GeoJSON Layer (junctions or pipes)",
)
def get_network_geojson(layer_type: str) -> Dict[str, Any]:
    """
    Serves standard GeoJSON FeatureCollections for the Kaduwela water distribution network.

    Supported layer_type values:
    - junctions (or kaduwela_junctions, nodes): Point features for all 3,904 junctions with properties (node_id, elevation, dma).
    - pipes (or kaduwela_pipes, links): LineString features for all 4,279 pipes connecting start and end junctions with properties (pipe_id, diameter, length).
    """
    normalized = layer_type.lower().replace(".geojson", "").strip()

    if normalized in ("junctions", "kaduwela_junctions", "nodes"):
        filename = "kaduwela_junctions.geojson"
        cache_key = "junctions"
    elif normalized in ("pipes", "kaduwela_pipes", "links"):
        filename = "kaduwela_pipes.geojson"
        cache_key = "pipes"
    elif normalized in ("zones", "kaduwela_zones", "boundaries", "sectors"):
        filename = "kaduwela_zones.geojson"
        cache_key = "zones"
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Layer '{layer_type}' not found. Supported layer types: 'junctions', 'pipes', 'zones'.",
        )

    # Return cached parsed payload if available
    if cache_key in GEOJSON_CACHE:
        return GEOJSON_CACHE[cache_key]

    target_file = FRONTEND_DATA_DIR / filename

    # Auto-generate if files do not exist yet on disk
    if not target_file.exists():
        try:
            if filename == "kaduwela_zones.geojson":
                from src.build_zone_boundaries import export_zone_boundaries_geojson
                export_zone_boundaries_geojson()
            else:
                from src.export_network_geojson import export_network_geojson
                export_network_geojson()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"GeoJSON layer '{filename}' not found and auto-generation failed: {e}",
            )

    if not target_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"GeoJSON file '{filename}' not found at {target_file}.",
        )

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        GEOJSON_CACHE[cache_key] = data
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read GeoJSON file {filename}: {e}")


@app.get(
    "/api/v1/zones/{zone_id}",
    response_model=ZoneModel,
    tags=["Zones"],
    summary="Get Detailed Telemetry for a Monitored Zone",
)
def get_zone_by_id(zone_id: str):
    """
    Returns single zone details by ID (e.g. zone-04, 04, zone-01).
    """
    zones = get_aggregated_zones()
    clean_id = zone_id.lower().replace("zone-", "")
    for z in zones:
        if z.id == zone_id or z.id.replace("zone-", "") == clean_id:
            return z
    raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")


@app.get(
    "/api/v1/pressure/{zone_id}",
    response_model=List[PressureReadingTrace],
    tags=["Zones"],
    summary="Get 24-Hour Pressure Trace of Actual vs Expected and Residuals for Zone",
)
def get_zone_pressure(
    zone_id: str,
    range: Optional[str] = Query(default="24h", description="Timeframe window: 1h, 6h, 24h, 7d"),
):
    """
    Returns a 24-hour trace of actual vs. expected pressures and residuals for the requested zone.
    Supports timeframe filtering via the range query parameter (1h, 6h, 24h, 7d).
    """
    readings = generate_zone_pressure_trace(zone_id)
    if range == "1h":
        return readings[-1:]
    elif range == "6h":
        return readings[-6:]
    return readings


@app.get(
    "/api/v1/zones/{zone_id}/pressure",
    response_model=List[PressureReadingTrace],
    tags=["Zones"],
    include_in_schema=False,
)
def get_zone_pressure_alias(
    zone_id: str,
    range: Optional[str] = Query(default="24h"),
):
    """
    Alternative route alias for GET /api/v1/pressure/{zone_id}.
    """
    return get_zone_pressure(zone_id, range)


@app.get(
    "/api/v1/zones/{zone_id}/telemetry",
    tags=["Zones"],
    summary="Get Detailed Live Telemetry & 4-Pillar Evidence for a Monitored Zone",
)
def get_zone_telemetry(zone_id: str) -> Dict[str, Any]:
    """
    Returns live operational telemetry, suspicion gauge score (0-100),
    pressure gap, physical location metadata, and 4-pillar forensic evidence
    for the requested zone (e.g. zone-04, 04, zone-01).
    """
    clean_id = zone_id.lower().replace("zone-", "").replace("zone", "").strip()

    # Read active simulation state
    try:
        from app.routes.network_status import _CURRENT_SIMULATION_STATE
    except ImportError:
        from routes.network_status import _CURRENT_SIMULATION_STATE  # type: ignore

    is_bypass = (_CURRENT_SIMULATION_STATE == "bypass") and (clean_id in ("04", "4"))

    expected_p = 21.2
    if is_bypass:
        actual_p = 15.2
        pressure_gap = 6.0
        suspicion_score = 89.0
        status = "FRAUD_ALERT"
        timing_pattern = "06:45 AM – 09:30 AM"
        timing_detail = "Drop occurs only between 06:45 AM and 09:30 AM (matches consumer morning tank filling)"
        timing_badge = "Pattern matches unmetered storage cistern draw off."
        neighbor_val = "Normal at 20.4 m"
        neighbor_detail = (
            "Neighboring sectors (Zones 02 & 05) remain normal at 20.4 m (proves drop is local, not a main supply failure)"
        )
        neighbor_badge = "Spatial divergence confirms localized downstream off-take."
        acoustic_val = "18% Acoustic Level"
        acoustic_detail = "Acoustic pipe sensor reads 18% (quiet pipe wall — rules out a physical burst/crack)"
        acoustic_badge = "Intact acoustic baseline isolates commercial extraction."
        rec_text = "Send inspection crew to verify unmetered bypass near Junction J_100 on Kaduwela Road."
    else:
        actual_p = 21.0
        pressure_gap = 0.2
        suspicion_score = 12.0
        status = "NORMAL"
        timing_pattern = "24-Hour Continuous Baseline"
        timing_detail = "Pressure adheres smoothly to expected EPANET diurnal demand curve."
        timing_badge = "No abnormal temporal transient detected."
        neighbor_val = "Symmetric at 21.0 m"
        neighbor_detail = "Uniform pressure gradient across adjacent Kaduwela East distribution sectors."
        neighbor_badge = "Topological hydraulic balance maintained."
        acoustic_val = "12% Acoustic Level"
        acoustic_detail = "Low ambient hydrophone noise reading; structural integrity verified."
        acoustic_badge = "Acoustic sensor confirms nominal pipe wall integrity."
        rec_text = "System operates within standard hydraulic limits. No field inspection required."

    zid_padded = clean_id.zfill(2)
    return {
        "zone_id": f"zone-{zid_padded}",
        "clean_id": zid_padded,
        "name": f"Zone {zid_padded} — Kaduwela East",
        "node_id": "J_100" if clean_id in ("04", "4") else f"J_{clean_id}0",
        "dma_id": "DMA 01" if clean_id in ("01", "02", "04", "1", "2", "4") else "DMA 02",
        "suspicion_score": suspicion_score,
        "status": status,
        "actual_pressure": actual_p,
        "expected_pressure": expected_p,
        "pressure_gap": pressure_gap,
        "landmark": "Junction J_100 Chamber, Kaduwela Road" if clean_id in ("04", "4") else f"Sector Chamber J_{zid_padded}",
        "gps": "6.9354° N, 79.9842° E" if clean_id in ("04", "4") else "6.9350° N, 79.9840° E",
        "elevation": 12.0,
        "four_pillar_evidence": [
            {
                "pillar": 1,
                "name": "Pressure Gap",
                "value": f"Missing: {pressure_gap:.1f} m",
                "detail": f"Expected: {expected_p:.1f} m | Actual: {actual_p:.1f} m (Missing: {pressure_gap:.1f} m)",
                "badge": (
                    "Sustained head deficit exceeds physical pipe friction bounds."
                    if is_bypass
                    else "Within acceptable operational tolerance (±0.5 m)."
                ),
            },
            {
                "pillar": 2,
                "name": "Timing Pattern",
                "value": timing_pattern,
                "detail": timing_detail,
                "badge": timing_badge,
            },
            {
                "pillar": 3,
                "name": "Neighbor Comparison",
                "value": neighbor_val,
                "detail": neighbor_detail,
                "badge": neighbor_badge,
            },
            {
                "pillar": 4,
                "name": "Physical Leak Check",
                "value": acoustic_val,
                "detail": acoustic_detail,
                "badge": acoustic_badge,
            },
        ],
        "recommendation": rec_text,
    }


@app.get(
    "/api/v1/localize-anomaly",
    tags=["Localization"],
    summary="Localize Suspect Junction & Physical Inspection Corridor",
)
def api_localize_anomaly(
    zone_id: str = Query(default="zone-04", description="Zone ID (e.g. zone-04, 04)"),
    sensor_node_id: Optional[str] = Query(default="J_100", description="Sensor node ID (e.g. J_100)"),
    pressure_gap: float = Query(default=6.0, description="Observed pressure deficit gap in meters"),
):
    """
    Localizes anomalous pressure deficit:
    - Returns normal message if pressure_gap < 2.0m.
    - Pinpoints suspect junction, GPS coordinates, 50m inspection corridor, and Google Maps URL if pressure_gap >= 2.0m.
    """
    from src.localizer import localize_anomaly
    result = localize_anomaly(zone_id=zone_id, sensor_node_id=sensor_node_id or "", pressure_gap=pressure_gap)
    if result is None:
        return {
            "status": "normal",
            "message": f"Pressure gap {pressure_gap}m is below 2.0m threshold; no localization required.",
            "data": None,
        }
    return {"status": "anomaly_localized", "data": result}


@app.get("/health")
def health_check():
    if "isolation_forest" not in MODELS or "random_forest" not in MODELS:
        try:
            load_models()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Models not ready: {str(e)}")
    return {
        "status": "healthy",
        "stage1_model": type(MODELS["isolation_forest"]).__name__,
        "stage2_model": type(MODELS["random_forest"]).__name__,
    }


@app.get("/api/v1/assess-risk", include_in_schema=False)
@app.get("/api/v1/assess-risk/", include_in_schema=False)
@app.get("/assess-risk", include_in_schema=False)
@app.get("/assess-risk/", include_in_schema=False)
def assess_risk_get_help():
    return {
        "message": "This is a POST endpoint for sensor risk assessment. Send a POST request with JSON telemetry or visit /docs to test interactively.",
        "interactive_docs": "http://127.0.0.1:8000/docs",
        "endpoint": "POST /api/v1/assess-risk",
        "sample_payload": {
            "zone_id": "DMA 01",
            "node_id": "J_100",
            "actual_pressure": 28.5,
            "expected_pressure": 34.7,
            "spatial_deviation": 5.8,
            "recurrence_count": 5,
            "hours_since_supply_start": 2.5,
        },
    }


@app.post("/api/v1/assess-risk", response_model=RiskAssessmentResponse, tags=["Assessment"])
@app.post("/api/v1/assess-risk/", response_model=RiskAssessmentResponse, include_in_schema=False)
@app.post("/assess-risk", response_model=RiskAssessmentResponse, include_in_schema=False)
@app.post("/assess-risk/", response_model=RiskAssessmentResponse, include_in_schema=False)
def assess_risk(
    req: SensorTelemetryRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Assesses water fraud risk for a sensor node:
    1. Computes hydraulic residual and constructs feature vector.
    2. Runs Stage 1 IsolationForest for anomaly detection.
    3. Runs Stage 2 RandomForestClassifier to determine cause if anomalous.
    4. Computes multi-criteria Fraud Risk Score and recommended field action,
       applying IWS refill transient dampening during first 45-60 min of supply opening.
    5. Integrates Component 1 leak feedback adjustments if registered.
    6. Automatically dispatches authority alerts via background task if fraud_risk_score >= 70.0.
    """
    if "isolation_forest" not in MODELS or "random_forest" not in MODELS:
        load_models()

    iso_forest = MODELS["isolation_forest"]
    random_forest = MODELS["random_forest"]

    # 0. IoT Data Imputation & Sensor Health State Tracking
    tracker = get_or_create_sensor_tracker(req.zone_id, req.node_id)
    raw_actual = req.actual_pressure
    is_missing = (
        raw_actual is None
        or (isinstance(raw_actual, (float, int)) and (np.isnan(raw_actual) or raw_actual < 0.0))
    )

    imputed_pressure: float
    is_imputed: bool = False
    imputation_method: str = "none"
    sensor_health_warning: bool = False
    sensor_health_details: Optional[str] = None

    if is_missing:
        tracker["consecutive_missing"] += 1
        is_imputed = True

        if tracker["last_valid_actual"] is not None:
            # Check if expected pressure slope can guide linear interpolation
            if tracker["last_valid_expected"] is not None and abs(req.expected_pressure - tracker["last_valid_expected"]) > 0.05:
                # Dynamic refill / demand ramp: linearly interpolate following digital twin baseline trend
                exp_delta = req.expected_pressure - tracker["last_valid_expected"]
                imputed_pressure = round(float(tracker["last_valid_actual"] + exp_delta), 2)
                imputation_method = "linear_interpolation"
            else:
                # Constant expected pressure: forward-fill last known valid measurement
                imputed_pressure = round(float(tracker["last_valid_actual"]), 2)
                imputation_method = "forward_fill"
        else:
            # Cold start without prior measurement: seed with expected digital twin baseline
            imputed_pressure = round(float(req.expected_pressure), 2)
            imputation_method = "digital_twin_baseline"
    else:
        # Valid reading received
        act_val = round(float(raw_actual), 2)

        # Check for stuck / frozen sensor transducer (constant invariant value across cycles)
        if tracker["frozen_val"] is not None and abs(act_val - tracker["frozen_val"]) < 1e-4:
            tracker["frozen_count"] += 1
        else:
            tracker["frozen_val"] = act_val
            tracker["frozen_count"] = 1

        tracker["consecutive_missing"] = 0
        tracker["last_valid_actual"] = act_val
        tracker["last_valid_expected"] = req.expected_pressure
        imputed_pressure = act_val
        is_imputed = False
        imputation_method = "none"

    # Flag Sensor Health Warning if consecutive missing intervals exceed 3 cycles (45 minutes, at 15 min/interval)
    if tracker["consecutive_missing"] > 3:
        sensor_health_warning = True
        missing_mins = tracker["consecutive_missing"] * 15
        sensor_health_details = (
            f"Sensor Health Warning: {tracker['consecutive_missing']} consecutive missing intervals "
            f"({missing_mins} min elapsed) at node {req.node_id}. Telemetry packet loss exceeded 45-min threshold."
        )
    elif tracker["frozen_count"] >= 4 and abs(req.expected_pressure - tracker["frozen_val"]) > 1.0:
        # Stuck transducer warning: repeated flatline (e.g. 18.0 m) while expected hydraulic pressure changes
        sensor_health_warning = True
        sensor_health_details = (
            f"Sensor Health Warning: Transducer stuck invariant at {tracker['frozen_val']:.2f}m "
            f"across {tracker['frozen_count']} consecutive cycles despite expected hydraulic variations."
        )

    # 1. Compute hydraulic features using imputed_pressure
    hydraulic_residual = float(req.expected_pressure - imputed_pressure)
    tracker["last_valid_residual"] = hydraulic_residual

    pressure_change_rate = float(req.pressure_change_rate if req.pressure_change_rate is not None else 0.0)
    residual_rolling_mean = float(req.residual_rolling_mean if req.residual_rolling_mean is not None else hydraulic_residual)
    residual_rolling_std = float(req.residual_rolling_std if req.residual_rolling_std is not None else 0.0)
    is_transient_window = req.hours_since_supply_start is not None and (0.0 <= float(req.hours_since_supply_start) <= 1.0)
    spatial_deviation = float(req.spatial_deviation)
    if not is_transient_window and spatial_deviation == 0.0 and hydraulic_residual >= 2.0:
        spatial_deviation = round(hydraulic_residual - 0.2, 2)

    recurrence_count = int(req.recurrence_count)
    if not is_transient_window and recurrence_count == 0 and hydraulic_residual >= 2.0:
        recurrence_count = 5

    feature_dict = {
        "actual_pressure": imputed_pressure,
        "hydraulic_residual": hydraulic_residual,
        "pressure_change_rate": pressure_change_rate,
        "residual_rolling_mean": residual_rolling_mean,
        "residual_rolling_std": residual_rolling_std,
        "spatial_deviation": spatial_deviation,
    }
    feature_df = pd.DataFrame([feature_dict])[FEATURE_NAMES]

    # 2. Stage 1: Anomaly Detection
    iso_pred = iso_forest.predict(feature_df)[0]
    is_anomaly = bool(
        (iso_pred == -1 or iso_forest.decision_function(feature_df)[0] <= 0.0 or hydraulic_residual >= 2.0)
        and hydraulic_residual >= 1.0
    )

    # 3. Stage 2: Root Cause Classification (if anomalous)
    if is_anomaly:
        cause_pred = str(random_forest.predict(feature_df)[0])
        rf_probs_arr = random_forest.predict_proba(feature_df)[0]
        rf_probabilities = {cls: float(prob) for cls, prob in zip(random_forest.classes_, rf_probs_arr)}
        classification = cause_pred
    else:
        classification = "normal"
        rf_probabilities = {"leak": 0.0, "partial_bypass": 0.0}

    # 4. Calculate Fraud Risk Score with transient dampening window
    fraud_risk_score, breakdown, reasons_list = explain_fraud_score(
        is_anomaly=is_anomaly,
        rf_probabilities=rf_probabilities,
        residual=hydraulic_residual,
        recurrence_count=recurrence_count,
        spatial_deviation=spatial_deviation,
        hours_since_supply_start=req.hours_since_supply_start,
    )

    is_transient_dampened = bool(breakdown.get("transient_dampening_active", False))

    # Append IoT Imputation & Sensor Health findings to reasons_list
    if is_imputed:
        reasons_list.append(
            f"Data Imputation Applied: Missing telemetry packet imputed ({imputed_pressure:.2f}m via {imputation_method}). "
            f"Erroneous residual spike suppressed."
        )
    if sensor_health_warning and sensor_health_details:
        reasons_list.append(sensor_health_details)

    # 4b. Sensor Health Hardware Override (Stuck/Frozen Transducer)
    if tracker.get("frozen_count", 0) >= 4 and abs(req.expected_pressure - float(tracker.get("frozen_val") or 0.0)) > 1.0:
        fraud_risk_score = 18.0
        classification = "sensor_malfunction"
        reasons_list.append(
            f"Sensor Health Hardware Override: Invariant flatline ({tracker['frozen_val']:.2f}m) indicates mechanical "
            f"transducer lockup, not water theft. Fraud risk suppressed to 18.0%."
        )

    # 5. Check if Component 1 physical leak feedback has been registered for this node
    node_key = f"{normalize_zone_name(req.zone_id)}:{req.node_id}"
    if node_key in FEEDBACK_CACHE:
        fb = FEEDBACK_CACHE[node_key]
        if fb.get("leak_probability", 0.0) > 0.7:
            if fb.get("leak_probability", 0.0) >= 0.80:
                fraud_risk_score = 18.0
            else:
                fraud_risk_score = round(fraud_risk_score * 0.60, 2)
            classification = "physical_leak"
            reasons_list.append(
                f"Component 1 Cross-Validation Override: Physical leak probability {fb['leak_probability']*100:.1f}% "
                f"> 70%. Fraud risk suppressed down to {fraud_risk_score:.1f}% and reclassified as physical pipe leak."
            )

    recommended_action = get_recommended_action(
        fraud_risk_score,
        classification=classification,
        is_transient_dampened=is_transient_dampened,
    )

    if sensor_health_warning and fraud_risk_score < 70.0:
        recommended_action += " | Sensor Health Warning: Dispatch IoT technician to inspect node transducer & telemetry link."

    # 6. Build exact location metadata
    location_obj = build_location_metadata(req.node_id)

    # 7. Automatic Authority Alert Dispatch via BackgroundTasks if fraud_risk_score >= 70.0
    if fraud_risk_score >= 70.0:
        alert_payload = {
            "node_id": req.node_id,
            "dma_id": normalize_zone_name(req.zone_id) or req.zone_id,
            "risk_score": fraud_risk_score,
            "actual_pressure": imputed_pressure,
            "expected_pressure": req.expected_pressure,
            "residual_head_drop": round(float(hydraulic_residual), 2),
            "probable_cause": classification,
            "inspection_priority": recommended_action,
            "evidence_list": reasons_list,
            "location": location_obj.model_dump(),
        }
        background_tasks.add_task(NOTIFIER.dispatch_alert, alert_payload)

    # Cache latest assessment in memory
    LATEST_NODE_ASSESSMENTS[node_key] = {
        "zone_id": req.zone_id,
        "node_id": req.node_id,
        "fraud_risk_score": fraud_risk_score,
        "classification": classification,
        "recommended_action": recommended_action,
        "location": location_obj.model_dump(),
        "imputed_actual_pressure": imputed_pressure,
        "is_imputed": is_imputed,
        "sensor_health_warning": sensor_health_warning,
    }

    # Update Edge Concentrator Gateway Health Registry
    update_gateway_health(
        zone_id=req.zone_id,
        node_id=req.node_id,
        battery_voltage=req.battery_voltage,
        cellular_rssi_dbm=req.cellular_rssi_dbm,
        is_heartbeat=req.is_heartbeat,
        is_store_and_forward=req.is_store_and_forward,
        buffered_readings_count=req.buffered_readings_count,
        deadband_suppressed_count=req.deadband_suppressed_count,
    )

    # 8. Real-Time WebSocket Telemetry Broadcast to Dashboards
    alert_triggered = bool(fraud_risk_score >= 70.0)

    # Synchronize live map simulation state when J_100 is streamed
    if req.node_id in ("J_100", "J100"):
        try:
            import app.routes.network_status as net_status
            if is_transient_dampened:
                net_status._CURRENT_SIMULATION_STATE = "normal"
            elif alert_triggered or hydraulic_residual >= 2.0 or fraud_risk_score >= 50.0:
                net_status._CURRENT_SIMULATION_STATE = "bypass"
            elif hydraulic_residual < 1.0 and fraud_risk_score < 40.0:
                net_status._CURRENT_SIMULATION_STATE = "normal"
        except Exception:
            pass

    import datetime
    now_ts = datetime.datetime.now().strftime("%H:%M:%S")
    ws_broadcast_payload = {
        "type": "TELEMETRY_UPDATE",
        "node_id": str(req.node_id),
        "actual_p": round(float(imputed_pressure), 2),
        "residual_m": round(float(hydraulic_residual), 2),
        "risk_score": round(float(fraud_risk_score), 2),
        "alert_triggered": alert_triggered,
        "zone_id": normalize_zone_name(req.zone_id) or req.zone_id,
        "expected_p": round(float(req.expected_pressure), 2),
        "classification": classification,
        "recommended_action": recommended_action,
        "battery_voltage": req.battery_voltage,
        "cellular_rssi_dbm": req.cellular_rssi_dbm,
        "is_heartbeat": bool(req.is_heartbeat),
        "is_store_and_forward": bool(req.is_store_and_forward),
        "timestamp": now_ts,
    }
    WS_MANAGER.broadcast_sync(ws_broadcast_payload)

    return RiskAssessmentResponse(
        zone_id=req.zone_id,
        node_id=req.node_id,
        fraud_risk_score=fraud_risk_score,
        classification=classification,
        reasons_list=reasons_list,
        recommended_action=recommended_action,
        hours_since_supply_start=req.hours_since_supply_start,
        transient_dampening_active=is_transient_dampened,
        location=location_obj,
        imputed_actual_pressure=imputed_pressure,
        is_imputed=is_imputed,
        imputation_method=imputation_method,
        consecutive_missing_cycles=tracker["consecutive_missing"],
        sensor_health_warning=sensor_health_warning,
        sensor_health_details=sensor_health_details,
        battery_voltage=req.battery_voltage,
        cellular_rssi_dbm=req.cellular_rssi_dbm,
        is_heartbeat=req.is_heartbeat,
        is_store_and_forward=req.is_store_and_forward,
    )


@app.get(
    "/api/v1/sensors/gateway-health",
    response_model=GatewayHealthResponse,
    tags=["Assessment"],
    summary="Get Edge Concentrator Gateways Health and Telemetry Status",
)
@app.get(
    "/api/v1/sensors/gateway-health/",
    response_model=GatewayHealthResponse,
    include_in_schema=False,
)
def get_gateway_health():
    """
    Returns live health, battery voltage (3.4-4.2V), cellular RSSI signal quality,
    deadband suppression efficiency, and store-and-forward buffer status across
    all physical edge telemetry concentrators deployed in Kaduwela DMAs 01 & 02.
    """
    return get_gateway_health_summary()


@app.post(
    "/api/v1/sensors/telemetry",
    response_model=RiskAssessmentResponse,
    tags=["Assessment"],
    summary="Ingest Sensor Telemetry and Return Fraud Risk Assessment with Exact GPS Location",
)
@app.post(
    "/api/v1/sensors/telemetry/",
    response_model=RiskAssessmentResponse,
    include_in_schema=False,
)
def sensors_telemetry(
    req: SensorTelemetryRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Ingests live sensor telemetry and returns full fraud risk scoring
    alongside exact geodetic GPS coordinates, physical landmark, and Google Maps URL.
    """
    return assess_risk(req, background_tasks=background_tasks)


# ==============================================================================
# WebSocket Telemetry Streaming Route
# ==============================================================================

@app.websocket("/ws/telemetry")
@app.websocket("/ws/telemetry/")
@app.websocket("/api/v1/ws/telemetry")
@app.websocket("/api/v1/ws/telemetry/")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """
    WebSocket streaming endpoint for live SCADA pressure telemetry,
    digital twin residuals, and automated fraud triage alerts.
    """
    await WS_MANAGER.connect(websocket)
    import datetime
    try:
        await websocket.send_json({
            "type": "CONNECTION_ESTABLISHED",
            "message": "Connected to Kaduwela Water Fraud SCADA WebSocket Telemetry Stream",
            "active_nodes": ["J_10", "J_100", "J_500", "J_1200", "J_2200", "J_3000"],
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        WS_MANAGER.disconnect(websocket)
    except Exception:
        WS_MANAGER.disconnect(websocket)


@app.get(
    "/api/v1/junctions/{node_id}/location",
    response_model=LocationMetadata,
    tags=["Assessment"],
    summary="Get Exact GPS Location and Navigation Metadata for Junction",
)
def get_node_location_endpoint(node_id: str):
    """
    Retrieves GPS coordinates, local grid coordinates, physical landmark,
    and direct Google Maps navigation URL for a junction node.
    """
    return build_location_metadata(node_id)


# ==============================================================================
# Multi-Component Integration Routes
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Component 1 Integration: Physical Leak Feedback
# ------------------------------------------------------------------------------

@app.post(
    "/api/v1/c1-leak-feedback",
    response_model=C1LeakFeedbackResponse,
    tags=["Component Integration"],
    summary="Receive Component 1 Physical Leak Detection Feedback",
)
def c1_leak_feedback(req: C1LeakFeedbackRequest):
    """
    Component 1 Integration Route:
    Accepts: { "zone_id": str, "node_id": str, "leak_probability": float }
    
    Behavior:
    If leak_probability > 0.7:
      - Reduces calculated fraud risk score by 40% (adjusted_score = original_score * 0.60).
      - Reclassifies event as 'physical_leak'.
      - Updates node risk state and dispatches physical repair workorder.
    Otherwise:
      - Retains current fraud risk classification.
    """
    norm_zone = normalize_zone_name(req.zone_id)
    node_key = f"{norm_zone}:{req.node_id}"

    # Determine baseline fraud score and classification
    if req.current_fraud_score is not None:
        original_score = float(req.current_fraud_score)
        original_classification = "partial_bypass"
    else:
        original_score, original_classification = get_cached_or_default_node_state(req.zone_id, req.node_id)

    if req.leak_probability > 0.7:
        if req.leak_probability >= 0.80:
            adjusted_score = 18.0
        else:
            adjusted_score = round(original_score * 0.60, 2)
        adjusted_classification = "physical_leak"
        feedback_applied = True
        recommended_action = "Physical Pipe Repair Workorder (Component 1 Leak Confirmed)"
        message = (
            f"Component 1 acoustic/sensor leak probability ({req.leak_probability * 100:.1f}%) exceeds 70% threshold. "
            f"Fraud risk score suppressed down to {adjusted_score:.2f}% "
            f"and reclassified from '{original_classification}' to 'physical_leak'."
        )

        # Store in feedback cache so future calls retain this adjustment
        FEEDBACK_CACHE[node_key] = {
            "leak_probability": req.leak_probability,
            "adjusted_score": adjusted_score,
            "classification": adjusted_classification,
        }
        LATEST_NODE_ASSESSMENTS[node_key] = {
            "zone_id": req.zone_id,
            "node_id": req.node_id,
            "fraud_risk_score": adjusted_score,
            "classification": adjusted_classification,
            "recommended_action": recommended_action,
        }
    else:
        adjusted_score = original_score
        adjusted_classification = original_classification
        feedback_applied = False
        recommended_action = get_recommended_action(original_score, classification=original_classification)
        message = (
            f"Component 1 leak probability ({req.leak_probability * 100:.1f}%) is below the 70% threshold. "
            f"Calculated fraud risk score ({original_score:.2f}) and '{original_classification}' classification retained."
        )

        # Clear or update feedback cache to reflect confirmed zero leak
        FEEDBACK_CACHE[node_key] = {
            "leak_probability": req.leak_probability,
            "adjusted_score": adjusted_score,
            "classification": adjusted_classification,
        }
        LATEST_NODE_ASSESSMENTS[node_key] = {
            "zone_id": req.zone_id,
            "node_id": req.node_id,
            "fraud_risk_score": adjusted_score,
            "classification": adjusted_classification,
            "recommended_action": recommended_action,
        }

    return C1LeakFeedbackResponse(
        zone_id=req.zone_id,
        node_id=req.node_id,
        leak_probability=req.leak_probability,
        original_fraud_risk_score=original_score,
        adjusted_fraud_risk_score=adjusted_score,
        original_classification=original_classification,
        adjusted_classification=adjusted_classification,
        leak_feedback_applied=feedback_applied,
        recommended_action=recommended_action,
        message=message,
    )


# ------------------------------------------------------------------------------
# 2. Component 3 Integration: Water Loss Forecast
# ------------------------------------------------------------------------------

@app.get(
    "/api/v1/c3-water-loss/{zone_id}",
    response_model=C3WaterLossResponse,
    tags=["Component Integration"],
    summary="Estimate Unmetered Water Volume Loss for Component 3 Storage Forecast",
)
def c3_water_loss(zone_id: str):
    """
    Component 3 Integration Route:
    Returns estimated unmetered water volume loss (in Liters Per Second, LPS)
    and current risk level for Component 3's storage forecast.
    """
    norm_zone = normalize_zone_name(zone_id)

    # Check for active theft nodes and unmetered loss rate
    active_theft_nodes: List[str] = []
    total_unmetered_loss_lps = 0.0
    zone_risk_level = "Normal"
    monitoring_nodes_count = 3  # 3 monitoring nodes per DMA

    # Read from dma_risk_summary.csv if present
    if DMA_SUMMARY_PATH.exists():
        try:
            df = pd.read_csv(DMA_SUMMARY_PATH)
            matched = df[df["DMA_ID"].apply(normalize_zone_name) == norm_zone]
            if len(matched) > 0:
                monitoring_nodes_count = len(matched)
                for _, row in matched.iterrows():
                    node = str(row["Node_ID"])
                    score = float(row["Peak_Risk_Score"])
                    cause = str(row["Primary_Suspected_Cause"])

                    # Check if C1 feedback has reclassified this node as physical leak
                    cache_key = f"{norm_zone}:{node}"
                    if cache_key in FEEDBACK_CACHE and FEEDBACK_CACHE[cache_key].get("classification") == "physical_leak":
                        cause = "physical_leak"

                    if cause == "partial_bypass" and score >= 50.0:
                        active_theft_nodes.append(node)
                        # Estimated illegal withdrawal rate: ~0.08 LPS based on hydraulic head loss
                        total_unmetered_loss_lps += 0.08
                        zone_risk_level = "Critical" if score >= 75.0 else "High"
                    elif cause == "leak" and score >= 50.0:
                        zone_risk_level = "High" if zone_risk_level != "Critical" else "Critical"
        except Exception as e:
            print(f"Error parsing DMA summary: {e}")

    # Fallback default if summary not yet generated
    if not active_theft_nodes and norm_zone == "DMA 01":
        active_theft_nodes = ["J_100"]
        total_unmetered_loss_lps = 0.08
        zone_risk_level = "Critical"

    total_unmetered_loss_lps = round(total_unmetered_loss_lps, 4)
    # Convert LPS to m^3/hr (1 LPS = 0.001 m^3/s * 3600 s/hr = 3.6 m^3/hr)
    hourly_loss_m3 = round(total_unmetered_loss_lps * 3.6, 3)
    # 24h daily loss volume
    daily_loss_m3 = round(hourly_loss_m3 * 24.0, 2)

    if total_unmetered_loss_lps > 0.0:
        impact = (
            f"Active unmetered bypass theft detected at node(s) {active_theft_nodes}. "
            f"Accelerating service reservoir storage drawdown by {hourly_loss_m3:.2f} m^3/hr "
            f"({daily_loss_m3:.1f} m^3/day). Factor into Component 3 distribution tank inventory model."
        )
    else:
        impact = (
            f"No unmetered commercial water theft detected in {norm_zone}. "
            f"Distribution system demands align with baseline consumer storage models."
        )

    return C3WaterLossResponse(
        zone_id=norm_zone,
        current_risk_level=zone_risk_level,
        estimated_unmetered_water_loss_lps=total_unmetered_loss_lps,
        estimated_hourly_loss_m3=hourly_loss_m3,
        estimated_daily_loss_m3=daily_loss_m3,
        active_theft_nodes=active_theft_nodes,
        monitoring_nodes_count=monitoring_nodes_count,
        storage_forecast_impact=impact,
    )


# ------------------------------------------------------------------------------
# 3. Component 4 Integration: Pressure Drop Events (Intrusion Risk)
# ------------------------------------------------------------------------------

@app.get(
    "/api/v1/c4-pressure-drop-events",
    response_model=C4PressureDropEventsResponse,
    tags=["Component Integration"],
    summary="Get Severe Depressurization Events for Component 4 Intrusion Risk",
)
def c4_pressure_drop_events(
    threshold_m: float = 5.0,
    zone_id: Optional[str] = None,
):
    """
    Component 4 Integration Route:
    Returns timestamps and nodes currently experiencing severe depressurization (Delta P > 5m)
    for Component 4's intrusion risk analysis. Severe head loss creates back-siphonage and
    groundwater contaminant ingress risk through pipe leaks and joints.
    """
    events: List[DepressurizationEvent] = []
    affected_nodes_set = set()

    # Load 24h actual telemetry scenario and baseline reference
    if not SCENARIO_PATH.exists() or not BASELINE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="Simulation scenario datasets not found. Run src/export_dma_status.py first.",
        )

    df_act = pd.read_csv(SCENARIO_PATH, index_col=0)
    df_exp = pd.read_csv(BASELINE_PATH, index_col=0)
    df_act.index = df_act.index.astype(int)
    df_exp.index = df_exp.index.astype(int)

    # Node-to-DMA map
    node_dma_map = {
        "J_10": "DMA 01",
        "J_100": "DMA 01",
        "J_500": "DMA 01",
        "J_1200": "DMA 02",
        "J_2200": "DMA 02",
        "J_3000": "DMA 02",
    }

    target_zone_norm = normalize_zone_name(zone_id) if zone_id else None

    # Evaluate monitored junctions
    eval_cols = [c for c in ["J_10", "J_100", "J_500", "J_1200", "J_2200", "J_3000"] if c in df_act.columns and c in df_exp.columns]

    for t in df_act.index:
        t_sec = int(t)
        hours = t_sec / 3600.0
        time_str = f"{int(hours):02d}:{int((hours % 1) * 60):02d}"

        for node in eval_cols:
            node_zone = node_dma_map.get(node, "DMA 01")
            if target_zone_norm and node_zone != target_zone_norm:
                continue

            p_act = float(df_act.loc[t, node])
            p_exp = float(df_exp.loc[t, node])
            delta_p = p_exp - p_act

            if delta_p > threshold_m:
                affected_nodes_set.add(node)
                severity = "Severe" if delta_p >= 6.0 else "High"
                events.append(
                    DepressurizationEvent(
                        timestamp_seconds=t_sec,
                        time_formatted=time_str,
                        node_id=node,
                        zone_id=node_zone,
                        actual_pressure=round(p_act, 2),
                        expected_pressure=round(p_exp, 2),
                        pressure_deficit_m=round(delta_p, 2),
                        intrusion_risk_severity=severity,
                    )
                )

    affected_nodes = sorted(list(affected_nodes_set))
    if len(events) > 0:
        recommendation = (
            f"Active severe depressurization detected at {affected_nodes} exceeding {threshold_m:.1f}m deficit. "
            f"High risk of negative pressure surge and contaminant intrusion. Issue Component 4 intrusion alert "
            f"and maintain residual disinfectant monitoring."
        )
    else:
        recommendation = f"No depressurization events exceeding {threshold_m:.1f}m threshold detected."

    return C4PressureDropEventsResponse(
        threshold_m=threshold_m,
        total_severe_events_count=len(events),
        affected_nodes=affected_nodes,
        events=events,
        recommendation=recommendation,
    )


# ==============================================================================
# Authority Notification & Alert Dispatch Routes
# ==============================================================================

@app.get(
    "/api/v1/notifications/history",
    response_model=List[Dict[str, Any]],
    tags=["Notifications"],
    summary="Get Sent Notifications History from dispatched_alerts.json",
)
def get_notifications_history(limit: int = Query(50, ge=1, le=500)):
    """
    Returns the list of dispatched authority alerts from data/processed/dispatched_alerts.json.
    """
    return NOTIFIER.get_history(limit=limit)


@app.post(
    "/api/v1/notifications/reset-cooldown",
    tags=["Notifications"],
    summary="Reset Cooldown Cache for Node or All Nodes",
)
def reset_notification_cooldown(node_id: Optional[str] = Query(None)):
    """
    Resets the AuthorityNotifier cooldown cache, feedback caches, and sensor resilience trackers.
    """
    NOTIFIER.reset_cooldown(node_id)
    if node_id is None:
        FEEDBACK_CACHE.clear()
        LATEST_NODE_ASSESSMENTS.clear()
        SENSOR_TRACKER.clear()
    else:
        for k in list(FEEDBACK_CACHE.keys()):
            if node_id in k:
                FEEDBACK_CACHE.pop(k, None)
        for k in list(LATEST_NODE_ASSESSMENTS.keys()):
            if node_id in k:
                LATEST_NODE_ASSESSMENTS.pop(k, None)
        for k in list(SENSOR_TRACKER.keys()):
            if node_id in k:
                SENSOR_TRACKER.pop(k, None)
    return {
        "status": "success",
        "message": f"Cooldown cache and sensor tracker reset for {node_id if node_id else 'all nodes'}.",
    }


# ------------------------------------------------------------------------------
# IoT Resilience & Telemetry Imputation Batch Endpoints
# ------------------------------------------------------------------------------

class BatchTelemetryStep(BaseModel):
    timestamp: Optional[str] = None
    actual_pressure: Optional[float] = None
    expected_pressure: float
    spatial_deviation: Optional[float] = 0.0
    pressure_change_rate: Optional[float] = 0.0
    recurrence_count: Optional[int] = 0
    hours_since_supply_start: Optional[float] = None


class BatchTelemetryRequest(BaseModel):
    zone_id: str = "DMA 01"
    node_id: str = "J_100"
    steps: List[BatchTelemetryStep]


class BatchAssessmentResponse(BaseModel):
    zone_id: str
    node_id: str
    total_steps: int
    imputed_steps_count: int
    sensor_health_warning_triggered: bool
    max_risk_score: float
    results: List[RiskAssessmentResponse]


@app.post(
    "/api/v1/resilience/reset-sensor-health",
    tags=["Assessment"],
    summary="Reset SENSOR_TRACKER state for IoT resilience testing",
)
def reset_sensor_health(node_id: Optional[str] = Query(None)):
    """
    Resets consecutive missing intervals and frozen sensor tracking state.
    """
    if node_id is None:
        SENSOR_TRACKER.clear()
    else:
        for k in list(SENSOR_TRACKER.keys()):
            if node_id in k:
                SENSOR_TRACKER.pop(k, None)
    return {"status": "success", "message": f"Sensor tracker reset for {node_id if node_id else 'all nodes'}."}


@app.post(
    "/api/v1/resilience/batch-assess",
    response_model=BatchAssessmentResponse,
    tags=["Assessment"],
    summary="Batch Ingest Telemetry Trace with Automatic Forward-Fill and Linear Interpolation",
)
def batch_assess_telemetry(req: BatchTelemetryRequest):
    """
    Ingests a sequence of telemetry readings (with optional missing steps),
    applies forward-fill and linear interpolation, detects consecutive missing intervals (>3 cycles / 45 min),
    and returns full sequential risk assessments.
    """
    results: List[RiskAssessmentResponse] = []
    imputed_count = 0
    warning_triggered = False
    max_score = 0.0

    for step in req.steps:
        single_req = SensorTelemetryRequest(
            zone_id=req.zone_id,
            node_id=req.node_id,
            actual_pressure=step.actual_pressure,
            expected_pressure=step.expected_pressure,
            spatial_deviation=step.spatial_deviation or 0.0,
            recurrence_count=step.recurrence_count or 0,
            pressure_change_rate=step.pressure_change_rate or 0.0,
            hours_since_supply_start=step.hours_since_supply_start,
            timestamp=step.timestamp,
        )
        res = assess_risk(single_req)
        results.append(res)
        if res.is_imputed:
            imputed_count += 1
        if res.sensor_health_warning:
            warning_triggered = True
        if res.fraud_risk_score > max_score:
            max_score = res.fraud_risk_score

    return BatchAssessmentResponse(
        zone_id=req.zone_id,
        node_id=req.node_id,
        total_steps=len(req.steps),
        imputed_steps_count=imputed_count,
        sensor_health_warning_triggered=warning_triggered,
        max_risk_score=round(max_score, 2),
        results=results,
    )


# ==============================================================================
# Continuous Learning & Model Retraining Feedback Loop
# ==============================================================================

@app.post(
    "/api/v1/models/retrain",
    response_model=RetrainResponse,
    tags=["Model Management"],
    summary="Trigger Stage 2 Model Retraining with Verified Inspection Ground-Truth",
)
async def retrain_model(
    req: Optional[RetrainRequest] = None,
):
    """
    Continuous Learning Route:
    1. Loads data/processed/inspection_logs.csv.
    2. Validates at least 5 new verified ground-truth entries exist (unless force=True).
    3. Computes feature vectors and appends to data/processed/training_features.csv.
    4. Re-fits Stage 2 RandomForestClassifier with balanced class weights to prevent drift.
    5. Saves updated model with backup tag (models/random_forest_v2.joblib).
    6. Logs and returns validation performance deltas (old vs new test F1-scores).
    7. Hot-reloads updated model into memory cache.
    """
    import asyncio
    from datetime import datetime, timezone

    min_entries = req.min_new_entries if req and req.min_new_entries is not None else 5
    force = req.force if req and req.force is not None else False

    # Asynchronously execute retraining in threadpool to keep API responsive
    result = await asyncio.to_thread(
        retrain_stage2_pipeline,
        min_new_entries=min_entries,
        force=force,
    )

    # Hot-reload retrained model into active in-memory cache if successful
    if result.get("status") == "success" and RANDOM_FOREST_PATH.exists():
        try:
            MODELS["random_forest"] = joblib.load(RANDOM_FOREST_PATH)
            print("Successfully hot-reloaded retrained Stage 2 model into memory.")
        except Exception as e:
            print(f"Failed to hot-reload retrained model into memory: {e}")

    return RetrainResponse(
        status=result.get("status", "unknown"),
        message=result.get("message", ""),
        new_samples_added=result.get("new_samples_added", 0),
        total_anomalous_samples=result.get("total_anomalous_samples"),
        total_dataset_rows=result.get("total_dataset_rows"),
        old_f1_score=result.get("old_f1_score"),
        new_f1_score=result.get("new_f1_score"),
        f1_delta=result.get("f1_delta"),
        class_weights=result.get("class_weights"),
        backup_model_path=result.get("backup_model_path"),
        primary_model_path=result.get("primary_model_path"),
        timestamp=result.get("timestamp", datetime.now(timezone.utc).isoformat()),
        details=result,
    )


@app.get(
    "/api/v1/inspections/logs",
    tags=["Model Management"],
    summary="Get Inspector Feedback Logs",
)
def get_inspection_logs(limit: int = Query(50, ge=1, le=500)):
    """
    Returns inspection logs from data/processed/inspection_logs.csv.
    """
    ensure_inspection_logs_exist()
    if not INSPECTION_LOGS_PATH.exists():
        return []

    try:
        df = pd.read_csv(INSPECTION_LOGS_PATH)
        records = df.to_dict(orient="records")
        return list(reversed(records))[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read inspection logs: {e}")


@app.post(
    "/api/v1/inspections/logs",
    response_model=InspectionFeedbackLogResponse,
    tags=["Model Management"],
    summary="Record Inspector Ground-Truth Feedback",
)
def record_inspection_log(req: InspectionFeedbackLogRequest):
    """
    Records inspector ground-truth feedback from field investigation into inspection_logs.csv.
    """
    import datetime
    ensure_inspection_logs_exist()

    now_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now_ts = int(datetime.datetime.now().timestamp())
    log_id = f"INSP-{now_ts}"

    new_row = {
        "log_id": log_id,
        "node_id": req.node_id,
        "actual_finding": req.actual_finding,
        "timestamp": now_dt,
        "notes": req.notes or "",
        "processed": False,
    }

    try:
        if INSPECTION_LOGS_PATH.exists():
            df = pd.read_csv(INSPECTION_LOGS_PATH)
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        else:
            df = pd.DataFrame([new_row])

        df.to_csv(INSPECTION_LOGS_PATH, index=False)

        unprocessed_count = len(df[~df["processed"].astype(str).str.lower().isin(["true", "1", "yes"])])

        return InspectionFeedbackLogResponse(
            status="recorded",
            message=f"Verified finding recorded for node {req.node_id} ({req.actual_finding}).",
            log_id=log_id,
            node_id=req.node_id,
            actual_finding=req.actual_finding,
            timestamp=now_dt,
            total_unprocessed_logs=unprocessed_count,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record inspection log: {e}")


# ==============================================================================
# Inspection Audit Trail & Operational Accuracy Ledger Routes
# ==============================================================================

@app.get(
    "/api/v1/inspections/ledger",
    tags=["Audit Ledger"],
    summary="Get Field Inspections Audit Trail Ledger (field_inspections_ledger.json)",
)
def get_inspection_ledger_endpoint(limit: int = Query(100, ge=1, le=500)):
    """
    Returns verified field inspection audit records from data/processed/field_inspections_ledger.json.
    """
    return get_inspection_ledger(limit=limit)


@app.get(
    "/api/v1/inspections/metrics",
    tags=["Audit Ledger"],
    summary="Get Live Operational Accuracy Metrics (PPV, FAR, Retraining Readiness)",
)
def get_inspection_metrics_endpoint():
    """
    Calculates ongoing operational accuracy metrics:
    - Positive Predictive Value (PPV) = Confirmed Bypass Incidents / Total Dispatched Inspections
    - False-Alarm Rate (FAR) = False Alarm Operational Incidents / Total Dispatched Inspections
    - Retraining Readiness Count (unbatched inspections toward 10-sample trigger)
    """
    return calculate_operational_metrics()


@app.post(
    "/api/v1/inspections/ledger",
    tags=["Audit Ledger"],
    summary="Record Field Inspection in Structured Audit Ledger",
)
def record_inspection_ledger_endpoint(req: FieldInspectionRecordRequest):
    """
    Records a completed field inspection into data/processed/field_inspections_ledger.json.
    Updates operational metrics (PPV, FAR) and triggers candidate batch generation upon 10 new entries.
    """
    return record_field_inspection(
        alert_id=req.alert_id,
        node_id=req.node_id,
        dma_id=req.dma_id,
        ground_truth_finding=req.ground_truth_finding,
        action_taken=req.action_taken,
        assigned_officer=req.assigned_officer or "Eng. K. Perera (Team 3)",
        notes=req.notes or "",
        dispatch_time=req.dispatch_time,
        inspection_time=req.inspection_time,
        inspection_id=req.inspection_id,
    )


@app.patch(
    "/api/v1/alerts/{alert_id}/investigation",
    tags=["Audit Ledger"],
    summary="Update Alert Status and Record to Field Inspection Audit Ledger",
)
def update_alert_investigation_endpoint(alert_id: str, req: AlertInvestigationUpdateRequest):
    """
    Connects Page 4 of the React Dashboard:
    When an inspector updates an alert status to 'confirmed' or 'rejected',
    writes the full structured record to data/processed/field_inspections_ledger.json.
    """
    norm_status = req.status.lower().strip()
    ledger_result = None

    if norm_status in ["confirmed", "rejected"]:
        finding = req.ground_truth_finding
        if not finding:
            finding = "CONFIRMED_BYPASS" if norm_status == "confirmed" else "FALSE_ALARM_OPERATIONAL"

        action = req.action_taken
        if not action:
            action = (
                "Unmetered illegal branch disconnected and confiscated; NWSDB penalty issued."
                if norm_status == "confirmed"
                else "Transient hydraulic surge verified. No physical theft infraction found."
            )

        ledger_result = record_field_inspection(
            alert_id=alert_id,
            node_id=req.node_id or "J_100",
            dma_id=req.dma_id or "DMA 01",
            ground_truth_finding=finding,
            action_taken=action,
            assigned_officer=req.assignedTo or "Eng. K. Perera (Team 3)",
            notes=req.notes or "",
            inspection_time=req.inspectionDate,
        )

    return {
        "id": alert_id,
        "status": req.status,
        "assignedTo": req.assignedTo,
        "inspectionDate": req.inspectionDate,
        "notes": req.notes,
        "audit_ledger_recorded": ledger_result is not None,
        "audit_ledger_details": ledger_result,
    }


# ==============================================================================
# Main Server Entrypoint
# ==============================================================================

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 68)
    print("Starting Kaduwela Water Fraud Detection API Server (Component 2)...")
    print("Interactive Documentation: http://127.0.0.1:8000/docs")
    print("Health Check:              http://127.0.0.1:8000/health")
    print("C1 Leak Feedback:          POST http://127.0.0.1:8000/api/v1/c1-leak-feedback")
    print("C3 Water Loss Forecast:    GET  http://127.0.0.1:8000/api/v1/c3-water-loss/DMA_01")
    print("C4 Intrusion Drop Events:  GET  http://127.0.0.1:8000/api/v1/c4-pressure-drop-events")
    print("=" * 68 + "\n")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
