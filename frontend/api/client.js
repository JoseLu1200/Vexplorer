export class ApiError extends Error {
  constructor(message, { status = 0, code = "network_error", details = {}, retryable = false } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.retryable = retryable;
  }
}

async function readJson(response) {
  let envelope;
  try {
    envelope = await response.json();
  } catch {
    throw new ApiError("El servidor devolvió una respuesta no válida.", { status: response.status, code: "invalid_response" });
  }
  if (!response.ok) {
    const error = envelope?.error ?? {};
    throw new ApiError(error.message ?? `La solicitud falló con estado ${response.status}.`, {
      status: response.status,
      code: error.code ?? "request_failed",
      details: error.details ?? {},
      retryable: Boolean(error.retryable),
    });
  }
  return envelope?.data ?? envelope;
}

function defaultId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createApiClient({ fetchImpl = globalThis.fetch, idFactory = defaultId } = {}) {
  const json = async (path, init = {}) => {
    let response;
    try {
      response = await fetchImpl(path, init);
    } catch (cause) {
      throw new ApiError("No se pudo conectar con Vexplorer.", { code: "network_error", retryable: true, details: { cause: cause?.message } });
    }
    return readJson(response);
  };
  const post = (path, body, { idempotent = true } = {}) => json(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(idempotent ? { "Idempotency-Key": idFactory() } : {}),
    },
    body: JSON.stringify(body),
  });

  return {
    getConfig: () => json("/api/v1/config"),
    async upload(file) {
      const form = new FormData();
      form.append("file", file);
      return json("/api/v1/documents", { method: "POST", headers: { "Idempotency-Key": idFactory() }, body: form });
    },
    createRun: (documentId, mode) => post("/api/v1/runs", { document_id: documentId, mode }),
    getRun: (runId) => json(`/api/v1/runs/${encodeURIComponent(runId)}`),
    getDrawing: (runId) => json(`/api/v1/runs/${encodeURIComponent(runId)}/drawing`),
    getLedger: (runId) => json(`/api/v1/runs/${encodeURIComponent(runId)}/ledger`),
    async getEventHistory(runId) {
      const response = await fetchImpl(`/api/v1/runs/${encodeURIComponent(runId)}/events`);
      if (!response.ok) throw new ApiError("No se pudo recuperar la traza.", { status: response.status, code: "event_history_unavailable" });
      return response.text();
    },
    getComparables: (runId) => json(`/api/v1/runs/${encodeURIComponent(runId)}/comparables`),
    estimate: (runId, body = {}) => post(`/api/v1/runs/${encodeURIComponent(runId)}/estimate`, body),
    review: (runId, body) => post(`/api/v1/runs/${encodeURIComponent(runId)}/reviews`, body),
    cancel: (runId) => post(`/api/v1/runs/${encodeURIComponent(runId)}/cancel`, {}, { idempotent: false }),
    exportUrl: (runId, format) => `/api/v1/runs/${encodeURIComponent(runId)}/exports?format=${encodeURIComponent(format)}`,
  };
}
