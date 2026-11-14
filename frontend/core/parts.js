const FAMILY_LABELS = { rectangular_shelving: "Estantería rectangular", unknown: "Familia desconocida" };
const LAYOUT_LABELS = { between_sides: "Tapa y base entre laterales", cap_sides: "Tapa y base cubren laterales", unknown: "Montaje desconocido" };
const FIELD_LABELS = { quantity: "Cantidad", length: "Largo", width: "Ancho", thickness: "Grosor", material: "Material", finish: "Acabado" };
const ROLE_LABELS = { side_panel: "Lateral", shelf: "Balda", top_panel: "Tapa", base_panel: "Base", back_panel: "Trasera", door: "Puerta", divider: "Divisor", unknown: "Rol desconocido" };
const REVIEW_STATE_LABELS = { confirmed: "Confirmado por persona", observed: "Observado", calculated: "Calculado", unknown: "Desconocido" };
const NUMBER = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });
const ASSUMPTION_LABELS = {
  "Role allocation is a dimensional hypothesis; opaque part keys carry no role semantics.": "La asignación de roles es una hipótesis dimensional; las claves de pieza no indican su función.",
  "Assembly layout is not observed and requires human review.": "La disposición de montaje no está observada y requiere revisión humana.",
  "No back, hardware, material, or manufacturing detail is inferred.": "No se infieren trasera, herrajes, material ni detalles de fabricación.",
  "Boxes are schematic reviewed panel occurrences, not manufacturing solids.": "Los volúmenes son ocurrencias esquemáticas revisadas, no sólidos de fabricación.",
  "Shelf heights are schematic evenly spaced hypotheses because separate part views do not observe assembly levels.": "Las alturas de las baldas son hipótesis esquemáticas equidistantes: las vistas separadas no observan niveles de montaje.",
  "Collision checking is not certified and remains not_evaluated.": "Las colisiones no están evaluadas ni certificadas.",
  "No part solid is created before explicit assembly-candidate review.": "No se crea ningún sólido antes de revisar explícitamente el montaje.",
};

export function translateAssumption(value) { return ASSUMPTION_LABELS[value] ?? value; }

function dimension(value = {}) {
  return { value: value.value_mm ?? null, state: value.state ?? "unknown", evidenceIds: [...(value.evidence_ids ?? [])], measurementIds: [...(value.measurement_ids ?? [])], viewIds: [...(value.view_ids ?? [])] };
}

