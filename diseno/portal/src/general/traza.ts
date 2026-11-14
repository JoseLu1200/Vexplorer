/**
 * Traza del pipeline: de los eventos del run (events.json o GET /runs/{id}/events) a una línea de tiempo corta.
 *
 * - Cada etiqueta sale de un mapa fijo de event_type y de tool_name; el resumen en inglés del payload no se muestra.
 * - Modelo: provider_model o reviewer_model del payload. Resultado: "ok" o el código de fallo (code o reason_code).
 * - Se descartan los eventos de contabilidad del run (estado, cierre) y el evento que repite la misma respuesta
 *   del proveedor (general_auto_review duplica general_auto_review_tool_completed).
 * - Los eventos seguidos del mismo tipo y la misma herramienta se agrupan, con cada resultado y sus veces.
 */
import type { PasoTraza } from "./modelo";

export interface EventoRun { sequence: number; event_type: string; data: Record<string, unknown> | string | null }

const HERRAMIENTA: Record<string, string> = {
  inspeccionar_evidencia_general: "Inspecciona la evidencia",
  proponer_mueble_general: "Propone el mueble",
  entregar_revision_autonoma: "Entrega la autorrevisión",
  inspeccionar_contexto_general: "Inspecciona el contexto",
  inspeccionar_pieza: "Inspecciona una pieza",
  proponer_descomposicion: "Propone el despiece",
  seleccionar_candidato_montaje: "Elige el montaje",
  entregar_despiece: "Entrega el despiece",
};

const EVENTO: Record<string, string> = {
  result_committed: "Resultado guardado",
  general_proposal_committed: "Propuesta guardada",
  general_auto_review_started: "Empieza la autorrevisión",
  general_auto_review_completed: "Autorrevisión terminada",
  general_auto_review_failed: "Autorrevisión fallida",
  general_auto_review_resumed: "Autorrevisión reanudada",
  general_assembly_started: "Empieza el montaje",
  general_assembly_failed: "Montaje fallido",
  general_assembly_unavailable: "Montaje sin proveedor",
  general_assembly_completed: "Montaje terminado",
  human_review_committed: "Revisión humana",
  table_drawings_committed: "Láminas guardadas",
  table_cost_committed: "Coste guardado",
  library_item_saved: "Guardado en biblioteca",
  estimate_committed: "Estimación guardada",
};
/** Eventos de contabilidad del run, sin información para la oficina técnica. */
const OMITIR = new Set(["run_state_changed", "run_finished", "general_auto_review"]);

const ESTADO: Record<string, string> = {
  incomplete: "incompleta", accepted: "aceptada", conflict: "en conflicto", abstained: "abstención",
  complete: "completo", partial: "parcial", rejected: "rechazado", needs_review: "en revisión", completed: "completado",
};

const str = (value: unknown) => (typeof value === "string" && value ? value : null);

function hora(timestamp: string | null): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
}

export function trazaDesdeEventos(eventos: EventoRun[]): PasoTraza[] {
  const pasos: PasoTraza[] = [];
  const respuestas = new Set<string>();
  const ordenados = [...eventos].sort((a, b) => a.sequence - b.sequence);
  for (const evento of ordenados) {
    const raw = evento.data;
    const data: Record<string, unknown> = typeof raw === "string" ? safeParse(raw) : raw ?? {};
    const respuesta = str(data.provider_response_id);
    const herramienta = str(data.tool_name);
    // general_auto_review repite la respuesta de general_auto_review_tool_completed: se cuenta una vez.
    if (respuesta && herramienta) {
      const clave = `${respuesta}:${herramienta}`;
      if (respuestas.has(clave)) continue;
      respuestas.add(clave);
    }
    if (OMITIR.has(evento.event_type)) continue;
    const okFlag = typeof data.ok === "boolean" ? data.ok : null;
    const codigo = str(data.code) ?? str(data.reason_code);
    const fallo = okFlag === false || evento.event_type.endsWith("_failed") || evento.event_type.endsWith("_unavailable");
    const resultado = fallo ? codigo ?? "fallo" : "ok";
    const revision = typeof data.result_revision === "number" ? data.result_revision : typeof data.proposal_revision === "number" ? data.proposal_revision : null;
    const base = (herramienta && HERRAMIENTA[herramienta]) ?? EVENTO[evento.event_type] ?? (herramienta ?? evento.event_type);
    const etiqueta = revision != null && (evento.event_type === "result_committed" || evento.event_type === "general_proposal_committed" || evento.event_type === "human_review_committed")
      ? `${base} r${revision}` : base;
    const estadoRaw = str(data.status) ?? str(data.total_state);
    const paso: PasoTraza = {
      id: `${evento.sequence}`,
      hora: hora(str(data.timestamp)),
      horaFin: null,
      etiqueta,
      herramienta,
      modelo: str(data.provider_model) ?? str(data.reviewer_model),
      resultados: [{ resultado, veces: 1 }],
      estado: estadoRaw ? ESTADO[estadoRaw] ?? estadoRaw : null,
      veces: 1,
      ok: !fallo,
    };
    const previo = pasos[pasos.length - 1];
    if (previo && previo.etiqueta === paso.etiqueta && previo.herramienta === paso.herramienta && previo.modelo === paso.modelo && previo.estado === paso.estado) {
      previo.veces += 1;
      previo.horaFin = paso.hora;
      previo.ok = previo.ok && paso.ok;
      const mismo = previo.resultados.find((r) => r.resultado === resultado);
      if (mismo) mismo.veces += 1; else previo.resultados.push({ resultado, veces: 1 });
      continue;
    }
    pasos.push(paso);
  }
  return pasos;
}

function safeParse(text: string): Record<string, unknown> {
  try {
    const value = JSON.parse(text);
    return value && typeof value === "object" ? value as Record<string, unknown> : {};
  } catch {
    return {};
  }
}
