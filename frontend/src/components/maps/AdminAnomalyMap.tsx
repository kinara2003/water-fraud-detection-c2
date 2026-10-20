import React, { useEffect, useState, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, GeoJSON, Marker, Circle, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';
import {
  AlertTriangle,
  ExternalLink,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import { fetchLiveMapState, setServerSimulationState } from '../../services/api';
import { useLivePolling } from '../../hooks';

// ==============================================================================
// Leaflet Default Icon Fix (prevents broken marker images in Vite/Webpack)
// ==============================================================================
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
});

// Custom high-contrast pulsing red pin for suspicious anomaly target
const redTargetIcon = L.divIcon({
  className: 'leaflet-red-target-marker',
  html: `
    <div style="position: relative; width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; cursor: pointer;">
      <span style="position: absolute; width: 32px; height: 32px; border-radius: 50%; background: #e11d48; opacity: 0.55; animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;"></span>
      <div style="position: relative; width: 26px; height: 26px; border-radius: 50%; background: #e11d48; border: 2.5px solid #ffffff; box-shadow: 0 4px 10px rgba(225, 29, 72, 0.5); display: flex; align-items: center; justify-content: center; color: white;">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="22" y1="12" x2="18" y2="12"></line>
          <line x1="6" y1="12" x2="2" y2="12"></line>
          <line x1="12" y1="6" x2="12" y2="2"></line>
          <line x1="12" y1="22" x2="12" y2="18"></line>
        </svg>
      </div>
    </div>
  `,
  iconSize: [34, 34],
  iconAnchor: [17, 17],
  popupAnchor: [0, -18],
});

// Map recenter controller helper component
const RecenterOnIncident: React.FC<{ coordinates: [number, number] | null }> = ({ coordinates }) => {
  const map = useMap();
  useEffect(() => {
    if (coordinates && coordinates.length === 2 && !isNaN(coordinates[0]) && !isNaN(coordinates[1])) {
      map.flyTo(coordinates, 15, { duration: 1.0 });
    } else {
      map.flyTo([6.9354, 79.9842], 14, { duration: 0.8 });
    }
  }, [coordinates, map]);
  return null;
};

export interface ActiveIncidentProp {
  zone_id: string;
  suspect_junction: string;
  coordinates: [number, number];
  search_radius_m?: number;
  landmark?: string;
  google_maps_url?: string;
  reasons?: string[];
  [key: string]: any;
}

export interface AdminAnomalyMapProps {
  /** Explicit active incident. If omitted or undefined, polls backend live state. */
  activeIncident?: ActiveIncidentProp | null;
  /** Optional callback when operator clicks to inspect a zone */
  onInspectZone?: (zoneId: string) => void;
  /** Optional wrapper CSS className */
  className?: string;
  /** Optional custom container height */
  height?: string | number;
  /** Default simulation toggle state if self-polling ('normal' | 'bypass') */
  defaultSimulationState?: 'normal' | 'bypass';
  /** Whether to show the interactive simulation bar header (default: true if self-polling) */
  showControls?: boolean;
}

