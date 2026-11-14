const RUN_KEY = "vexplorer.run_id";
const JOB_KEY = "vexplorer.job";

function updatedUrl(location, runId) {
  const params = new URLSearchParams(location.search ?? "");
  if (runId) params.set("run", runId); else params.delete("run");
  const search = params.toString();
  return `${location.pathname ?? "/"}${search ? `?${search}` : ""}${location.hash ?? ""}`;
}

export function restoreRunId(location, storage) {
  const fromUrl = new URLSearchParams(location?.search ?? "").get("run");
  return fromUrl || storage?.getItem(RUN_KEY) || null;
}

export function restoredRunRecovery(runId, error = {}) {
  const validRunId = typeof runId === "string" && /^run-[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(runId);
  if (!validRunId) return { discard: true, retry: false, reason: "invalid_run_id" };
  if (error?.status === 404 && error?.code === "run_not_found") return { discard: true, retry: false, reason: "run_not_found" };
  return { discard: false, retry: true, reason: "temporarily_unavailable" };
}

export function persistRunId(runId, storage, location, history) {
  storage?.setItem(RUN_KEY, runId);
  storage?.removeItem(JOB_KEY);
  history?.replaceState(null, "", updatedUrl(location, runId));
}

export function clearRunSession(storage, location, history) {
  storage?.removeItem(RUN_KEY);
  storage?.removeItem(JOB_KEY);
  history?.replaceState(null, "", updatedUrl(location, null));
}

export function persistJob(job, storage) {
  if (!job?.id) return;
  storage?.setItem(JOB_KEY, JSON.stringify({ id: job.id, run_id: job.run_id ?? null, state: job.state ?? "queued" }));
}

export function restoreJob(storage) {
  try {
    const job = JSON.parse(storage?.getItem(JOB_KEY) ?? "null");
    return job && typeof job.id === "string" && typeof job.state === "string" ? job : null;
  } catch {
    return null;
  }
}
