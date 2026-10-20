import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { DisclaimerBanner } from '../common';

export const AppLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-surface-bg text-content-primary flex flex-col">
      {/* Persistent Top Disclaimer Banner on all pages */}
      <DisclaimerBanner />

      <div className="flex-1 flex">
        {/* Sidebar: Fixed on desktop (>1024px), drawer on mobile/tablet */}
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 lg:pl-64">
          <Header onToggleSidebar={() => setSidebarOpen((prev) => !prev)} />

          <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
            <Outlet />
          </main>

          <footer className="py-4 px-6 border-t border-surface-border bg-surface-card text-center text-xs text-content-secondary">
            National Water Supply & Drainage Board (NWSDB) • Component 2 Dual-Stage Fraud Surveillance & Hydraulic Twin • Kaduwela DMAs
          </footer>
        </div>
      </div>
    </div>
  );
};

export default AppLayout;
