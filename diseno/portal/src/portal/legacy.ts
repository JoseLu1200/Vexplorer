/**
 * Análisis de vistas montadas (input_kind `mounted_views_legacy`), como los de la carpeta «Demo procesada» del backend real.
 * No traen `part_analysis` ni candidatos de montaje: las piezas salen de `result.pieces` (revisión de persona) o, antes de
 * revisar, de los componentes del escenario elegido. Este adaptador da a la mesa la misma forma de fila que el contrato 0.4
 * sin calcular nada: copia valores y estados tal como llegan y los contornos de origen de cada pieza.
 */
import type { ComponentProposal, DecompositionScenario, DrawingExtraction, ObservedPartDimension, ResolvedPiece, Result, SeparatedPartObservation } from "../api/types";
import { classOfFieldState, ROLE_LABELS, type Cell, type DataClass, type PartRow } from "../lib/domain";

export const isLegacy = (result: Result | null) => Boolean(result && result.input_semantics === "mounted_views_legacy");

/** Escenario vigente: el que eligió la revisión, el que propuso el agente o el primero. */
export function legacyScenario(result: Result): DecompositionScenario | null {
  const id = result.review?.selected_scenario_id ?? result.agent_selected_scenario_id;
  return result.scenarios.find((item) => item.id === id) ?? result.scenarios[0] ?? null;
}

function observationOf(id: string, contourIds: string[], evidenceIds: string[], drawing: DrawingExtraction | null, states: Record<"length" | "width" | "thickness", boolean>, quantityObserved: boolean): SeparatedPartObservation {
  const byView = new Map<string, string[]>();
  for (const contourId of contourIds) {
    const viewId = drawing?.contours.find((c) => c.id === contourId)?.view_id ?? "";
    byView.set(viewId, [...(byView.get(viewId) ?? []), contourId]);
  }
  const zero = { x: 0, y: 0 };
  const box = { min_x: 0, min_y: 0, max_x: 0, max_y: 0 };
  const dim = (observed: boolean): ObservedPartDimension => ({ value_mm: null, state: observed ? "observed" : "unknown", origin: "observed", measurement_ids: [], view_ids: [], evidence_ids: [] });
  return {
    id, part_key: null, association_basis: "explicit_key",
    views: [...byView].map(([viewId, ids]) => {
      const label = drawing?.views.find((view) => view.id === viewId)?.label;
      return { view_id: viewId, role: label === "TOP" || label === "SIDE" ? label : "FRONT", contour_ids: ids, local_origin_source: zero, local_origin_mm: null, local_bounds_source: box, local_bounds_mm: null };
    }),
    dimensions: { length: dim(states.length), width: dim(states.width), thickness: dim(states.thickness) },
    quantity: { value: null, state: quantityObserved ? "observed" : "unknown", evidence_ids: [] },
    status: "complete", source_entity_ids: [], evidence_ids: evidenceIds, warnings: [],
  };
}

function fromPiece(piece: ResolvedPiece, drawing: DrawingExtraction | null): PartRow {
  const states = piece.field_states;
  const cell = (field: string, value: number | string | null): Cell => classOfFieldState(states[field], value);
  return {
    id: piece.proposal_id, observationId: piece.proposal_id, key: piece.label,
    role: { value: ROLE_LABELS[piece.role] ?? piece.role, cls: "confirmed" },
    quantity: cell("quantity", piece.quantity), length: cell("length_mm", piece.length_mm), width: cell("width_mm", piece.width_mm),
    thickness: cell("thickness_mm", piece.thickness_mm), material: cell("material", piece.material),
    contourIds: piece.source_contour_ids, viewIds: [], evidenceIds: piece.evidence_ids, note: piece.human_confirmation || null,
    observation: observationOf(piece.proposal_id, piece.source_contour_ids, piece.evidence_ids, drawing,
      { length: states.length_mm === "observed", width: states.width_mm === "observed", thickness: states.thickness_mm === "observed" }, states.quantity === "observed"),
    use: null, changed: new Set<string>(),
  };
}

/** Componente de un escenario sin revisar: todo es hipótesis salvo el largo leído directamente en el plano. */
function fromComponent(component: ComponentProposal, drawing: DrawingExtraction | null): PartRow {
  const value = (v: number | null, cls: DataClass): Cell => (v === null ? { value: null, cls: "unknown" } : { value: v, cls });
  return {
    id: component.id, observationId: component.id, key: component.label,
    role: { value: ROLE_LABELS[component.role] ?? component.role, cls: "hypothesis" },
    quantity: value(component.quantity, "hypothesis"),
    length: value(component.length_mm, component.length_derivation === "direct_observation" ? "observed" : "hypothesis"),
    width: value(component.width_mm, "hypothesis"), thickness: value(component.thickness_mm, "hypothesis"),
    material: { value: null, cls: "unknown" },
    contourIds: component.source_contour_ids, viewIds: [], evidenceIds: component.evidence_ids, note: null,
    observation: observationOf(component.id, component.source_contour_ids, component.evidence_ids, drawing, { length: false, width: false, thickness: false }, false),
    use: null, changed: new Set<string>(),
  };
}

export function legacyRows(result: Result, drawing: DrawingExtraction | null): PartRow[] {
  if (result.pieces.length) return result.pieces.map((piece) => fromPiece(piece, drawing));
  return legacyScenario(result)?.components.map((component) => fromComponent(component, drawing)) ?? [];
}
