function xyz(value) {
  if (Array.isArray(value) && value.length >= 3) return value.slice(0, 3);
  if (value && [value.x, value.y, value.z].every(Number.isFinite)) return [value.x, value.y, value.z];
  return null;
}

export function normaliseScene(raw = {}) {
  const warnings = [...(raw.warnings ?? [])];
  const objects = (raw.objects ?? []).flatMap((item, index) => {
    const position = xyz(item.position_mm);
    const dimensions = xyz(item.dimensions_mm);
    if (!position || !dimensions || dimensions.some((value) => value <= 0)) return [];
    const pieceId = item.piece_id ?? item.proposal_id ?? `object-${index}`;
    return [{
      key: `${pieceId}:${item.occurrence_index ?? index}`,
      pieceId, proposalId: item.proposal_id, role: item.role, label: item.label ?? item.role ?? pieceId,
      position, dimensions, evidenceIds: [...(item.evidence_ids ?? [])], contourIds: [...(item.source_contour_ids ?? item.contour_ids ?? [])],
      placementBasis: item.placement_basis ?? null, partObservationId: item.part_observation_id ?? null,
      placementStatus: item.placement_status ?? "human_selected", placementConstraintIds: [...(item.placement_constraint_ids ?? [])],
    }];
  });
  if (objects.length < (raw.objects ?? []).length && !warnings.some((item) => /dimension|medida|grosor/i.test(item))) warnings.push("No se representan objetos con posición o medidas incompletas.");
  return { state: raw.state ?? "unavailable", coordinateSystem: raw.coordinate_system, objects, warnings, assumptions: raw.assumptions ?? [], collisionStatus: raw.collision_status ?? "not_evaluated" };
}

export function sceneMeshCenter(item) {
  return item.position.map((value, index) => value + item.dimensions[index] / 2);
}

export function cameraZoomPosition(position, target, factor) {
  return position.map((value, index) => target[index] + (value - target[index]) * factor);
}
