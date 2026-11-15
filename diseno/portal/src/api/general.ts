/**
 * Cliente HTTP de la vía de muebles generales (input_kind "general_furniture") del backend real.
 *
 * Rutas cubiertas, con método y ruta exactos de backend/app/main.py, general_furniture/router.py
 * y reconstruction3d/router.py:
 *   GET  /api/v1/config                                   → capacidades de la vía general
 *   POST /api/v1/documents                                → subir plano (multipart)
 *   POST /api/v1/jobs              (Idempotency-Key)      → crear trabajo durable
 *   GET  /api/v1/jobs/{job}                               → estado (consulta periódica)
 *   POST /api/v1/jobs/{job}/retry  (Idempotency-Key)      → reintento completo
 *   POST /api/v1/jobs/{job}/resume                        → reanudar revisión desde la propuesta guardada
 *   GET  /api/v1/runs/{run}                               → run + result
 *   GET  /api/v1/runs/{run}/drawing                       → ledger del plano (contornos con id)
 *   GET  /api/v1/runs/{run}/scene?result_revision=        → escena 3D esquemática (vía legacy; en general suele ser "unavailable")
 *   GET  /api/v1/runs/{run}/general[?proposal_revision&review_revision]
 *   POST /api/v1/runs/{run}/general/proposals             → propuesta manual (origen humano) o live (exige job)
 *   POST /api/v1/runs/{run}/general/reviews               → revisión humana
 *   POST /api/v1/runs/{run}/general/auto-review           → revisión automática (exige job durable)
 *   GET  /api/v1/runs/{run}/general/assembly?proposal_revision&review_revision
 *   GET  /api/v1/runs/{run}/general/derived?proposal_revision&review_revision
 *   GET  /api/v1/runs/{run}/general/artifacts/{id}?proposal_revision&review_revision → SVG/DXF/CSV/JSON
 *   POST /api/v1/runs/{run}/general/assembly/retry         (Idempotency-Key)
 *   POST /api/v1/runs/{run}/general/assembly/retry/{job}/cancel
 *   POST /api/v1/runs/{run}/reconstruction  (Idempotency-Key) → trabajo de reconstrucción 3D
 *   GET  /api/v1/reconstruction/{job}                     → estado y artefactos
 *   POST /api/v1/reconstruction/{job}/refine (Idempotency-Key)
 *   GET  /api/v1/reconstruction/{job}/source.png
 *   GET  /api/v1/reconstruction/{job}/artifacts/{ruta}    → assembly.glb, proposal.json, scene.json…
 *   GET  /api/v1/runs/{run}/events                        → traza completa (text/event-stream finito)
 *   GET  /api/v1/documents/{doc}  y  /documents/{doc}/original → nombre y DXF original («Abrir en CAD»)
 *   GET  /api/v1/runs/{run}/table?result_revision=        → programa de mesa evaluado (vía de vistas montadas)
 *   GET  /api/v1/runs/{run}/table-drawings?result_revision= → manifiesto de láminas; cada formato trae su URL
 *   GET  /api/v1/runs/{run}/table-costs?result_revision=  → coste guardado (404 si no hay)
 *   POST /api/v1/runs/{run}/reviews                       → revisión humana (aceptar la plantilla de mesa)
 *   POST /api/v1/runs/{run}/table-drawings  y  /table-costs → generar láminas y coste de una revisión
 *   POST /api/v1/replay-availability                      → si hay una grabación del modelo para ese plano
 *
 * Parámetros obligatorios que el backend valida con 422: general/derived, general/assembly y
 * general/artifacts piden proposal_revision y review_revision; table, table-drawings y table-costs
 * piden result_revision. Este cliente siempre los envía.
 *
 * Formas de respuesta que este cliente normaliza:
 *   - main.py responde { schema_version, data } o { schema_version, error: {code, message, retryable} }.
 *   - Los routers general y reconstruction fallan con { detail: "codigo" } (o { detail: [...] } en 422 de validación).
 *   - general/assembly y /reconstruction/* responden el objeto sin sobre { data }.
 * Todo error sale como GeneralApiError; `needsModel` marca lo que solo funciona con proveedor de modelo.
 *
 * Sin dependencias de import.meta.env: la base se inyecta para poder usarlo desde scripts de Node.
 */
