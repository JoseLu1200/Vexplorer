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

function cleanNumber(value) { return Math.abs(value) < 1e-10 ? 0 : Number(value.toFixed(10)); }
function segmentLength(start, end) {
  if (!start || !end) return null;
  const value = Math.hypot(end[0] - start[0], end[1] - start[1]);
  return Number.isFinite(value) ? cleanNumber(value) : null;
}

function dimensionConflictsByEntity(warnings = []) {
  const conflicts = new Map();
  warnings.forEach((warning) => {
    const match = /^(dimension_(?:scale_conflict|text_conflict|text_override)):([^:]+):(.*)$/.exec(String(warning));
    if (!match) return;
    const [, kind, entityId, detail] = match;
    const reason = kind === "dimension_scale_conflict"
      ? `Cota en conflicto: DIMLFAC ${detail.replace(/^scale=/, "")} difiere de la geometría.`
      : kind === "dimension_text_conflict"
        ? `Cota en conflicto: el texto (${detail}) difiere de la geometría.`
        : `Cota en conflicto: texto forzado (${detail.replace(/^text=/, "")}).`;
    const current = conflicts.get(entityId) ?? [];
    current.push(reason);
    conflicts.set(entityId, current);
  });
  return conflicts;
}
function circlePoint(center, radius, angleDeg) { const radians=angleDeg*Math.PI/180; return [cleanNumber(center[0]+radius*Math.cos(radians)),cleanNumber(center[1]+radius*Math.sin(radians))]; }
function positiveSweep(start,end){const delta=((end-start)%360+360)%360;return delta||360;}

function resolvedCircular(entity,metric){
  const raw=entity?.circular,kind=String(raw?.kind??"").toLowerCase(),center=resolvedPoint(raw,"center",metric),radius=metric?raw?.radius_mm:raw?.radius_source;
  if(!["circle","arc"].includes(kind)||!center||!Number.isFinite(radius)||radius<=0)return null;
  if(kind==="arc"&&(!Number.isFinite(raw.start_angle_deg)||!Number.isFinite(raw.end_angle_deg)))return null;
  return {kind,center,radius,startAngle:raw.start_angle_deg??null,endAngle:raw.end_angle_deg??null};
}

function circularFitPoints(circular){
  if(circular.kind==="circle")return [0,90,180,270].map((angle)=>circlePoint(circular.center,circular.radius,angle));
  const delta=positiveSweep(circular.startAngle,circular.endAngle),angles=[circular.startAngle];
  [0,90,180,270].forEach((angle)=>{const relative=((angle-circular.startAngle)%360+360)%360;if(relative>1e-9&&relative<delta-1e-9)angles.push(angle);});
  angles.push(circular.endAngle);return angles.map((angle)=>circlePoint(circular.center,circular.radius,angle));
}

export function safeText(value) {
  return String(value ?? "");
}

function parseViewBounds(view, metric) {
  const raw = metric ? view?.bounds_mm : (view?.bounds_source ?? view?.bounds_mm);
  if (Array.isArray(raw) && raw.length >= 4 && raw.slice(0, 4).every(Number.isFinite)) {
    return { minX: raw[0], minY: raw[1], maxX: raw[2], maxY: raw[3] };
  }
  if (raw && typeof raw === "object") {
    const minX = raw.min_x ?? raw.minX;
    const minY = raw.min_y ?? raw.minY;
    const maxX = raw.max_x ?? raw.maxX;
    const maxY = raw.max_y ?? raw.maxY;
    if ([minX, minY, maxX, maxY].every(Number.isFinite)) {
      return { minX, minY, maxX, maxY };
    }
  }
  return null;
}

function pointsInBounds(points, bounds, eps = 1e-6) {
  return Array.isArray(points) && points.length > 0 && points.every(([x, y]) => (
    x >= bounds.minX - eps && x <= bounds.maxX + eps
    && y >= bounds.minY - eps && y <= bounds.maxY + eps
  ));
}

