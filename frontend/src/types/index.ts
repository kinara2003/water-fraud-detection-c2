/**
 * frontend/src/types/index.ts
 * Data contracts and type definitions for Component 2:
 * NWSDB Unauthorized Water Withdrawal & Physical Twin Surveillance Engine.
 */

export type RiskLevel = 'normal' | 'medium' | 'high' | 'critical';
export type FaultCause = 'normal' | 'leak' | 'burst' | 'illegal_tap' | 'partial_bypass' | 'operational_event';
export type InvestigationStatus = 'new' | 'investigating' | 'field_inspection' | 'confirmed' | 'rejected';

export interface LocationInfo {
  junction_id?: string;
  node_id?: string;
  grid_x?: number;
  grid_y?: number;
  latitude: number;
  longitude: number;
  elevation_m?: number;
  landmark?: string;
  google_maps_url: string;
  nearest_sector?: {
    dma_boundary?: string;
    nearest_access_road?: string;
    sector_name?: string;
    sector_id?: string;
    dma_id?: string;
    distance_m?: number;
    formatted?: string;
  } | string;
  dma_boundary?: string;
  nearest_access_road?: string;
  sector_name?: string;
  dma_id?: string;
}

export interface Zone {
  id: string;
  name: string;
  dmaId: string;
  status: RiskLevel;
  fraudRisk: number; // 0-100
  actualPressure: number;
  expectedPressure: number;
  residual: number;
  anomalyScore: number;
  lastUpdated: string;
  customerCount: number;
  supplyWindow: string;
  location?: LocationInfo;
}

export interface PressureReading {
  timestamp: string;
  actualPressure: number;
  expectedPressure: number;
  residual: number;
  isAbnormal: boolean;
}

export interface Alert {
  id: string;
  zoneId: string;
  zoneName: string;
  timestamp: string;
  riskScore: number;
  classification: FaultCause;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: InvestigationStatus;
  evidenceList: string[];
  assignedTo?: string;
  inspectionDate?: string;
  notes?: string;
  location?: LocationInfo;
}

export interface DigitalTwinScenarioMatch {
  scenario: string;
  expectedPressure: number;
  actualPressure: number;
  similarityScore: number; // 0-1
  isBestMatch: boolean;
}

export interface AIModelAnalysis {
  stage1: {
    modelName: 'Isolation Forest';
    isAnomaly: boolean;
    anomalyScore: number; // 0 to 1
  };
  stage2: {
    modelName: 'Random Forest';
    probabilities: Record<FaultCause, number>;
  };
}

export interface ComponentIntegrationStates {
  c1LeakCrossCheck: {
    leakProbability: number;
    statusText: string;
    impactOnFraud: string;
  };
  c3WaterSecurityImpact: {
    unexplainedLossVolumeLps: number;
    waterSecurityIndexDelta: number;
    shortageRiskIncreased: boolean;
  };
  c4ContaminationRisk: {
    depressurizationEventActive: boolean;
    intrusionSeverity: 'low' | 'medium' | 'high';
  };
}

export interface AlertFilters {
  status?: InvestigationStatus;
  severity?: 'low' | 'medium' | 'high' | 'critical';
  zoneId?: string;
  classification?: FaultCause;
  search?: string;
}

export interface ModelPerformanceMetrics {
  stage1IsolationForest: {
    f1Score: number;
    precision: number;
    recall: number;
    aucRoc: number;
  };
  stage2RandomForest: {
    macroF1: number;
    accuracy: number;
    classes: Record<FaultCause, { f1: number; precision: number; recall: number }>;
  };
  retrainedAt?: string;
  fieldSamplesCount: number;
}

export interface FeaturePipelineStatus {
  activeSensors: number;
  samplingIntervalSec: number;
  telemetryFreshnessSec: number;
  spatialDeviationsActive: boolean;
  refillTransientFilterActive: boolean;
  status: 'operational' | 'degraded' | 'offline';
}

// -------------------------------------------------------------
// Telemetry & Backend Integration Types
// -------------------------------------------------------------

export interface EvidenceChecklist {
  pressure_drop: boolean;
  spatial_mismatch: boolean;
  digital_twin_residual_match: boolean;
  leak_rule_insufficient: boolean;
}

