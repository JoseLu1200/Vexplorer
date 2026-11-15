/**
 * Presentación del dominio. Traduce estados del contrato a las cinco clases de dato y organiza filas.
 * No calcula medidas, cantidades ni totales: copia los valores tal como llegan del backend.
 */
import type {
  AssemblyCandidate, AssemblyPartUse, ObservedPartDimension, Result, RunSnapshot, SeparatedPartObservation, FieldState,
} from "../api/types";

export type DataClass = "observed" | "calculated" | "hypothesis" | "confirmed" | "unknown";

export interface Cell {
  value: number | string | null;
  cls: DataClass;
  /** Estado literal del contrato cuando aporta algo (p. ej. «conflicto entre vistas»). */
  note?: string;
  /** El valor participa en una restricción en conflicto del montaje elegido. */
  conflict?: boolean;
}

export const ROLE_LABELS: Record<string, string> = {
  side_panel: "Lateral", shelf: "Balda", top_panel: "Tapa", base_panel: "Base", back_panel: "Trasera",
  door: "Puerta", divider: "Divisor", unknown: "Sin función",
};
export const LAYOUT_LABELS: Record<string, string> = {
  between_sides: "Tapa y base entre laterales", cap_sides: "Tapa y base sobre laterales", unknown: "Montaje desconocido",
};
export const FAMILY_LABELS: Record<string, string> = { rectangular_shelving: "Estantería rectangular", unknown: "Familia desconocida" };
export const VIEW_LABELS: Record<string, string> = { FRONT: "Alzado", TOP: "Planta", SIDE: "Perfil", UNKNOWN: "Vista sin rótulo" };
export const AXIS_LABELS: Record<string, string> = { width: "Ancho", height: "Alto", depth: "Fondo" };
export const CONSTRAINT_LABELS: Record<string, string> = {
  length: "Largo común", width: "Ancho común", thickness: "Espesor común", assembled_width: "Ancho exterior", assembled_height: "Alto exterior", assembled_depth: "Fondo exterior",
};

const PREMISES: Record<string, string> = {
  "Role allocation is a dimensional hypothesis; opaque part keys carry no role semantics.": "Función supuesta por las medidas, no indicada en el plano.",
  "Assembly layout is not observed and requires human review.": "El montaje no aparece en el plano y requiere revisión.",
  "No back, hardware, material, or manufacturing detail is inferred.": "No se infieren trasera, herrajes, material ni detalles de fabricación.",
  "Boxes are schematic reviewed panel occurrences, not manufacturing solids.": "Los volúmenes representan piezas revisadas de forma esquemática.",
  "Shelf heights are schematic evenly spaced hypotheses because separate part views do not observe assembly levels.": "Las baldas se reparten a la misma distancia porque las vistas separadas no indican su altura.",
  "Collision checking is not certified and remains not_evaluated.": "Las colisiones no están evaluadas.",
  "No part solid is created before explicit assembly-candidate review.": "No se crea ningún volumen hasta que una persona confirma un montaje.",
  role_assignment_is_hypothesis: "",
  assembly_layout_is_hypothesis: "",
  human_confirmed_operands_used: "Usa valores confirmados por persona",
  human_selected_assembly_candidate: "Montaje elegido por persona",
  assembly_review_required: "Falta confirmar un montaje",
};
/** Traduce una premisa; las que repiten otra ya traducida devuelven "" y se omiten. */
export const translatePremise = (value: string) => PREMISES[value] ?? value;

const EVIDENCE: Record<string, string> = {
  "Closed source polyline observed in drawing": "Polilínea cerrada en el plano",
  "Linear dimension annotation observed in drawing": "Cota lineal en el plano",
  "Public text annotation observed in drawing": "Texto en el plano",
};
export const translateEvidence = (value: string) => EVIDENCE[value] ?? value;

export function translateWarning(value: string): string {
  if (value.startsWith("missing_part_key:")) return "Una vista no lleva etiqueta de pieza";
  if (value.startsWith("unassociated_quantity_annotation:")) return "Hay una cantidad anotada que no se puede asignar a ninguna pieza";
  return value;
}

const NUMBER = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });
const EUR = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const FACTOR = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 6 });
export const fmt = (value: number) => NUMBER.format(value);
/** Único formateador de importes: «127,84 €». */
export const fmtEur = (value: number) => EUR.format(value);
/** Factores con toda la precisión que trae el backend, para que la cuenta se pueda comprobar. */
export const fmtFactor = (value: number) => FACTOR.format(value);
/** Reescribe en es-ES los importes que el backend incrusta en sus textos («50.00 EUR/m²» → «50,00 €/m²»). */
export const localizeAmounts = (text: string) =>
  text.replace(/(\d+(?:\.\d+)?) EUR(\/m²)?/g, (_, n: string, unit?: string) => `${fmtEur(Number(n))}${unit ?? ""}`);
export const fmtDate = (iso: string) =>
  new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Madrid" }).format(new Date(iso));

// ---- Mapeo explícito de estados reales a las cinco clases ----
export function classOfDimension(dim: ObservedPartDimension): Cell {
  if (dim.state === "observed") return { value: dim.value_mm, cls: "observed" };
  if (dim.state === "conflict") return { value: null, cls: "unknown", note: "Conflicto entre vistas" };
  return { value: null, cls: "unknown" };
}
export function classOfUseQuantity(use: AssemblyPartUse): Cell {
  if (use.quantity_source === "observed_annotation") return { value: use.allocated_quantity, cls: "observed" };
  if (use.quantity_source === "human_confirmed") return { value: use.allocated_quantity, cls: "confirmed" };
  return { value: null, cls: "unknown" };
}
export function classOfFieldState(state: FieldState | undefined, value: number | string | null): Cell {
  switch (state) {
    case "observed": return { value, cls: "observed" };
    case "calculated": return { value, cls: "calculated" };
    case "confirmed": return { value, cls: "confirmed" };
    default: return { value: null, cls: "unknown" };
  }
}
export function classOfDerived(state: "derived" | "unknown" | "conflict", value: number | null): Cell {
  if (state === "derived") return { value, cls: "calculated" };
  if (state === "conflict") return { value: null, cls: "unknown", note: "Conflicto" };
  return { value: null, cls: "unknown" };
}

