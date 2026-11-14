const TERMINAL_STATES = new Set(["succeeded", "failed", "interrupted"]);

function abortError() {
  return new DOMException("Operación cancelada", "AbortError");
}

export async function pollJob(jobId, { getJob, onUpdate = () => {}, wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)), intervalMs = 500, signal } = {}) {
  if (!jobId || typeof getJob !== "function") throw new TypeError("El job y su consulta son obligatorios.");
  while (true) {
    if (signal?.aborted) throw abortError();
    const raw = await getJob(jobId);
    if (signal?.aborted) throw abortError();
    const job = { id: raw?.id ?? jobId, state: raw?.state ?? "failed", runId: raw?.run_id ?? null, error: raw?.error ?? null };
    await onUpdate(job);
    if (TERMINAL_STATES.has(job.state)) return job;
    await wait(intervalMs);
  }
}

export function jobStatusLabel(job) {
  return ({ queued: "En cola", running: "Analizando", succeeded: "Análisis terminado", failed: "Análisis fallido", interrupted: "Análisis interrumpido" })[job?.state] ?? "Estado del trabajo desconocido";
}