import { ApiError } from "./client";
import type { TablaCoste, TablaLaminas, TablaRespuesta } from "../general/adaptador";
import type { EventoRun } from "../general/traza";
import type {
  DrawingExtraction, GeneralAssemblyState, GeneralAutoReviewRequest, GeneralDerivedResponse,
  GeneralFurnitureRecord, GeneralFurnitureReviewRequest, GeneralProposalRequest, ReconstructionRequest,
  ReconstructionScene, RefinementRequest, AssemblyProposal,
} from "./general.gen";

export type * from "./general.gen";

/** Códigos que significan «esto solo existe con el modo con modelo». */
const NEEDS_MODEL = new Set([
  "live_provider_unavailable",
  "general_live_unavailable",
  "general_live_requires_durable_job",
  "general_auto_review_unavailable",
  "general_auto_review_requires_durable_job",
  "general_assembly_unavailable",
  "reconstruction_model_unavailable",
  "general_proposal_not_found",
]);

export const NEEDS_MODEL_MESSAGE = "Requiere modelo";

const MESSAGES: Record<string, string> = {
  live_provider_unavailable: `${NEEDS_MODEL_MESSAGE}: el servidor no tiene proveedor de modelo configurado.`,
  general_live_unavailable: `${NEEDS_MODEL_MESSAGE}: la propuesta automática no está disponible en este servidor.`,
  general_live_requires_durable_job: "La propuesta automática se pide con un trabajo (POST /jobs), no directamente.",
  general_auto_review_unavailable: `${NEEDS_MODEL_MESSAGE}: la revisión automática no está disponible.`,
  general_auto_review_requires_durable_job: "La revisión automática se pide con un trabajo durable.",
  general_assembly_unavailable: `${NEEDS_MODEL_MESSAGE}: el montaje 3D no está disponible.`,
  reconstruction_model_unavailable: `${NEEDS_MODEL_MESSAGE}: la reconstrucción 3D no está disponible.`,
  general_proposal_not_found: `${NEEDS_MODEL_MESSAGE}: este análisis no tiene propuesta de piezas.`,
  general_derived_not_found: "No hay despiece derivado para esa revisión.",
  general_assembly_not_found: "No hay montaje para esa revisión.",
  general_artifact_not_found: "Ese archivo no existe en la revisión pedida.",
  general_furniture_context_required: "Este análisis no es de la vía de muebles generales.",
  general_ledger_revision_mismatch: "La propuesta se hizo sobre otra versión del plano.",
  general_furniture_revision_conflict: "La revisión cambió mientras tanto. Recarga antes de seguir.",
  manual_proposal_requires_human_origin: "Una propuesta manual tiene que declarar origen humano.",
  run_not_found: "Análisis inexistente.",
  general_run_not_found: "Análisis inexistente.",
  job_not_found: "Trabajo inexistente.",
  original_visual_evidence_required: "La reconstrucción necesita el plano original como imagen.",
  reconstruction_call_limit_reached: "Se alcanzó el límite de reconstrucciones para este análisis.",
  job_queue_full: "La cola de trabajos está completa.",
  idempotency_key_conflict: "Esa clave de idempotencia ya se usó para otra petición.",
  job_capacity_exhausted: "La cola de trabajos está completa.",
};

export class GeneralApiError extends ApiError {
  readonly needsModel: boolean;
  readonly detail: unknown;
  constructor(message: string, status: number, code: string, retryable: boolean, detail?: unknown) {
    super(message, status, code, retryable);
    this.name = "GeneralApiError";
    this.needsModel = NEEDS_MODEL.has(code);
    this.detail = detail;
  }
}

export function describeError(code: string, fallback?: string): string {
  return MESSAGES[code] ?? fallback ?? `Error del servidor (${code}).`;
}

// ---- Tipos de respuestas sin modelo Pydantic (dicts de main.py / reconstruction3d/router.py) ----

