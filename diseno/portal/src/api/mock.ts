/**
 * Implementación de ejemplo con la misma interfaz que el cliente real.
 *
 * Los datos son respuestas reales del backend de Vexplorer capturadas al ejecutarlo en proceso contra los
 * fixtures públicos de data/planos_demo (piezas_espesor_desconocido.dxf, piezas_qty_desconocida.dxf,
 * piezas_ambigua_sin_id.dxf, piezas_completo.dxf, piezas_dimensiones_variante.dxf, piezas_espesor_36.dxf).
 * El mock no calcula medidas: elige la respuesta grabada que corresponde a cada petición.
 *
 * Única excepción: el modo `live` no se pudo grabar sin clave de proveedor. Sus eventos `tool_completed`
 * se componen con los nombres de herramienta y los textos de resumen literales de backend/app/agente/runner.py
 * y con IDs de evidencia reales del ledger. La interfaz rotula todo el modo mock como «Datos de ejemplo».
 */
import { ApiError, type VexplorerApi } from "./client";
import { parseEventStream } from "./sse";
import type {
  AppConfig, CreatedRun, DrawingExtraction, Estimate, ExplanationBundle, LibraryItem, ReconstructionScene, Result,
  RunEvent, RunSnapshot, SimilarityGroup, SimilarityMatch, UploadedDocument, Comparable, ReviewRequest,
} from "./types";
import principalRaw from "./fixtures/principal.json";
import conflictoRaw from "./fixtures/conflicto.json";
import qtyRaw from "./fixtures/qty.json";
import ambiguaRaw from "./fixtures/ambigua.json";
import configRaw from "./fixtures/config.json";
import libraryRaw from "./fixtures/library.json";
import similarityRaw from "./fixtures/similarity_principal.json";
import groupsRaw from "./fixtures/groups.json";
import semanticErrorRaw from "./fixtures/similarity_semantic_error.json";
import replayErrorRaw from "./fixtures/error_replay.json";
import libraryDrawingsRaw from "./fixtures/library_drawings.json";

type Raw = { status: number; body: { error: { code: string; message: string; retryable: boolean } } } | { status: number; body: { data: unknown } };

interface Fixture {
  document: UploadedDocument;
  create_run: CreatedRun;
  run_drawing: DrawingExtraction;
  explanations_r1: ExplanationBundle;
  scene_r1: ReconstructionScene;
  estimate_r1_error: Raw;
  comparables: Comparable[];
  events_text: string;
  export_csv: string;
  review_r2?: Result;
  scene_r2?: ReconstructionScene;
  explanations_r2?: ExplanationBundle;
  estimate_raw?: Raw;
  library_item?: LibraryItem;
}

const principal = principalRaw as unknown as Fixture & { error_observed_override: Raw; error_stale: Raw };
const conflicto = conflictoRaw as unknown as { review_r2: Result; scene_r2: ReconstructionScene; explanations_r2: ExplanationBundle; estimate_raw: Raw };
const FIXTURES: Record<string, Fixture> = { principal, qty: qtyRaw as unknown as Fixture, ambigua: ambiguaRaw as unknown as Fixture };

/** Planos de ejemplo disponibles solo en modo mock. Nombres de archivo reales de data/planos_demo. */
export const MOCK_SAMPLES = [
  { filename: "piezas_espesor_desconocido.dxf", fixture: "principal" },
  { filename: "piezas_qty_desconocida.dxf", fixture: "qty" },
  { filename: "piezas_ambigua_sin_id.dxf", fixture: "ambigua" },
] as const;

/** Contornos del ledger grabado de un plano de ejemplo, para la vista previa de Carga (solo mock). */
export function mockSamplePreview(filename: string) {
  const sample = MOCK_SAMPLES.find((item) => item.filename === filename);
  if (!sample) return null;
  const drawing = FIXTURES[sample.fixture].run_drawing;
  return { contours: drawing.contours, views: drawing.views, texts: drawing.texts, unit: drawing.coordinate_unit, count: drawing.contours.length };
}

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const wait = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(id); reject(new DOMException("aborted", "AbortError")); });
  });