export const AdminAnomalyMap: React.FC<AdminAnomalyMapProps> = ({
  activeIncident: propActiveIncident,
  onInspectZone,
  className = '',
  height = '460px',
  defaultSimulationState = 'bypass',
  showControls,
}) => {
  // Center map on Kaduwela East
  const centerPosition: [number, number] = [6.9354, 79.9842];

  const [simulationState, setSimulationState] = useState<'normal' | 'bypass'>(defaultSimulationState);
  const [geoJsonData, setGeoJsonData] = useState<any>(null);
  const [geoJsonKey, setGeoJsonKey] = useState<number>(1);
  const markerRef = useRef<L.Marker | null>(null);

  // If propActiveIncident is explicitly passed (including null), we don't need to poll
  const isControlled = propActiveIncident !== undefined;

  // 1. Live polling of backend map state when uncontrolled
  const fetchMapState = useCallback(() => fetchLiveMapState(), []);
  const { data: polledMapState, refreshNow: refreshMapState } = useLivePolling(
    fetchMapState,
    isControlled ? 0 : 3000
  );

  // Determine effective active incident
  const effectiveIncident: ActiveIncidentProp | null = isControlled
    ? (propActiveIncident ?? null)
    : (polledMapState?.active_incident ?? null);

  // Sync simulation toggle state from polled response
  useEffect(() => {
    if (!isControlled && polledMapState) {
      if (polledMapState.simulation_state === 'normal' || polledMapState.simulation_state === 'bypass') {
        setSimulationState(polledMapState.simulation_state);
      }
      setGeoJsonKey((k) => k + 1);
    }
  }, [polledMapState, isControlled]);

  // 2. Load GeoJSON zone boundaries from /data/kaduwela_zones.geojson
  useEffect(() => {
    let isMounted = true;
    const loadGeoJson = async () => {
      try {
        const res = await fetch('/data/kaduwela_zones.geojson');
        if (res.ok) {
          const data = await res.json();
          if (isMounted) setGeoJsonData(data);
        }
      } catch (err) {
        console.warn('Could not load kaduwela_zones.geojson:', err);
      }
    };
    loadGeoJson();
    return () => {
      isMounted = false;
    };
  }, []);

  // 3. Automatically open marker popup when active incident appears
  useEffect(() => {
    if (markerRef.current && effectiveIncident) {
      const timer = setTimeout(() => {
        markerRef.current?.openPopup();
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [effectiveIncident]);

  // Handler to toggle simulation mode
  const handleToggleState = async (target: 'normal' | 'bypass') => {
    setSimulationState(target);
    try {
      await setServerSimulationState(target);
    } catch (err) {
      console.warn('Server simulation state set error:', err);
    }
    await refreshMapState();
  };

  // GeoJSON Zone styling function
  const getZoneStyle = (feature: any) => {
    const rawZoneId = feature?.properties?.zone_id || feature?.id || '';
    const cleanId = String(rawZoneId).toLowerCase().replace('zone-', '').replace('zone ', '').trim();

    const isFlagged =
      effectiveIncident !== null &&
      (effectiveIncident.zone_id.toLowerCase().includes(cleanId) ||
        cleanId === '04' ||
        cleanId === 'zone-04');

    if (isFlagged) {
      // Alerted State: Solid Crimson (#e11d48, weight 3) and fill opacity 0.25 with pulse effect
      return {
        color: '#e11d48',
        weight: 3,
        fillColor: '#ef4444',
        fillOpacity: 0.25,
        dashArray: undefined,
      };
    }

    // Normal State: Render zones with light slate borders (#94a3b8) and subtle semi-transparent green fill (#10b981, opacity 0.08)
    return {
      color: '#94a3b8',
      weight: 1.5,
      fillColor: '#10b981',
      fillOpacity: 0.08,
      dashArray: '3, 3',
    };
  };

  // GeoJSON onEachFeature handler for click & tooltips
  const onEachZone = (feature: any, layer: L.Layer) => {
    const zoneName = feature?.properties?.name || feature?.properties?.zone_id || 'Kaduwela Zone';
    const zoneId = feature?.properties?.zone_id || feature?.id || '';

    layer.bindTooltip(
      `<div style="font-family: system-ui; font-size: 11px; font-weight: 600; padding: 2px 4px;">${zoneName}</div>`,
      { sticky: true, direction: 'auto', opacity: 0.9 }
    );

    layer.on({
      click: () => {
        if (onInspectZone && zoneId) {
          onInspectZone(zoneId);
        }
      },
    });
  };

  const shouldShowControls = showControls !== undefined ? showControls : !isControlled;

  return (
    <div className={`bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs ${className}`}>
      {/* Header & Status Bar */}
      {shouldShowControls && (
        <div className="p-4 bg-slate-50/80 border-b border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center space-x-3">
            <div className={`p-2 rounded-xl ${effectiveIncident ? 'bg-rose-100 text-rose-600' : 'bg-emerald-100 text-emerald-600'}`}>
              {effectiveIncident ? <ShieldAlert className="w-5 h-5 animate-pulse" /> : <ShieldCheck className="w-5 h-5" />}
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-sm font-bold text-slate-900">
                  Kaduwela East — Surveillance GIS Map
                </h3>
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                    effectiveIncident
                      ? 'bg-rose-100 text-rose-700 border border-rose-200'
                      : 'bg-emerald-100 text-emerald-700 border border-emerald-200'
                  }`}
                >
                  {effectiveIncident ? 'CRITICAL FRAUD ALERT' : 'ALL 6 ZONES NORMAL'}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                {effectiveIncident
                  ? `Active diversion pinpointed at Junction ${effectiveIncident.suspect_junction} (${effectiveIncident.zone_id})`
                  : 'Zero anomalies detected. Blind target state active (clean map view).'}
              </p>
            </div>
          </div>

          {/* Interactive Simulation Controls */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-500 hidden sm:inline">Simulation Mode:</span>
            <div className="inline-flex rounded-xl bg-slate-200/80 p-0.5 border border-slate-300/80 text-xs font-semibold">
              <button
                onClick={() => handleToggleState('normal')}
                className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                  simulationState === 'normal'
                    ? 'bg-white text-emerald-700 shadow-xs font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Normal (Blind)
              </button>
              <button
                onClick={() => handleToggleState('bypass')}
                className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                  simulationState === 'bypass'
                    ? 'bg-rose-600 text-white shadow-xs font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Simulate Theft (-6.0m)
              </button>
            </div>
            {!isControlled && (
              <button
                onClick={() => refreshMapState()}
                title="Refresh Map State"
                className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 transition-colors cursor-pointer"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Map Canvas */}
      <div style={{ height, width: '100%', position: 'relative' }}>
        <MapContainer
          center={centerPosition}
          zoom={14}
          scrollWheelZoom={true}
          style={{ height: '100%', width: '100%', zIndex: 10 }}
        >
          {/* Free Open-Source OpenStreetMap Tiles (Zero API Keys Required, No Watermark) */}
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />

          {/* Re-center smoothly on active anomaly or default */}
          <RecenterOnIncident coordinates={effectiveIncident ? effectiveIncident.coordinates : null} />

          {/* Zone Boundaries GeoJSON Layer */}
          {geoJsonData && (
            <GeoJSON
              key={geoJsonKey}
              data={geoJsonData}
              style={getZoneStyle}
              onEachFeature={onEachZone}
            />
          )}

          {/* Blind Target Marker & 50m Inspection Corridor Circle */}
          {effectiveIncident && effectiveIncident.coordinates && (
            <>
              {/* 50-meter semi-transparent red circle recommended field search area */}
              <Circle
                center={effectiveIncident.coordinates}
                radius={effectiveIncident.search_radius_m || 50}
                pathOptions={{
                  color: '#e11d48',
                  fillColor: '#ef4444',
                  fillOpacity: 0.22,
                  weight: 2,
                  dashArray: '4, 4',
                }}
              />

              {/* High-visibility pulsing target marker */}
              <Marker
                ref={markerRef}
                position={effectiveIncident.coordinates}
                icon={redTargetIcon}
              >
                <Popup autoPan={true} className="anomaly-incident-popup">
                  <div className="p-3 max-w-xs space-y-2.5 font-sans">
                    <div className="flex items-center space-x-2 border-b border-rose-100 pb-2">
                      <div className="p-1.5 bg-rose-50 text-rose-600 rounded-lg shrink-0">
                        <AlertTriangle className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-slate-900 leading-tight">
                          Suspicious Anomaly Detected
                        </h4>
                        <span className="text-[10px] font-semibold text-rose-600 uppercase tracking-wider">
                          {effectiveIncident.zone_id} • Critical Flag
                        </span>
                      </div>
                    </div>

                    <div className="space-y-1.5 text-xs text-slate-700">
                      <div className="flex justify-between items-baseline">
                        <span className="text-slate-400 text-[11px] font-medium">Suspect Node:</span>
                        <strong className="font-mono text-rose-700 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200">
                          {effectiveIncident.suspect_junction}
                        </strong>
                      </div>
                      {effectiveIncident.landmark && (
                        <div>
                          <span className="text-slate-400 text-[11px] font-medium block">Access Landmark:</span>
                          <span className="text-[11px] text-slate-800 leading-snug">
                            {effectiveIncident.landmark}
                          </span>
                        </div>
                      )}
                      <div className="flex justify-between items-baseline text-[11px]">
                        <span className="text-slate-400 font-medium">Search Radius:</span>
                        <span className="text-slate-600 font-mono font-medium">
                          {effectiveIncident.search_radius_m || 50}m corridor
                        </span>
                      </div>
                      <div className="flex justify-between items-baseline text-[11px]">
                        <span className="text-slate-400 font-medium">Coordinates:</span>
                        <span className="text-slate-600 font-mono">
                          [{effectiveIncident.coordinates[0].toFixed(5)}, {effectiveIncident.coordinates[1].toFixed(5)}]
                        </span>
                      </div>
                    </div>

                    {effectiveIncident.reasons && effectiveIncident.reasons.length > 0 && (
                      <div className="p-2 bg-slate-50 rounded-lg border border-slate-200/80 space-y-1">
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">
                          Telemetry Evidence:
                        </span>
                        <ul className="text-[10px] text-slate-600 space-y-0.5 list-disc pl-3">
                          {effectiveIncident.reasons.map((r, i) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div className="pt-1 flex flex-col gap-1.5">
                      <a
                        href={
                          effectiveIncident.google_maps_url ||
                          `https://www.google.com/maps/search/?api=1&query=${effectiveIncident.coordinates[0]},${effectiveIncident.coordinates[1]}`
                        }
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full inline-flex items-center justify-center space-x-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs shadow-xs transition-colors no-underline cursor-pointer"
                      >
                        <span>Navigate on Google Maps</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                      {onInspectZone && (
                        <button
                          onClick={() => onInspectZone(effectiveIncident.zone_id)}
                          className="w-full inline-flex items-center justify-center space-x-1 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 font-medium text-xs transition-colors cursor-pointer border border-slate-200"
                        >
                          <span>Inspect Zone Diagnostics</span>
                        </button>
                      )}
                    </div>
                  </div>
                </Popup>
              </Marker>
            </>
          )}
        </MapContainer>

        {/* Legend Overlay at bottom-left */}
        <div className="absolute bottom-3 left-3 z-[400] bg-white/90 backdrop-blur-xs px-3 py-2 rounded-xl border border-slate-200 shadow-xs text-[11px] space-y-1">
          <div className="font-bold text-slate-700 text-[10px] uppercase tracking-wider">
            GIS Layer Legend
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-3 h-2 rounded border border-slate-400 bg-emerald-500/20" />
            <span className="text-slate-600">Normal Sector (Hydraulically Balanced)</span>
          </div>
          {effectiveIncident && (
            <>
              <div className="flex items-center space-x-2">
                <span className="w-3 h-2 rounded border border-rose-600 bg-rose-500/30" />
                <span className="text-rose-700 font-semibold">Flagged Sector (Pressure Drop)</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-600" />
                <span className="text-slate-600">Suspect Junction ({effectiveIncident.suspect_junction})</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="w-3 h-2 rounded-full border border-dashed border-rose-500 bg-rose-500/10" />
                <span className="text-slate-600">50m Physical Inspection Corridor</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdminAnomalyMap;