export type JobState = "queued" | "running" | "succeeded" | "failed" | "interrupted";
/** Error persistido de un job. `phase` y `run_id` solo en la vía general live. */
export interface JobError { code: string; message: string; retryable: boolean; phase?: string; run_id?: string; proposal_revision?: number | null; [extra: string]: unknown }
/** main.py: recoverable_job_view() sobre repository._get_job_in_transaction(). */
export interface JobView {
  id: string;
  state: JobState;
  run_id: string | null;
  error: JobError | null;
  retry_of_job_id?: string;
  /** Solo en GET /jobs/{id} y /resume. */
  checkpoint?: { phase: string; proposal_saved: boolean; proposal_id: string | null; proposal_revision: number; review_revision: number };
  recovery?: {
    safe_action: "resume_review" | "retry_from_start" | null; endpoint: string | null;
    attempt_kind: "review_from_saved_proposal" | "full_retry" | null; repeats_proposer: boolean;
    continues_original_provider_call: boolean; review_attempt_timeout_s: number;
    max_model_calls: number; max_validation_repairs: number; max_semantic_repairs: number;
  };
}
export const JOB_FINAL_STATES: ReadonlySet<JobState> = new Set(["succeeded", "failed", "interrupted"]);

/** GET /config → capabilities.general_furniture (dict de main.py). */
export interface GeneralCapabilities {
  available: boolean;
  live_available: boolean;
  visual_pdf_pages: boolean;
  autonomous_review: { available: boolean; reviewer_model: string | null; human_required: boolean; limits: Record<string, number> } & Record<string, unknown>;
  construction_completion: { available: boolean; dimension_states: string[]; piece_drawing_formats: string[] } & Record<string, unknown>;
}
export interface GeneralConfigSummary {
  environment: string;
  modes: string[];
  liveAvailable: boolean;
  unavailableReason: string | null;
  pollIntervalMs: number;
  general: GeneralCapabilities | null;
}

/** POST /documents (dict de main.py). */
export interface GeneralUploadedDocument { document_id: string; original_filename: string; size_bytes: number; sha256: string; source_kind: string; [extra: string]: unknown }

/** GET /runs/{id}: solo se tipan los campos que usa la vía general. */
export interface GeneralRunDetail {
  run: { id: string; mode: string; state: string; reason_code: string | null; candidate_revision: string; result_revision: number | null; created_at: string; document_id: string | null; input_kind: string; [extra: string]: unknown };
  result: { result_revision: number; state: string; input_semantics: string; [extra: string]: unknown };
  estimate: unknown;
}

export type ReconstructionStatus = "queued" | "running" | "proposed" | "insufficient_evidence" | "unsupported" | "failed" | "interrupted";
/** reconstruction3d/router.py: status.json tal cual. */
export interface ReconstructionJob {
  job_id: string;
  run_id: string;
  ledger_revision: string;
  status: ReconstructionStatus | string;
  source_sha256: string;
  source_refs: string[];
  original_image_sha256: string[];
  unit: "mm" | "relative";
  intended_use_from_user: string;
  certified_for_manufacturing: false;
  parent_job_id: string | null;
  revision: number;
  clarifications: { question: string; answer: string }[];
  envelope_mm: Record<string, number>;
  refinement_supported: boolean;
  /** Presente al terminar. */
  outcome?: { status: string; proposal: AssemblyProposal; checks: unknown; user_declarations: unknown; [extra: string]: unknown };
  /** Rutas relativas servidas por /artifacts/{ruta}; incluye "assembly.glb" cuando hay propuesta. */
  artifacts?: string[];
  error?: string;
  error_type?: string;
  partial_result_available?: boolean;
  baseline?: unknown;
  [extra: string]: unknown;
}
export const RECONSTRUCTION_FINAL_STATES = new Set(["proposed", "insufficient_evidence", "unsupported", "failed", "interrupted"]);

export interface Revisions { proposalRevision: number; reviewRevision: number }
export interface PollOptions { intervalMs?: number; timeoutMs?: number; signal?: AbortSignal; onUpdate?: (value: unknown) => void }
export interface DownloadedFile { filename: string; mediaType: string; body: string }

