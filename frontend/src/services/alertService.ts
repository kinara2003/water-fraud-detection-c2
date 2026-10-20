import type {
  Alert,
  AlertFilters,
  FieldInspectionAuditRecord,
  InspectionOperationalMetrics,
} from '../types';
import { initialAlerts } from '../data/mockData';
import { apiClient, IS_USE_MOCK, simulateLatency } from './apiClient';

// In-memory state cache for simulated mutations
let alertsState: Alert[] = [...initialAlerts];

// In-memory audit metrics fallback
let mockOperationalMetrics: InspectionOperationalMetrics = {
  total_inspections: 12,
  confirmed_bypass_count: 9,
  confirmed_leak_count: 2,
  false_alarm_count: 1,
  ppv: 0.75,
  ppv_percentage: 75.0,
  false_alarm_rate: 0.0833,
  false_alarm_percentage: 8.3,
  leak_confirmation_rate: 0.1667,
  leak_confirmation_percentage: 16.7,
  unbatched_inspections_count: 2,
  candidate_batch_threshold: 10,
  candidate_batch_ready: false,
};

let mockLedgerState: FieldInspectionAuditRecord[] = [
  {
    inspection_id: 'INSP-20261008-012',
    alert_id: 'ALT-02',
    node_id: 'J_500',
    dma_id: 'DMA 01',
    dispatch_time: '2026-10-08T08:00:00Z',
    inspection_time: '2026-10-08T10:15:00Z',
    assigned_officer: 'Eng. M. Fernando (Leak Squad)',
    ground_truth_finding: 'CONFIRMED_LEAK',
    action_taken: 'Pinhole pipe leak repaired with mechanical repair clamp.',
    notes: 'Electrochemical pipe corrosion under low pH soil conditions.',
    batched_for_retraining: false,
  },
  {
    inspection_id: 'INSP-20261008-011',
    alert_id: 'ALT-03',
    node_id: 'J_2200',
    dma_id: 'DMA 02',
    dispatch_time: '2026-10-08T07:45:00Z',
    inspection_time: '2026-10-08T09:30:00Z',
    assigned_officer: 'Officer S. Jayasinghe',
    ground_truth_finding: 'CONFIRMED_BYPASS',
    action_taken: 'Unauthorized commercial car detailer bypass dismantled.',
    notes: 'Flexible pressure hose buried 20cm below turf line.',
    batched_for_retraining: false,
  },
  {
    inspection_id: 'INSP-20261007-010',
    alert_id: 'ALT-01',
    node_id: 'J_100',
    dma_id: 'DMA 01',
    dispatch_time: '2026-10-07T11:00:00Z',
    inspection_time: '2026-10-07T14:00:00Z',
    assigned_officer: 'Eng. K. Perera (Team 3)',
    ground_truth_finding: 'CONFIRMED_BYPASS',
    action_taken: 'Tampered water meter bypass confiscated; legal filing initiated.',
    notes: 'Lead seal broken and auxiliary pipe attached directly to inlet coupling.',
    batched_for_retraining: true,
  },
];

export async function getAlerts(filters?: AlertFilters): Promise<Alert[]> {
  if (IS_USE_MOCK) {
    await simulateLatency(150);
    let result = [...alertsState];

    if (filters) {
      if (filters.status) {
        result = result.filter((a) => a.status === filters.status);
      }
      if (filters.severity) {
        result = result.filter((a) => a.severity === filters.severity);
      }
      if (filters.zoneId) {
        result = result.filter((a) => a.zoneId.toLowerCase() === filters.zoneId!.toLowerCase());
      }
      if (filters.classification) {
        result = result.filter((a) => a.classification === filters.classification);
      }
      if (filters.search) {
        const query = filters.search.toLowerCase();
        result = result.filter(
          (a) =>
            a.id.toLowerCase().includes(query) ||
            a.zoneName.toLowerCase().includes(query) ||
            a.classification.toLowerCase().includes(query) ||
            (a.assignedTo && a.assignedTo.toLowerCase().includes(query))
        );
      }
    }
    return result;
  }

  try {
    const params = new URLSearchParams();
    if (filters?.status) params.append('status', filters.status);
    if (filters?.severity) params.append('severity', filters.severity);
    if (filters?.zoneId) params.append('zone_id', filters.zoneId);
    if (filters?.classification) params.append('classification', filters.classification);
    if (filters?.search) params.append('search', filters.search);

    const queryString = params.toString() ? `?${params.toString()}` : '';
    return await apiClient.get<Alert[]>(`/api/v1/alerts${queryString}`);
  } catch (err) {
    console.warn('Live API unavailable for getAlerts(), falling back to mock:', err);
    return [...alertsState];
  }
}

