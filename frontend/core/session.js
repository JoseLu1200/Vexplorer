const RUN_KEY = "vexplorer.run_id";
const JOB_KEY = "vexplorer.job";

export function createResilientStorage(primary) {
  const memory = new Map();
  const removed = new Set();
  return {
    getItem(key) {
      if (memory.has(key)) return memory.get(key);
      if (removed.has(key)) return null;
      try { return primary?.getItem(key) ?? null; } catch { return null; }
    },
    setItem(key, value) {
      const stringValue = String(value); memory.set(key, stringValue); removed.delete(key);
      try { primary?.setItem(key, stringValue); } catch { /* memory remains authoritative */ }
    },
    removeItem(key) {
      memory.delete(key); removed.add(key);
      try { primary?.removeItem(key); } catch { /* tombstone hides stale primary data */ }
    },
  };
}

export function browserStorage(scope = globalThis) {
  let primary = null;
  try { primary = scope?.localStorage ?? null; } catch { /* opaque or blocked origin */ }
  return createResilientStorage(primary);
}

function replaceUrl(history, url) {
  try { history?.replaceState(null, "", url); } catch { /* URL fallback unavailable on opaque origins */ }
}

function updatedUrl(location, runId) {
  const params = new URLSearchParams(location.search ?? "");
  if (runId) params.set("run", runId); else params.delete("run");
  const search = params.toString();
  return `${location.pathname ?? "/"}${search ? `?${search}` : ""}${location.hash ?? ""}`;
}

export function restoreRunId(location, storage) {
  const fromUrl = new URLSearchParams(location?.search ?? "").get("run");
  if (fromUrl) return fromUrl;
  try { return storage?.getItem(RUN_KEY) || null; } catch { return null; }
}

export function restoredRunRecovery(runId, error = {}) {
  const validRunId = typeof runId === "string" && /^run-[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(runId);
  if (!validRunId) return { discard: true, retry: false, reason: "invalid_run_id" };
  if (error?.status === 404 && error?.code === "run_not_found") return { discard: true, retry: false, reason: "run_not_found" };
  return { discard: false, retry: true, reason: "temporarily_unavailable" };
}

export function persistRunId(runId, storage, location, history) {
  try { storage?.setItem(RUN_KEY, runId); } catch { /* URL remains the durable fallback */ }
  try { storage?.removeItem(JOB_KEY); } catch { /* stale storage must not block navigation */ }
  replaceUrl(history, updatedUrl(location, runId));
}

export function clearRunSession(storage, location, history) {
  try { storage?.removeItem(RUN_KEY); } catch { /* URL clearing still proceeds */ }
  try { storage?.removeItem(JOB_KEY); } catch { /* best effort */ }
  replaceUrl(history, updatedUrl(location, null));
}

export function persistJob(job, storage) {
  if (!job?.id) return;
  if (job.state === "cancelled") { try { storage?.removeItem(JOB_KEY); } catch { /* best effort */ } return; }
  try { storage?.setItem(JOB_KEY, JSON.stringify({ id: job.id, run_id: job.run_id ?? null, state: job.state ?? "queued" })); } catch { /* in-memory state still follows the job */ }
}

export function restoreJob(storage) {
  try {
    const job = JSON.parse(storage?.getItem(JOB_KEY) ?? "null");
    return job && typeof job.id === "string" && typeof job.state === "string" ? job : null;
  } catch {
    return null;
  }
}
