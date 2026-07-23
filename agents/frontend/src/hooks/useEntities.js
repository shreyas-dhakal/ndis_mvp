import { useEffect, useState } from "react";
import { api } from "../lib/api.js";

// List of participants/orgs for selectors (dashboard filter today, a future
// per-participant route can reuse this the same way).
export function useEntities() {
  const [entities, setEntities] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    api
      .get("/entities")
      .then((data) => active && setEntities(data || []))
      .catch((err) => active && setError(err.message));
    return () => {
      active = false;
    };
  }, []);

  return { entities, error };
}
