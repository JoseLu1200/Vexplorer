const SOURCE_LABELS = Object.freeze({
  observed: "Observado",
  derived: "Calculado",
  hypothesis: "Hipótesis",
  human_confirmed: "Confirmado por persona",
  unknown: "Desconocido",
});

function decimalsForTolerance(tolerance) { const numeric=Number(tolerance); return Number.isFinite(numeric)&&numeric>0?Math.min(6,Math.max(0,Math.ceil(-Math.log10(numeric)))):2; }

export function formatMeasurement(value, unit = "mm", { tolerance = 0.01 } = {}) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "Desconocido";
  }
  const suffix = unit === "source" ? "u. fuente" : unit;
  return `${new Intl.NumberFormat("es-ES",{maximumFractionDigits:decimalsForTolerance(tolerance)}).format(Number(value))} ${suffix}`;
}

export function sourceLabel(origin) {
  return SOURCE_LABELS[origin] ?? SOURCE_LABELS.unknown;
}
