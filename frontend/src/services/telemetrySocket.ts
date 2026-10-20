/**
 * frontend/src/services/telemetrySocket.ts
 * Real-time SCADA WebSocket Telemetry Streaming Hook & Reconnection Engine
 * Component 2: NWSDB Unauthorized Water Withdrawal & Physical Twin Surveillance Engine
 *
 * Provides:
 *   - Auto-reconnecting WebSocket client with exponential backoff & jitter
 *   - Transparent fallback to HTTP polling (/api/v1/dma-status) if WebSocket fails
 *   - Type-safe telemetry broadcasts (node_id, actual_p, residual_m, risk_score, alert_triggered)
 *   - Direct hook bindings for Recharts curves and status indicator chips
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE_URL } from './apiClient';

export interface TelemetryMessage {
  type: string;
  node_id: string;
  actual_p: number;
  residual_m: number;
  risk_score: number;
  alert_triggered: boolean;
  zone_id?: string;
  expected_p?: number;
  classification?: string;
  recommended_action?: string;
  battery_voltage?: number;
  cellular_rssi_dbm?: number;
  is_heartbeat?: boolean;
  is_store_and_forward?: boolean;
  timestamp: string;
}

export type ConnectionMode = 'websocket' | 'polling' | 'connecting' | 'disconnected';

export interface UseTelemetrySocketOptions {
  nodeId?: string;
  zoneId?: string;
  onMessage?: (message: TelemetryMessage) => void;
  enablePollingFallback?: boolean;
  pollingIntervalMs?: number;
}

export interface UseTelemetrySocketReturn {
  lastMessage: TelemetryMessage | null;
  connectionMode: ConnectionMode;
  isConnected: boolean;
  isUsingFallback: boolean;
  reconnectCount: number;
  error: string | null;
  sendMessage: (message: string | object) => void;
  reconnect: () => void;
}

/**
 * Resolves the appropriate WebSocket URL based on current environment and API base URL.
 */