export interface GeneralApi {
  readonly base: string;
  config(): Promise<GeneralConfigSummary>;
  uploadDocument(file: Blob, filename: string): Promise<GeneralUploadedDocument>;
  /** Crea el trabajo. mode "live" exige proposal_mode "model_generated"; "geometry_only" exige "none". */
  submitJob(body: { document_id: string; mode: "live" | "geometry_only" }, idempotencyKey: string): Promise<JobView>;
  getJob(jobId: string): Promise<JobView>;
  /** Consulta GET /jobs/{id} hasta succeeded, failed o interrupted. */
  followJob(jobId: string, options?: PollOptions): Promise<JobView>;
  retryJob(jobId: string, idempotencyKey: string): Promise<JobView>;
  resumeJob(jobId: string): Promise<JobView>;
  getRun(runId: string): Promise<GeneralRunDetail>;
  getDrawing(runId: string): Promise<DrawingExtraction>;
  getScene(runId: string, resultRevision: number): Promise<ReconstructionScene>;
  /** null si el run no tiene propuesta (sin modelo, un job geometry_only termina así). */
  getGeneral(runId: string, revisions?: Partial<Revisions>): Promise<GeneralFurnitureRecord | null>;
  createProposal(runId: string, body: GeneralProposalRequest): Promise<GeneralFurnitureRecord>;
  createReview(runId: string, body: GeneralFurnitureReviewRequest): Promise<GeneralFurnitureRecord>;
  autoReview(runId: string, body: GeneralAutoReviewRequest): Promise<GeneralFurnitureRecord>;
  getDerived(runId: string, revisions: Revisions): Promise<GeneralDerivedResponse>;
  /** null si esa revisión no tiene montaje. */
  getAssembly(runId: string, revisions: Revisions): Promise<GeneralAssemblyState | null>;
  retryAssembly(runId: string, revisions: Revisions, idempotencyKey: string): Promise<JobView>;
  cancelAssemblyRetry(runId: string, jobId: string): Promise<{ job_id: string; cancel_requested: boolean }>;
  artifactUrl(runId: string, artifactId: string, revisions: Revisions): string;
  getArtifact(runId: string, artifactId: string, revisions: Revisions): Promise<DownloadedFile>;
  startReconstruction(runId: string, body: ReconstructionRequest, idempotencyKey: string): Promise<ReconstructionJob>;
  getReconstruction(jobId: string): Promise<ReconstructionJob>;
  followReconstruction(jobId: string, options?: PollOptions): Promise<ReconstructionJob>;
  refineReconstruction(jobId: string, body: RefinementRequest, idempotencyKey: string): Promise<ReconstructionJob>;
  reconstructionSourceUrl(jobId: string): string;
  /** Para assembly.glb: reconstructionArtifactUrl(job, "assembly.glb"). */
  reconstructionArtifactUrl(jobId: string, filename: string): string;
  /** Eventos del run con `data` como objeto. */
  getEvents(runId: string): Promise<EventoRun[]>;
  getDocument(documentId: string): Promise<{ document_id: string; original_filename: string; [extra: string]: unknown }>;
  documentOriginalUrl(documentId: string): string;
  getTable(runId: string, resultRevision: number): Promise<TablaRespuesta>;
  getTableDrawings(runId: string, resultRevision: number): Promise<TablaLaminas | null>;
  getTableCosts(runId: string, resultRevision: number): Promise<TablaCoste | null>;
  /** Texto de una ruta servida por el backend (p. ej. el SVG de una lámina de mesa). */
  getText(path: string): Promise<string>;
  /** Ruta del backend (/api/v1/…) a URL con la base del cliente. */
  absolute(path: string): string;
  /** Job de mesa sin modelo con plantilla de catálogo (mounted_orthographic_views). */
  submitTableJob(documentId: string, templateId: string, idempotencyKey: string): Promise<JobView>;
  /** Job de mesa reproduciendo una grabación real del modelo. */
  submitReplayTableJob(documentId: string, idempotencyKey: string): Promise<JobView>;
  replayAvailability(documentId: string): Promise<{ available: boolean; reason?: string; [extra: string]: unknown }>;
  createRunReview(runId: string, body: Record<string, unknown>): Promise<{ result_revision: number; state: string }>;
  createTableDrawings(runId: string, resultRevision: number): Promise<TablaLaminas>;
  createTableCosts(runId: string, resultRevision: number, scope: Record<string, unknown>): Promise<TablaCoste>;
}

