const TERMINAL_STATES = new Set(["succeeded", "failed", "interrupted", "cancelled"]);

function abortError() {
  return new DOMException("Operación cancelada", "AbortError");
}

function timeoutError() {
  return new DOMException("La espera local alcanzó 600 segundos. El trabajo continúa guardado en el servidor; recarga para retomar su seguimiento.", "TimeoutError");
}

export async function pollJob(jobId, { getJob, onUpdate = () => {}, wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)), now = () => Date.now(), intervalMs = 500, timeoutMs = 600_000, signal } = {}) {
  if (!jobId || typeof getJob !== "function") throw new TypeError("El job y su consulta son obligatorios.");
  const startedAt=now();
  while (true) {
    if (signal?.aborted) throw abortError();
    if (now()-startedAt>=timeoutMs) throw timeoutError();
    const raw = await getJob(jobId);
    if (signal?.aborted) throw abortError();
    const job = { id: raw?.id ?? jobId, state: raw?.state ?? "failed", runId: raw?.run_id ?? null, error: raw?.error ?? null, cause:raw?.error?.reason_code??raw?.cause??raw?.error?.code??null, checkpoint:raw?.checkpoint??null, recovery:raw?.recovery??null, queuePosition:Number.isInteger(raw?.queue_position)?raw.queue_position:null, cancelRequested:raw?.cancel_requested===true, canCancel:raw?.can_cancel===true };
    await onUpdate(job);
    if (TERMINAL_STATES.has(job.state)) return job;
    await wait(intervalMs);
  }
}

export function jobStatusLabel(job) {
  if (job?.cancelRequested && ["queued", "running"].includes(job.state)) return "Cancelación solicitada…";
  if (job?.state === "queued" && Number.isInteger(job.queuePosition)) return `En cola · posición ${job.queuePosition}`;
  return ({ queued: "En cola", running: "Analizando", succeeded: "Análisis terminado", failed: "Análisis fallido", interrupted: "Análisis interrumpido", cancelled: "Análisis cancelado" })[job?.state] ?? "Estado del trabajo desconocido";
}
