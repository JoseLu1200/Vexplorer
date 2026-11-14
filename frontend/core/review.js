export function buildReviewPayload(snapshot, decisions) {
  if (!Number.isInteger(snapshot?.result_revision)) throw new TypeError("Falta la revisión base del resultado.");
  const clean = (decisions ?? []).map((decision) => {
    const reason = String(decision.reason ?? "").trim();
    if (!reason) throw new TypeError("Cada decisión necesita un motivo.");
    return { scenario_id: decision.scenario_id, decision: decision.decision, reason };
  });
  return { base_result_revision: snapshot.result_revision, decisions: clean };
}

export function buildScenarioReviewPayload(snapshot, values) {
  if (!Number.isInteger(snapshot?.result_revision)) throw new TypeError("Falta la revisión base del resultado.");
  if (!values?.scenario_id) throw new TypeError("Selecciona un escenario de montaje.");
  const reviewerName = String(values.reviewer_name ?? "").trim();
  if (!reviewerName) throw new TypeError("Indica el nombre de la persona revisora.");
  const thickness = Number(values.confirmed_thickness_mm);
  if (!Number.isFinite(thickness) || thickness <= 0) throw new TypeError("Indica un espesor confirmado mayor que cero.");
  const notes = String(values.notes ?? "").trim();
  if (!notes) throw new TypeError("La decisión necesita notas técnicas.");
  return {
    base_result_revision: snapshot.result_revision,
    reviewer_name: reviewerName,
    scenario_id: values.scenario_id,
    confirmed_thickness_mm: thickness,
    material: String(values.material ?? "").trim() || null,
    finish: String(values.finish ?? "").trim() || null,
    notes,
  };
}

export function buildAssemblyReviewPayload(snapshot, values) {
  if (!Number.isInteger(snapshot?.result_revision)) throw new TypeError("Falta la revisión base del resultado.");
  if (!values?.assembly_candidate_id) throw new TypeError("Selecciona una hipótesis de montaje.");
  const reviewerName = String(values.reviewer_name ?? "").trim();
  if (!reviewerName) throw new TypeError("Indica el nombre de la persona revisora.");
  const notes = String(values.notes ?? "").trim();
  if (!notes) throw new TypeError("La decisión necesita notas técnicas.");
  const payload = { base_result_revision: snapshot.result_revision, reviewer_name: reviewerName, assembly_candidate_id: values.assembly_candidate_id, notes };
  const reviewMaterial = String(values.material ?? "").trim();
  const reviewFinish = String(values.finish ?? "").trim();
  if (reviewMaterial) payload.material = reviewMaterial;
  if (reviewFinish) payload.finish = reviewFinish;
  const decisions = (values.decisions ?? []).map((decision) => {
    if (!decision.use_id) throw new TypeError("Falta la asignación de pieza que se confirma.");
    const quantity = decision.quantity === "" || decision.quantity == null ? null : Number(decision.quantity);
    const length = decision.length_mm === "" || decision.length_mm == null ? null : Number(decision.length_mm);
    const width = decision.width_mm === "" || decision.width_mm == null ? null : Number(decision.width_mm);
    const thickness = decision.thickness_mm === "" || decision.thickness_mm == null ? null : Number(decision.thickness_mm);
    if (quantity != null && (!Number.isInteger(quantity) || quantity <= 0)) throw new TypeError("La cantidad confirmada debe ser un entero mayor que cero.");
    if (length != null && (!Number.isFinite(length) || length <= 0)) throw new TypeError("El largo confirmado debe ser mayor que cero.");
    if (width != null && (!Number.isFinite(width) || width <= 0)) throw new TypeError("El ancho confirmado debe ser mayor que cero.");
    if (thickness != null && (!Number.isFinite(thickness) || thickness <= 0)) throw new TypeError("El grosor confirmado debe ser mayor que cero.");
    const mapped = {
      proposal_id: decision.use_id,
      action: "confirm",
      role: decision.role ?? "unknown",
      quantity,
      thickness_mm: thickness,
      material: String(decision.material ?? "").trim() || null,
      finish: String(decision.finish ?? "").trim() || null,
      notes: String(decision.notes ?? "").trim() || null,
    };
    if (length != null) mapped.length_mm = length;
    if (width != null) mapped.width_mm = width;
    return mapped;
  });
  if (decisions.length) payload.decisions = decisions;
  return payload;
}

export function changedReviewDecisionValues(current = {}, original = {}) {
  const changed = Object.keys({ ...original, ...current }).some((key) => String(current[key] ?? "") !== String(original[key] ?? ""));
  return changed ? { ...current } : null;
}
