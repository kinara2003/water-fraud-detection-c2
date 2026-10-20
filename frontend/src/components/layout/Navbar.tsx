import React from 'react';
import { Droplets, Activity, ShieldAlert, FileText } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

export const Navbar: React.FC = () => {
  const location = useLocation();

  const navItems = [
    { name: 'Dashboard', path: '/', icon: Activity },
    { name: 'Alerts & Inspections', path: '/alerts', icon: ShieldAlert },
    { name: 'Logs & Retraining', path: '/logs', icon: FileText },
  ];

  return (
    <header className="bg-[#0B192C] border-b border-slate-800 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-[#008DDA]/20 rounded-lg border border-[#008DDA]/40 text-[#41C9E2]">
              <Droplets className="w-6 h-6" />
            </div>
            <div>
              <span className="text-lg font-bold tracking-tight text-white">NWSDB Water Guard</span>
              <span className="block text-xs text-slate-400 font-mono">Kaduwela DMA 01 & 02 Twin</span>
            </div>
          </div>

          <nav className="flex space-x-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-[#1E3E62] text-white shadow-sm'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
    </header>
  );
};
