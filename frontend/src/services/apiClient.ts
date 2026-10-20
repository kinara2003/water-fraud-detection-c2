/**
 * frontend/src/services/apiClient.ts
 * Base HTTP & mock abstraction client for Component 2 services.
 * Features runtime toggle logic with automatic live connectivity detection
 * and graceful fallback to offline mock data.
 */

import { useState, useEffect } from 'react';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
export const INITIAL_USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export const NO_CACHE_HEADERS: Record<string, string> = {
  'Cache-Control': 'no-cache',
  'Pragma': 'no-cache',
};

export const simulateLatency = (ms = 150): Promise<void> => {
  return new Promise((resolve) => setTimeout(resolve, ms));
};

type ConnectionListener = (isLive: boolean) => void;

export class ApiClient {
  public baseUrl: string;
  public useMock: boolean;
  private _isBackendConnected: boolean = false;
  private listeners: Set<ConnectionListener> = new Set();
  private healthCheckInProgress = false;

  constructor() {
    this.baseUrl = API_BASE_URL;
    this.useMock = INITIAL_USE_MOCK;
  }

  public isLive(): boolean {
    return !this.useMock && this._isBackendConnected;
  }

  public setUseMock(useMock: boolean): void {
    if (this.useMock !== useMock) {
      this.useMock = useMock;
      if (!useMock) {
        this.checkHealth();
      } else {
        this.notifyListeners();
      }
    }
  }

  public toggleMock(): boolean {
    this.setUseMock(!this.useMock);
    return this.useMock;
  }

  public subscribe(listener: ConnectionListener): () => void {
    this.listeners.add(listener);
    listener(this.isLive());
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notifyListeners(): void {
    const live = this.isLive();
    this.listeners.forEach((listener) => {
      try {
        listener(live);
      } catch (e) {
        console.error('[apiClient] Error notifying listener:', e);
      }
    });
  }

  private setConnectionState(connected: boolean): void {
    if (this._isBackendConnected !== connected) {
      this._isBackendConnected = connected;
      this.notifyListeners();
    }
  }

  /**
   * Health probe verifying live backend availability.
   */
  public async checkHealth(): Promise<boolean> {
    if (this.useMock) {
      this.setConnectionState(false);
      return false;
    }

    if (this.healthCheckInProgress) {
      return this._isBackendConnected;
    }

    this.healthCheckInProgress = true;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2500);

      const res = await fetch(`${this.baseUrl}/health`, {
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          'Cache-Control': 'no-cache',
          Pragma: 'no-cache',
        },
      });
      clearTimeout(timeoutId);

      const isOk = res.ok;
      this.setConnectionState(isOk);
      return isOk;
    } catch {
      this.setConnectionState(false);
      return false;
    } finally {
      this.healthCheckInProgress = false;
    }
  }

  /**
   * Dispatches GET requests with runtime toggle and graceful fallback.
   */
  async get<T>(path: string, fallbackData?: T): Promise<T> {
    if (this.useMock) {
      if (fallbackData !== undefined) return fallbackData;
      throw new Error(`Mock mode active for path: ${path}`);
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      const response = await fetch(`${this.baseUrl}${path}`, {
        headers: {
          Accept: 'application/json',
          'Cache-Control': 'no-cache',
          Pragma: 'no-cache',
        },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`API GET ${path} failed with HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      this.setConnectionState(true);
      return data as T;
    } catch (err) {
      console.warn(`[apiClient] Live GET request failed for ${path}. Gracefully falling back to mock:`, err);
      this.setConnectionState(false);
      if (fallbackData !== undefined) {
        return fallbackData;
      }
      throw err;
    }
  }

  /**
   * Dispatches POST requests with runtime toggle and graceful fallback.
   */
  async post<T>(path: string, body?: unknown, fallbackData?: T): Promise<T> {
    if (this.useMock) {
      if (fallbackData !== undefined) return fallbackData;
      throw new Error(`Mock mode active for path: ${path}`);
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);

      const response = await fetch(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'Cache-Control': 'no-cache',
          Pragma: 'no-cache',
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`API POST ${path} failed with HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      this.setConnectionState(true);
      return data as T;
    } catch (err) {
      console.warn(`[apiClient] Live POST request failed for ${path}. Gracefully falling back to mock:`, err);
      this.setConnectionState(false);
      if (fallbackData !== undefined) {
        return fallbackData;
      }
      throw err;
    }
  }

  /**
   * Dispatches PATCH requests with runtime toggle and graceful fallback.
   */
  async patch<T>(path: string, body?: unknown, fallbackData?: T): Promise<T> {
    if (this.useMock) {
      if (fallbackData !== undefined) return fallbackData;
      throw new Error(`Mock mode active for path: ${path}`);
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 8000);

      const response = await fetch(`${this.baseUrl}${path}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'Cache-Control': 'no-cache',
          Pragma: 'no-cache',
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`API PATCH ${path} failed with HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      this.setConnectionState(true);
      return data as T;
    } catch (err) {
      console.warn(`[apiClient] Live PATCH request failed for ${path}. Gracefully falling back to mock:`, err);
      this.setConnectionState(false);
      if (fallbackData !== undefined) {
        return fallbackData;
      }
      throw err;
    }
  }
}

export const apiClient = new ApiClient();

// Backwards compatibility export
export const IS_USE_MOCK = INITIAL_USE_MOCK;

/**
 * React hook providing reactive data mode tracking and toggle actions.
 */
export function useDataMode(): {
  isLive: boolean;
  modeText: string;
  toggleDataMode: () => void;
  checkConnection: () => Promise<boolean>;
} {
  const [isLive, setIsLive] = useState<boolean>(apiClient.isLive());

  useEffect(() => {
    const unsubscribe = apiClient.subscribe((live) => setIsLive(live));
    apiClient.checkHealth();
    return unsubscribe;
  }, []);

  return {
    isLive,
    modeText: isLive ? 'Live Backend (FastAPI Connected)' : 'Mock Fallback',
    toggleDataMode: () => apiClient.toggleMock(),
    checkConnection: () => apiClient.checkHealth(),
  };
}
