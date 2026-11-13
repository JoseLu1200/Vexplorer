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
  const thickness = Number(values.confirmed_thickness_mm);
  if (!Number.isFinite(thickness) || thickness <= 0) throw new TypeError("Indica un espesor confirmado mayor que cero.");
  const notes = String(values.notes ?? "").trim();
  if (!notes) throw new TypeError("La decisión necesita notas técnicas.");
  return {
    base_result_revision: snapshot.result_revision,
    scenario_id: values.scenario_id,
    confirmed_thickness_mm: thickness,
    material: String(values.material ?? "").trim() || null,
    finish: String(values.finish ?? "").trim() || null,
    notes,
  };
}
