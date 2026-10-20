/**
 * frontend/src/services/zoneService.ts
 * Zone telemetry and pressure monitoring service with live backend connectivity
 * and seamless fallback to mock data.
 */

import type { Zone, PressureReading } from '../types';
import { initialZones, zone04HourlyReadings } from '../data/mockData';
import { apiClient, simulateLatency } from './apiClient';

function getFallbackPressureHistory(id: string): PressureReading[] {
  if (id === 'zone-04' || id.toLowerCase().includes('04')) {
    return [...zone04HourlyReadings];
  }
  // Generate normalized baseline readings for other zones
  const zone = initialZones.find((z) => z.id === id);
  const baseExpected = zone ? zone.expectedPressure : 21.0;
  const baseActual = zone ? zone.actualPressure : 21.0;

  return zone04HourlyReadings.map((reading) => {
    const hour = parseInt(reading.timestamp.split(':')[0], 10);
    const isSupplyWindow = hour >= 6 && hour <= 18;
    const expected = isSupplyWindow ? baseExpected : 0.0;
    const actual = isSupplyWindow ? baseActual : 0.0;
    return {
      timestamp: reading.timestamp,
      expectedPressure: expected,
      actualPressure: actual,
      residual: parseFloat((actual - expected).toFixed(2)),
      isAbnormal: Math.abs(actual - expected) > 2.0,
    };
  });
}

export async function getZones(): Promise<Zone[]> {
  if (apiClient.useMock) {
    await simulateLatency(150);
    return [...initialZones];
  }

  try {
    return await apiClient.get<Zone[]>('/api/v1/zones', initialZones);
  } catch (err) {
    console.warn('[zoneService] Live API unavailable for getZones(), falling back to mock:', err);
    return [...initialZones];
  }
}

export async function getZoneById(id: string): Promise<Zone | undefined> {
  const fallback = initialZones.find(
    (z) => z.id.toLowerCase() === id.toLowerCase() || z.name.toLowerCase().includes(id.toLowerCase())
  );

  if (apiClient.useMock) {
    await simulateLatency(150);
    return fallback;
  }

  try {
    return await apiClient.get<Zone>(`/api/v1/zones/${id}`, fallback);
  } catch (err) {
    console.warn(`[zoneService] Live API unavailable for getZoneById(${id}), falling back to mock:`, err);
    return fallback;
  }
}

export async function getZonePressureHistory(id: string, timeRange = '24h'): Promise<PressureReading[]> {
  const fallback = getFallbackPressureHistory(id);

  if (apiClient.useMock) {
    await simulateLatency(150);
    return fallback;
  }

  try {
    return await apiClient.get<PressureReading[]>(
      `/api/v1/pressure/${id}?range=${encodeURIComponent(timeRange)}`,
      fallback
    );
  } catch (err) {
    console.warn(`[zoneService] Live API unavailable for getZonePressureHistory(${id}), falling back to mock:`, err);
    return fallback;
  }
}
