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

function requiredRevision(revision) {
  if (!Number.isInteger(revision) || revision < 1) throw new TypeError("Indica una revisión de resultado válida.");
  return encodeURIComponent(revision);
}

function browserBasePath() {
  if (typeof document === "undefined") return "";
  const path = new URL(".", document.baseURI).pathname.replace(/\/$/, "");
  return path === "" || path === "/" ? "" : path;
}

export function createApiClient({ fetchImpl = globalThis.fetch, idFactory = defaultId, basePath = browserBasePath() } = {}) {
  const base = String(basePath ?? "").replace(/\/+$/, "").replace(/^([^/])/, "/$1");
  const resourceUrl = (path) => {
    if (!path || /^(?:[a-z]+:)?\/\//i.test(path)) return path;
    if (base && (path === base || path.startsWith(`${base}/`))) return path;
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
  };
  const json = async (path, init = {}) => {
    let response;
    try {
      response = await fetchImpl(resourceUrl(path), init);
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
    resourceUrl,
    getSession: () => json("/api/v1/session"),
    async upload(file) {
      const form = new FormData();
      form.append("file", file);
      return json("/api/v1/documents", { method: "POST", headers: { "Idempotency-Key": idFactory() }, body: form });
    },
    createRun: (documentId, mode, inputKind, table = {}) => post("/api/v1/runs", {
      document_id: documentId,
      mode,
      ...(inputKind ? { input_kind: inputKind } : {}),
      ...(table.table_profile ? { table_profile: table.table_profile } : {}),
      ...(table.proposal_mode ? { proposal_mode: table.proposal_mode } : {}),
      ...(table.table_template_id ? { table_template_id: table.table_template_id } : {}),
    }),
    createJob: (request) => post("/api/v1/jobs", request),
    getJob: (jobId) => json(`/api/v1/jobs/${encodeURIComponent(jobId)}`),
    getReplayAvailability: (request) => post("/api/v1/replay-availability", request, { idempotent: false }),
    getDocumentDrawing: (documentId, inputKind) => json(`/api/v1/documents/${encodeURIComponent(documentId)}/drawing${inputKind ? `?input_kind=${encodeURIComponent(inputKind)}` : ""}`),
    documentPreviewUrl: (documentId) => resourceUrl(`/api/v1/documents/${encodeURIComponent(documentId)}/preview.svg`),
    getRun: (runId) => json(`/api/v1/runs/${encodeURIComponent(runId)}`),
    getDrawing: (runId) => json(`/api/v1/runs/${encodeURIComponent(runId)}/drawing`),
    getLedger: (runId) => json(`/api/v1/runs/${encodeURIComponent(runId)}/ledger`),
    getRevisions: (runId) => json(`/api/v1/runs/${encodeURIComponent(runId)}/revisions`),
    getParts: (runId, revision) => json(`/api/v1/runs/${encodeURIComponent(runId)}/parts?result_revision=${requiredRevision(revision)}`),
    getTable: (runId, revision) => json(`/api/v1/runs/${encodeURIComponent(runId)}/table?result_revision=${requiredRevision(revision)}`),
    generateTableDrawings: (runId, body) => post(`/api/v1/runs/${encodeURIComponent(runId)}/table-drawings`, body),
    getTableDrawings: (runId, revision) => json(`/api/v1/runs/${encodeURIComponent(runId)}/table-drawings${Number.isInteger(revision) ? `?result_revision=${encodeURIComponent(revision)}` : ""}`),
    tableDrawingUrl: (runId, sheetId, format, revision, programHash) => {
      const query = new URLSearchParams({ result_revision: String(revision), program_hash: programHash });
      return resourceUrl(`/api/v1/runs/${encodeURIComponent(runId)}/table-drawings/${encodeURIComponent(sheetId)}.${encodeURIComponent(format)}?${query}`);
    },
    generateTableCosts: (runId, body) => post(`/api/v1/runs/${encodeURIComponent(runId)}/table-costs`, body),
    getTableCosts: (runId, revision) => json(`/api/v1/runs/${encodeURIComponent(runId)}/table-costs${Number.isInteger(revision) ? `?result_revision=${encodeURIComponent(revision)}` : ""}`),
    getTableCostCatalog: () => json("/api/v1/table-cost-catalog"),
    getExplanations: (runId, revision) => json(`/api/v1/runs/${encodeURIComponent(runId)}/explanations?result_revision=${encodeURIComponent(revision)}`),
    getScene: (runId, revision) => json(`/api/v1/runs/${encodeURIComponent(runId)}/scene?result_revision=${encodeURIComponent(revision)}`),
    getLibrary: () => json("/api/v1/library"),
    saveToLibrary: (runId, body) => post(`/api/v1/runs/${encodeURIComponent(runId)}/library`, body),
    findSimilar: (runId, body) => post(`/api/v1/runs/${encodeURIComponent(runId)}/similarity`, body),
    groupLibrary: (body) => post("/api/v1/library/groups", body),
    async getEventHistory(runId) {
      const response = await fetchImpl(resourceUrl(`/api/v1/runs/${encodeURIComponent(runId)}/events`));
      if (!response.ok) throw new ApiError("No se pudo recuperar la traza.", { status: response.status, code: "event_history_unavailable" });
      return response.text();
    },
    getComparables: (runId) => json(`/api/v1/runs/${encodeURIComponent(runId)}/comparables`),
    estimate: (runId, body = {}) => post(`/api/v1/runs/${encodeURIComponent(runId)}/estimate`, body),
    review: (runId, body) => post(`/api/v1/runs/${encodeURIComponent(runId)}/reviews`, body),
    cancel: (runId) => post(`/api/v1/runs/${encodeURIComponent(runId)}/cancel`, {}, { idempotent: false }),
    exportUrl: (runId, format) => resourceUrl(`/api/v1/runs/${encodeURIComponent(runId)}/exports?format=${encodeURIComponent(format)}`),
  };
}
