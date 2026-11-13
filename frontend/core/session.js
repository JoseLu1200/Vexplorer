const RUN_KEY = "vexplorer.run_id";

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

export function persistRunId(runId, storage, location, history) {
  storage?.setItem(RUN_KEY, runId);
  history?.replaceState(null, "", updatedUrl(location, runId));
}

export function clearRunSession(storage, location, history) {
  storage?.removeItem(RUN_KEY);
  history?.replaceState(null, "", updatedUrl(location, null));
}
