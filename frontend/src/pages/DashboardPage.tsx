import React, { useEffect, useState } from 'react';
import { Activity, AlertTriangle, ShieldCheck, Waves } from 'lucide-react';
import { fetchDmaStatus } from '../services';
import type { DmaStatusResponse } from '../types';
import { StatCard } from '../components/cards';
import { PressureChart } from '../components/charts';
import { Badge } from '../components/common';

export const DashboardPage: React.FC = () => {
  const [data, setData] = useState<DmaStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDmaStatus().then((res) => {
      setData(res);
      setLoading(false);
    });
  }, []);

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#008DDA]"></div>
      </div>
    );
  }

  const { supply_window, dma_summary, nodes, timeseries } = data;

  return (
    <div className="space-y-6">
      {/* Top Banner / Supply Window */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between bg-[#0B192C] p-5 rounded-xl border border-slate-800 shadow-md">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Kaduwela DMA Real-Time Fraud Surveillance</h1>
          <p className="text-xs text-slate-400 mt-1 font-mono">Last Synchronized: {data.timestamp}</p>
        </div>
        <div className="mt-3 md:mt-0 flex items-center space-x-3">
          <Badge variant="info">
            <Waves className="w-3.5 h-3.5 mr-1" />
            Supply: {supply_window.state} ({supply_window.window_start} - {supply_window.window_end})
          </Badge>
          {supply_window.refill_transient_active && (
            <Badge variant="warning">Refill Transient Suppression Active</Badge>
          )}
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="DMA 01 Status"
          value={dma_summary.dma_01.status}
          subtitle={`Unmetered loss: ${dma_summary.dma_01.unmetered_loss_lps} LPS (${(dma_summary.dma_01.unmetered_loss_lps * 3.6).toFixed(2)} m³/h)`}
          status={dma_summary.dma_01.active_theft_count > 0 ? 'danger' : 'normal'}
          icon={<AlertTriangle className="w-5 h-5 text-rose-400" />}
        />
        <StatCard
          title="DMA 02 Status"
          value={dma_summary.dma_02.status}
          subtitle={`Unmetered loss: ${dma_summary.dma_02.unmetered_loss_lps} LPS`}
          status={dma_summary.dma_02.active_theft_count > 0 ? 'danger' : 'normal'}
          icon={<ShieldCheck className="w-5 h-5 text-emerald-400" />}
        />
        <StatCard
          title="Highest Risk Sector"
          value={`${dma_summary.highest_risk_sector.node_id} (${dma_summary.highest_risk_sector.peak_risk_score}%)`}
          subtitle={`Zone: ${dma_summary.highest_risk_sector.dma_id} • Priority: P1`}
          status="danger"
          icon={<Activity className="w-5 h-5 text-[#008DDA]" />}
        />
        <StatCard
          title="Monitored Junctions"
          value={`${nodes.length} Nodes`}
          subtitle="6 Critical SCADA telemetry pressure sensors"
          status="info"
        />
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {timeseries.nodes_data['J_100'] && (
          <PressureChart
            nodeId="J_100 (DMA 01 - Under Bypass Theft)"
            labels={timeseries.labels}
            expected={timeseries.nodes_data['J_100'].expected_pressure}
            actual={timeseries.nodes_data['J_100'].actual_pressure}
          />
        )}
        {timeseries.nodes_data['J_2200'] && (
          <PressureChart
            nodeId="J_2200 (DMA 02 - Baseline Control Reference)"
            labels={timeseries.labels}
            expected={timeseries.nodes_data['J_2200'].expected_pressure}
            actual={timeseries.nodes_data['J_2200'].actual_pressure}
          />
        )}
      </div>

      {/* Monitored Nodes Table */}
      <div className="bg-[#0B192C] rounded-xl border border-slate-800 p-5 shadow-lg overflow-hidden">
        <h2 className="text-base font-semibold text-white mb-4">Monitored Junctions Status & Triage</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-[#1E3E62]/50 text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-3 px-4">Junction</th>
                <th className="py-3 px-4">DMA</th>
                <th className="py-3 px-4">Risk Score</th>
                <th className="py-3 px-4">Actual (m)</th>
                <th className="py-3 px-4">Expected (m)</th>
                <th className="py-3 px-4">Residual (ΔP)</th>
                <th className="py-3 px-4">Classification</th>
                <th className="py-3 px-4">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {nodes.map((node) => {
                const isTheft = node.classification === 'partial_bypass';
                return (
                  <tr key={node.node_id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-mono font-medium text-white">{node.node_id}</td>
                    <td className="py-3 px-4">{node.dma_id}</td>
                    <td className="py-3 px-4 font-bold">
                      <span className={node.peak_risk_score >= 75 ? 'text-rose-400' : 'text-emerald-400'}>
                        {node.peak_risk_score.toFixed(2)}%
                      </span>
                    </td>
                    <td className="py-3 px-4">{node.current_actual_pressure.toFixed(2)}</td>
                    <td className="py-3 px-4">{node.current_expected_pressure.toFixed(2)}</td>
                    <td className="py-3 px-4 font-mono">
                      {node.current_residual > 1.5 ? (
                        <span className="text-rose-400 font-bold">-{node.current_residual.toFixed(2)}m</span>
                      ) : (
                        <span>{node.current_residual.toFixed(2)}m</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant={isTheft ? 'danger' : 'normal'}>{node.classification}</Badge>
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-400">{node.inspection_priority}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
