const EURO = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: 2 });
const NUMBER = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

export function availableModes(capabilities = {}) {
  return [
    { id: "geometry_only", enabled: true },
    { id: "live", enabled: Boolean(capabilities.live_available) },
    { id: "recorded_replay", enabled: Boolean(capabilities.recorded_replay_available ?? capabilities.replay_available) },
  ];
}

export function normaliseRunPayload(payload = {}) {
  if (!payload.run) return payload;
  const result = payload.result ?? null;
  return {
    ...payload.run,
    result,
    result_revision: result?.result_revision ?? payload.run.result_revision ?? null,
  };
}

export function componentsForSnapshot(snapshot = {}, ledger = {}) {
  const scenarios = snapshot.result?.scenarios ?? snapshot.scenarios ?? snapshot.decomposition_scenarios ?? ledger.scenarios ?? [];
  const selectedId = snapshot.result?.review?.selected_scenario_id ?? snapshot.selected_scenario_id;
  const active = scenarios.find((item) => item.id === selectedId) ?? scenarios[0];
  const reviewedPieces = snapshot.result?.pieces ?? [];
  return {
    scenarios,
    components: reviewedPieces.length ? reviewedPieces : (active?.components ?? active?.component_proposals ?? ledger.component_proposals ?? []),
  };
}

function known(value, suffix = "") {
  return Number.isFinite(value) ? `${NUMBER.format(value)}${suffix}` : "Desconocido";
}

export function presentEstimate(estimate = {}) {
  return {
    provisional: estimate.provisional !== false,
    revisionLabel: Number.isInteger(estimate.result_revision) ? `Revisión ${estimate.result_revision}` : "Revisión desconocida",
    totalLabel: Number.isFinite(estimate.total) ? EURO.format(estimate.total) : "Total pendiente",
    hoursLabel: known(estimate.total_hours ?? estimate.hours, " h"),
    items: (estimate.line_items ?? estimate.concepts ?? []).map((item) => ({
      ...item,
      quantityLabel: Number.isFinite(item.factor) ? `Factor ${NUMBER.format(item.factor)}` : known(item.quantity, item.unit ? ` ${item.unit}` : ""),
      rateLabel: Number.isFinite(item.base_amount) ? `Base ${EURO.format(item.base_amount)}` : (Number.isFinite(item.rate) ? EURO.format(item.rate) : "Desconocido"),
      amountLabel: Number.isFinite(item.amount) ? EURO.format(item.amount) : "Pendiente",
    })),
    exclusions: estimate.exclusions ?? [],
  };
}