const enc = encodeURIComponent;
const revQuery = (r: Revisions) => `proposal_revision=${r.proposalRevision}&review_revision=${r.reviewRevision}`;

/** Clave de idempotencia nueva. Para reintentar la misma petición, reutiliza la misma clave. */
export function newIdempotencyKey(prefix = "portal"): string {
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${random}`.slice(0, 128);
}

function errorFrom(status: number, body: unknown): GeneralApiError {
  const value = body as { error?: { code?: string; message?: string; retryable?: boolean }; detail?: unknown } | null;
  if (value?.error) {
    const code = value.error.code ?? "request_failed";
    return new GeneralApiError(describeError(code, value.error.message), status, code, Boolean(value.error.retryable), value.error);
  }
  if (typeof value?.detail === "string") {
    return new GeneralApiError(describeError(value.detail), status, value.detail, status === 429 || status === 503, value.detail);
  }
  if (Array.isArray(value?.detail)) {
    const first = value.detail[0] as { msg?: string; loc?: unknown[] } | undefined;
    const where = first?.loc ? ` (${first.loc.join(".")})` : "";
    return new GeneralApiError(`La petición no cumple el contrato${where}: ${first?.msg ?? "inválida"}.`, status, "request_validation_failed", false, value.detail);
  }
  return new GeneralApiError(`Error ${status}`, status, "request_failed", false, body);
}

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(timer); reject(new GeneralApiError("Consulta cancelada.", 0, "aborted", false)); }, { once: true });
  });

export function createGeneralClient(base = "", fetchImpl: typeof fetch = (...args) => fetch(...args)): GeneralApi {
  const root = base.replace(/\/$/, "");
  const api = `${root}/api/v1`;

  async function raw(path: string, init: RequestInit = {}): Promise<{ status: number; ok: boolean; body: unknown; response: Response }> {
    let response: Response;
    try {
      response = await fetchImpl(`${api}${path}`, init);
    } catch {
      throw new GeneralApiError("No hay conexión con el servidor de Vexplorer.", 0, "network_error", true);
    }
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      throw new GeneralApiError("El servidor devolvió una respuesta que no es JSON.", response.status, "invalid_response", false);
    }
    return { status: response.status, ok: response.ok, body, response };
  }

  /** Respuestas con sobre { data }. */
  async function enveloped<T>(path: string, init?: RequestInit): Promise<T> {
    const { ok, status, body } = await raw(path, init);
    if (!ok) throw errorFrom(status, body);
    return (body as { data: T }).data;
  }
  /** Respuestas sin sobre (general/assembly, /reconstruction/*). */
  async function bare<T>(path: string, init?: RequestInit): Promise<T> {
    const { ok, status, body } = await raw(path, init);
    if (!ok) throw errorFrom(status, body);
    return body as T;
  }
  const json = (method: string, body: unknown, key?: string): RequestInit => ({
    method,
    headers: { "Content-Type": "application/json", ...(key ? { "Idempotency-Key": key } : {}) },
    body: JSON.stringify(body),
  });
  const nullOn404 = async <T>(work: Promise<T>, codes: string[]): Promise<T | null> => {
    try {
      return await work;
    } catch (error) {
      if (error instanceof GeneralApiError && error.status === 404 && codes.includes(error.code)) return null;
      throw error;
    }
  };

  async function poll<T>(read: () => Promise<T>, done: (value: T) => boolean, options: PollOptions = {}, fallbackInterval = 500): Promise<T> {
    const interval = options.intervalMs ?? fallbackInterval;
    const deadline = Date.now() + (options.timeoutMs ?? 10 * 60_000);
    for (;;) {
      const value = await read();
      options.onUpdate?.(value);
      if (done(value)) return value;
      if (Date.now() > deadline) throw new GeneralApiError("El trabajo no terminó en el tiempo de espera del portal.", 0, "poll_timeout", true);
      await sleep(interval, options.signal);
    }
  }

  const getJob = (jobId: string) => enveloped<JobView>(`/jobs/${enc(jobId)}`);
  const getReconstruction = (jobId: string) => bare<ReconstructionJob>(`/reconstruction/${enc(jobId)}`);
  const artifactUrl = (runId: string, artifactId: string, r: Revisions) =>
    `${api}/runs/${enc(runId)}/general/artifacts/${enc(artifactId)}?${revQuery(r)}`;

  return {
    base: root,
    async config() {
      const data = await enveloped<Record<string, any>>("/config");
      return {
        environment: String(data.environment ?? ""),
        modes: Array.isArray(data.modes) ? data.modes : [],
        liveAvailable: Boolean(data.live_available),
        unavailableReason: data.unavailable_reason ?? null,
        pollIntervalMs: Number(data.run_submission?.poll_interval_ms ?? 500),
        general: data.capabilities?.general_furniture ?? null,
      };
    },
    uploadDocument(file, filename) {
      const form = new FormData();
      form.append("file", file, filename);
      return enveloped("/documents", { method: "POST", body: form });
    },
    submitJob(body, key) {
      const request = {
        document_id: body.document_id,
        mode: body.mode,
        input_kind: "general_furniture",
        proposal_mode: body.mode === "live" ? "model_generated" : "none",
      };
      return enveloped("/jobs", json("POST", request, key));
    },
    getJob,
    followJob: (jobId, options) => poll(() => getJob(jobId), (job) => JOB_FINAL_STATES.has(job.state), options),
    retryJob: (jobId, key) => enveloped(`/jobs/${enc(jobId)}/retry`, { method: "POST", headers: { "Idempotency-Key": key } }),
    resumeJob: (jobId) => enveloped(`/jobs/${enc(jobId)}/resume`, { method: "POST" }),
    getRun: (runId) => enveloped(`/runs/${enc(runId)}`),
    getDrawing: (runId) => enveloped(`/runs/${enc(runId)}/drawing`),
    getScene: (runId, rev) => enveloped(`/runs/${enc(runId)}/scene?result_revision=${rev}`),
    getGeneral(runId, revisions = {}) {
      const query = [
        revisions.proposalRevision != null ? `proposal_revision=${revisions.proposalRevision}` : "",
        revisions.reviewRevision != null ? `review_revision=${revisions.reviewRevision}` : "",
      ].filter(Boolean).join("&");
      return nullOn404(enveloped<GeneralFurnitureRecord>(`/runs/${enc(runId)}/general${query ? `?${query}` : ""}`), ["general_proposal_not_found"]);
    },
    createProposal: (runId, body) => enveloped(`/runs/${enc(runId)}/general/proposals`, json("POST", body)),
    createReview: (runId, body) => enveloped(`/runs/${enc(runId)}/general/reviews`, json("POST", body)),
    autoReview: (runId, body) => enveloped(`/runs/${enc(runId)}/general/auto-review`, json("POST", body)),
    getDerived: (runId, r) => enveloped(`/runs/${enc(runId)}/general/derived?${revQuery(r)}`),
    getAssembly: (runId, r) => nullOn404(bare<GeneralAssemblyState>(`/runs/${enc(runId)}/general/assembly?${revQuery(r)}`), ["general_assembly_not_found"]),
    retryAssembly: (runId, r, key) =>
      enveloped(`/runs/${enc(runId)}/general/assembly/retry`, json("POST", { base_proposal_revision: r.proposalRevision, base_review_revision: r.reviewRevision }, key)),
    cancelAssemblyRetry: (runId, jobId) => enveloped(`/runs/${enc(runId)}/general/assembly/retry/${enc(jobId)}/cancel`, { method: "POST" }),
    artifactUrl,
    async getArtifact(runId, artifactId, r) {
      let response: Response;
      try {
        response = await fetchImpl(artifactUrl(runId, artifactId, r));
      } catch {
        throw new GeneralApiError("No hay conexión con el servidor de Vexplorer.", 0, "network_error", true);
      }
      if (!response.ok) {
        let body: unknown = null;
        try { body = await response.json(); } catch { /* cuerpo no JSON */ }
        throw errorFrom(response.status, body);
      }
      const disposition = response.headers.get("Content-Disposition") ?? "";
      const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? artifactId;
      return { filename, mediaType: response.headers.get("Content-Type") ?? "", body: await response.text() };
    },
    startReconstruction: (runId, body, key) => bare(`/runs/${enc(runId)}/reconstruction`, json("POST", body, key)),
    getReconstruction,
    followReconstruction: (jobId, options) =>
      poll(() => getReconstruction(jobId), (job) => RECONSTRUCTION_FINAL_STATES.has(String(job.status)), options, 1500),
    refineReconstruction: (jobId, body, key) => bare(`/reconstruction/${enc(jobId)}/refine`, json("POST", body, key)),
    reconstructionSourceUrl: (jobId) => `${api}/reconstruction/${enc(jobId)}/source.png`,
    reconstructionArtifactUrl: (jobId, filename) =>
      `${api}/reconstruction/${enc(jobId)}/artifacts/${filename.split("/").map(enc).join("/")}`,
    async getEvents(runId) {
      let response: Response;
      try {
        response = await fetchImpl(`${api}/runs/${enc(runId)}/events`, { headers: { Accept: "text/event-stream" } });
      } catch {
        throw new GeneralApiError("No hay conexión con el servidor de Vexplorer.", 0, "network_error", true);
      }
      if (!response.ok) throw new GeneralApiError("No se pudo leer la traza.", response.status, "event_history_unavailable", true);
      const out: EventoRun[] = [];
      for (const raw of (await response.text()).split(String.fromCharCode(10))) {
        const line = raw.trim();
        if (!line.startsWith("data:")) continue;
        try {
          const value = JSON.parse(line.slice(5).trim()) as { sequence: number; event_type: string; data: Record<string, unknown> };
          if (!out.some((item) => item.sequence === value.sequence)) out.push({ sequence: value.sequence, event_type: value.event_type, data: value.data });
        } catch { /* línea incompleta */ }
      }
      return out;
    },
    getDocument: (documentId) => enveloped(`/documents/${enc(documentId)}`),
    documentOriginalUrl: (documentId) => `${api}/documents/${enc(documentId)}/original`,
    getTable: (runId, rev) => enveloped(`/runs/${enc(runId)}/table?result_revision=${rev}`),
    getTableDrawings: (runId, rev) => nullOn404(enveloped<TablaLaminas>(`/runs/${enc(runId)}/table-drawings?result_revision=${rev}`), ["table_drawings_not_found"]),
    getTableCosts: (runId, rev) => nullOn404(enveloped<TablaCoste>(`/runs/${enc(runId)}/table-costs?result_revision=${rev}`), ["table_cost_not_found"]),
    async getText(path) {
      const response = await fetchImpl(path.startsWith("http") ? path : `${root}${path}`);
      if (!response.ok) throw new GeneralApiError(`No se pudo leer ${path}.`, response.status, "artifact_unavailable", false);
      return response.text();
    },
    absolute: (path) => (path.startsWith("http") ? path : `${root}${path}`),
    submitTableJob: (documentId, templateId, key) => enveloped("/jobs", json("POST", {
      document_id: documentId, mode: "geometry_only", input_kind: "mounted_orthographic_views",
      table_profile: "rectangular_table_v1", proposal_mode: "catalog_baseline", table_template_id: templateId,
    }, key)),
    submitReplayTableJob: (documentId, key) => enveloped("/jobs", json("POST", {
      document_id: documentId, mode: "recorded_replay", input_kind: "mounted_orthographic_views",
      table_profile: "rectangular_table_v1", proposal_mode: "model_generated",
    }, key)),
    replayAvailability: (documentId) => enveloped("/replay-availability", json("POST", {
      document_id: documentId, mode: "recorded_replay", input_kind: "mounted_orthographic_views",
      table_profile: "rectangular_table_v1", proposal_mode: "model_generated",
    })),
    createRunReview: (runId, body) => enveloped(`/runs/${enc(runId)}/reviews`, json("POST", body)),
    createTableDrawings: (runId, rev) => enveloped(`/runs/${enc(runId)}/table-drawings`, json("POST", { result_revision: rev })),
    createTableCosts: (runId, rev, scope) => enveloped(`/runs/${enc(runId)}/table-costs`, json("POST", { result_revision: rev, scope })),
  };
}
