import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Droplets,
  Gauge,
  Radio,
  RefreshCw,
  SlidersHorizontal,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceArea,
} from 'recharts';
import { fetchLiveMapState, useTelemetrySocket, type TelemetryMessage } from '../services';
import type { PressureReading, LiveMapStateResponse } from '../types';
import { zone04HourlyReadings } from '../data/mockData';
import { AdminAnomalyMap } from '../components/maps/AdminAnomalyMap';
import { useLivePolling } from '../hooks';

interface ZoneSchematicItem {
  id: string;
  name: string;
  dma: string;
  nodeId: string;
  pressure: number;
  status: 'safe' | 'flagged';
  statusLabel: string;
}

export const NetworkOverview: React.FC = () => {
  const navigate = useNavigate();

  // Zone Data state for the 6 monitored sectors across DMA 01 & DMA 02
  const [dma01Zones, setDma01Zones] = useState<ZoneSchematicItem[]>([
    {
      id: '01',
      name: 'Zone 01 — Town Central',
      dma: 'DMA 01',
      nodeId: 'J_10',
      pressure: 21.0,
      status: 'safe',
      statusLabel: 'Safe',
    },
    {
      id: '02',
      name: 'Zone 02 — Nawagamuwa North',
      dma: 'DMA 01',
      nodeId: 'J_20',
      pressure: 20.8,
      status: 'safe',
      statusLabel: 'Safe',
    },
    {
      id: '04',
      name: 'Zone 04 — East Industrial',
      dma: 'DMA 01',
      nodeId: 'J_100',
      pressure: 14.2,
      status: 'flagged',
      statusLabel: 'Flagged',
    },
  ]);

  const [dma02Zones, setDma02Zones] = useState<ZoneSchematicItem[]>([
    {
      id: '03',
      name: 'Zone 03 — Korathota Junction',
      dma: 'DMA 02',
      nodeId: 'J_500',
      pressure: 21.4,
      status: 'safe',
      statusLabel: 'Safe',
    },
    {
      id: '05',
      name: 'Zone 05 — Welihinda Ridge',
      dma: 'DMA 02',
      nodeId: 'J_1200',
      pressure: 20.5,
      status: 'safe',
      statusLabel: 'Safe',
    },
    {
      id: '06',
      name: 'Zone 06 — Welivita Highway Exit',
      dma: 'DMA 02',
      nodeId: 'J_3000',
      pressure: 21.2,
      status: 'safe',
      statusLabel: 'Safe',
    },
  ]);

  // Rolling 24-step Pressure Timeseries Data
  const [pressureData, setPressureData] = useState<PressureReading[]>(() => [...zone04HourlyReadings]);

  // Poll GET /api/v1/network/live-map-state every 3000ms
  const {
    data: liveMapState,
    refreshNow: reloadLiveMapState,
    loading: mapLoading,
  } = useLivePolling<LiveMapStateResponse>(fetchLiveMapState, 3000);

  // Live incident state from API poller
  const liveIncident = liveMapState?.active_incident ?? null;

  // Real-time WebSocket connection to edge telemetry
  const { connectionMode } = useTelemetrySocket({
    onMessage: (msg: TelemetryMessage) => {
      // Live update Zone 04 if J_100 message is received
      if (msg.node_id === 'J_100') {
        setDma01Zones((prev) =>
          prev.map((z) =>
            z.id === '04'
              ? {
                  ...z,
                  pressure: parseFloat(msg.actual_p.toFixed(1)),
                  status: msg.risk_score >= 50 || msg.alert_triggered ? 'flagged' : 'safe',
                  statusLabel: msg.risk_score >= 50 || msg.alert_triggered ? 'Fraud Alert' : 'Safe',
                }
              : z
          )
        );
      }
    },
  });

  const NODE_BASELINE_PRESSURE: Record<string, number> = {
    J_10: 21.0,
    J_20: 20.8,
    J_100: 21.2,
    J_500: 21.4,
    J_1200: 20.5,
    J_3000: 21.2,
  };

  // When liveMapState arrives, dynamically update 4 metric cards, zone schematic status, and rolling chart
  useEffect(() => {
    if (!liveMapState?.zones || liveMapState.zones.length === 0) return;

    // 1. Update DMA 01 zones (NORMAL -> Safe/Green, FRAUD_ALERT -> Flagged/Red)
    setDma01Zones((prev) =>
      prev.map((item) => {
        const live = liveMapState.zones.find(
          (z) => z.sensor_node_id === item.nodeId || z.zone_id.endsWith(item.id) || z.zone_id.includes(item.id)
        );
        if (!live) return item;
        const isFlagged = live.status === 'FRAUD_ALERT';
        const base = NODE_BASELINE_PRESSURE[item.nodeId] ?? 21.0;
        const currentP = isFlagged ? 14.2 : parseFloat((base + (live.pressure_residual_m ?? 0)).toFixed(1));
        return {
          ...item,
          pressure: currentP,
          status: isFlagged ? 'flagged' : 'safe',
          statusLabel: isFlagged ? 'Fraud Alert' : 'Safe',
        };
      })
    );

    // 2. Update DMA 02 zones
    setDma02Zones((prev) =>
      prev.map((item) => {
        const live = liveMapState.zones.find(
          (z) => z.sensor_node_id === item.nodeId || z.zone_id.endsWith(item.id) || z.zone_id.includes(item.id)
        );
        if (!live) return item;
        const isFlagged = live.status === 'FRAUD_ALERT';
        const base = NODE_BASELINE_PRESSURE[item.nodeId] ?? 21.0;
        const currentP = isFlagged ? 14.5 : parseFloat((base + (live.pressure_residual_m ?? 0)).toFixed(1));
        return {
          ...item,
          pressure: currentP,
          status: isFlagged ? 'flagged' : 'safe',
          statusLabel: isFlagged ? 'Fraud Alert' : 'Safe',
        };
      })
    );

    // 3. Append latest reading to the Recharts pressure line chart (maintaining rolling 24-step buffer)
    const z04 = liveMapState.zones.find((z) => z.zone_id === 'Zone 04' || z.sensor_node_id === 'J_100');
    const isAlert = z04?.status === 'FRAUD_ALERT';
    const expectedP = 21.2;
    const actualP = isAlert ? 15.2 : 21.0;

    const now = new Date();
    const timeLabel = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;

    const newReading: PressureReading = {
      timestamp: timeLabel,
      actualPressure: actualP,
      expectedPressure: expectedP,
      residual: parseFloat((actualP - expectedP).toFixed(1)),
      isAbnormal: isAlert,
    };

    setPressureData((prev) => {
      const base = prev.length > 0 ? prev : [...zone04HourlyReadings];
      // Keep rolling 24-step buffer: discard oldest, append incoming reading
      const rolling = base.length >= 24 ? base.slice(base.length - 23) : [...base];
      return [...rolling, newReading];
    });
  }, [liveMapState]);

  // Derived Top 4 Metrics based on live polling payload
  const totalMonitoredZones = liveMapState?.total_zones || liveMapState?.zones?.length || 6;
  const flaggedCount = useMemo(() => {
    if (liveMapState?.zones) {
      return liveMapState.zones.filter((z) => z.status === 'FRAUD_ALERT').length;
    }
    return dma01Zones.filter((z) => z.status === 'flagged').length;
  }, [liveMapState, dma01Zones]);

  const healthyCount = Math.max(0, totalMonitoredZones - flaggedCount);
  const healthPercentage = Math.round((healthyCount / totalMonitoredZones) * 100);

  const averagePressure = useMemo(() => {
    if (!liveMapState?.zones || liveMapState.zones.length === 0) {
      return flaggedCount > 0 ? '19.8' : '21.0';
    }
    const sum = liveMapState.zones.reduce((acc, z) => {
      const base = NODE_BASELINE_PRESSURE[z.sensor_node_id] ?? 21.0;
      const current = base + (z.pressure_residual_m ?? 0);
      return acc + current;
    }, 0);
    return (sum / liveMapState.zones.length).toFixed(1);
  }, [liveMapState, flaggedCount]);

  const dma01HasFlagged = useMemo(() => dma01Zones.some((z) => z.status === 'flagged'), [dma01Zones]);
  const dma02HasFlagged = useMemo(() => dma02Zones.some((z) => z.status === 'flagged'), [dma02Zones]);

  // Format Recharts data with clear line keys
  const chartData = useMemo(() => {
    if (!pressureData || pressureData.length === 0) return [];
    return pressureData.map((d) => ({
      timestamp: d.timestamp,
      expectedPressure: d.expectedPressure,
      actualPressure: d.actualPressure,
      drop: (d.expectedPressure - d.actualPressure).toFixed(1),
    }));
  }, [pressureData]);

  const handleInspectZone = (zoneId: string) => {
    navigate(`/zone/${zoneId}`);
  };

  return (
    <div className="space-y-6">
      {/* Page Title & Operational Status Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-2 border-b border-slate-200">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
            Network Operational Overview
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Kaduwela Scheme — Continuous Monitoring of DMAs 01 & 02
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <div className="inline-flex items-center space-x-2 px-3 py-1.5 rounded-full bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700">
            <Radio className="w-3.5 h-3.5 text-emerald-600 animate-pulse" />
            <span>SCADA Stream: <strong className="font-semibold text-slate-900 capitalize">{connectionMode}</strong></span>
          </div>

          <button
            onClick={reloadLiveMapState}
            title="Refresh network telemetry"
            className="p-2 rounded-xl bg-white border border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50 shadow-2xs transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${mapLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* TOP SECTION — 4 Live Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Card 1: Network Health */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs hover:border-slate-300 transition-all flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Network Health
            </span>
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
              healthPercentage === 100
                ? 'bg-emerald-50 border border-emerald-100 text-emerald-600'
                : 'bg-amber-50 border border-amber-100 text-amber-600'
            }`}>
              <CheckCircle2 className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-4">
            <div className="text-3xl font-extrabold text-slate-900 font-mono tracking-tight">
              {healthPercentage}% Operational
            </div>
            <p className="text-xs text-slate-500 mt-1.5">
              {healthyCount} of {totalMonitoredZones} monitored sectors normal
            </p>
          </div>
        </div>

        {/* Card 2: Average Pressure */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs hover:border-slate-300 transition-all flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Average Pressure
            </span>
            <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600">
              <Gauge className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-4">
            <div className="text-3xl font-extrabold text-slate-900 font-mono tracking-tight">
              {averagePressure} m
            </div>
            <p className="text-xs text-slate-500 mt-1.5">
              Standard range: 15–25 m
            </p>
          </div>
        </div>

        {/* Card 3: Flagged Sectors / Active Alert */}
        <div className={`bg-white rounded-2xl border ${
          flaggedCount > 0 ? 'border-rose-200 bg-rose-50/20' : 'border-slate-200 bg-emerald-50/10'
        } p-6 shadow-xs hover:border-slate-300 transition-all flex flex-col justify-between relative overflow-hidden`}>
          <div className={`absolute top-0 left-0 w-1.5 h-full ${flaggedCount > 0 ? 'bg-rose-500' : 'bg-emerald-500'}`} />
          <div className="flex items-center justify-between">
            <span className={`text-xs font-semibold uppercase tracking-wider ${flaggedCount > 0 ? 'text-rose-700' : 'text-slate-500'}`}>
              Flagged Sectors
            </span>
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
              flaggedCount > 0
                ? 'bg-rose-50 border border-rose-200 text-rose-600'
                : 'bg-emerald-50 border border-emerald-100 text-emerald-600'
            }`}>
              {flaggedCount > 0 ? <AlertTriangle className="w-5 h-5" /> : <CheckCircle2 className="w-5 h-5" />}
            </div>
          </div>
          <div className="mt-4">
            <div className="flex items-baseline gap-2">
              <div className={`text-3xl font-extrabold font-mono tracking-tight ${
                flaggedCount > 0 ? 'text-rose-600' : 'text-slate-900'
              }`}>
                {flaggedCount > 0 ? `${flaggedCount} Sector Flagged` : '0 Sectors Flagged'}
              </div>
            </div>
            <div className="flex items-center gap-1.5 mt-1.5">
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                flaggedCount > 0
                  ? 'bg-rose-100 text-rose-800 border border-rose-200'
                  : 'bg-emerald-100 text-emerald-800 border border-emerald-200'
              }`}>
                {flaggedCount > 0 ? 'Action Needed' : 'All Clear'}
              </span>
              <p className="text-xs font-medium text-slate-600">
                {flaggedCount > 0
                  ? `${liveMapState?.active_incident?.zone_id || 'Zone 04'} — Needs inspection`
                  : 'All 6 monitored sectors normal'}
              </p>
            </div>
          </div>
        </div>

        {/* Card 4: Estimated Water Loss */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs hover:border-slate-300 transition-all flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Estimated Water Loss
            </span>
            <div className="w-10 h-10 rounded-xl bg-sky-50 border border-sky-100 flex items-center justify-center text-sky-600">
              <Droplets className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-4">
            <div className="text-3xl font-extrabold text-slate-900 font-mono tracking-tight">
              {flaggedCount > 0 ? '0.06 L/s' : '0.00 L/s'}
            </div>
            <p className="text-xs text-slate-500 mt-1.5">
              {flaggedCount > 0
                ? `~216 liters per hour in ${liveMapState?.active_incident?.zone_id || 'Zone 04'}`
                : 'Nominal baseline distribution'}
            </p>
          </div>
        </div>
      </div>

      {/* GEOSPATIAL ANOMALY MAP — react-leaflet GIS Surveillance */}
      <AdminAnomalyMap activeIncident={liveIncident} onInspectZone={handleInspectZone} />

      {/* OPERATIONAL SECTOR TELEMETRY — 2-DMA Operational Grid */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center space-x-2">
              <Activity className="w-5 h-5 text-blue-600" />
              <span>Operational Sector Telemetry</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Topological junction concentrators across DMA 01 (Western Commercial) and DMA 02 (Eastern Suburban).
            </p>
          </div>

          <div className="flex items-center gap-3 text-xs">
            <span className="flex items-center gap-1.5 text-slate-600 font-medium">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              Safe Operation
            </span>
            <span className="flex items-center gap-1.5 text-rose-600 font-semibold">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
              Flagged Sector
            </span>
          </div>
        </div>

        {/* 2-DMA Schematic Box Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 pt-1">
          {/* DMA 01 Column */}
          <div className="space-y-3.5">
            <div className="flex items-center justify-between pb-1 border-b border-slate-200">
              <div className="flex items-center space-x-2">
                <span className="w-3 h-3 rounded-full bg-blue-600" />
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                  DMA 01 — Kaduwela Western Corridor
                </h3>
              </div>
              <span
                className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                  dma01HasFlagged
                    ? 'bg-rose-50 text-rose-700 border border-rose-200'
                    : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                }`}
              >
                {dma01HasFlagged ? '1 Sector Flagged' : 'All Sectors Safe'}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {dma01Zones.map((z) => {
                const isFlagged = z.status === 'flagged';
                return (
                  <div
                    key={z.id}
                    className={`rounded-xl p-4 flex flex-col justify-between transition-all shadow-2xs ${
                      isFlagged
                        ? 'border-2 border-rose-500 bg-rose-50/30 ring-2 ring-rose-500/10'
                        : 'border border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <div>
                      <div className="flex items-start justify-between gap-1">
                        <span className="text-xs font-bold text-slate-900 leading-tight">
                          {z.name}
                        </span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider shrink-0 ${
                            isFlagged
                              ? 'bg-rose-100 text-rose-700 border border-rose-300'
                              : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          }`}
                        >
                          {z.statusLabel}
                        </span>
                      </div>

                      <div className="mt-2 text-[11px] text-slate-500 flex items-center space-x-1">
                        <span>Node:</span>
                        <strong className="font-mono text-slate-800">{z.nodeId}</strong>
                      </div>

                      <div className="mt-3">
                        <span className="text-[10px] uppercase font-semibold text-slate-400 block">
                          Current Pressure
                        </span>
                        <div
                          className={`text-2xl font-black font-mono tracking-tight ${
                            isFlagged ? 'text-rose-600' : 'text-slate-900'
                          }`}
                        >
                          {z.pressure.toFixed(1)} m
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-slate-100">
                      <button
                        onClick={() => handleInspectZone(z.id)}
                        className={`w-full py-2 px-3 rounded-lg text-xs font-bold flex items-center justify-center space-x-1 transition-colors cursor-pointer ${
                          isFlagged
                            ? 'bg-rose-600 hover:bg-rose-700 text-white shadow-xs'
                            : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                        }`}
                      >
                        <span>Inspect Zone</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* DMA 02 Column */}
          <div className="space-y-3.5">
            <div className="flex items-center justify-between pb-1 border-b border-slate-200">
              <div className="flex items-center space-x-2">
                <span className="w-3 h-3 rounded-full bg-emerald-600" />
                <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                  DMA 02 — Kaduwela Eastern Corridor
                </h3>
              </div>
              <span
                className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                  dma02HasFlagged
                    ? 'bg-rose-50 text-rose-700 border border-rose-200'
                    : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                }`}
              >
                {dma02HasFlagged ? '1 Sector Flagged' : 'All Sectors Safe'}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {dma02Zones.map((z) => {
                const isFlagged = z.status === 'flagged';
                return (
                  <div
                    key={z.id}
                    className={`rounded-xl p-4 flex flex-col justify-between transition-all shadow-2xs ${
                      isFlagged
                        ? 'border-2 border-rose-500 bg-rose-50/30 ring-2 ring-rose-500/10'
                        : 'border border-slate-200 bg-white hover:border-slate-300'
                    }`}
                  >
                    <div>
                      <div className="flex items-start justify-between gap-1">
                        <span className="text-xs font-bold text-slate-900 leading-tight">
                          {z.name}
                        </span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider shrink-0 ${
                            isFlagged
                              ? 'bg-rose-100 text-rose-700 border border-rose-300'
                              : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          }`}
                        >
                          {z.statusLabel}
                        </span>
                      </div>

                      <div className="mt-2 text-[11px] text-slate-500 flex items-center space-x-1">
                        <span>Node:</span>
                        <strong className="font-mono text-slate-800">{z.nodeId}</strong>
                      </div>

                      <div className="mt-3">
                        <span className="text-[10px] uppercase font-semibold text-slate-400 block">
                          Current Pressure
                        </span>
                        <div
                          className={`text-2xl font-black font-mono tracking-tight ${
                            isFlagged ? 'text-rose-600' : 'text-slate-900'
                          }`}
                        >
                          {z.pressure.toFixed(1)} m
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-slate-100">
                      <button
                        onClick={() => handleInspectZone(z.id)}
                        className={`w-full py-2 px-3 rounded-lg text-xs font-bold flex items-center justify-center space-x-1 transition-colors cursor-pointer ${
                          isFlagged
                            ? 'bg-rose-600 hover:bg-rose-700 text-white shadow-xs'
                            : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                        }`}
                      >
                        <span>Inspect Zone</span>
                        <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* BOTTOM SECTION — 24-Hour Rolling Network Pressure Trend */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center space-x-2">
              <SlidersHorizontal className="w-5 h-5 text-blue-600" />
              <span>24-Hour Rolling Network Pressure Trend</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Normal Expected Pressure (EPANET Digital Twin) vs Actual Monitored Pressure (Rolling 24-step buffer).
            </p>
          </div>

          {/* Clean Legend Pill */}
          <div className="flex flex-wrap items-center gap-3 text-xs bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-200">
            <span className="flex items-center gap-1.5 font-medium text-slate-700">
              <span className="w-3 h-0.5 bg-blue-600 rounded-full" />
              Normal Expected Pressure
            </span>
            <span className="flex items-center gap-1.5 font-medium text-slate-700">
              <span className="w-3 h-0.5 border-t-2 border-dashed border-sky-500" />
              Actual Monitored Pressure
            </span>
            <span className="flex items-center gap-1.5 font-medium text-amber-800">
              <span className="w-3 h-3 bg-amber-100 border border-amber-300 rounded-xs" />
              Morning Supply Window (06:00–09:00)
            </span>
          </div>
        </div>

        {/* Recharts Canvas */}
        <div className="h-80 w-full pt-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 15, right: 20, left: -10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              
              <XAxis
                dataKey="timestamp"
                stroke="#64748b"
                fontSize={12}
                tickLine={false}
                axisLine={{ stroke: '#e2e8f0' }}
              />
              
              <YAxis
                stroke="#64748b"
                fontSize={12}
                domain={[0, 30]}
                unit="m"
                tickLine={false}
                axisLine={{ stroke: '#e2e8f0' }}
              />

              {/* Shaded highlight between 06:00 and 09:00 labeled 'Morning Supply Window' */}
              <ReferenceArea
                x1="06:00"
                x2="09:00"
                fill="#fef3c7"
                fillOpacity={0.65}
                stroke="#f59e0b"
                strokeOpacity={0.4}
                strokeDasharray="3 3"
                label={{
                  value: 'Morning Supply Window',
                  position: 'insideTop',
                  fill: '#92400e',
                  fontSize: 12,
                  fontWeight: 700,
                  offset: 8,
                }}
              />

              <Tooltip
                content={({ active, payload, label }) => {
                  if (active && payload && payload.length) {
                    const expected = payload.find((p) => p.dataKey === 'expectedPressure')?.value;
                    const actual = payload.find((p) => p.dataKey === 'actualPressure')?.value;
                    const drop = typeof expected === 'number' && typeof actual === 'number'
                      ? (expected - actual).toFixed(1)
                      : '0.0';
                    const isDeficit = parseFloat(drop) > 2.0;

                    return (
                      <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-md text-xs space-y-1.5">
                        <div className="font-bold text-slate-900 border-b border-slate-100 pb-1 flex items-center justify-between gap-4">
                          <span>Time: {label ?? ''}</span>
                          {typeof label === 'string' && label >= '06:00' && label <= '09:00' && (
                            <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-amber-100 text-amber-800">
                              Morning Window
                            </span>
                          )}
                        </div>
                        <div className="flex items-center justify-between gap-4 text-blue-700">
                          <span>Normal Expected:</span>
                          <span className="font-mono font-bold">{expected} m</span>
                        </div>
                        <div className="flex items-center justify-between gap-4 text-sky-700">
                          <span>Actual Monitored:</span>
                          <span className="font-mono font-bold">{actual} m</span>
                        </div>
                        {isDeficit && (
                          <div className="pt-1 border-t border-slate-100 flex items-center justify-between gap-4 text-rose-600 font-bold">
                            <span>Pressure Gap:</span>
                            <span className="font-mono">-{drop} m</span>
                          </div>
                        )}
                      </div>
                    );
                  }
                  return null;
                }}
              />

              <Legend verticalAlign="top" height={36} iconType="plainline" />

              {/* Blue solid line: 'Normal Expected Pressure' */}
              <Line
                type="monotone"
                dataKey="expectedPressure"
                name="Normal Expected Pressure"
                stroke="#2563eb"
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 6, fill: '#2563eb' }}
              />

              {/* Teal dashed line: 'Actual Monitored Pressure' */}
              <Line
                type="monotone"
                dataKey="actualPressure"
                name="Actual Monitored Pressure"
                stroke="#0ea5e9"
                strokeWidth={3}
                strokeDasharray="6 6"
                dot={{ r: 3, fill: '#0ea5e9' }}
                activeDot={{ r: 6, fill: '#0ea5e9' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Executive Context Subtext */}
        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-slate-600">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span>
              <strong>06:00–09:00 Window:</strong> Refill transient dampening filters suppress false alarms during network pressurization.
            </span>
          </div>
          <div className="flex items-center gap-2 text-rose-700 font-medium">
            <span className="w-2 h-2 rounded-full bg-rose-500" />
            <span>
              <strong>07:00 Onwards:</strong> Sustained -6.0 m pressure deficit isolates unmetered extraction at Node J_100 (Zone 04).
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default NetworkOverview;
