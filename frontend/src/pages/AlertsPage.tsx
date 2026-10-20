import React, { useEffect, useState } from 'react';
import { ShieldAlert, CheckCircle2, Clock, Mail, Globe, AlertTriangle } from 'lucide-react';
import { fetchAlertsHistory } from '../services';
import type { DispatchedAlert } from '../types';
import { Badge } from '../components/common';

export const AlertsPage: React.FC = () => {
  const [alerts, setAlerts] = useState<DispatchedAlert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAlertsHistory().then((data) => {
      setAlerts(data);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#008DDA]"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between bg-[#0B192C] p-5 rounded-xl border border-slate-800 shadow-md">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center">
            <ShieldAlert className="w-5 h-5 mr-2 text-rose-500" />
            Authority Alert Notification Dispatch
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time multi-channel escalation logs dispatched to NWSDB investigation units & municipal endpoints
          </p>
        </div>
        <div className="mt-3 md:mt-0 flex items-center space-x-2">
          <Badge variant="danger">
            {alerts.length} Total Incident{alerts.length !== 1 ? 's' : ''} Dispatched
          </Badge>
        </div>
      </div>

      {/* Dispatched Alerts Cards / List */}
      <div className="space-y-4">
        {alerts.length === 0 ? (
          <div className="bg-[#0B192C] rounded-xl border border-slate-800 p-8 text-center text-slate-400">
            No active alerts currently recorded.
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.alert_id}
              className="bg-[#0B192C] rounded-xl border border-slate-800 p-5 shadow-lg space-y-4 hover:border-slate-700 transition-colors"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800/80 gap-2">
                <div className="flex items-center space-x-3">
                  <span className="font-mono text-sm font-semibold text-white px-2.5 py-1 bg-[#1E3E62] rounded">
                    {alert.alert_id}
                  </span>
                  <Badge variant={alert.risk_score >= 80 ? 'danger' : 'warning'}>
                    Risk Score: {alert.risk_score.toFixed(1)}%
                  </Badge>
                  <span className="text-xs font-mono text-slate-400">
                    Target: <strong className="text-white">{alert.node_id}</strong> ({alert.dma_id})
                  </span>
                </div>
                <div className="flex items-center space-x-2 text-xs text-slate-400">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{new Date(alert.timestamp).toLocaleString()}</span>
                </div>
              </div>

              {/* Metrics & Probable Cause */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 bg-slate-900/60 p-3 rounded-lg border border-slate-800/50 text-xs">
                <div>
                  <span className="text-slate-400 block">Probable Cause</span>
                  <span className="font-semibold text-rose-400 uppercase tracking-wide">
                    {alert.probable_cause.replace('_', ' ')}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block">Observed vs Expected</span>
                  <span className="font-mono font-medium text-white">
                    {alert.actual_pressure !== undefined ? `${alert.actual_pressure}m` : 'N/A'} /{' '}
                    {alert.expected_pressure !== undefined ? `${alert.expected_pressure}m` : 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block">Residual Head Drop</span>
                  <span className="font-mono font-bold text-rose-400">
                    -{alert.residual_head_drop ?? '0.00'}m
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block">Field Priority</span>
                  <span className="font-semibold text-amber-400">{alert.inspection_priority}</span>
                </div>
              </div>

              {/* Evidence Breakdown */}
              <div>
                <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2 flex items-center">
                  <AlertTriangle className="w-3.5 h-3.5 mr-1 text-amber-400" />
                  Hydraulic & Spatial Evidence Breakdown
                </h4>
                <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                  {alert.evidence_list.map((item, idx) => (
                    <li
                      key={idx}
                      className="flex items-start space-x-2 text-slate-300 bg-slate-900/40 p-2 rounded border border-slate-800/40"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#008DDA] shrink-0 mt-0.5" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Dispatch Channels */}
              <div className="flex flex-wrap items-center gap-3 pt-2 text-xs text-slate-400 border-t border-slate-800/60">
                <div className="flex items-center space-x-1">
                  <Mail className="w-3.5 h-3.5 text-blue-400" />
                  <span>
                    Email: <code className="text-slate-300">{alert.recipient_email || 'Console Dispatch'}</code>
                  </span>
                </div>
                {alert.webhook_url && (
                  <div className="flex items-center space-x-1">
                    <Globe className="w-3.5 h-3.5 text-emerald-400" />
                    <span>
                      Webhook: <code className="text-slate-300">{alert.webhook_url}</code>
                    </span>
                  </div>
                )}
                <div className="ml-auto">
                  <Badge variant={alert.delivery_status === 'Sent' ? 'normal' : 'warning'}>
                    Status: {alert.delivery_status}
                  </Badge>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
