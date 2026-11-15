/**
 * Cliente HTTP del backend real. Una función por ruta de backend/app/main.py, con método y ruta exactos.
 * Base URL por VITE_API_BASE (vacía = mismo origen; el backend no declara CORS).
 */
import type {
  AppConfig, CreatedRun, DrawingExtraction, Estimate, ExplanationBundle, GroupRequest, InputKind, LibraryItem,
  LibrarySaveRequest, PartsView, ReconstructionScene, Result, ReviewRequest, RunDetail, RunEvent, RunMode,
  SimilarityGroup, SimilarityMatch, SimilarityRequest, UploadedDocument, Comparable, ApiErrorBody,
} from "./types";
import { parseEventStream } from "./sse";

export class ApiError extends Error {
  status: number;
  code: string;
  retryable: boolean;
  constructor(message: string, status: number, code: string, retryable = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

/** Interfaz común a cliente real y mock. */
export interface VexplorerApi {
  readonly isMock: boolean;
  health(): Promise<{ status: string }>;
  getConfig(): Promise<AppConfig>;
  uploadDocument(file: File): Promise<UploadedDocument>;
  getDocumentDrawing(documentId: string, inputKind?: InputKind): Promise<DrawingExtraction>;
  documentPreviewUrl(documentId: string): string;
  createRun(body: { document_id: string; mode: RunMode; input_kind?: InputKind }): Promise<CreatedRun>;
  getRun(runId: string): Promise<RunDetail>;
  getRevisions(runId: string): Promise<Result[]>;
  getParts(runId: string, resultRevision: number): Promise<PartsView>;
  getExplanations(runId: string, resultRevision: number): Promise<ExplanationBundle>;
  getScene(runId: string, resultRevision: number): Promise<ReconstructionScene>;
  getLedger(runId: string): Promise<DrawingExtraction>;
  getDrawing(runId: string): Promise<DrawingExtraction>;
  createReview(runId: string, body: ReviewRequest): Promise<Result>;
  getComparables(runId: string, limit?: number): Promise<Comparable[]>;
  saveToLibrary(runId: string, body: LibrarySaveRequest): Promise<LibraryItem>;
  getLibrary(): Promise<LibraryItem[]>;
  findSimilar(runId: string, body: SimilarityRequest): Promise<SimilarityMatch[]>;
  groupLibrary(body: GroupRequest): Promise<SimilarityGroup[]>;
  createEstimate(runId: string, body: { result_revision: number }): Promise<Estimate>;
  /** Devuelve el contenido exportado de la revisión vigente (el backend no admite elegir revisión). */
  getExport(runId: string, format: "json" | "csv"): Promise<{ filename: string; mediaType: string; body: string }>;
  exportUrl(runId: string, format: "json" | "csv"): string | null;
  /**
   * Eventos del run. El backend real responde un text/event-stream finito (historial completo y cierre),
   * así que no se usa EventSource, que reconectaría y repetiría el historial. Se descartan duplicados por sequence.
   */
  streamEvents(runId: string, onEvent: (event: RunEvent) => void, signal?: AbortSignal): Promise<void>;
}

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const enc = encodeURIComponent;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError("No hay conexión con el servidor de Vexplorer.", 0, "network_error", true);
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError("El servidor devolvió una respuesta que no es JSON.", response.status, "invalid_response");
  }
  if (!response.ok) {
    const error = (body as ApiErrorBody)?.error;
    throw new ApiError(error?.message ?? `Error ${response.status}`, response.status, error?.code ?? "request_failed", Boolean(error?.retryable));
  }
  return (body as { data: T }).data;
}

const postJson = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function createHttpClient(): VexplorerApi {
  return {
    isMock: false,
    health: () => request("/api/v1/health"),
    getConfig: () => request("/api/v1/config"),
    uploadDocument(file) {
      const form = new FormData();
      form.append("file", file);
      return request("/api/v1/documents", { method: "POST", body: form });
    },
    getDocumentDrawing: (documentId, inputKind) =>
      request(`/api/v1/documents/${enc(documentId)}/drawing${inputKind ? `?input_kind=${enc(inputKind)}` : ""}`),
    documentPreviewUrl: (documentId) => `${BASE}/api/v1/documents/${enc(documentId)}/preview.svg`,
    createRun: (body) => postJson("/api/v1/runs", body),
    getRun: (runId) => request(`/api/v1/runs/${enc(runId)}`),
    getRevisions: (runId) => request(`/api/v1/runs/${enc(runId)}/revisions`),
    getParts: (runId, rev) => request(`/api/v1/runs/${enc(runId)}/parts?result_revision=${rev}`),
    getExplanations: (runId, rev) => request(`/api/v1/runs/${enc(runId)}/explanations?result_revision=${rev}`),
    getScene: (runId, rev) => request(`/api/v1/runs/${enc(runId)}/scene?result_revision=${rev}`),
    getLedger: (runId) => request(`/api/v1/runs/${enc(runId)}/ledger`),
    getDrawing: (runId) => request(`/api/v1/runs/${enc(runId)}/drawing`),
    createReview: (runId, body) => postJson(`/api/v1/runs/${enc(runId)}/reviews`, body),
    getComparables: (runId, limit = 3) => request(`/api/v1/runs/${enc(runId)}/comparables?limit=${limit}`),
    saveToLibrary: (runId, body) => postJson(`/api/v1/runs/${enc(runId)}/library`, body),
    getLibrary: () => request("/api/v1/library"),
    findSimilar: (runId, body) => postJson(`/api/v1/runs/${enc(runId)}/similarity`, body),
    groupLibrary: (body) => postJson("/api/v1/library/groups", body),
    createEstimate: (runId, body) => postJson(`/api/v1/runs/${enc(runId)}/estimate`, body),
    async getExport(runId, format) {
      const response = await fetch(`${BASE}/api/v1/runs/${enc(runId)}/exports?format=${format}`);
      if (!response.ok) throw new ApiError("No se pudo generar la exportación.", response.status, "export_failed");
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `${runId}.${format}`;
      return { filename, mediaType: response.headers.get("Content-Type") ?? "", body: await response.text() };
    },
    exportUrl: (runId, format) => `${BASE}/api/v1/runs/${enc(runId)}/exports?format=${format}`,
    async streamEvents(runId, onEvent, signal) {
      const response = await fetch(`${BASE}/api/v1/runs/${enc(runId)}/events`, { signal, headers: { Accept: "text/event-stream" } });
      if (!response.ok || !response.body) throw new ApiError("No se pudo leer la traza del análisis.", response.status, "event_history_unavailable", true);
      const seen = new Set<number>();
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        const cut = buffer.lastIndexOf("\n\n");
        if (cut >= 0) {
          for (const event of parseEventStream(buffer.slice(0, cut + 2))) {
            if (seen.has(event.sequence)) continue;
            seen.add(event.sequence);
            onEvent(event);
          }
          buffer = buffer.slice(cut + 2);
        }
        if (done) break;
      }
    },
  };
}