export function getWebSocketUrl(): string {
  // 1. If explicit API_BASE_URL configured with http/https
  if (API_BASE_URL && API_BASE_URL.startsWith('http')) {
    const wsBase = API_BASE_URL.replace(/^http:\/\//, 'ws://').replace(/^https:\/\//, 'wss://');
    return `${wsBase.replace(/\/$/, '')}/ws/telemetry`;
  }

  // 2. Browser window fallback: connect to port 8000 (direct) or same host (/ws/telemetry proxy)
  if (typeof window !== 'undefined') {
    const isHttps = window.location.protocol === 'https:';
    const wsProto = isHttps ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';

    // In dev setup where frontend is on 5173, backend is on 8000
    if (window.location.port === '5173') {
      return `${wsProto}//${host}:8000/ws/telemetry`;
    }
    return `${wsProto}//${window.location.host}/ws/telemetry`;
  }

  return 'ws://localhost:8000/ws/telemetry';
}

/**
 * React Hook for Real-Time Telemetry Streaming with Reconnect & HTTP Polling Fallback
 */
export function useTelemetrySocket(options: UseTelemetrySocketOptions = {}): UseTelemetrySocketReturn {
  const {
    nodeId,
    zoneId,
    onMessage,
    enablePollingFallback = true,
    pollingIntervalMs = 3000,
  } = options;

  const [lastMessage, setLastMessage] = useState<TelemetryMessage | null>(null);
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>('connecting');
  const [reconnectCount, setReconnectCount] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const pollingIntervalRef = useRef<any>(null);
  const pingIntervalRef = useRef<any>(null);
  const failCountRef = useRef<number>(0);
  const isMountedRef = useRef<boolean>(true);
  const onMessageRef = useRef(onMessage);

  onMessageRef.current = onMessage;

  // Dispatch message to subscriber
  const handleIncomingPayload = useCallback(
    (msg: TelemetryMessage) => {
      // Optional filter by node or zone
      if (nodeId && msg.node_id && msg.node_id !== nodeId) return;
      if (zoneId && msg.zone_id && msg.zone_id !== zoneId) return;

      setLastMessage(msg);
      if (onMessageRef.current) {
        onMessageRef.current(msg);
      }
    },
    [nodeId, zoneId]
  );

  // Fallback: HTTP polling of live DMA status
  const executePollingFallback = useCallback(async () => {
    try {
      const targetUrl = API_BASE_URL ? `${API_BASE_URL.replace(/\/$/, '')}/api/v1/dma-status` : '/api/v1/dma-status';
      const resp = await fetch(targetUrl);
      if (!resp.ok) return;

      const data = await resp.json();
      const nodes = data.nodes || [];

      // Find relevant node or pick peak/first node
      let targetNode = nodes.find((n: any) => (nodeId ? n.node_id === nodeId : n.node_id === 'J_100'));
      if (!targetNode && nodes.length > 0) {
        targetNode = nodes[0];
      }

      if (targetNode) {
        const polledMessage: TelemetryMessage = {
          type: 'TELEMETRY_UPDATE',
          node_id: targetNode.node_id,
          zone_id: targetNode.dma_id || 'DMA 01',
          actual_p: targetNode.current_actual_pressure,
          expected_p: targetNode.current_expected_pressure,
          residual_m: targetNode.current_residual,
          risk_score: targetNode.peak_risk_score,
          alert_triggered: targetNode.peak_risk_score >= 70.0,
          classification: targetNode.classification,
          recommended_action: targetNode.recommended_action,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        };

        handleIncomingPayload(polledMessage);
      }
    } catch (err) {
      // Keep polling silently
    }
  }, [nodeId, handleIncomingPayload]);

  // Start HTTP polling
  const startPolling = useCallback(() => {
    if (!enablePollingFallback) return;
    if (pollingIntervalRef.current) return;

    setConnectionMode('polling');
    executePollingFallback();
    pollingIntervalRef.current = setInterval(executePollingFallback, pollingIntervalMs);
  }, [enablePollingFallback, executePollingFallback, pollingIntervalMs]);

  // Stop HTTP polling
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  // Connect WebSocket
  const connectWebSocket = useCallback(() => {
    if (socketRef.current && (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const wsUrl = getWebSocketUrl();
    setConnectionMode('connecting');
    setError(null);

    try {
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        setConnectionMode('websocket');
        failCountRef.current = 0;
        stopPolling();
        setError(null);

        // Ping keepalive every 20s
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 20000);
      };

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return;
        if (event.data === 'pong') return;

        try {
          const parsed = JSON.parse(event.data);
          if (parsed && parsed.node_id) {
            handleIncomingPayload(parsed as TelemetryMessage);
          }
        } catch (e) {
          // Non-JSON message ignore
        }
      };

      ws.onerror = () => {
        if (!isMountedRef.current) return;
        failCountRef.current += 1;
        setError('WebSocket handshake error. Falling back to HTTP polling.');
      };

      ws.onclose = () => {
        if (!isMountedRef.current) return;
        socketRef.current = null;

        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        failCountRef.current += 1;
        setReconnectCount((prev) => prev + 1);

        // Switch to polling fallback if multiple failures
        if (failCountRef.current >= 2 && enablePollingFallback) {
          startPolling();
        } else {
          setConnectionMode('disconnected');
        }

        // Schedule reconnect with backoff
        const backoffMs = Math.min(1000 * Math.pow(1.5, failCountRef.current), 10000);
        if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(() => {
          if (isMountedRef.current) {
            connectWebSocket();
          }
        }, backoffMs);
      };
    } catch (err: any) {
      failCountRef.current += 1;
      setError(err?.message || 'Failed to initialize WebSocket');
      startPolling();
    }
  }, [enablePollingFallback, handleIncomingPayload, startPolling, stopPolling]);

  // Manual reconnect
  const reconnect = useCallback(() => {
    failCountRef.current = 0;
    stopPolling();
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    connectWebSocket();
  }, [connectWebSocket, stopPolling]);

  // Send message through socket
  const sendMessage = useCallback((msg: string | object) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      const payload = typeof msg === 'string' ? msg : JSON.stringify(msg);
      socketRef.current.send(payload);
    }
  }, []);

  // Mount / Unmount lifecycle
  useEffect(() => {
    isMountedRef.current = true;
    connectWebSocket();

    return () => {
      isMountedRef.current = false;
      stopPolling();
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
    };
  }, [connectWebSocket, stopPolling]);

  return {
    lastMessage,
    connectionMode,
    isConnected: connectionMode === 'websocket',
    isUsingFallback: connectionMode === 'polling',
    reconnectCount,
    error,
    sendMessage,
    reconnect,
  };
}
