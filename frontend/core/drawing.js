function finitePoint(point) {
  return (Array.isArray(point) && point.length >= 2 && point.slice(0, 2).every(Number.isFinite))
    || (point && Number.isFinite(point.x) && Number.isFinite(point.y));
}

function pointTuple(point) { return Array.isArray(point) ? point.slice(0, 2) : [point.x, point.y]; }

export function safeText(value) {
  return String(value ?? "");
}

export function normaliseDrawing(extraction) {
  const metric = extraction?.coordinate_unit === "mm" || (extraction?.source_unit !== "unknown" && Number.isFinite(extraction?.unit_scale_to_mm));
  const contours = extraction?.contours ?? [];
  const paths = contours.flatMap((contour) => {
    const points = metric ? contour.points_mm : (contour.source_points ?? contour.points_source);
    if (!Array.isArray(points) || points.length < 2 || !points.every(finitePoint)) return [];
    return [{
      id: contour.id,
      viewId: contour.view_id ?? contour.view,
      entityIds: [...(contour.source_entity_ids ?? [])],
      points: points.map(pointTuple),
      closed: Boolean(contour.closed),
    }];
  });
  const claimedEntities = new Set(contours.flatMap((contour) => contour.source_entity_ids ?? []));
  (extraction?.entities ?? []).forEach((entity) => {
    if (claimedEntities.has(entity.id)) return;
    const points = metric ? entity.points_mm : entity.source_points;
    if (!Array.isArray(points) || points.length < 2 || !points.every(finitePoint)) return;
    paths.push({ id: `entity:${entity.id}`, viewId: null, entityIds: [entity.id], points: points.map(pointTuple), closed: false, kind: entity.kind });
  });
  return {
    drawingId: extraction?.drawing_id,
    coordinateUnit: metric ? "mm" : "source",
    unitLabel: metric ? "Milímetros" : "Unidad sin resolver",
    views: extraction?.views ?? [],
    paths,
    warnings: extraction?.warnings ?? [],
  };
}

export function selectionForComponent(component, drawing) {
  const contourIds = new Set(component?.source_contour_ids ?? component?.contour_ids ?? []);
  const evidenceIds = new Set(component?.evidence_ids ?? []);
  const entityIds = new Set();
  (drawing?.contours ?? []).forEach((contour) => {
    if (contourIds.has(contour.id)) (contour.source_entity_ids ?? []).forEach((id) => entityIds.add(id));
  });
  (drawing?.evidence ?? []).forEach((evidence) => {
    if (evidenceIds.has(evidence.id)) (evidence.source_entity_ids ?? []).forEach((id) => entityIds.add(id));
  });
  return { componentId: component?.id, contourIds, evidenceIds, entityIds };
}

export function svgPath(points, closed = false) {
  if (!Array.isArray(points) || points.length < 2 || !points.every(finitePoint)) return "";
  return `${points.map((raw, index) => { const point = pointTuple(raw); return `${index ? "L" : "M"} ${point[0]} ${-point[1]}`; }).join(" ")}${closed ? " Z" : ""}`;
}
