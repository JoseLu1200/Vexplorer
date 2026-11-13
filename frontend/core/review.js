export function buildReviewPayload(snapshot, decisions) {
  if (!Number.isInteger(snapshot?.result_revision)) throw new TypeError("Falta la revisión base del resultado.");
  const clean = (decisions ?? []).map((decision) => {
    const reason = String(decision.reason ?? "").trim();
    if (!reason) throw new TypeError("Cada decisión necesita un motivo.");
    return { scenario_id: decision.scenario_id, decision: decision.decision, reason };
  });
  return { base_result_revision: snapshot.result_revision, decisions: clean };
}
