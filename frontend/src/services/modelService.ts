/**
 * frontend/src/services/modelService.ts
 * AI Model inference, performance metrics, and digital twin simulation analysis service.
 */

import type {
  ModelPerformanceMetrics,
  DigitalTwinScenarioMatch,
  AIModelAnalysis,
  FeaturePipelineStatus,
} from '../types';
import {
  mockModelPerformance,
  zone04ScenarioMatches,
  zone04AIModelAnalysis,
  mockFeaturePipelineStatus,
} from '../data/mockData';
import { apiClient, IS_USE_MOCK, simulateLatency } from './apiClient';

export interface DigitalTwinAnalysisResult {
  scenarios: DigitalTwinScenarioMatch[];
  aiAnalysis: AIModelAnalysis;
}

export async function getModelPerformance(): Promise<ModelPerformanceMetrics> {
  if (IS_USE_MOCK) {
    await simulateLatency(150);
    return { ...mockModelPerformance };
  }

  try {
    return await apiClient.get<ModelPerformanceMetrics>('/api/v1/models/performance');
  } catch (err) {
    console.warn('Live API unavailable for getModelPerformance(), falling back to mock:', err);
    return { ...mockModelPerformance };
  }
}

export async function getDigitalTwinAnalysis(zoneId: string): Promise<DigitalTwinAnalysisResult> {
  if (IS_USE_MOCK) {
    await simulateLatency(150);
    return {
      scenarios: [...zone04ScenarioMatches],
      aiAnalysis: { ...zone04AIModelAnalysis },
    };
  }

  try {
    return await apiClient.get<DigitalTwinAnalysisResult>(`/api/v1/models/digital-twin/${zoneId}`);
  } catch (err) {
    console.warn(`Live API unavailable for getDigitalTwinAnalysis(${zoneId}), falling back to mock:`, err);
    return {
      scenarios: [...zone04ScenarioMatches],
      aiAnalysis: { ...zone04AIModelAnalysis },
    };
  }
}

export async function getFeaturePipelineStatus(): Promise<FeaturePipelineStatus> {
  if (IS_USE_MOCK) {
    await simulateLatency(150);
    return { ...mockFeaturePipelineStatus };
  }

  try {
    return await apiClient.get<FeaturePipelineStatus>('/api/v1/telemetry/pipeline-status');
  } catch (err) {
    console.warn('Live API unavailable for getFeaturePipelineStatus(), falling back to mock:', err);
    return { ...mockFeaturePipelineStatus };
  }
}
