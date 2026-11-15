import { useCallback, useEffect, useState } from "react";
import { toAppError, type AppError } from "../state";

/** Carga asíncrona con estados de carga y error explícitos. */
export function useApi<T>(load: (() => Promise<T>) | null, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<AppError | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!load) return;
    let alive = true;
    setLoading(true);
    setError(null);
    load()
      .then((value) => { if (alive) setData(value); })
      .catch((err) => { if (alive) setError(toAppError(err)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const retry = useCallback(() => setTick((value) => value + 1), []);
  return { data, error, loading, retry, setData };
}
