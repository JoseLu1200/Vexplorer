/**
 * Puente entre el modelo de vista de src/general (MesaTrabajo) y los componentes de la mesa de trabajo.
 * Convierte el plano al formato que dibuja DrawingCanvas, traduce los estados de medida a las clases de dato
 * y carga cada mueble una sola vez por sesión. No calcula medidas: copia valores, textos y estados.
 */
import { api, generalApi } from "../api";
import type { DrawingExtraction, Point2D } from "../api/types";
import { abrirRun, cargarCaso, cargarDatosCaso, conNombresCortos, runDeCaso, type ArchivoVista, type CasoId, type EstadoMedida, type MesaTrabajo, type PlanoVista, type Punto } from "../general";
import { saveFile } from "../workspace/store";
import { cargarRaro, PREFIJO_RARO } from "../casos/raros";
import { COPY } from "../copy";
import type { DataClass } from "../lib/domain";
import type { PlanRecord } from "../workspace/types";

const P = ([x, y]: Punto): Point2D => ({ x, y });
const VIEW: Record<string, "FRONT" | "TOP" | "SIDE"> = { FRONT: "FRONT", TOP: "TOP", SIDE: "SIDE" };

/** El plano de la vista general con la forma de DrawingExtraction: contornos, cotas, textos y trazos sueltos como entidades. */
export function planoComoDrawing(plano: PlanoVista): DrawingExtraction {
  const mm = plano.coordenadas === "mm";
  const pts = (list: Punto[]) => list.map(P);
  const circle = (c: { centro: Punto; radio: number }) =>
    Array.from({ length: 49 }, (_, i) => ({ x: c.centro[0] + c.radio * Math.cos((i / 48) * 2 * Math.PI), y: c.centro[1] + c.radio * Math.sin((i / 48) * 2 * Math.PI) }));
  return {
    schema_version: "0.2.0", drawing_id: plano.id, input_kind: "separated_part_views", status: "ready",
    source_unit: (plano.unidad as DrawingExtraction["source_unit"]) ?? "unknown", unit_scale_to_mm: mm ? 1 : null, coordinate_unit: mm ? "mm" : "source",
    entities: [
      ...plano.contornos.flatMap((c) => c.entidades.map((id) => ({ id, kind: "CONTOUR", layer: "contornos", source_points: [], points_mm: null }))),
      ...plano.trazos.map((t) => {
        const points = t.circulo ? circle(t.circulo) : pts(t.puntos);
        return { id: t.id, kind: t.tipo, layer: t.capa, source_points: points, points_mm: mm ? points : null };
      }),
    ],
    views: plano.vistas.map((v) => {
      const b = { min_x: v.limites.minX, min_y: v.limites.minY, max_x: v.limites.maxX, max_y: v.limites.maxY };
      return { id: v.id, label: VIEW[v.etiqueta] ?? "UNKNOWN", entity_ids: [], bounds_source: b, bounds_mm: mm ? b : null };
    }),
    contours: plano.contornos.map((c) => ({ id: c.id, view_id: c.vista, source_entity_ids: c.entidades, points_source: pts(c.puntos), points_mm: mm ? pts(c.puntos) : null, closed: c.cerrado })),
    dimensions: [], evidence: [], observations: [],
    texts: plano.textos.map((t) => ({ id: t.id, source_entity_id: t.id, view_id: t.vista, layer: "textos", text: t.texto, position_source: P(t.posicion), position_mm: mm ? P(t.posicion) : null })),
    dimension_graphics: plano.cotas.map((c) => {
      const [[a, s], [b, e]] = c.lineas;
      const at = (p: Punto) => (mm ? P(p) : null);
      return {
        id: c.id, dimension_id: c.id, source_entity_id: c.id, view_id: c.vista, layer: "cotas", display_text: c.texto, raw_text: c.texto,
        extension_start_a_source: P(a), extension_start_a_mm: at(a), extension_start_b_source: P(b), extension_start_b_mm: at(b),
        dimension_start_source: P(s), dimension_start_mm: at(s), dimension_end_source: P(e), dimension_end_mm: at(e),
        text_position_source: P(c.posicionTexto), text_position_mm: at(c.posicionTexto),
      };
    }),
    warnings: plano.avisos, synthetic: false,
  };
}

