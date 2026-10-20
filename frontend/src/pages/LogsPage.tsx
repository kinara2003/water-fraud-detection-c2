import React, { useEffect, useState, useCallback } from 'react';
import { FileText, RefreshCw, CheckCircle, Database, Sparkles, AlertCircle } from 'lucide-react';
import { fetchInspectionLogs, triggerModelRetrain } from '../services';
import type { RetrainResponse } from '../services';
import type { InspectionLog } from '../types';
import { Badge } from '../components/common';
import { useLivePolling } from '../hooks';

export const LogsPage: React.FC = () => {
  const [logs, setLogs] = useState<InspectionLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [retraining, setRetraining] = useState(false);
  const [retrainResult, setRetrainResult] = useState<RetrainResponse | null>(null);

  const fetchLogs = useCallback(() => fetchInspectionLogs(), []);
  const { data: polledLogs } = useLivePolling<InspectionLog[]>(fetchLogs, 3000);

  useEffect(() => {
    if (polledLogs) {
      setLogs(polledLogs);
      setLoading(false);
    }
  }, [polledLogs]);

  const handleRetrain = async () => {
    setRetraining(true);
    setRetrainResult(null);
    try {
      const res = await triggerModelRetrain();
      setRetrainResult(res);
    } catch {
      setRetrainResult({
        status: 'error',
        message: 'Retraining failed. Please ensure the backend is available.',
      });
    } finally {
      setRetraining(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#008DDA]"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header & Retrain Action */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between bg-[#0B192C] p-5 rounded-xl border border-slate-800 shadow-md">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center">
            <FileText className="w-5 h-5 mr-2 text-[#008DDA]" />
            Field Verification Logs & Model Retraining
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Ground-truth inspection feedback collected from physical site audits to prevent classification drift
          </p>
        </div>
        <div className="mt-4 md:mt-0 flex items-center space-x-3">
          <button
            onClick={handleRetrain}
            disabled={retraining}
            className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-[#008DDA] to-[#1E3E62] hover:from-[#41C9E2] hover:to-[#008DDA] text-white font-medium text-sm rounded-lg shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {retraining ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Retraining in progress...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>Retrain Model with Field Verifications</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Retraining Feedback Notification / Toast Banner */}
      {retrainResult && (
        <div
          className={`p-4 rounded-xl border flex items-start space-x-3 transition-all ${
            retrainResult.status === 'error'
              ? 'bg-rose-950/40 border-rose-800 text-rose-200'
              : 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
          }`}
        >
          {retrainResult.status === 'error' ? (
            <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          ) : (
            <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          )}
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-white">
              {retrainResult.status === 'error' ? 'Retraining Failed' : 'Model Retrained Successfully'}
            </h4>
            <p className="text-xs mt-0.5">{retrainResult.message}</p>
            {retrainResult.new_f1 !== undefined && (
              <div className="mt-2 flex flex-wrap items-center gap-3 text-xs font-mono">
                <span className="bg-slate-900/60 px-2 py-1 rounded border border-slate-700/60">
                  Samples Added: {retrainResult.samples_added}
                </span>
                <span className="bg-slate-900/60 px-2 py-1 rounded border border-slate-700/60">
                  Old F1: {retrainResult.old_f1}
                </span>
                <span className="bg-slate-900/60 px-2 py-1 rounded border border-slate-700/60 text-emerald-300 font-bold">
                  New F1: {retrainResult.new_f1}
                </span>
                {retrainResult.delta !== undefined && (
                  <span className="bg-slate-900/60 px-2 py-1 rounded border border-slate-700/60 text-emerald-400">
                    Δ (+{(retrainResult.delta * 100).toFixed(2)}%)
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Verification Logs Table */}
      <div className="bg-[#0B192C] rounded-xl border border-slate-800 p-5 shadow-lg overflow-hidden">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-white flex items-center">
            <Database className="w-4 h-4 mr-2 text-[#41C9E2]" />
            Inspection Audit Trails (data/processed/inspection_logs.csv)
          </h2>
          <span className="text-xs text-slate-400 font-mono">{logs.length} logged records</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-[#1E3E62]/50 text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Log ID</th>
                <th className="py-3 px-4">Node Target</th>
                <th className="py-3 px-4">Actual Finding</th>
                <th className="py-3 px-4">Audit Timestamp</th>
                <th className="py-3 px-4">Field Notes</th>
                <th className="py-3 px-4">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {logs.map((log) => (
                <tr key={log.log_id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-3 px-4 font-mono font-medium text-white">{log.log_id}</td>
                  <td className="py-3 px-4 font-mono font-semibold text-[#41C9E2]">{log.node_id}</td>
                  <td className="py-3 px-4">
                    <Badge variant={log.actual_finding === 'partial_bypass' ? 'danger' : 'normal'}>
                      {log.actual_finding.replace('_', ' ')}
                    </Badge>
                  </td>
                  <td className="py-3 px-4 text-xs font-mono text-slate-400">{log.timestamp}</td>
                  <td className="py-3 px-4 text-xs text-slate-300 max-w-md truncate">{log.notes}</td>
                  <td className="py-3 px-4">
                    <Badge variant={log.processed ? 'normal' : 'warning'}>
                      {log.processed ? 'Incorporated' : 'Pending Retrain'}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
