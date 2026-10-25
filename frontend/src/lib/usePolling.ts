"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Polling helper: fetch immediately, then refresh on an interval. */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  { intervalMs = 3000, enabled = true }: { intervalMs?: number; enabled?: boolean } = {},
): {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);

  // Keep the latest fetcher without touching refs during render.
  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);

  const refresh = useCallback(async () => {
    try {
      const next = await fetcherRef.current();
      setData(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    void refresh();
    const id = setInterval(() => void refresh(), intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs, enabled]);

  return { data, error, loading, refresh };
}