/** Estado de medida de la vía general en las cinco clases de dato de la interfaz. */
export const CLASE: Record<EstadoMedida, DataClass> = {
  observada: "observed", deducida: "calculated", derivada: "calculated", calculada: "calculated",
  estimada: "hypothesis", hipotesis: "hypothesis", confirmada: "confirmed", sin_medida: "unknown", conflicto: "unknown",
};
export const ESTADO_TEXTO: Record<EstadoMedida, string> = {
  observada: "observada", deducida: "deducida", derivada: "derivada", calculada: "calculada", estimada: "estimada",
  hipotesis: "hipótesis", confirmada: "confirmada", sin_medida: "sin medida", conflicto: "en conflicto",
};
/** Las cifras van en tinta: el estado se marca con la muestra cuadrada o la «≈», nunca con el color del texto. */
export const TONO: Record<DataClass, string> = { observed: "text-ink", calculated: "text-ink", hypothesis: "text-ink", confirmed: "text-ink", unknown: "text-muted" };
export const ESTADO_MESA: Record<MesaTrabajo["estado"], string> = {
  listo: "Listo", incompleto: "Incompleto", en_revision: "En revisión", sin_propuesta: "Sin propuesta", error: "Error",
};

/** Cifra corta para cotas y listas: «≈ 862», «1200» o «?» si no hay medida. */
export const corta = (m: { valor_mm: number | null; estimada: boolean }) =>
  m.valor_mm == null ? "?" : `${m.estimada ? "≈ " : ""}${Number.isInteger(m.valor_mm) ? m.valor_mm : Number(m.valor_mm.toFixed(1))}`;

// ---- Carga de cada mueble, una vez por sesión ----
const cache = new Map<string, Promise<MesaTrabajo>>();

/** Recuerda una mesa ya obtenida (p. ej. la que devuelve la subida de un mueble general). */
export function recordarMesa(planId: string, mesa: MesaTrabajo) { cache.set(planId, Promise.resolve(mesa)); }
/** Olvida la mesa de un plano para volver a pedirla (tras una revisión). */
export function olvidarMesa(planId: string) { cache.delete(planId); }

/**
 * Mueble de la carpeta «Muebles procesados» o subido como mueble general. En modo real, los casos con run guardado
 * (RUNS_PLANK y RUNS_DEMO) se abren del servidor con abrirRun; si ese backend no tiene el run (cada demo vive en
 * su propio backend), se usa el caso congelado de src/casos, que es la misma ejecución exportada.
 */
export function cargarMesa(plan: PlanRecord): Promise<MesaTrabajo> {
  const hit = cache.get(plan.id);
  if (hit) return hit;
  const casoId = plan.asset as CasoId | undefined;
  const guardado = !api.isMock && casoId ? runDeCaso(casoId) : undefined;
  const task = plan.asset?.startsWith(PREFIJO_RARO)
    ? cargarRaro(plan.asset.slice(PREFIJO_RARO.length), plan.name)
    : plan.source === "general" && plan.casoGuardado
    ? cargarCaso(plan.casoGuardado as CasoId)
    : plan.source === "general" && plan.runId
    ? abrirRun(generalApi, plan.runId, { titulo: plan.name })
    : guardado
      ? abrirRun(generalApi, guardado.runId, { titulo: plan.name, atribucion: guardado.atribucion ?? null }).then((mesa) => conNombresCortos(mesa, casoId!)).catch(() => cargarCaso(casoId!))
      : casoId?.startsWith("recon_") && !api.isMock
        ? cargarReconstruccionReal(casoId)
        : cargarCaso(casoId!);
  cache.set(plan.id, task);
  task.catch(() => cache.delete(plan.id));
  return task;
}

/**
 * Construcción 3D en modo real: los mismos trabajos con sus archivos servidos por /reconstruction/{job}; si ese backend
 * no tiene el trabajo (otro runtime), los archivos incrustados en el caso.
 */
async function cargarReconstruccionReal(casoId: CasoId): Promise<MesaTrabajo> {
  const datos = await cargarDatosCaso(casoId);
  const job = datos.lane === "reconstruccion" ? datos.jobs[0]?.job_id : undefined;
  const servido = job ? await generalApi.getReconstruction(job).then(() => true).catch(() => false) : false;
  if (!servido) return cargarCaso(casoId);
  return cargarCaso(casoId, { reconUrl: (j, archivo) => (archivo === "source.png" ? generalApi.reconstructionSourceUrl(j) : generalApi.reconstructionArtifactUrl(j, archivo)) });
}

/** Descarga un archivo del modelo de vista: su contenido si viaja con los datos, si no su URL. */
export async function descargarArchivo(file: ArchivoVista, toast: (message: string, options?: { tone?: "error" }) => void): Promise<void> {
  if (file.contenido != null) {
    const outcome = await saveFile(new Blob([file.contenido], { type: file.mediaType ?? "application/octet-stream" }), file.nombre).catch(() => "unavailable" as const);
    if (outcome === "saved") toast(COPY.cad.downloaded(file.nombre));
    else if (outcome === "rejected") toast(COPY.cad.viewerRejects, { tone: "error" });
    else if (outcome === "unavailable") toast(COPY.cad.viewerUnavailable, { tone: "error" });
    return;
  }
  if (file.url) window.open(file.url, "_blank", "noopener");
}
