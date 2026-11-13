const FAMILY_LABELS = { rectangular_shelving: "Estantería rectangular", unknown: "Familia desconocida" };
const LAYOUT_LABELS = { between_sides: "Tapa y base entre laterales", cap_sides: "Tapa y base cubren laterales", unknown: "Montaje desconocido" };
const FIELD_LABELS = { quantity: "Cantidad", length: "Largo", width: "Ancho", thickness: "Grosor", material: "Material", finish: "Acabado" };

function dimension(value = {}) {
  return { value: value.value_mm ?? null, state: value.state ?? "unknown", evidenceIds: [...(value.evidence_ids ?? [])], measurementIds: [...(value.measurement_ids ?? [])], viewIds: [...(value.view_ids ?? [])] };
}

export function normalisePartsWorkspace(snapshot = {}) {
  const result = snapshot.result ?? snapshot;
  const analysis = result.part_analysis;
  const observations = (analysis?.observations ?? []).map((item, index) => ({
    id: item.id, partKey: item.part_key ?? null, label: item.part_key ? `Pieza ${item.part_key}` : `Vista sin asociar ${index + 1}`,
    associationBasis: item.association_basis, status: item.status,
    views: (item.views ?? []).map((view) => ({ id: view.view_id, role: view.role, contourIds: [...(view.contour_ids ?? [])], bounds: view.local_bounds_mm ?? view.local_bounds_source ?? null })),
    viewIds: (item.views ?? []).map((view) => view.view_id),
    dimensions: { length: dimension(item.dimensions?.length), width: dimension(item.dimensions?.width), thickness: dimension(item.dimensions?.thickness) },
    quantity: { value: item.quantity?.value ?? null, state: item.quantity?.state ?? "unknown", evidenceIds: [...(item.quantity?.evidence_ids ?? [])] },
    sourceEntityIds: [...(item.source_entity_ids ?? [])], evidenceIds: [...(item.evidence_ids ?? [])], warnings: [...(item.warnings ?? [])],
  }));
  const candidates = (result.assembly_candidates ?? []).map((item) => ({
    id: item.id, family: item.family, familyLabel: FAMILY_LABELS[item.family] ?? item.family, familyState: item.family_status,
    layout: item.layout, layoutLabel: LAYOUT_LABELS[item.layout] ?? item.layout, layoutState: item.layout_status,
    uses: (item.uses ?? []).map((use) => ({ partObservationId: use.part_observation_id, role: use.role, roleState: use.role_status, quantity: { value: use.quantity ?? null, state: use.quantity_source, evidenceIds: [...(use.evidence_ids ?? [])] } })),
    unassignedObservationIds: [...(item.unassigned_part_observation_ids ?? [])], constraints: [...(item.constraints ?? [])], derivedDimensions: [...(item.derived_dimensions ?? [])],
    unknownFields: [...(item.unknown_fields ?? [])], assumptions: [...(item.assumptions ?? [])], evidenceIds: [...(item.evidence_ids ?? [])], state: item.state, needsReview: item.needs_review !== false,
  }));
  return { isPartsOnly: result.input_semantics === "separated_part_views" && Boolean(analysis), candidateRevision: analysis?.candidate_revision ?? null, observations, candidates, warnings: [...(analysis?.warnings ?? [])], selectedCandidateId: result.selected_assembly_candidate_id ?? null };
}

export function partSelectionViewIds(workspace, selection) {
  if (!workspace?.isPartsOnly || selection === "all") return null;
  const observation = workspace.observations.find((item) => item.id === selection);
  return observation ? new Set(observation.viewIds) : new Set();
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
