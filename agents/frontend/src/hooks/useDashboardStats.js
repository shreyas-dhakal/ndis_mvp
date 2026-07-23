import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api.js";

// Shared by the org dashboard today; a future per-participant route can
// reuse this unchanged by just passing its own entityId.
export function useDashboardStats(entityId) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .get("/dashboard/stats", entityId ? { entity_id: entityId } : undefined)
      .then((data) => {
        if (!active) return;
        setStats(data);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [entityId, reloadToken]);

  return { stats, loading, error, reload };
}
