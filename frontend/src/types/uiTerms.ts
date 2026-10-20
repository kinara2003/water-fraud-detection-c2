/**
 * frontend/src/types/uiTerms.ts
 * Plain-language UI terminology and definitions for NWSDB WaterGuard.
 * Replaces dense hydraulic/statistical engineering jargon with clear, operator-friendly terms:
 *
 * 1. 'Hydraulic Residual (ΔP)'             -> 'Pressure Gap' (Unit: meters)
 * 2. 'Baseline Reference Head'            -> 'Expected Pressure' (Unit: meters)
 * 3. 'Transduced Telemetry Head'          -> 'Actual Observed Pressure' (Unit: meters)
 * 4. 'Stage 1 Anomaly Confidence'         -> 'Unusual Drop Detection' (Yes/No)
 * 5. 'Stage 2 Root-Cause Classification'  -> 'Probable Reason' (Unmetered Withdrawal / Pipe Burst / Normal Supply Opening)
 * 6. 'Fraud Risk Index'                   -> 'Suspicion Level' (0–100%)
 */

export const DISCLAIMER_TEXT =
  'National Water Supply & Drainage Board — Kaduwela Decision Support Tool. Identifies network sectors requiring physical inspection. Does not accuse individual households.';

export interface UITermDefinition {
  label: string;
  legacy: string;
  unit?: string;
  unitShort?: string;
  description: string;
}

export const UI_TERMS = {
  pressureGap: {
    label: 'Pressure Gap',
    legacy: 'Hydraulic Residual (ΔP)',
    unit: 'meters',
    unitShort: 'm',
    description: 'The difference between the expected digital twin pressure and the actual measured pressure.',
  },
  expectedPressure: {
    label: 'Expected Pressure',
    legacy: 'Baseline Reference Head',
    unit: 'meters',
    unitShort: 'm',
    description: 'Normal hydraulic pressure head simulated by the EPANET digital twin for this time of day.',
  },
  actualObservedPressure: {
    label: 'Actual Observed Pressure',
    legacy: 'Transduced Telemetry Head',
    unit: 'meters',
    unitShort: 'm',
    description: 'Real-time water pressure measured at the physical pipeline sensor.',
  },
  unusualDropDetection: {
    label: 'Unusual Drop Detection',
    legacy: 'Stage 1 Anomaly Confidence',
    unit: 'Yes/No',
    unitShort: '',
    description: 'Indicates whether the Stage 1 screening filter detected an abnormal sudden pressure drop.',
  },
  probableReason: {
    label: 'Probable Reason',
    legacy: 'Stage 2 Root-Cause Classification',
    options: {
      partial_bypass: 'Unmetered Withdrawal',
      illegal_tap: 'Unmetered Withdrawal',
      theft: 'Unmetered Withdrawal',
      leak: 'Pipe Burst',
      burst: 'Pipe Burst',
      normal: 'Normal Supply Opening',
      operational_event: 'Normal Supply Opening',
    },
    description: 'Machine learning assessment identifying the most likely physical cause of the pressure deficit.',
  },
  suspicionLevel: {
    label: 'Suspicion Level',
    legacy: 'Fraud Risk Index',
    unit: '0–100%',
    unitShort: '%',
    description: 'Prioritization score indicating how strongly evidence points to unauthorized water withdrawal.',
  },
} as const;

/**
 * Translates machine learning failure code into plain language probable reason.
 */
export function getProbableReasonLabel(cause: string | undefined | null): string {
  if (!cause) return 'Normal Supply Opening';
  const c = cause.toLowerCase();
  if (c.includes('bypass') || c.includes('tap') || c.includes('theft')) {
    return 'Unmetered Withdrawal';
  }
  if (c.includes('leak') || c.includes('burst')) {
    return 'Pipe Burst';
  }
  return 'Normal Supply Opening';
}

/**
 * Formats unusual drop boolean into operator-friendly Yes/No.
 */
export function formatUnusualDrop(isAnomaly: boolean | undefined | null): 'Yes' | 'No' {
  return isAnomaly ? 'Yes' : 'No';
}

/**
 * Returns color tokens and status badge metadata for suspicion levels.
 */
export function getSuspicionTier(score: number): {
  tier: 'safe' | 'caution' | 'suspicious';
  label: string;
  badgeBg: string;
  badgeText: string;
  badgeBorder: string;
  barColor: string;
} {
  if (score >= 70) {
    return {
      tier: 'suspicious',
      label: 'High Suspicion (Action Needed)',
      badgeBg: 'bg-rose-50',
      badgeText: 'text-rose-700',
      badgeBorder: 'border-rose-200',
      barColor: '#E11D48',
    };
  }
  if (score >= 40) {
    return {
      tier: 'caution',
      label: 'Caution (Refill Surge / Monitor)',
      badgeBg: 'bg-amber-50',
      badgeText: 'text-amber-700',
      badgeBorder: 'border-amber-200',
      barColor: '#D97706',
    };
  }
  return {
    tier: 'safe',
    label: 'Normal (Safe)',
    badgeBg: 'bg-emerald-50',
    badgeText: 'text-emerald-700',
    badgeBorder: 'border-emerald-200',
    barColor: '#059669',
  };
}
