import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from './components/layout';
import {
  NetworkOverview,
  ZoneAnalysis,
  AlertsInvestigation,
  DataModelMonitoring,
  LogsPage,
} from './pages';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<NetworkOverview />} />
          <Route path="/zone/:zoneId" element={<ZoneAnalysis />} />
          <Route path="/zone" element={<Navigate to="/zone/04" replace />} />
          <Route path="/alerts" element={<AlertsInvestigation />} />
          <Route path="/models" element={<DataModelMonitoring />} />
          <Route path="/logs" element={<LogsPage />} />
          {/* Catch-all fallback */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