export async function getAlertById(id: string): Promise<Alert | undefined> {
  if (IS_USE_MOCK) {
    await simulateLatency(150);
    return alertsState.find(
      (a) => a.id.toLowerCase() === id.toLowerCase() || a.id.replace('-', '').toLowerCase() === id.replace('-', '').toLowerCase()
    );
  }

  try {
    return await apiClient.get<Alert>(`/api/v1/alerts/${id}`);
  } catch (err) {
    console.warn(`Live API unavailable for getAlertById(${id}), falling back to mock:`, err);
    return alertsState.find((a) => a.id.toLowerCase() === id.toLowerCase());
  }
}

export interface InvestigationUpdatePayload extends Partial<Alert> {
  ground_truth_finding?: import('../types').GroundTruthFinding;
  action_taken?: string;
  node_id?: string;
  dma_id?: string;
}

export async function updateInvestigation(id: string, payload: InvestigationUpdatePayload): Promise<Alert> {
  // Update local memory state
  const index = alertsState.findIndex((a) => a.id.toLowerCase() === id.toLowerCase());
  if (index !== -1) {
    alertsState[index] = {
      ...alertsState[index],
      ...payload,
    };
  }

  const normStatus = (payload.status || '').toLowerCase();
  const targetAlert = index !== -1 ? alertsState[index] : null;
  const groundTruth =
    payload.ground_truth_finding ||
    (normStatus === 'confirmed'
      ? (targetAlert?.classification === 'leak' ? 'CONFIRMED_LEAK' : 'CONFIRMED_BYPASS')
      : 'FALSE_ALARM_OPERATIONAL');

  const action =
    payload.action_taken ||
    (normStatus === 'confirmed'
      ? 'Illegal commercial bypass disconnected and confiscated; NWSDB penalty notice issued.'
      : 'Transient hydraulic pressure surge verified; baseline recalibrated.');

  if (IS_USE_MOCK) {
    await simulateLatency(150);
    if (index === -1) {
      throw new Error(`Alert with id ${id} not found`);
    }

    // If status is confirmed or rejected, trigger mock audit ledger entry
    if (normStatus === 'confirmed' || normStatus === 'rejected') {
      try {
        await recordAuditInspection({
          alert_id: id,
          node_id: payload.node_id || (targetAlert?.zoneId === 'zone-04' ? 'J_100' : 'J_500'),
          dma_id: payload.dma_id || (targetAlert?.zoneName.includes('DMA 02') ? 'DMA 02' : 'DMA 01'),
          ground_truth_finding: groundTruth,
          action_taken: action,
          assigned_officer: payload.assignedTo || 'Eng. K. Perera (Team 3)',
          notes: payload.notes || '',
        });
      } catch (auditErr) {
        console.warn('Failed to post to audit ledger via updateInvestigation (mock):', auditErr);
      }
    }

    return { ...alertsState[index] };
  }

  try {
    const fullPayload = {
      ...payload,
      ground_truth_finding: groundTruth,
      action_taken: action,
      node_id: payload.node_id || (targetAlert?.zoneId === 'zone-04' ? 'J_100' : 'J_500'),
      dma_id: payload.dma_id || (targetAlert?.zoneName.includes('DMA 02') ? 'DMA 02' : 'DMA 01'),
    };
    return await apiClient.patch<Alert>(`/api/v1/alerts/${id}/investigation`, fullPayload);
  } catch (err) {
    console.warn(`Live API unavailable for updateInvestigation(${id}), mutating mock state:`, err);
    if (index !== -1) {
      return { ...alertsState[index] };
    }
    throw err;
  }
}

