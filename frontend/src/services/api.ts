/**
 * frontend/src/services/api.ts
 * API Client connecting to FastAPI backend (Component 2) with offline mock fallback.
 */

import type { DmaStatusResponse, DispatchedAlert, InspectionLog, LiveMapStateResponse } from '../types';
import { mockDmaStatus, mockAlerts, mockInspectionLogs } from '../data/mockData';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

const NO_CACHE_HEADERS: HeadersInit = {
  'Cache-Control': 'no-cache',
  Pragma: 'no-cache',
};

export async function fetchDmaStatus(): Promise<DmaStatusResponse> {
  if (USE_MOCK) {
    return Promise.resolve(mockDmaStatus);
  }
  try {
    const res = await fetch(`${BASE_URL}/api/v1/dma-status`, { headers: NO_CACHE_HEADERS });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('API error, falling back to mock data:', err);
    return mockDmaStatus;
  }
}

export async function fetchAlertsHistory(limit = 50): Promise<DispatchedAlert[]> {
  if (USE_MOCK) {
    return Promise.resolve(mockAlerts);
  }
  try {
    const res = await fetch(`${BASE_URL}/api/v1/notifications/history?limit=${limit}`, { headers: NO_CACHE_HEADERS });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('API error, falling back to mock alerts:', err);
    return mockAlerts;
  }
}

export async function fetchInspectionLogs(limit = 50): Promise<InspectionLog[]> {
  if (USE_MOCK) {
    return Promise.resolve(mockInspectionLogs);
  }
  try {
    const res = await fetch(`${BASE_URL}/api/v1/inspections/logs?limit=${limit}`, { headers: NO_CACHE_HEADERS });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('API error, falling back to mock logs:', err);
    return mockInspectionLogs;
  }
}

export interface RetrainResponse {
  status: string;
  message: string;
  samples_added?: number;
  old_f1?: number;
  new_f1?: number;
  delta?: number;
}