function fail(raw: Raw): never {
  const error = "error" in raw.body ? raw.body.error : { code: "mock_error", message: "Error", retryable: false };
  throw new ApiError(error.message, raw.status, error.code, error.retryable);
}

function fixtureFor(filename: string): string {
  const name = filename.toLowerCase();
  if (name.includes("qty") || name.includes("cantidad")) return "qty";
  if (name.includes("ambigua") || name.includes("sin_id")) return "ambigua";
  return "principal";
}

interface RunState {
  fixture: string;
  run: RunSnapshot;
  revisions: Result[];
  scenes: Record<number, ReconstructionScene>;
  explanations: Record<number, ExplanationBundle>;
  estimate: Estimate | null;
  events: RunEvent[];
  drawing: DrawingExtraction;
}

export function createMockClient(): VexplorerApi {
  const documents = new Map<string, { fixture: string; doc: UploadedDocument }>();
  const runs = new Map<string, RunState>();
  const savedLibrary = new Map<string, LibraryItem>();

  const config: AppConfig = {
    ...(configRaw as unknown as AppConfig),
    // El backend capturado no tenía proveedor; el mock habilita `live` para enseñar la traza del agente.
    live_available: true,
    unavailable_reason: null,
    model: "modelo-de-ejemplo",
    modes: ["geometry_only", "live"],
  };

  const runOf = (runId: string) => {
    const state = runs.get(runId);
    if (!state) throw new ApiError("Ejecución inexistente.", 404, "run_not_found");
    return state;
  };
  const resultOf = (state: RunState, revision?: number) => {
    const value = revision === undefined ? state.revisions[state.revisions.length - 1] : state.revisions.find((item) => item.result_revision === revision);
    if (!value) throw new ApiError("Revisión inexistente.", 404, "result_not_found");
    return value;
  };
  const pushEvent = (state: RunState, event_type: string, data: Record<string, unknown>) => {
    state.events.push({ schema_version: "0.2.0", run_id: state.run.id, sequence: state.events.length + 1, event_type, data: { timestamp: new Date().toISOString(), ...data } });
  };

  const api: VexplorerApi = {
    isMock: true,
    async health() { return { status: "ok" }; },
    async getConfig() { await wait(120); return clone(config); },

    async uploadDocument(file) {
      await wait(450);
      if (!file.name.toLowerCase().endsWith(".dxf")) throw new ApiError("La demo admite exclusivamente DXF.", 415, "unsupported_format");
      if (file.size > 20 * 1024 * 1024) throw new ApiError("El archivo supera 20 MiB.", 413, "upload_too_large");
      const fixture = fixtureFor(file.name);
      const doc = { ...clone(FIXTURES[fixture].document), original_filename: file.name, size_bytes: file.size || FIXTURES[fixture].document.size_bytes };
      documents.set(doc.document_id, { fixture, doc });
      return doc;
    },
    async getDocumentDrawing(documentId) {
      const entry = documents.get(documentId);
      if (!entry) throw new ApiError("Documento inexistente.", 404, "document_not_found");
      return clone(FIXTURES[entry.fixture].run_drawing);
    },
    documentPreviewUrl: () => "",

    async createRun({ document_id, mode }) {
      if (mode === "recorded_replay") fail(replayErrorRaw as Raw);
      const entry = documents.get(document_id);
      if (!entry) throw new ApiError("Documento inexistente.", 404, "document_not_found");
      await wait(mode === "live" ? 2600 : 1200);
      const fx = FIXTURES[entry.fixture];
      const created = clone(fx.create_run);
      const events = parseEventStream(fx.events_text).filter((event) => event.sequence <= 3);
      if (mode === "live") {
        const candidate = created.result.assembly_candidates[0];
        created.run.mode = "live";
        created.run.agent_selected_assembly_candidate_id = candidate?.id ?? null;
        const stamp = events[0]?.data.timestamp;
        const tools: RunEvent["data"][] = (created.result.part_analysis?.observations ?? []).map((observation) => ({
          timestamp: stamp, tool_name: "inspeccionar_pieza", ok: true, evidence_ids: observation.evidence_ids,
          summary: "Observación de pieza y sus fuentes inspeccionadas.", selected_scenario_id: null, selected_assembly_candidate_id: null,
        }));
        if (candidate) tools.push({ timestamp: stamp, tool_name: "entregar_candidato_montaje", ok: true, evidence_ids: [], summary: "Candidato hipotético entregado para revisión humana.", selected_scenario_id: null, selected_assembly_candidate_id: candidate.id });
        const head = { ...events[0], data: { ...events[0].data, mode: "live" } };
        const tail = events.slice(1);
        const all = [head, ...tools.map((data) => ({ ...head, event_type: "tool_completed", data })), ...tail];
        events.splice(0, events.length, ...all.map((event, index) => ({ ...event, sequence: index + 1 })));
      }
      const state: RunState = {
        fixture: entry.fixture, run: created.run, revisions: [created.result], scenes: { 1: clone(fx.scene_r1) },
        explanations: { 1: clone(fx.explanations_r1) }, estimate: null, events, drawing: clone(fx.run_drawing),
      };
      runs.set(created.run.id, state);
      return clone(created);
    },
    async getRun(runId) {
      await wait(80);
      const state = runOf(runId);
      const result = resultOf(state);
      return clone({ run: { ...state.run, result_revision: result.result_revision }, result, estimate: state.estimate?.result_revision === result.result_revision ? state.estimate : null });
    },
    async getRevisions(runId) { await wait(80); return clone(runOf(runId).revisions); },
    async getParts(runId, revision) {
      const result = resultOf(runOf(runId), revision);
      if (!result.part_analysis) throw new ApiError("La ejecución no contiene vistas de piezas separadas.", 409, "parts_analysis_unavailable");
      return clone({ part_analysis: result.part_analysis, assembly_candidates: result.assembly_candidates, selected_assembly_candidate_id: result.selected_assembly_candidate_id });
    },
    async getExplanations(runId, revision) {
      const state = runOf(runId);
      resultOf(state, revision);
      return clone(state.explanations[revision] ?? state.explanations[1]);
    },
    async getScene(runId, revision) {
      await wait(150);
      const state = runOf(runId);
      resultOf(state, revision);
      return clone(state.scenes[revision] ?? state.scenes[1]);
    },
    async getLedger(runId) { return clone(runOf(runId).drawing); },
    async getDrawing(runId) {
      await wait(100);
      const library = (libraryDrawingsRaw as unknown as Record<string, { drawing_id: string; source_unit: DrawingExtraction["source_unit"]; coordinate_unit: DrawingExtraction["coordinate_unit"]; contours: DrawingExtraction["contours"] }>)[runId];
      if (!runs.has(runId) && library) {
        // Ledger reducido a contornos: suficiente para la miniatura de la biblioteca.
        return {
          schema_version: "0.2.0", drawing_id: library.drawing_id, input_kind: "separated_part_views", status: "ready", source_unit: library.source_unit,
          unit_scale_to_mm: 1, coordinate_unit: library.coordinate_unit, entities: [], views: [], contours: clone(library.contours), dimensions: [],
          evidence: [], observations: [], texts: [], dimension_graphics: [], warnings: [], synthetic: false,
        } satisfies DrawingExtraction;
      }
      return clone(runOf(runId).drawing);
    },

    async createReview(runId, body: ReviewRequest) {
      await wait(700);
      const state = runOf(runId);
      const current = resultOf(state);
      if (body.base_result_revision !== current.result_revision) fail(principal.error_stale);
      const analysis = current.part_analysis;
      const candidate = current.assembly_candidates.find((item) => item.id === body.assembly_candidate_id);
      if (!analysis || !candidate) throw new ApiError("La revisión no es aplicable.", 422, "assembly_candidate_required");
      const observations = new Map(analysis.observations.map((item) => [item.id, item]));
      for (const decision of body.decisions ?? []) {
        const use = candidate.uses.find((item) => item.id === decision.proposal_id);
        const observation = use ? observations.get(use.part_observation_id) : undefined;
        if (!use || !observation) throw new ApiError("La revisión no es aplicable.", 422, "unknown_proposal");
        for (const field of ["length", "width", "thickness"] as const) {
          const value = decision[`${field}_mm`];
          const observed = observation.dimensions[field];
          if (value != null && observed.state === "observed" && Math.abs(value - (observed.value_mm ?? 0)) > 0.1) fail(principal.error_observed_override);
        }
      }
      const recorded = state.fixture === "principal" ? principal.review_r2 : FIXTURES[state.fixture].review_r2;
      if (!recorded || candidate.id !== recorded.selected_assembly_candidate_id) {
        throw new ApiError("Solo está disponible la revisión guardada del primer candidato de montaje.", 422, "mock_review_unavailable");
      }
      const thickness = (body.decisions ?? []).find((item) => item.thickness_mm != null)?.thickness_mm;
      const useConflict = state.fixture === "principal" && thickness != null && Math.abs(thickness - 18) > 0.1;
      const revision = current.result_revision + 1;
      const next = clone(useConflict ? conflicto.review_r2 : recorded);
      next.run_id = runId;
      next.result_revision = revision;
      next.created_at = new Date().toISOString();
      next.review = { ...next.review!, reviewer_name: body.reviewer_name, reason: body.notes ?? next.review!.reason, timestamp: next.created_at };
      for (const piece of next.pieces) {
        const decision = (body.decisions ?? []).find((item) => item.proposal_id === piece.proposal_id);
        if (decision?.notes) piece.human_confirmation = decision.notes;
        else if (body.notes) piece.human_confirmation = body.notes;
        // Como el backend (repository._review_parts): material de la decisión, si no el de la petición,
        // si no el de la pieza de la revisión anterior con el mismo candidato; si no hay ninguno, desconocido.
        const before = current.selected_assembly_candidate_id === candidate.id ? current.pieces.find((item) => item.proposal_id === piece.proposal_id) : undefined;
        piece.material = decision?.material ?? body.material ?? before?.material ?? null;
        piece.finish = decision?.finish ?? body.finish ?? before?.finish ?? null;
        piece.field_states = { ...piece.field_states, material: piece.material ? "confirmed" : "unknown", finish: piece.finish ? "confirmed" : "unknown" };
      }
      state.revisions.push(next);
      state.scenes[revision] = clone(useConflict ? conflicto.scene_r2 : (FIXTURES[state.fixture].scene_r2 ?? principal.scene_r2!));
      state.scenes[revision].result_revision = revision;
      state.explanations[revision] = clone(useConflict ? conflicto.explanations_r2 : (FIXTURES[state.fixture].explanations_r2 ?? principal.explanations_r2!));
      state.explanations[revision].result_revision = revision;
      pushEvent(state, "human_review_committed", { result_revision: revision, reviewer_name: body.reviewer_name, selected_scenario_id: null, selected_assembly_candidate_id: candidate.id });
      return clone(next);
    },

    async getComparables(runId) {
      await wait(120);
      const state = runOf(runId);
      return clone(FIXTURES[state.fixture].comparables);
    },
    async saveToLibrary(runId, body) {
      await wait(300);
      const state = runOf(runId);
      resultOf(state, body.result_revision);
      const base = principal.library_item!;
      const item: LibraryItem = { ...clone(base), id: `library-${runId}`, run_id: runId, result_revision: body.result_revision, label: body.label, created_at: new Date().toISOString() };
      savedLibrary.set(item.id, item);
      pushEvent(state, "library_item_saved", { result_revision: body.result_revision, embedding_mode: body.embedding_mode });
      return clone(item);
    },
    async getLibrary() {
      await wait(150);
      const base = (libraryRaw as unknown as LibraryItem[]).filter((item) => item.run_id !== principal.create_run.run.id);
      return clone([...base, ...savedLibrary.values()]);
    },
    async findSimilar(runId, body) {
      await wait(250);
      runOf(runId);
      if (body.mode === "semantic") fail(semanticErrorRaw as Raw);
      return clone((similarityRaw as unknown as SimilarityMatch[]).slice(0, body.limit ?? 10));
    },
    async groupLibrary() {
      await wait(150);
      const known = new Set([...(libraryRaw as unknown as LibraryItem[]).filter((item) => item.run_id !== principal.create_run.run.id).map((item) => item.id), ...savedLibrary.keys()]);
      const principalItemId = principal.library_item!.id;
      return clone((groupsRaw as unknown as SimilarityGroup[])
        .map((group) => ({ ...group, member_ids: group.member_ids.map((id) => (id === principalItemId ? [...savedLibrary.keys()][0] ?? id : id)).filter((id) => known.has(id)) }))
        .filter((group) => group.member_ids.length >= 2));
    },
    async createEstimate(runId, body) {
      await wait(500);
      const state = runOf(runId);
      const result = resultOf(state, body.result_revision);
      if (result.state !== "completed") fail(FIXTURES[state.fixture].estimate_r1_error);
      const materials = new Set(result.pieces.map((piece) => piece.material));
      const finishes = new Set(result.pieces.map((piece) => piece.finish));
      if (materials.has(null) || finishes.has(null) || materials.size !== 1 || finishes.size !== 1) {
        // Respuesta real de backend/app/estimacion/service.py para este caso.
        throw new ApiError("No hay evidencia suficiente para estimar.", 422, "missing_compatible_material_or_finish");
      }
      const raw = FIXTURES[state.fixture].estimate_raw ?? principal.estimate_raw!;
      if (!("data" in raw.body)) fail(raw);
      const estimate = { ...clone(raw.body.data as Estimate), run_id: runId, result_revision: result.result_revision };
      state.estimate = estimate;
      pushEvent(state, "estimate_committed", { result_revision: estimate.result_revision, total: estimate.total, currency: estimate.currency });
      return clone(estimate);
    },
    async getExport(runId, format) {
      await wait(200);
      const state = runOf(runId);
      const result = resultOf(state);
      const filename = `${runId}-r${result.result_revision}.${format}`;
      if (format === "csv") {
        const csv = FIXTURES[state.fixture].export_csv;
        const [header, ...rows] = csv.trimEnd().split(/\r?\n/);
        const body = result.pieces.length ? [header, ...rows.map((row) => row.replace(/,\d+,(completed|needs_review),/, `,${result.result_revision},${result.state},`))].join("\n") + "\n" : `${header}\n`;
        return { filename, mediaType: "text/csv; charset=utf-8", body };
      }
      const bundle = {
        schema_version: "0.2.0", result_revision: result.result_revision, result, scene: state.scenes[result.result_revision] ?? null,
        explanations: state.explanations[result.result_revision] ?? null, comparables: FIXTURES[state.fixture].comparables,
        estimate: state.estimate?.result_revision === result.result_revision ? state.estimate : null, events: state.events,
      };
      return { filename, mediaType: "application/json", body: JSON.stringify(bundle, null, 2) };
    },
    exportUrl: () => null,
    async streamEvents(runId, onEvent, signal) {
      const state = runOf(runId);
      for (const event of [...state.events]) {
        await wait(event.event_type === "tool_completed" ? 520 : 380, signal);
        onEvent(clone(event));
      }
    },
  };
  return api;
}
