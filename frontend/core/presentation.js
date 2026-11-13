const EURO = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: 2 });
const NUMBER = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

export function availableModes(capabilities = {}) {
  return [
    { id: "geometry_only", enabled: true },
    { id: "live", enabled: Boolean(capabilities.live_available) },
    { id: "recorded_replay", enabled: Boolean(capabilities.replay_available) },
  ];
}

function known(value, suffix = "") {
  return Number.isFinite(value) ? `${NUMBER.format(value)}${suffix}` : "Desconocido";
}

export function presentEstimate(estimate = {}) {
  return {
    provisional: estimate.provisional !== false,
    revisionLabel: Number.isInteger(estimate.result_revision) ? `Revisión ${estimate.result_revision}` : "Revisión desconocida",
    totalLabel: Number.isFinite(estimate.total) ? EURO.format(estimate.total) : "Total pendiente",
    hoursLabel: known(estimate.total_hours, " h"),
    items: (estimate.line_items ?? estimate.concepts ?? []).map((item) => ({
      ...item,
      quantityLabel: known(item.quantity, item.unit ? ` ${item.unit}` : ""),
      rateLabel: Number.isFinite(item.rate) ? EURO.format(item.rate) : "Desconocido",
      amountLabel: Number.isFinite(item.amount) ? EURO.format(item.amount) : "Pendiente",
    })),
    exclusions: estimate.exclusions ?? [],
  };
}