export async function triggerModelRetrain(): Promise<RetrainResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 1200));
    return {
      status: 'success',
      message: 'Model retraining triggered successfully with ground-truth field samples.',
      samples_added: 5,
      old_f1: 0.9412,
      new_f1: 0.9625,
      delta: 0.0213,
    };
  }
  try {
    const res = await fetch(`${BASE_URL}/api/v1/models/retrain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('Retrain API call failed, falling back to simulated response:', err);
    return {
      status: 'simulated',
      message: 'Model retrain simulation completed.',
      samples_added: 5,
      old_f1: 0.9412,
      new_f1: 0.9625,
      delta: 0.0213,
    };
  }
}

export async function fetchLiveMapState(stateOverride?: string): Promise<LiveMapStateResponse> {
  try {
    const query = stateOverride ? `?state=${encodeURIComponent(stateOverride)}` : '';
    const res = await fetch(`${BASE_URL}/api/v1/network/live-map-state${query}`, { headers: NO_CACHE_HEADERS });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('Live map state API error, falling back to mock state:', err);
    const isBypass = stateOverride === 'bypass';
    return {
      status: 'fallback',
      simulation_state: isBypass ? 'bypass' : 'normal',
      active_incident: isBypass
        ? {
            zone_id: 'Zone 04',
            suspect_junction: 'J_100',
            coordinates: [6.93541, 79.98425],
            search_radius_m: 50,
            landmark: 'Kaduwela East Sector Road (Near Node J_100 Chamber)',
            google_maps_url: 'https://www.google.com/maps/search/?api=1&query=6.93541,79.98425',
            reasons: [
              'Missing 6.0m pressure',
              'Recurring 06:45–09:30 AM',
              'Acoustic leak check negative',
            ],
            detected_at: '06:45 AM',
            suspicion_score: 89.0,
          }
        : null,
      zones: [
        { zone_id: 'Zone 01', name: 'Zone 01 - Kaduwela Town Central', dma_id: 'DMA 01', status: 'NORMAL', color: '#10b981', sensor_node_id: 'J_10', risk_score: 12.0, pressure_residual_m: -0.2 },
        { zone_id: 'Zone 02', name: 'Zone 02 - Nawagamuwa North', dma_id: 'DMA 01', status: 'NORMAL', color: '#10b981', sensor_node_id: 'J_20', risk_score: 18.0, pressure_residual_m: -0.2 },
        { zone_id: 'Zone 03', name: 'Zone 03 - Korathota Junction', dma_id: 'DMA 02', status: 'NORMAL', color: '#10b981', sensor_node_id: 'J_500', risk_score: 15.0, pressure_residual_m: -0.1 },
        { zone_id: 'Zone 04', name: 'Zone 04 - Kaduwela East Industrial', dma_id: 'DMA 01', status: isBypass ? 'FRAUD_ALERT' : 'NORMAL', color: isBypass ? '#ef4444' : '#10b981', sensor_node_id: 'J_100', risk_score: isBypass ? 89.0 : 14.0, pressure_residual_m: isBypass ? -6.0 : -0.3 },
        { zone_id: 'Zone 05', name: 'Zone 05 - Welihinda Ridge', dma_id: 'DMA 02', status: 'NORMAL', color: '#10b981', sensor_node_id: 'J_1200', risk_score: 22.0, pressure_residual_m: -0.3 },
        { zone_id: 'Zone 06', name: 'Zone 06 - Welivita Highway Exit', dma_id: 'DMA 02', status: 'NORMAL', color: '#10b981', sensor_node_id: 'J_3000', risk_score: 16.0, pressure_residual_m: -0.1 },
      ],
      total_zones: 6,
      incident_count: isBypass ? 1 : 0,
    };
  }
}

export async function setServerSimulationState(targetState: 'normal' | 'bypass'): Promise<LiveMapStateResponse> {
  try {
    const res = await fetch(`${BASE_URL}/api/v1/network/live-map-state/simulate?state=${targetState}`, {
      method: 'POST',
      headers: NO_CACHE_HEADERS,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('Set simulation state API error:', err);
    return fetchLiveMapState(targetState);
  }
}

export interface PillarEvidence {
  pillar: number;
  name: string;
  value: string;
  detail: string;
  badge: string;
}

export interface ZoneTelemetryResponse {
  zone_id: string;
  clean_id: string;
  name: string;
  node_id: string;
  dma_id: string;
  suspicion_score: number;
  status: 'NORMAL' | 'CAUTION' | 'FRAUD_ALERT';
  actual_pressure: number;
  expected_pressure: number;
  pressure_gap: number;
  landmark: string;
  gps: string;
  elevation: number;
  four_pillar_evidence: PillarEvidence[];
  recommendation: string;
}

export async function fetchZoneTelemetry(zoneId: string): Promise<ZoneTelemetryResponse> {
  const cleanId = zoneId.toLowerCase().replace('zone-', '').replace('zone', '').trim();
  try {
    const res = await fetch(`${BASE_URL}/api/v1/zones/${cleanId}/telemetry`, { headers: NO_CACHE_HEADERS });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`Zone telemetry API error for zone ${zoneId}, falling back to mock:`, err);
    const isZone04 = cleanId === '04' || cleanId === '4';
    return {
      zone_id: `zone-${cleanId.padStart(2, '0')}`,
      clean_id: cleanId.padStart(2, '0'),
      name: `Zone ${cleanId.padStart(2, '0')} — Kaduwela East`,
      node_id: isZone04 ? 'J_100' : `J_${cleanId}0`,
      dma_id: ['01', '02', '04', '1', '2', '4'].includes(cleanId) ? 'DMA 01' : 'DMA 02',
      suspicion_score: isZone04 ? 89.0 : 12.0,
      status: isZone04 ? 'FRAUD_ALERT' : 'NORMAL',
      actual_pressure: isZone04 ? 15.2 : 21.0,
      expected_pressure: 21.2,
      pressure_gap: isZone04 ? 6.0 : 0.2,
      landmark: isZone04 ? 'Junction J_100 Chamber, Kaduwela Road' : `Sector Chamber J_${cleanId.padStart(2, '0')}`,
      gps: isZone04 ? '6.9354° N, 79.9842° E' : '6.9350° N, 79.9840° E',
      elevation: 12.0,
      four_pillar_evidence: [
        {
          pillar: 1,
          name: 'Pressure Gap',
          value: isZone04 ? 'Missing: 6.0 m' : 'Missing: 0.2 m',
          detail: isZone04
            ? 'Expected: 21.2 m | Actual: 15.2 m (Missing: 6.0 m)'
            : 'Expected: 21.2 m | Actual: 21.0 m (Missing: 0.2 m)',
          badge: isZone04
            ? 'Sustained head deficit exceeds physical pipe friction bounds.'
            : 'Within acceptable operational tolerance (±0.5 m).',
        },
        {
          pillar: 2,
          name: 'Timing Pattern',
          value: isZone04 ? '06:45 AM – 09:30 AM' : '24-Hour Continuous Baseline',
          detail: isZone04
            ? 'Drop occurs only between 06:45 AM and 09:30 AM (matches consumer morning tank filling)'
            : 'Pressure adheres smoothly to expected EPANET diurnal demand curve.',
          badge: isZone04
            ? 'Pattern matches unmetered storage cistern draw off.'
            : 'No abnormal temporal transient detected.',
        },
        {
          pillar: 3,
          name: 'Neighbor Comparison',
          value: isZone04 ? 'Normal at 20.4 m' : 'Symmetric at 21.0 m',
          detail: isZone04
            ? 'Neighboring sectors (Zones 02 & 05) remain normal at 20.4 m (proves drop is local, not a main supply failure)'
            : 'Uniform pressure gradient across adjacent Kaduwela East distribution sectors.',
          badge: isZone04
            ? 'Spatial divergence confirms localized downstream off-take.'
            : 'Topological hydraulic balance maintained.',
        },
        {
          pillar: 4,
          name: 'Physical Leak Check',
          value: isZone04 ? '18% Acoustic Level' : '12% Acoustic Level',
          detail: isZone04
            ? 'Acoustic pipe sensor reads 18% (quiet pipe wall — rules out a physical burst/crack)'
            : 'Low ambient hydrophone noise reading; structural integrity verified.',
          badge: isZone04
            ? 'Intact acoustic baseline isolates commercial extraction.'
            : 'Acoustic sensor confirms nominal pipe wall integrity.',
        },
      ],
      recommendation: isZone04
        ? 'Send inspection crew to verify unmetered bypass near Junction J_100 on Kaduwela Road.'
        : 'System operates within standard hydraulic limits. No field inspection required.',
    };
  }
}
