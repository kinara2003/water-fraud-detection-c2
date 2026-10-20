/**
 * frontend/src/hooks/useLivePolling.ts
 * Reusable React hook for live periodic API polling.
 *
 * Features:
 * - Accepts an async fetcher function and polling interval in ms (default: 3000ms).
 * - Returns { data, loading, error, refreshNow }.
 * - Prevents overlapping requests while in-flight.
 * - Automatically cleans up timer interval on component unmount.
 */

import { useState, useEffect, useCallback, useRef } from 'react';

export interface UseLivePollingReturn<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  refreshNow: () => Promise<void>;
}

export function useLivePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number = 3000
): UseLivePollingReturn<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);

  // Store fetcher in ref to avoid resetting interval on non-memoized fetchers
  const fetcherRef = useRef<() => Promise<T>>(fetcher);
  fetcherRef.current = fetcher;

  // Track in-flight state to prevent race conditions or overlapping fetches
  const isFetchingRef = useRef<boolean>(false);

  const execute = useCallback(async (isInitial = false) => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;

    if (isInitial) {
      setLoading(true);
    }

    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
    } catch (err) {
      const errorObj = err instanceof Error ? err : new Error(String(err));
      setError(errorObj);
      console.warn('[useLivePolling] Polling request failed:', errorObj);
    } finally {
      isFetchingRef.current = false;
      if (isInitial) {
        setLoading(false);
      }
    }
  }, []);

  const refreshNow = useCallback(async () => {
    await execute(false);
  }, [execute]);

  useEffect(() => {
    let isMounted = true;

    // Initial fetch on mount or interval change
    execute(true);

    if (intervalMs <= 0) return;

    const timerId = setInterval(() => {
      if (isMounted) {
        execute(false);
      }
    }, intervalMs);

    // Clean up interval timer on unmount
    return () => {
      isMounted = false;
      clearInterval(timerId);
    };
  }, [intervalMs, execute]);

  return { data, loading, error, refreshNow };
}

export default useLivePolling;
