import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity,
  Layers,
  ShieldAlert,
  Cpu,
  Droplets,
  X,
  Radio,
} from 'lucide-react';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen, onClose }) => {
  const navItems = [
    {
      name: 'Network Overview',
      path: '/dashboard',
      icon: Activity,
    },
    {
      name: 'Zone Analysis',
      path: '/zone/04',
      icon: Layers,
    },
    {
      name: 'Alerts & Investigation',
      path: '/alerts',
      icon: ShieldAlert,
    },
    {
      name: 'Data & Models',
      path: '/models',
      icon: Cpu,
    },
  ];

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-40 lg:hidden transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 w-64 bg-[#0B192C] text-slate-200 border-r border-[#1E3E62]/60 flex flex-col transition-transform duration-300 ease-in-out lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Branding Header */}
        <div className="h-20 px-6 flex items-center justify-between border-b border-[#1E3E62]/40 bg-[#071324]">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#008DDA] to-[#1E3E62] flex items-center justify-center text-white shadow-lg shadow-[#008DDA]/20 border border-[#41C9E2]/30">
              <Droplets className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-1.5">
                <span className="font-extrabold tracking-wider text-white text-base">WATERGUARD</span>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#1E3E62] text-[#41C9E2] border border-[#008DDA]/40">
                  NWSDB
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-medium tracking-tight">
                Network Intelligence (Component 2)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-[#1E3E62]/60 lg:hidden cursor-pointer"
            aria-label="Close menu"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 px-4 py-6 space-y-1.5 overflow-y-auto">
          <div className="px-3 pb-2 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            Operational Navigation
          </div>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => {
                  if (window.innerWidth < 1024) onClose();
                }}
                className={({ isActive }) =>
                  `flex items-center space-x-3 px-3.5 py-2.5 rounded-xl font-medium text-sm transition-all duration-200 ${
                    isActive
                      ? 'bg-gradient-to-r from-[#008DDA] to-[#1E3E62] text-white shadow-md shadow-[#008DDA]/25 border border-[#41C9E2]/30'
                      : 'text-slate-300 hover:bg-[#1E3E62]/40 hover:text-white'
                  }`
                }
              >
                <Icon className="w-5 h-5 shrink-0" />
                <span className="truncate">{item.name}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* System Status Footer */}
        <div className="p-4 border-t border-[#1E3E62]/40 bg-[#071324]/80">
          <div className="bg-[#0B192C] p-3 rounded-xl border border-[#1E3E62]/60 space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-300">
              <span className="flex items-center space-x-1.5">
                <Radio className="w-3.5 h-3.5 text-[#008DDA]" />
                <span>System Status</span>
              </span>
              <span className="inline-flex items-center text-[#10B981] text-[11px] font-bold">
                <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse mr-1.5" />
                Operational
              </span>
            </div>
            <div className="text-[11px] text-slate-400 font-mono">
              (IWS Schedule Active)
            </div>
            <div className="text-[10px] text-slate-500 flex justify-between pt-1 border-t border-slate-800">
              <span>Telemetry Twin: 900s</span>
              <span>DMA 01 & 02</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};
