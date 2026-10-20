/**
 * frontend/src/services/integrationService.ts
 * Cross-component integration service for C1 (Acoustic Leak Detection),
 * C3 (Water Security Impact), and C4 (Contamination & Depressurization Risk).
 */

import type { ComponentIntegrationStates } from '../types';
import { zone04IntegrationStates } from '../data/mockData';
import { apiClient, IS_USE_MOCK, simulateLatency } from './apiClient';

export async function getCrossComponentIntegrations(zoneId: string): Promise<ComponentIntegrationStates> {
  if (IS_USE_MOCK) {
    await simulateLatency(150);
    // Return zone 04 states or adapted states based on requested zone
    if (zoneId === 'zone-04' || zoneId.toLowerCase().includes('04')) {
      return { ...zone04IntegrationStates };
    }

    return {
      c1LeakCrossCheck: {
        leakProbability: 0.05,
        statusText: 'Nominal acoustic baseline across all sector sensors.',
        impactOnFraud: 'No anomalous acoustic signature or fracture indicators detected.',
      },
      c3WaterSecurityImpact: {
        unexplainedLossVolumeLps: 0.0,
        waterSecurityIndexDelta: 0.0,
        shortageRiskIncreased: false,
      },
      c4ContaminationRisk: {
        depressurizationEventActive: false,
        intrusionSeverity: 'low',
      },
    };
  }

  try {
    return await apiClient.get<ComponentIntegrationStates>(`/api/v1/integrations/cross-component/${zoneId}`);
  } catch (err) {
    console.warn(`Live API unavailable for getCrossComponentIntegrations(${zoneId}), falling back to mock:`, err);
    return { ...zone04IntegrationStates };
  }
}
