import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from 'recharts';

interface PressureChartProps {
  labels: string[];
  expected: number[];
  actual: number[];
  nodeId: string;
}

export const PressureChart: React.FC<PressureChartProps> = ({
  labels,
  expected,
  actual,
  nodeId,
}) => {
  const data = labels.map((label, i) => ({
    time: label,
    expected: expected[i] ?? 0,
    actual: actual[i] ?? 0,
    residual: Math.max(0, (expected[i] ?? 0) - (actual[i] ?? 0)),
  }));

  return (
    <div className="bg-[#0B192C] rounded-xl p-5 border border-slate-800 shadow-lg">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-white">Pressure Timeseries — {nodeId}</h3>
          <p className="text-xs text-slate-400">Expected Pressure vs Actual Observed Pressure (m)</p>
        </div>
      </div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" />
            <XAxis dataKey="time" stroke="#64748B" fontSize={12} />
            <YAxis stroke="#64748B" fontSize={12} domain={[0, 40]} />
            <Tooltip
              contentStyle={{ backgroundColor: '#0B192C', borderColor: '#334155', borderRadius: '8px' }}
              labelStyle={{ color: '#E2E8F0', fontWeight: 'bold' }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="expected"
              name="Expected Pressure"
              stroke="#64748B"
              strokeDasharray="4 4"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="actual"
              name="Actual Observed Pressure"
              stroke="#008DDA"
              strokeWidth={2.5}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
