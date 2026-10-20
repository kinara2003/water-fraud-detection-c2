import React, { useState } from 'react';
import {
  CheckCircle2,
  Cpu,
  ArrowRight,
  ShieldCheck,
  Gauge,
  Waves,
  RefreshCw,
  Sparkles,
  Clock,
} from 'lucide-react';

export const DataModelMonitoring: React.FC = () => {
  const [lastRefreshed, setLastRefreshed] = useState<string>('Just now');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleManualRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => {
      setLastRefreshed('Just now');
      setIsRefreshing(false);
    }, 600);
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
            System Health & AI Decision Engine
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Operational status of Kaduwela physical digital twin and two-stage fraud classification models.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <div className="inline-flex items-center space-x-2 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-800">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>All Systems Nominal</span>
          </div>

          <button
            onClick={handleManualRefresh}
            title="Refresh system status"
            className="p-2 rounded-xl bg-white border border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50 shadow-2xs transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* TOP SECTION — 3 System Health Indicators (Green checkmarks) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Indicator 1: Digital Twin */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs hover:border-slate-300 transition-all flex items-start space-x-4">
          <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 shrink-0">
            <CheckCircle2 className="w-6 h-6" />
          </div>

          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Digital Twin
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                Synchronized
              </span>
            </div>
            <h3 className="text-base font-extrabold text-slate-900">
              Kaduwela Model Synced
            </h3>
            <p className="text-xs text-slate-500">
              3,300+ nodes active
            </p>
          </div>
        </div>

        {/* Indicator 2: AI Models */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs hover:border-slate-300 transition-all flex items-start space-x-4">
          <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 shrink-0">
            <CheckCircle2 className="w-6 h-6" />
          </div>

          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                AI Models
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                Stage 1 & 2
              </span>
            </div>
            <h3 className="text-base font-extrabold text-slate-900">
              Stage 1 & Stage 2 Online
            </h3>
            <p className="text-xs text-slate-500">
              Trained on Kaduwela IWS scenarios
            </p>
          </div>
        </div>

        {/* Indicator 3: Field Telemetry */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs hover:border-slate-300 transition-all flex items-start space-x-4">
          <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 shrink-0">
            <CheckCircle2 className="w-6 h-6" />
          </div>

          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Field Telemetry
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                SCADA Active
              </span>
            </div>
            <h3 className="text-base font-extrabold text-slate-900">
              Connected
            </h3>
            <p className="text-xs text-slate-500">
              Receiving 15-min pressure updates
            </p>
          </div>
        </div>
      </div>

      {/* HOW THE AI DECIDES (A simple 3-step visual flow card) */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-2 border-b border-slate-100">
          <div>
            <h2 className="text-base font-bold text-slate-900 flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-blue-600" />
              <span>How the AI Decides</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Three-step automated pipeline turning raw pressure telemetry into verified field inspection work orders.
            </p>
          </div>

          <div className="flex items-center space-x-2 text-xs font-mono text-slate-400">
            <span>Last audit: {lastRefreshed}</span>
          </div>
        </div>

        {/* 3-Step Visual Flow Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Step 1: Pressure Reading Arrives */}
          <div className="p-5 rounded-xl border border-slate-200 bg-slate-50/60 hover:bg-slate-50 transition-all flex flex-col justify-between space-y-4 relative group">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="px-2.5 py-1 rounded-md text-[10px] font-extrabold uppercase tracking-wider bg-blue-100 text-blue-800">
                  Step 1
                </span>
                <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600">
                  <Waves className="w-4 h-4" />
                </div>
              </div>

              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Pressure Reading Arrives
                </h3>
                <div className="mt-1.5 flex items-center text-xs font-semibold text-blue-700 gap-1.5">
                  <ArrowRight className="w-3.5 h-3.5 shrink-0" />
                  <span>Compares actual reading with digital twin baseline.</span>
                </div>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                Physical edge transducers measure pipeline head every 15 minutes. The EPANET digital twin calculates expected baseline head for the current time-of-day.
              </p>
            </div>

            <div className="pt-3 border-t border-slate-200 text-[11px] text-slate-400 font-mono">
              Output: Pressure Gap (ΔP in meters)
            </div>
          </div>

          {/* Step 2: Unusual Drop Detection */}
          <div className="p-5 rounded-xl border border-slate-200 bg-slate-50/60 hover:bg-slate-50 transition-all flex flex-col justify-between space-y-4 relative group">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="px-2.5 py-1 rounded-md text-[10px] font-extrabold uppercase tracking-wider bg-amber-100 text-amber-800">
                  Step 2
                </span>
                <div className="w-8 h-8 rounded-lg bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600">
                  <Gauge className="w-4 h-4" />
                </div>
              </div>

              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Unusual Drop Detection
                </h3>
                <div className="mt-1.5 flex items-center text-xs font-semibold text-amber-800 gap-1.5">
                  <ArrowRight className="w-3.5 h-3.5 shrink-0" />
                  <span>Isolation Forest checks if drop exceeds normal variation.</span>
                </div>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                Stage 1 anomaly screening filters out normal morning supply surges and consumer consumption, flagging statistical outliers as potential incidents.
              </p>
            </div>

            <div className="pt-3 border-t border-slate-200 text-[11px] text-slate-400 font-mono">
              Output: Unusual Drop Detection (Yes/No)
            </div>
          </div>

          {/* Step 3: Cause Identification */}
          <div className="p-5 rounded-xl border border-slate-200 bg-slate-50/60 hover:bg-slate-50 transition-all flex flex-col justify-between space-y-4 relative group">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="px-2.5 py-1 rounded-md text-[10px] font-extrabold uppercase tracking-wider bg-emerald-100 text-emerald-800">
                  Step 3
                </span>
                <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600">
                  <Cpu className="w-4 h-4" />
                </div>
              </div>

              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Cause Identification
                </h3>
                <div className="mt-1.5 flex items-center text-xs font-semibold text-emerald-800 gap-1.5">
                  <ArrowRight className="w-3.5 h-3.5 shrink-0" />
                  <span>Random Forest determines whether it is an illegal draw or pipe burst.</span>
                </div>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                Stage 2 classifier analyzes temporal recurrence, spatial gradients, and acoustic leak loggers to confirm unmetered bypass extraction and trigger crew dispatch.
              </p>
            </div>

            <div className="pt-3 border-t border-slate-200 text-[11px] text-slate-400 font-mono">
              Output: Probable Reason & Suspicion Level
            </div>
          </div>
        </div>
      </div>

      {/* PERFORMANCE SUMMARY CARD (Plain terms) */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-5">
        <div className="pb-2 border-b border-slate-100">
          <h2 className="text-base font-bold text-slate-900 flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>Performance Summary</span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Empirical validation results demonstrated across physical and synthetic Kaduwela test cases.
          </p>
        </div>

        {/* 3 Plain-Term Benchmark Highlights */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Metric 1: Bypass Detection Accuracy */}
          <div className="p-5 rounded-xl border border-slate-200/90 bg-slate-50 flex flex-col justify-between space-y-2">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wide">
              Bypass Detection Accuracy
            </span>
            <div className="text-3xl font-black text-emerald-600 font-mono tracking-tight">
              94.2%
            </div>
            <p className="text-xs text-slate-600">
              Evaluated on simulated Kaduwela scenarios
            </p>
          </div>

          {/* Metric 2: False Alarm Suppression */}
          <div className="p-5 rounded-xl border border-slate-200/90 bg-slate-50 flex flex-col justify-between space-y-2">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wide">
              False Alarm Suppression
            </span>
            <div className="text-xl font-black text-blue-600 font-mono tracking-tight flex items-center space-x-1.5">
              <span>Refill Surge Filter Active</span>
            </div>
            <p className="text-xs text-slate-600">
              Morning refill surges correctly filtered out
            </p>
          </div>

          {/* Metric 3: Average Decision Time */}
          <div className="p-5 rounded-xl border border-slate-200/90 bg-slate-50 flex flex-col justify-between space-y-2">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wide">
              Average Decision Time
            </span>
            <div className="text-3xl font-black text-slate-900 font-mono tracking-tight">
              Under 0.05 seconds
            </div>
            <p className="text-xs text-slate-600">
              Real-time inference speed per reading (<span className="font-mono font-bold">42 ms</span>)
            </p>
          </div>
        </div>

        {/* Plain Language Regulatory Footer Note */}
        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 text-xs text-slate-600 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center space-x-2">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>
              <strong>Evaluation Standard:</strong> Validated against 24-hour diurnal pressure cycles under Intermittent Water Supply (IWS).
            </span>
          </div>
          <div className="flex items-center space-x-1.5 font-medium text-emerald-700">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Component 2 AI Architecture Certified</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DataModelMonitoring;
