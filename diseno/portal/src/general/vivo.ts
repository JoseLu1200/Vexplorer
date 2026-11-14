/**
 * Cargadores en vivo: piden al backend real lo necesario y devuelven el modelo de vista.
 *
 *   abrirRun(api, runId)               cualquier run: vía general o legacy (p. ej. RUNS_DEMO).
 *   analizarPlano(api, archivo, modo)  sube el plano, crea el job general y lo sigue hasta el final.
 *
 * Sin clave de modelo no se lanza excepción. analizarPlano devuelve `necesitaModelo: true` y un mensaje
 * que empieza por «Hace falta el modo con modelo»:
 *   - modo "live": se para antes de crear el trabajo (job y mesa null).
 *   - modo "geometry_only": el job termina bien y la mesa llega con el plano, 0 piezas, estado
 *     "sin_propuesta" y un pendiente de tipo "modelo".
 *   - si un job falla (p. ej. live_provider_unavailable), su error entra en la mesa como aviso de fuente "trabajo".
 * Los errores de red o de contrato sí salen como GeneralApiError.
 */
import { NEEDS_MODEL_MESSAGE, newIdempotencyKey, type GeneralApi, type JobView, type PollOptions } from "../api/general";
import type { Result } from "../api/types";
import { desdeGeneral, desdeLegacy, desdeTabla } from "./adaptador";
import type { ArchivoVista, Aviso, MesaTrabajo, OrigenVista, Pendiente } from "./modelo";

const PENDIENTE_MODELO: Pendiente = { id: "modelo", tipo: "modelo", piezaId: null, campos: [], texto: "Pendiente: requiere modelo" };

function avisoTrabajo(job: JobView): Aviso | null {
  if (!job.error) return null;
  return { nivel: "error", codigo: job.error.code, mensaje: job.error.message, piezas: [], fuente: "trabajo" };
}

export interface OpcionesRun { titulo?: string; sintetico?: boolean; job?: JobView | null; atribucion?: string | null; notas?: string[] }

/**
 * Documento del run: el original para «Abrir en CAD» (solo si es DXF) y la imagen de su primera página (PDF raster).
 * null en cada campo si el run no tiene documento o el backend no responde.
 */
async function documentoDe(api: GeneralApi, documentId: string | null): Promise<{ original: ArchivoVista | null; preview: string | null }> {
  if (!documentId) return { original: null, preview: null };
  const doc = await api.getDocument(documentId).catch(() => null) as null | { original_filename: string; source?: { format?: string }; artifacts?: { pages?: { preview?: { url?: string } | null }[] } };
  if (!doc) return { original: null, preview: null };
  const formato = doc.source?.format ?? doc.original_filename.split(".").pop()?.toLowerCase();
  const pagina = doc.artifacts?.pages?.[0]?.preview?.url ?? null;
  return {
    original: formato === "dxf" ? {
      id: "original", tipo: "dxf_original", formato: "dxf", nombre: doc.original_filename, estado: "listo", motivosIncompleto: [],
      laminaId: null, piezaId: null, url: api.documentOriginalUrl(documentId), contenido: null, mediaType: "application/dxf",
    } : null,
    preview: pagina ? api.absolute(pagina) : null,
  };
}