export function normalisePartsWorkspace(snapshot = {}) {
  const result = snapshot.result ?? snapshot;
  const analysis = result.part_analysis;
  const reviewedByUse = new Map((result.pieces ?? []).map((piece) => [piece.proposal_id, {
    pieceId: piece.id,
    humanConfirmation: piece.human_confirmation,
    quantity: { value: piece.quantity ?? null, state: piece.field_states?.quantity ?? "unknown" },
    dimensions: {
      length: { value: piece.length_mm ?? null, state: piece.field_states?.length_mm ?? "unknown" },
      width: { value: piece.width_mm ?? null, state: piece.field_states?.width_mm ?? "unknown" },
      thickness: { value: piece.thickness_mm ?? null, state: piece.field_states?.thickness_mm ?? "unknown" },
    },
  }]));
  const observations = (analysis?.observations ?? []).map((item, index) => ({
    id: item.id, partKey: item.part_key ?? null, label: item.part_key ? `Pieza ${item.part_key}` : `Vista sin asociar ${index + 1}`,
    associationBasis: item.association_basis, status: item.status,
    views: (item.views ?? []).map((view) => ({ id: view.view_id, role: view.role, contourIds: [...(view.contour_ids ?? [])], bounds: view.local_bounds_mm ?? view.local_bounds_source ?? null })),
    viewIds: (item.views ?? []).map((view) => view.view_id),
    dimensions: { length: dimension(item.dimensions?.length), width: dimension(item.dimensions?.width), thickness: dimension(item.dimensions?.thickness) },
    quantity: { value: item.quantity?.value ?? null, state: item.quantity?.state ?? "unknown", evidenceIds: [...(item.quantity?.evidence_ids ?? [])] },
    sourceEntityIds: [...(item.source_entity_ids ?? [])], evidenceIds: [...(item.evidence_ids ?? [])], warnings: [...(item.warnings ?? [])],
  }));
  const candidates = (result.assembly_candidates ?? []).map((item) => {
    const uses = (item.uses ?? []).map((use) => ({
      id: use.id,
      partObservationId: use.part_observation_id,
      role: use.role,
      roleState: use.role_status,
      sourceQuantity: { value: use.source_quantity ?? null, state: use.quantity_source, evidenceIds: [...(use.evidence_ids ?? [])] },
      allocatedQuantity: { value: use.allocated_quantity ?? null, state: use.quantity_source, evidenceIds: [...(use.evidence_ids ?? [])] },
      occurrenceIndices: [...(use.occurrence_indices ?? [])],
      effective: reviewedByUse.get(use.id) ?? null,
    }));
    const assignments = new Map();
    uses.forEach((use) => {
      const label = observations.find((observation) => observation.id === use.partObservationId)?.label ?? use.partObservationId;
      assignments.set(label, [...(assignments.get(label) ?? []), ROLE_LABELS[use.role] ?? use.role]);
    });
    return ({
    id: item.id, family: item.family, familyLabel: FAMILY_LABELS[item.family] ?? item.family, familyState: item.family_status,
    layout: item.layout, layoutLabel: LAYOUT_LABELS[item.layout] ?? item.layout, layoutState: item.layout_status,
    uses,
    assignmentLabel: [...assignments].map(([label, roles]) => `${label} → ${[...new Set(roles)].join(" / ")}`).join(" · "),
    unassignedObservationIds: [...(item.unassigned_part_observation_ids ?? [])], constraints: [...(item.constraints ?? [])], derivedDimensions: [...(item.derived_dimensions ?? [])],
    unknownFields: [...(item.unknown_fields ?? [])], assumptions: (item.assumptions ?? []).map(translateAssumption), evidenceIds: [...(item.evidence_ids ?? [])], state: item.state, needsReview: item.needs_review !== false,
  });});
  return { isPartsOnly: result.input_semantics === "separated_part_views" && Boolean(analysis), candidateRevision: analysis?.candidate_revision ?? null, revisionNumber: result.result_revision ?? snapshot.result_revision ?? null, observations, candidates, warnings: [...(analysis?.warnings ?? [])], selectedCandidateId: result.selected_assembly_candidate_id ?? null, suggestedCandidateId: snapshot.agent_selected_assembly_candidate_id ?? snapshot.agent_selected_scenario_id ?? null };
}

export function preferredCandidateId(workspace, previewCandidateId = null) {
  return workspace?.selectedCandidateId ?? previewCandidateId ?? workspace?.suggestedCandidateId ?? workspace?.candidates?.[0]?.id ?? null;
}

export function partSelectionViewIds(workspace, selection) {
  if (!workspace?.isPartsOnly || selection === "all") return null;
  const observation = workspace.observations.find((item) => item.id === selection);
  return observation ? new Set(observation.viewIds) : new Set();
}

export function presentReviewedUse(use) {
  if (!use?.effective) return null;
  const field = (record, unit = "") => `${record?.value == null ? "Desconocido" : `${NUMBER.format(record.value)}${unit}`} · ${REVIEW_STATE_LABELS[record?.state] ?? record?.state ?? "Desconocido"}`;
  return {
    quantity: field(use.effective.quantity),
    length: field(use.effective.dimensions.length, " mm"),
    width: field(use.effective.dimensions.width, " mm"),
    thickness: field(use.effective.dimensions.thickness, " mm"),
  };
}

export function presentDescriptorV2(descriptor = {}) {
  return {
    version: descriptor.descriptor_version ?? "desconocida",
    familyLabel: FAMILY_LABELS[descriptor.family] ?? descriptor.family ?? "Familia desconocida",
    structureLabel: LAYOUT_LABELS[descriptor.structure === "top_base_between_sides" ? "between_sides" : descriptor.structure === "top_base_cap_sides" ? "cap_sides" : descriptor.structure] ?? descriptor.structure ?? "Montaje desconocido",
    thicknessLabel: (descriptor.thicknesses_mm ?? []).length ? descriptor.thicknesses_mm.map((value) => `${value} mm`).join(" · ") : "Grosor desconocido",
    classificationLabel: descriptor.classification_status === "confirmed" ? "Confirmada" : "Hipótesis",
    unknownLabels: (descriptor.unknown_fields ?? []).map((field) => FIELD_LABELS[field] ?? field),
  };
}
