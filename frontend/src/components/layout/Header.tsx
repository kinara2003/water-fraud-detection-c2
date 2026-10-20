import React from 'react';
import { useLocation } from 'react-router-dom';
import { Bell, Menu, ShieldCheck } from 'lucide-react';
import { useDataMode } from '../../services/apiClient';

interface HeaderProps {
  onToggleSidebar: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onToggleSidebar }) => {
  const location = useLocation();
  const { isLive, toggleDataMode } = useDataMode();

  const getPageTitle = (pathname: string): { title: string; subtitle: string } => {
    if (pathname === '/' || pathname.startsWith('/dashboard')) {
      return {
        title: 'Network Overview',
        subtitle: 'Kaduwela Multi-DMA Hydraulic Surveillance & Loss Triage',
      };
    }
    if (pathname.startsWith('/zone')) {
      return {
        title: 'Zone Analysis (Zone 04)',
        subtitle: 'Telemetry Residuals, Digital Twin Matching & Stage 1/2 Inference',
      };
    }
    if (pathname.startsWith('/alerts')) {
      return {
        title: 'Alerts & Investigation',
        subtitle: 'Real-Time Escalations, Automated Notifications & Field Dispatch',
      };
    }
    if (pathname.startsWith('/models') || pathname.startsWith('/logs')) {
      return {
        title: 'Data & Models',
        subtitle: 'Ground-Truth Inspection Logs & Continuous Retraining Engine',
      };
    }
    return {
      title: 'WATERGUARD Surveillance',
      subtitle: 'NWSDB Component 2 Intelligence Hub',
    };
  };

  const { title, subtitle } = getPageTitle(location.pathname);

  return (
    <header className="h-20 bg-white border-b border-slate-200/80 px-4 sm:px-6 lg:px-8 flex items-center justify-between sticky top-0 z-30 shadow-xs">
      {/* Left: Mobile Toggle & Page Title */}
      <div className="flex items-center space-x-4">
        <button
          onClick={onToggleSidebar}
          className="p-2 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 lg:hidden focus:outline-hidden cursor-pointer"
          aria-label="Toggle navigation"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 leading-tight">
            {title}
          </h1>
          <p className="text-xs text-slate-500 hidden sm:block mt-0.5">
            {subtitle}
          </p>
        </div>
      </div>

      {/* Right: Date/Time, Data Mode Badge, Status Chip, Notification Bell, Profile Avatar */}
      <div className="flex items-center space-x-2 sm:space-x-3 lg:space-x-4">
        {/* Current Date/Time */}
        <div className="hidden md:flex flex-col text-right pr-2">
          <span className="text-xs font-semibold text-slate-800">07 Oct 2026</span>
          <span className="text-[11px] font-mono text-slate-500">13:45:00 UTC+5:30</span>
        </div>

        {/* Data Mode Indicator Badge */}
        <button
          type="button"
          onClick={toggleDataMode}
          id="data-mode-badge"
          title={
            isLive
              ? 'Connected to FastAPI backend at http://127.0.0.1:8000 (Click to toggle Mock Fallback)'
              : 'Using Mock Fallback dataset (Click to test FastAPI Live connection)'
          }
          className={`inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold border transition-all cursor-pointer shadow-2xs select-none ${
            isLive
              ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
              : 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100'
          }`}
        >
          <span className={`text-[10px] leading-none ${isLive ? 'text-emerald-500 font-bold' : 'text-amber-500 font-bold'}`}>
            {isLive ? '●' : '○'}
          </span>
          <span className="whitespace-nowrap font-medium">
            {isLive ? '● Live Backend (FastAPI Connected)' : '○ Mock Fallback'}
          </span>
        </button>

        {/* Online Status Chip */}
        <div className="hidden lg:inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>SCADA Online</span>
        </div>

        {/* Notification Bell with Badge */}
        <div className="relative">
          <button
            className="p-2.5 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors relative cursor-pointer"
            aria-label="View notifications"
          >
            <Bell className="w-5 h-5" />
            <span className="absolute top-1 right-1 min-w-4.5 h-4.5 px-1 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center ring-2 ring-white shadow-xs">
              5
            </span>
          </button>
        </div>

        {/* Profile Avatar & Info */}
        <div className="flex items-center space-x-3 pl-2 sm:border-l sm:border-slate-200">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#0B192C] to-[#008DDA] text-white flex items-center justify-center font-bold text-xs shadow-sm ring-2 ring-slate-100">
            KP
          </div>
          <div className="hidden xl:flex flex-col">
            <span className="text-xs font-bold text-slate-900 leading-tight flex items-center">
              Eng. K. Perera
              <ShieldCheck className="w-3.5 h-3.5 text-[#008DDA] ml-1 inline" />
            </span>
            <span className="text-[10px] text-slate-500 font-medium">Chief SCADA Engineer</span>
          </div>
        </div>
      </div>
    </header>
  );
};
