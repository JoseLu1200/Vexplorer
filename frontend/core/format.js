const SOURCE_LABELS = Object.freeze({
  observed: "Observado",
  derived: "Calculado",
  hypothesis: "Hipótesis",
  human_confirmed: "Confirmado por persona",
  unknown: "Desconocido",
});

const NUMBER_FORMAT = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

export function formatMeasurement(value, unit = "mm") {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "Desconocido";
  }
  const suffix = unit === "source" ? "u. fuente" : unit;
  return `${NUMBER_FORMAT.format(Number(value))} ${suffix}`;
}

export function sourceLabel(origin) {
  return SOURCE_LABELS[origin] ?? SOURCE_LABELS.unknown;
}