// ---- Filas de la tabla de piezas ----
export interface PartRow {
  id: string;
  observationId: string;
  key: string;
  role: Cell;
  quantity: Cell;
  length: Cell;
  width: Cell;
  thickness: Cell;
  material: Cell;
  contourIds: string[];
  viewIds: string[];
  evidenceIds: string[];
  note: string | null;
  observation: SeparatedPartObservation;
  use: AssemblyPartUse | null;
  changed: Set<string>;
}

export function pickCandidate(result: Result, run: RunSnapshot | null, preferred?: string | null): AssemblyCandidate | null {
  const list = result.assembly_candidates;
  return (
    list.find((item) => item.id === preferred) ??
    list.find((item) => item.id === result.selected_assembly_candidate_id) ??
    list.find((item) => item.id === run?.agent_selected_assembly_candidate_id) ??
    list[0] ?? null
  );
}

function keyOf(observation: SeparatedPartObservation, index: number) {
  return observation.part_key ?? `Sin etiqueta ${index + 1}`;
}

export function buildRows(result: Result, candidate: AssemblyCandidate | null, previous?: Result | null): PartRow[] {
  const observations = result.part_analysis?.observations ?? [];
  const byId = new Map(observations.map((item, index) => [item.id, { item, index }]));
  const reviewed = candidate && result.selected_assembly_candidate_id === candidate.id && result.pieces.length > 0;
  const pieces = new Map(result.pieces.map((piece) => [piece.proposal_id, piece]));
  let rows: PartRow[];
  if (candidate) {
    rows = candidate.uses.map((use) => {
      const { item: observation, index } = byId.get(use.part_observation_id)!;
      const piece = reviewed ? pieces.get(use.id) : undefined;
      const contourIds = observation.views.flatMap((view) => view.contour_ids);
      const base = {
        id: use.id, observationId: observation.id, key: keyOf(observation, index), observation, use,
        contourIds, viewIds: observation.views.map((view) => view.view_id), evidenceIds: observation.evidence_ids, changed: new Set<string>(),
      };
      if (piece) {
        return {
          ...base,
          role: { value: ROLE_LABELS[piece.role] ?? piece.role, cls: "confirmed" as DataClass },
          quantity: classOfFieldState(piece.field_states.quantity, piece.quantity),
          length: classOfFieldState(piece.field_states.length_mm, piece.length_mm),
          width: classOfFieldState(piece.field_states.width_mm, piece.width_mm),
          thickness: classOfFieldState(piece.field_states.thickness_mm, piece.thickness_mm),
          material: classOfFieldState(piece.field_states.material, piece.material),
          note: piece.human_confirmation || null,
        };
      }
      return {
        ...base,
        role: { value: ROLE_LABELS[use.role] ?? use.role, cls: "hypothesis" as DataClass },
        quantity: classOfUseQuantity(use),
        length: classOfDimension(observation.dimensions.length),
        width: classOfDimension(observation.dimensions.width),
        thickness: classOfDimension(observation.dimensions.thickness),
        material: { value: null, cls: "unknown" as DataClass },
        note: null,
      };
    });
  } else {
    rows = observations.map((observation, index) => {
      const quantity: Cell = observation.quantity.state === "observed"
        ? { value: observation.quantity.value, cls: "observed" }
        : { value: null, cls: "unknown", note: observation.quantity.state === "ambiguous" ? "Ambigua" : undefined };
      return {
        id: observation.id, observationId: observation.id, key: keyOf(observation, index), observation, use: null,
        role: { value: null, cls: "unknown" }, quantity,
        length: classOfDimension(observation.dimensions.length), width: classOfDimension(observation.dimensions.width),
        thickness: classOfDimension(observation.dimensions.thickness), material: { value: null, cls: "unknown" },
        contourIds: observation.views.flatMap((view) => view.contour_ids), viewIds: observation.views.map((view) => view.view_id),
        evidenceIds: observation.evidence_ids, note: null, changed: new Set<string>(),
      };
    });
  }
  if (candidate && result.selected_assembly_candidate_id === candidate.id) {
    const fields = candidate.constraints
      .filter((item) => item.status === "conflict" && (item.dimension === "length" || item.dimension === "width" || item.dimension === "thickness"))
      .map((item) => item.dimension as "length" | "width" | "thickness");
    for (const row of rows) for (const field of fields) if (row[field].cls === "confirmed") row[field] = { ...row[field], conflict: true };
  }
  if (previous && candidate) {
    const prevCandidate = previous.assembly_candidates.find((item) => item.id === candidate.id) ?? null;
    const before = new Map(buildRows(previous, prevCandidate).map((row) => [row.id, row]));
    for (const row of rows) {
      const old = before.get(row.id);
      if (!old) continue;
      for (const field of ["quantity", "length", "width", "thickness", "material", "role"] as const) {
        if (old[field].cls !== row[field].cls || old[field].value !== row[field].value) row.changed.add(field);
      }
    }
  }
  return rows;
}

export const RESULT_STATE_LABELS: Record<string, string> = { completed: "Completo", needs_review: "Requiere revisión" };