function resolvePathViews(explicitIds, points, viewBoundsList) {
  const unique = [...new Set((explicitIds ?? []).filter(Boolean))];
  const viewIds = unique.length
    ? unique
    : viewBoundsList.filter(({ bounds }) => pointsInBounds(points, bounds)).map(({ id }) => id);
  return {
    viewId: viewIds.length === 1 ? viewIds[0] : null,
    viewIds,
  };
}

export function pathMatchesView(item, activeView) {
  if (!activeView || activeView === "all") return true;
  if (activeView instanceof Set) {
    return activeView.has(item?.viewId)
      || (Array.isArray(item?.viewIds) && item.viewIds.some((id) => activeView.has(id)));
  }
  return item?.viewId === activeView
    || (Array.isArray(item?.viewIds) && item.viewIds.includes(activeView));
}

export function normaliseDrawing(extraction) {
  const metric = extraction?.coordinate_unit === "mm" || (extraction?.source_unit !== "unknown" && Number.isFinite(extraction?.unit_scale_to_mm));
  const views = extraction?.views ?? [];
  const viewBoundsList = views
    .map((view) => ({ id: view?.id, bounds: parseViewBounds(view, metric) }))
    .filter((item) => item.id && item.bounds);
  const contours = extraction?.contours ?? [];
  const paths = contours.flatMap((contour) => {
    const rawPoints = metric ? contour.points_mm : (contour.source_points ?? contour.points_source);
    if (!Array.isArray(rawPoints) || rawPoints.length < 2 || !rawPoints.every(finitePoint)) return [];
    const points = rawPoints.map(pointTuple);
    const explicitIds = [
      ...(Array.isArray(contour.view_ids) ? contour.view_ids : []),
      contour.view_id ?? contour.view,
    ];
    const { viewId, viewIds } = resolvePathViews(explicitIds, points, viewBoundsList);
    return [{
      id: contour.id,
      viewId,
      viewIds,
      entityIds: [...(contour.source_entity_ids ?? [])],
      points,
      closed: Boolean(contour.closed),
    }];
  });
  const claimedEntities = new Set(contours.flatMap((contour) => contour.source_entity_ids ?? []));
  const entityViews = new Map();
  views.forEach((view) => {
    if (!view?.id) return;
    (view.entity_ids ?? []).forEach((id) => {
      const existing = entityViews.get(id);
      if (!existing) entityViews.set(id, [view.id]);
      else if (!existing.includes(view.id)) existing.push(view.id);
    });
  });
  const dimensionEntityIds = new Set((extraction?.dimension_graphics ?? []).map((item) => item.source_entity_id).filter(Boolean));
  (extraction?.entities ?? []).forEach((entity) => {
    if (claimedEntities.has(entity.id)) return;
    if (String(entity.kind).toUpperCase() === "DIMENSION" && ((extraction?.dimension_graphics?.length ?? 0) > 0 || dimensionEntityIds.has(entity.id))) return;
    const circular = resolvedCircular(entity, metric);
    const rawPoints = metric ? entity.points_mm : entity.source_points;
    const explicitIds = [
      ...(entityViews.get(entity.id) ?? []),
      ...(Array.isArray(entity.view_ids) ? entity.view_ids : []),
      entity.view_id ?? entity.view,
    ];
    if (circular) {
      const points = circularFitPoints(circular);
      const { viewId, viewIds } = resolvePathViews(explicitIds, points, viewBoundsList);
      paths.push({ id: `entity:${entity.id}`, viewId, viewIds, entityIds: [entity.id], points, closed: circular.kind === "circle", kind: entity.kind, circular });
      return;
    }
    if (!Array.isArray(rawPoints) || rawPoints.length < 2 || !rawPoints.every(finitePoint)) return;
    const points = rawPoints.map(pointTuple);
    const { viewId, viewIds } = resolvePathViews(explicitIds, points, viewBoundsList);
    paths.push({ id: `entity:${entity.id}`, viewId, viewIds, entityIds: [entity.id], points, closed: false, kind: entity.kind });
  });
  const texts = (extraction?.texts ?? []).flatMap((item) => {
    const position = resolvedPoint(item, "position", metric);
    return position ? [{ id: item.id, viewId: item.view_id, text: safeText(item.text), position }] : [];
  });
  const dimMap = new Map(
    (extraction?.dimensions ?? [])
      .filter((dim) => dim?.id != null)
      .map((dim) => [dim.id, dim]),
  );
  const warningConflicts = dimensionConflictsByEntity(extraction?.warnings);
  const dimensions = (extraction?.dimension_graphics ?? []).flatMap((item) => {
    const a = resolvedPoint(item, "extension_start_a", metric);
    const b = resolvedPoint(item, "extension_start_b", metric);
    const start = resolvedPoint(item, "dimension_start", metric);
    const end = resolvedPoint(item, "dimension_end", metric);
    const position = resolvedPoint(item, "text_position", metric);
    const segments = [[a, start], [b, end], [start, end]].filter((segment) => segment.every(Boolean));
    if (!segments.length && !position) return [];
    const dim = dimMap.get(item.dimension_id);
    const warningReasons = warningConflicts.get(item.source_entity_id) ?? [];
    const conflict = Boolean(warningReasons.length || dim?.conflict || dim?.state === "conflict" || item?.conflict);
    const baseLabel = safeText(item.display_text ?? item.raw_text);
    const declaredGeometry = metric ? dim?.value_mm : dim?.source_value;
    const measuredGeometry = segmentLength(start, end);
    const geomVal = Number.isFinite(declaredGeometry) ? declaredGeometry : measuredGeometry;
    const hasGeomVal = Number.isFinite(geomVal);
    const unitText = metric ? "mm" : "source-unit";
    const label = conflict
      ? (hasGeomVal ? `${baseLabel} [conflicto: geom ${cleanNumber(geomVal)} ${unitText}]` : `${baseLabel} [conflicto]`)
      : baseLabel;
    const conflictReason = conflict
      ? (dim?.conflict_reason ?? item?.conflict_reason ?? dim?.reason ?? item?.reason ?? (warningReasons.join(" ") || null))
      : null;
    return [{
      id: item.id,
      dimensionId: item.dimension_id,
      viewId: item.view_id,
      label,
      segments,
      position,
      conflict,
      conflictReason,
      geometryValue: conflict && hasGeomVal ? geomVal : null,
    }];
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
  model.pointsForViews = (viewIds) => [
    ...model.paths.filter((item) => pathMatchesView(item, viewIds)).flatMap((item) => item.points),
    ...model.texts.filter((item) => pathMatchesView(item, viewIds)).map((item) => item.position),
    ...model.dimensions.filter((item) => pathMatchesView(item, viewIds)).flatMap((item) => item.segments.flat()),
  ];
  model.fitPaddingForViews = (viewIds) => {
    const labels = [
      ...model.texts.filter((item) => pathMatchesView(item, viewIds)).map((item) => item.text),
      ...model.dimensions.filter((item) => pathMatchesView(item, viewIds)).map((item) => item.label),
    ];
    const longest = labels.reduce((length, label) => Math.max(length, String(label ?? "").length), 0);
    return { left: 28, right: Math.min(180, Math.max(28, longest * 8 + 16)), top: 28, bottom: 28 };
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

export function svgCircularPath(circular){
  if(!circular?.center||!Number.isFinite(circular.radius)||circular.radius<=0)return "";
  const [cx,cy]=circular.center,r=circular.radius;
  if(circular.kind==="circle")return `M ${cleanNumber(cx+r)} ${cleanNumber(-cy)} A ${r} ${r} 0 1 0 ${cleanNumber(cx-r)} ${cleanNumber(-cy)} A ${r} ${r} 0 1 0 ${cleanNumber(cx+r)} ${cleanNumber(-cy)} Z`;
  if(circular.kind!=="arc"||!Number.isFinite(circular.startAngle)||!Number.isFinite(circular.endAngle))return "";
  const start=circlePoint(circular.center,r,circular.startAngle),end=circlePoint(circular.center,r,circular.endAngle),large=positiveSweep(circular.startAngle,circular.endAngle)>180?1:0;
  return `M ${start[0]} ${cleanNumber(-start[1])} A ${r} ${r} 0 ${large} 0 ${end[0]} ${cleanNumber(-end[1])}`;
}
