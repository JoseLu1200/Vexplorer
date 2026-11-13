function finitePoint(point) {
  return (Array.isArray(point) && point.length >= 2 && point.slice(0, 2).every(Number.isFinite))
    || (point && Number.isFinite(point.x) && Number.isFinite(point.y));
}

function pointTuple(point) { return Array.isArray(point) ? point.slice(0, 2) : [point.x, point.y]; }

function resolvedPoint(record, name, metric) {
  const point = metric
    ? (record?.[`${name}_mm`] ?? record?.[name]?.mm)
    : (record?.[`${name}_source`] ?? record?.[name]?.source ?? record?.[name]);
  return finitePoint(point) ? pointTuple(point) : null;
}

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
  const entityViews = new Map();
  (extraction?.views ?? []).forEach((view) => (view.entity_ids ?? []).forEach((id) => entityViews.set(id, [...(entityViews.get(id) ?? []), view.id])));
  const dimensionEntityIds = new Set((extraction?.dimension_graphics ?? []).map((item) => item.source_entity_id).filter(Boolean));
  (extraction?.entities ?? []).forEach((entity) => {
    if (claimedEntities.has(entity.id)) return;
    if (String(entity.kind).toUpperCase() === "DIMENSION" && ((extraction?.dimension_graphics?.length ?? 0) > 0 || dimensionEntityIds.has(entity.id))) return;
    const points = metric ? entity.points_mm : entity.source_points;
    if (!Array.isArray(points) || points.length < 2 || !points.every(finitePoint)) return;
    const viewIds = entityViews.get(entity.id) ?? [];
    paths.push({ id: `entity:${entity.id}`, viewId: viewIds.length === 1 ? viewIds[0] : null, entityIds: [entity.id], points: points.map(pointTuple), closed: false, kind: entity.kind });
  });
  const texts = (extraction?.texts ?? []).flatMap((item) => {
    const position = resolvedPoint(item, "position", metric);
    return position ? [{ id: item.id, viewId: item.view_id, text: safeText(item.text), position }] : [];
  });
  const dimensions = (extraction?.dimension_graphics ?? []).flatMap((item) => {
    const a = resolvedPoint(item, "extension_start_a", metric);
    const b = resolvedPoint(item, "extension_start_b", metric);
    const start = resolvedPoint(item, "dimension_start", metric);
    const end = resolvedPoint(item, "dimension_end", metric);
    const position = resolvedPoint(item, "text_position", metric);
    const segments = [[a, start], [b, end], [start, end]].filter((segment) => segment.every(Boolean));
    if (!segments.length && !position) return [];
    return [{ id: item.id, dimensionId: item.dimension_id, viewId: item.view_id, label: safeText(item.display_text ?? item.raw_text), segments, position }];
  });
  const model = {
    drawingId: extraction?.drawing_id,
    coordinateUnit: metric ? "mm" : "source",
    unitLabel: metric ? "Milímetros" : "Unidad sin resolver",
    views: extraction?.views ?? [],
    paths,
    texts,
    dimensions,
    warnings: extraction?.warnings ?? [],
  };
  model.pointsForViews = (viewIds) => {
    const allowed = (viewId) => !viewIds || viewIds.has(viewId);
    return [
      ...model.paths.filter((item) => allowed(item.viewId)).flatMap((item) => item.points),
      ...model.texts.filter((item) => allowed(item.viewId)).map((item) => item.position),
      ...model.dimensions.filter((item) => allowed(item.viewId)).flatMap((item) => item.segments.flat()),
    ];
  };
  model.fitPaddingForViews = (viewIds) => {
    const allowed = (viewId) => !viewIds || viewIds.has(viewId);
    const labels = [
      ...model.texts.filter((item) => allowed(item.viewId)).map((item) => item.text),
      ...model.dimensions.filter((item) => allowed(item.viewId)).map((item) => item.label),
    ];
    const longest = labels.reduce((length, label) => Math.max(length, String(label ?? "").length), 0);
    return Math.min(180, Math.max(28, longest * 8 + 16));
  };
  return model;
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