export async function abrirRun(api: GeneralApi, runId: string, opciones: OpcionesRun = {}): Promise<MesaTrabajo> {
  const detail = await api.getRun(runId);
  const [drawing, eventos, documento] = await Promise.all([
    api.getDrawing(runId),
    api.getEvents(runId).catch(() => null),
    documentoDe(api, detail.run.document_id),
  ]);
  const comun = {
    id: runId, titulo: opciones.titulo ?? runId, sintetico: opciones.sintetico ?? false, drawing,
    eventos, original: documento.original, atribucion: opciones.atribucion ?? null, notas: opciones.notas ?? [],
    // Sin contornos (PDF raster), el original es la imagen de la página.
    imagenOriginal: drawing.contours.length ? null : documento.preview,
  };
  const avisos: Aviso[] = [];
  const jobAviso = opciones.job ? avisoTrabajo(opciones.job) : null;
  if (jobAviso) avisos.push(jobAviso);

  if (detail.run.input_kind === "mounted_orthographic_views") {
    const resultRevision = detail.result.result_revision;
    const [table, scene, drawings, costs] = await Promise.all([
      api.getTable(runId, resultRevision),
      api.getScene(runId, resultRevision),
      api.getTableDrawings(runId, resultRevision),
      api.getTableCosts(runId, resultRevision),
    ]);
    // El manifiesto da URLs; el SVG se pide para pintar la lámina en el portal.
    for (const sheet of drawings?.sheets ?? []) {
      for (const format of sheet.formats) {
        if (format.format === "svg") format.content = await api.getText(format.url).catch(() => undefined);
      }
    }
    return desdeTabla({
      ...comun, avisos, resultState: detail.result.state, table, scene, drawings, costs, url: api.absolute,
      origen: { tipo: "run", runId, resultRevision },
    });
  }

  if (detail.run.input_kind !== "general_furniture") {
    const resultRevision = detail.result.result_revision;
    const scene = await api.getScene(runId, resultRevision);
    return desdeLegacy({
      ...comun, avisos, result: detail.result as unknown as Result, scene,
      origen: { tipo: "run", runId, resultRevision },
    });
  }

  const record = await api.getGeneral(runId);
  if (!record) {
    return desdeGeneral({
      ...comun, avisos, pendientes: [PENDIENTE_MODELO],
      origen: opciones.job ? { tipo: "trabajo", jobId: opciones.job.id, runId } : { tipo: "run", runId },
    });
  }
  const revisions = { proposalRevision: record.proposal_revision, reviewRevision: record.review_revision };
  const origen: OrigenVista = { tipo: "run", runId, ...revisions };
  if (record.review_revision === 0) {
    return desdeGeneral({ ...comun, record, avisos, origen });
  }
  const [derived, assembly] = await Promise.all([
    api.getDerived(runId, revisions),
    api.getAssembly(runId, revisions),
  ]);
  const pkg = derived.package;
  return desdeGeneral({
    ...comun, origen, avisos, record,
    construction: pkg.construction, validation: record.review?.construction_validation ?? null,
    bomRows: pkg.bom_rows, packageScene: pkg.scene, packageStatus: pkg.status, assembly,
    artifacts: pkg.artifacts,
    artifactUrl: (id) => api.artifactUrl(runId, id, revisions),
  });
}

export interface ResultadoAnalisis { job: JobView | null; mesa: MesaTrabajo | null; necesitaModelo: boolean; mensaje: string }

/**
 * Flujo completo de la vía general. modo "live" pide propuesta al modelo; "geometry_only" solo extrae el plano.
 * Antes de enviar un "live" consulta /config y, si no hay modelo, no crea el trabajo.
 */
export async function analizarPlano(
  api: GeneralApi, archivo: Blob, nombre: string, modo: "live" | "geometry_only", opciones: PollOptions & { idempotencyKey?: string } = {},
): Promise<ResultadoAnalisis> {
  if (modo === "live") {
    const config = await api.config();
    if (!config.general?.live_available) {
      return { job: null, mesa: null, necesitaModelo: true, mensaje: `${NEEDS_MODEL_MESSAGE}: ${config.unavailableReason ?? "el servidor no tiene proveedor de modelo."}` };
    }
  }
  const documento = await api.uploadDocument(archivo, nombre);
  const creado = await api.submitJob({ document_id: documento.document_id, mode: modo }, opciones.idempotencyKey ?? newIdempotencyKey("general"));
  const job = await api.followJob(creado.id, opciones);
  const necesitaModelo = job.error?.code === "live_provider_unavailable";
  if (!job.run_id) {
    return { job, mesa: null, necesitaModelo, mensaje: job.error ? `${necesitaModelo ? `${NEEDS_MODEL_MESSAGE}. ` : ""}${job.error.message}` : "El trabajo terminó sin análisis." };
  }
  const mesa = await abrirRun(api, job.run_id, { titulo: nombre, job });
  const sinPropuesta = mesa.estado === "sin_propuesta";
  return {
    job, mesa, necesitaModelo: necesitaModelo || (sinPropuesta && modo === "geometry_only"),
    mensaje: sinPropuesta ? `Plano leído (${mesa.plano?.contornos.length ?? 0} contornos). ${NEEDS_MODEL_MESSAGE} para proponer piezas.` : `Análisis ${job.state}.`,
  };
}