export async function getInspectionMetrics(): Promise<InspectionOperationalMetrics> {
  if (IS_USE_MOCK) {
    await simulateLatency(120);
    return { ...mockOperationalMetrics };
  }

  try {
    return await apiClient.get<InspectionOperationalMetrics>('/api/v1/inspections/metrics');
  } catch (err) {
    console.warn('Live API unavailable for getInspectionMetrics(), falling back to mock:', err);
    return { ...mockOperationalMetrics };
  }
}

export async function getInspectionLedger(limit: number = 50): Promise<FieldInspectionAuditRecord[]> {
  if (IS_USE_MOCK) {
    await simulateLatency(120);
    return [...mockLedgerState].slice(0, limit);
  }

  try {
    return await apiClient.get<FieldInspectionAuditRecord[]>(`/api/v1/inspections/ledger?limit=${limit}`);
  } catch (err) {
    console.warn('Live API unavailable for getInspectionLedger(), falling back to mock:', err);
    return [...mockLedgerState].slice(0, limit);
  }
}

export async function recordAuditInspection(
  payload: Partial<FieldInspectionAuditRecord>
): Promise<any> {
  // Update mock stats
  const finding = payload.ground_truth_finding || 'CONFIRMED_BYPASS';
  const newRec: FieldInspectionAuditRecord = {
    inspection_id: `INSP-${Date.now() % 100000}`,
    alert_id: payload.alert_id || 'ALT-01',
    node_id: payload.node_id || 'J_100',
    dma_id: payload.dma_id || 'DMA 01',
    dispatch_time: payload.dispatch_time || new Date(Date.now() - 3600000).toISOString(),
    inspection_time: payload.inspection_time || new Date().toISOString(),
    assigned_officer: payload.assigned_officer || 'Eng. K. Perera (Team 3)',
    ground_truth_finding: finding,
    action_taken: payload.action_taken || 'Field inspection action recorded.',
    notes: payload.notes || '',
    batched_for_retraining: false,
  };

  mockLedgerState.unshift(newRec);
  mockOperationalMetrics.total_inspections += 1;
  if (finding === 'CONFIRMED_BYPASS') {
    mockOperationalMetrics.confirmed_bypass_count += 1;
  } else if (finding === 'CONFIRMED_LEAK') {
    mockOperationalMetrics.confirmed_leak_count += 1;
  } else {
    mockOperationalMetrics.false_alarm_count += 1;
  }
  mockOperationalMetrics.unbatched_inspections_count += 1;

  const total = mockOperationalMetrics.total_inspections;
  mockOperationalMetrics.ppv = round(mockOperationalMetrics.confirmed_bypass_count / total, 4);
  mockOperationalMetrics.ppv_percentage = round(mockOperationalMetrics.ppv * 100, 1);
  mockOperationalMetrics.false_alarm_rate = round(mockOperationalMetrics.false_alarm_count / total, 4);
  mockOperationalMetrics.false_alarm_percentage = round(mockOperationalMetrics.false_alarm_rate * 100, 1);

  if (mockOperationalMetrics.unbatched_inspections_count >= 10) {
    mockOperationalMetrics.candidate_batch_ready = true;
  }

  if (IS_USE_MOCK) {
    await simulateLatency(150);
    return { status: 'success', record: newRec, metrics: mockOperationalMetrics };
  }

  try {
    return await apiClient.post<any>('/api/v1/inspections/ledger', payload);
  } catch (err) {
    console.warn('Live API unavailable for recordAuditInspection(), falling back to mock:', err);
    return { status: 'success', record: newRec, metrics: mockOperationalMetrics };
  }
}

function round(val: number, decimals: number = 2): number {
  const factor = Math.pow(10, decimals);
  return Math.round(val * factor) / factor;
}

