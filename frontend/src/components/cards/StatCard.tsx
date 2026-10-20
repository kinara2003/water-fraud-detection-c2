import React from 'react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  status?: 'normal' | 'warning' | 'danger' | 'info';
  icon?: React.ReactNode;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtitle,
  status = 'info',
  icon,
}) => {
  const borderColor = {
    normal: 'border-emerald-500/30 hover:border-emerald-500/50',
    warning: 'border-amber-500/30 hover:border-amber-500/50',
    danger: 'border-rose-500/30 hover:border-rose-500/50',
    info: 'border-slate-800 hover:border-slate-700',
  }[status];

  return (
    <div className={`bg-[#0B192C]/90 rounded-xl p-5 border ${borderColor} transition-all shadow-lg`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-400">{title}</span>
        {icon && <div className="text-slate-400">{icon}</div>}
      </div>
      <div className="mt-3">
        <span className="text-2xl font-bold tracking-tight text-white">{value}</span>
      </div>
      {subtitle && <p className="mt-1 text-xs text-slate-400">{subtitle}</p>}
    </div>
  );
};