// ---------- Subida de una mesa de vistas montadas (sin modelo, plantilla de catálogo) ----------

/** Plantilla de catálogo con la que el backend evalúa la mesa sin modelo. */
export const PLANTILLA_MESA = "side_supports_v1";

/**
 * Alcance de coste de la demo guardada (data/plank_pipeline_demo/runs/run-161fc0b9…/table-costs.json): tablero por
 * superficie, cantos expuestos y 1,5 h de mecanizado con las tarifas sintéticas del catálogo del backend.
 */
export const ALCANCE_COSTE_DEMO: Record<string, unknown> = {
  material_tariff_id: "demo_board_area_v1",
  edge_scope: "all_exposed",
  edge_tariff_id: "demo_edge_exposed_v1",
  operation_tariff_ids: ["demo_machining_hour_v1"],
  operation_hours_by_tariff: { demo_machining_hour_v1: 1.5 },
  exclusions: [
    { scope: "labor", reason: "Demo: solo mecanizado, sin mano de obra adicional." },
    { scope: "finishing", reason: "Demo: pieza sin acabado." },
  ],
  provisional_margin_percent: 20,
};

export type FaseCallback = (fase: "subiendo" | "analizando" | "salidas" | "hecho") => void;

/** Sube el DXF, crea el job de mesa con plantilla de catálogo, lo sigue y genera las láminas de la revisión 1. */
export async function analizarMesa(api: GeneralApi, archivo: Blob, nombre: string, onFase: FaseCallback = () => undefined): Promise<{ job: JobView; runId: string | null }> {
  onFase("subiendo");
  const documento = await api.uploadDocument(archivo, nombre);
  onFase("analizando");
  const creado = await api.submitTableJob(documento.document_id, PLANTILLA_MESA, newIdempotencyKey("mesa"));
  const job = await api.followJob(creado.id, { intervalMs: 400, timeoutMs: 120_000 });
  if (!job.run_id) return { job, runId: null };
  onFase("salidas");
  await api.createTableDrawings(job.run_id, 1).catch(() => null);
  onFase("hecho");
  return { job, runId: job.run_id };
}

/**
 * Acción humana explícita: acepta la plantilla de catálogo (componentes y premisas) con una revisión del portal,
 * y genera láminas y coste de esa revisión. Devuelve la revisión nueva.
 */
export async function aceptarPlantillaMesa(api: GeneralApi, runId: string, revisor: string): Promise<number> {
  const detail = await api.getRun(runId);
  const base = detail.result.result_revision;
  const table = await api.getTable(runId, base);
  const programa = (table as unknown as { selected_table_program_id: string | null; table_programs?: { id: string }[] }).selected_table_program_id
    ?? (detail.result as unknown as { table_programs?: { id: string }[] }).table_programs?.[0]?.id;
  const componentes = (table.evaluated_table_program?.components ?? []) as unknown as { id: string; premise_ids?: string[] }[];
  const premisas = [...new Set(componentes.flatMap((c) => c.premise_ids ?? []))];
  const motivo = "Aceptación de la plantilla de catálogo desde el portal.";
  const review = await api.createRunReview(runId, {
    base_result_revision: base, reviewer_name: revisor, table_program_id: programa, notes: motivo,
    table_decisions: [
      ...componentes.map((c) => ({ target_kind: "component", target_id: c.id, action: "accept", reason: motivo })),
      ...premisas.map((id) => ({ target_kind: "premise", target_id: id, action: "accept", reason: motivo })),
      ...(programa ? [{ target_kind: "program", target_id: programa, action: "accept", reason: motivo }] : []),
    ],
  });
  await api.createTableDrawings(runId, review.result_revision).catch(() => null);
  await api.createTableCosts(runId, review.result_revision, ALCANCE_COSTE_DEMO).catch(() => null);
  return review.result_revision;
}

/** SHA-256 en hexadecimal de un archivo subido, para reconocer un plano ya procesado. */
export async function sha256Hex(archivo: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await archivo.arrayBuffer());
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