export interface MonitoredNodeStatus {
  dma_id: string;
  node_id: string;
  peak_risk_score: number;
  risk_level: 'Normal' | 'Medium' | 'High' | 'Critical';
  classification: 'normal' | 'partial_bypass' | 'leak' | 'burst' | 'physical_leak';
  recommended_action: string;
  inspection_priority: string;
  current_actual_pressure: number;
  current_expected_pressure: number;
  current_residual: number;
  evidence_checklist: EvidenceChecklist;
  location?: LocationInfo;
}

export interface DmaSummaryItem {
  status: string;
  unmetered_loss_lps: number;
  active_theft_count: number;
}

export interface HighestRiskSector {
  node_id: string;
  dma_id: string;
  risk_level: string;
  peak_risk_score: number;
}

export interface DmaSummary {
  dma_01: DmaSummaryItem;
  dma_02: DmaSummaryItem;
  highest_risk_sector: HighestRiskSector;
}

export interface SupplyWindowStatus {
  state: string;
  window_start: string;
  window_end: string;
  hours_since_supply_start: number;
  refill_transient_active: boolean;
}

export interface NodeTimeseries {
  expected_pressure: number[];
  actual_pressure: number[];
  residual: number[];
}

export interface TimeseriesData {
  labels: string[];
  nodes_data: Record<string, NodeTimeseries>;
}

export interface DmaStatusResponse {
  timestamp: string;
  supply_window: SupplyWindowStatus;
  dma_summary: DmaSummary;
  nodes: MonitoredNodeStatus[];
  timeseries: TimeseriesData;
}

export interface DispatchedAlert {
  alert_id: string;
  timestamp: string;
  node_id: string;
  dma_id: string;
  risk_score: number;
  evidence_list: string[];
  probable_cause: string;
  actual_pressure?: number;
  expected_pressure?: number;
  residual_head_drop?: number;
  inspection_priority: string;
  delivery_status: 'Sent' | 'Failed' | 'Pending';
  recipient_email?: string;
  webhook_url?: string;
  email_channel?: string;
  webhook_channel?: string;
  dispatch_reason?: string;
  location?: LocationInfo;
}

export interface InspectionLog {
  log_id: string;
  node_id: string;
  actual_finding: 'partial_bypass' | 'leak' | 'normal' | string;
  timestamp: string;
  notes: string;
  processed: boolean;
}

export type GroundTruthFinding =
  | 'CONFIRMED_BYPASS'
  | 'CONFIRMED_LEAK'
  | 'FALSE_ALARM_OPERATIONAL';

export interface FieldInspectionAuditRecord {
  inspection_id: string;
  alert_id: string;
  node_id: string;
  dma_id: string;
  dispatch_time: string;
  inspection_time: string;
  assigned_officer: string;
  ground_truth_finding: GroundTruthFinding;
  action_taken: string;
  notes: string;
  batched_for_retraining?: boolean;
}

export interface InspectionOperationalMetrics {
  total_inspections: number;
  confirmed_bypass_count: number;
  confirmed_leak_count: number;
  false_alarm_count: number;
  ppv: number;
  ppv_percentage: number;
  false_alarm_rate: number;
  false_alarm_percentage: number;
  leak_confirmation_rate: number;
  leak_confirmation_percentage: number;
  unbatched_inspections_count: number;
  candidate_batch_threshold: number;
  candidate_batch_ready: boolean;
}

export interface ActiveIncident {
  zone_id: string;
  suspect_junction: string;
  coordinates: [number, number];
  search_radius_m: number;
  landmark: string;
  google_maps_url: string;
  reasons: string[];
  detected_at?: string;
  suspicion_score?: number;
}

export interface ZoneLiveState {
  zone_id: string;
  name: string;
  dma_id: string;
  status: 'NORMAL' | 'CAUTION' | 'FRAUD_ALERT';
  color: string;
  sensor_node_id: string;
  risk_score: number;
  pressure_residual_m: number;
}

export interface LiveMapStateResponse {
  status: string;
  simulation_state: 'normal' | 'bypass' | 'caution';
  active_incident: ActiveIncident | null;
  zones: ZoneLiveState[];
  total_zones: number;
  incident_count: number;
}

