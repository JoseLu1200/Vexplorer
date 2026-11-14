const NUMBER_FORMAT = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

const DIMENSION_LABELS = Object.freeze({
  "dimensions.width_mm": "Ancho",
  "dimensions.depth_mm": "Fondo",
  "dimensions.height_mm": "Alto",
});

const ROLE_LABELS = Object.freeze({
  shelf: "Baldas",
  side: "Costados",
  top: "Tapa",
  base: "Base",
  back: "Trasera",
  divider: "Divisores",
  door: "Puertas",
  drawer: "Cajones",
  tabletop: "Tablero",
  side_support: "Soportes laterales",
  corner_support: "Patas",
});

const STRUCTURE_LABELS = Object.freeze({
  top_base_between_sides: "entre costados",
  top_base_cap_sides: "sobre costados",
  side_support_table: "dos soportes laterales",
  corner_support_table: "cuatro patas",
});

const SCORE_COMPONENT_LABELS = Object.freeze({
  dimensions: "Dimensiones",
  roles: "Roles",
  thickness: "Espesor",
  cosine: "Similitud coseno",
});

function isUnknownValue(value) {
  if (value === null || value === undefined) return true;
  const normalized = String(value).trim();
  return normalized === "" || normalized === "None" || normalized === "null" || normalized === "undefined" || normalized === "unknown";
}

function parseFiniteNumber(value) {
  if (value === null || value === undefined || typeof value === "boolean") return null;
  const trimmed = String(value).trim();
  if (!trimmed) return null;
  const num = Number(trimmed);
  return Number.isFinite(num) ? num : null;
}

function formatNumber(value) {
  return NUMBER_FORMAT.format(value);
}

function formatDelta(delta, unit = "") {
  if (!Number.isFinite(delta) || delta === 0) return "";
  const sign = delta > 0 ? "+" : "";
  const suffix = unit ? ` ${unit}` : "";
  return ` (${sign}${formatNumber(delta)}${suffix})`;
}

function parseNumberList(value) {
  if (Array.isArray(value)) {
    const nums = value.map(Number).filter(Number.isFinite);
    return nums.length ? nums : null;
  }
  if (isUnknownValue(value)) return null;
  const trimmed = String(value).trim();
  if (!trimmed.startsWith("[") && !trimmed.startsWith("(")) return null;
  const inner = trimmed.slice(1, -1).trim();
  if (!inner) return [];
  const nums = inner.split(",").map((part) => Number(part.trim())).filter(Number.isFinite);
  return nums;
}

function formatThicknessList(nums) {
  if (!nums || !nums.length) return "Desconocido";
  return `${nums.map(formatNumber).join(", ")} mm`;
}

function formatScalarValue(value, unit = "") {
  if (isUnknownValue(value)) return "Desconocido";
  const num = parseFiniteNumber(value);
  if (num !== null) return unit ? `${formatNumber(num)} ${unit}` : formatNumber(num);
  return String(value).trim();
}

function formatStructureValue(value) {
  if (isUnknownValue(value)) return "Desconocido";
  const key = String(value).trim();
  return STRUCTURE_LABELS[key] ?? key;
}

/**
 * Formats a single SimilarityDifference entry into a Spanish human-readable bullet
 * and a raw technical comparison line.
 * @param {object} difference
 * @returns {{ summary: string, technical: string }}
 */
export function formatDifference(difference) {
  if (typeof difference === "string") {
    return { summary: difference, technical: difference };
  }
  const field = String(difference?.field ?? "campo");
  const rawQuery = difference?.query_value;
  const rawCandidate = difference?.candidate_value;
  const technical = `${field}: ${isUnknownValue(rawQuery) ? "Desconocido" : String(rawQuery)} -> ${isUnknownValue(rawCandidate) ? "Desconocido" : String(rawCandidate)}`;

  if (DIMENSION_LABELS[field]) {
    const label = DIMENSION_LABELS[field];
    const qNum = parseFiniteNumber(rawQuery);
    const cNum = parseFiniteNumber(rawCandidate);
    const qText = formatScalarValue(rawQuery, "mm");
    const cText = formatScalarValue(rawCandidate, "mm");
    const deltaText = qNum !== null && cNum !== null ? formatDelta(cNum - qNum, "mm") : "";
    return { summary: `${label}: ${qText} -> ${cText}${deltaText}`, technical };
  }

  if (field.startsWith("roles.")) {
    const roleKey = field.slice("roles.".length);
    const label = ROLE_LABELS[roleKey] ?? roleKey;
    const qNum = parseFiniteNumber(rawQuery);
    const cNum = parseFiniteNumber(rawCandidate);
    const qText = formatScalarValue(rawQuery);
    const cText = formatScalarValue(rawCandidate);
    const deltaText = qNum !== null && cNum !== null ? formatDelta(cNum - qNum) : "";
    return { summary: `${label}: ${qText} -> ${cText}${deltaText}`, technical };
  }

  if (field === "thicknesses_mm") {
    const qList = parseNumberList(rawQuery);
    const cList = parseNumberList(rawCandidate);
    const qText = qList !== null ? formatThicknessList(qList) : formatScalarValue(rawQuery, "mm");
    const cText = cList !== null ? formatThicknessList(cList) : formatScalarValue(rawCandidate, "mm");
    const deltaText = qList?.length === 1 && cList?.length === 1 ? formatDelta(cList[0] - qList[0], "mm") : "";
    return { summary: `Espesor: ${qText} -> ${cText}${deltaText}`, technical };
  }

  if (field === "structure") {
    return {
      summary: `Estructura: ${formatStructureValue(rawQuery)} -> ${formatStructureValue(rawCandidate)}`,
      technical,
    };
  }

  if (field === "material") {
    return {
      summary: `Material: ${formatScalarValue(rawQuery)} -> ${formatScalarValue(rawCandidate)}`,
      technical,
    };
  }

  if (field === "finish") {
    return {
      summary: `Acabado: ${formatScalarValue(rawQuery)} -> ${formatScalarValue(rawCandidate)}`,
      technical,
    };
  }

  if (field === "components") {
    return { summary: "Componentes: configuración distinta", technical };
  }

  return {
    summary: `${field}: ${formatScalarValue(rawQuery)} -> ${formatScalarValue(rawCandidate)}`,
    technical,
  };
}

/**
 * Formats score_components from a SimilarityMatch into labeled Spanish breakdown items
 * without referring to similarity scores as probabilities.
 * @param {Record<string, number> | null | undefined} scoreComponents
 * @returns {Array<{ key: string, label: string, value: number, weight: number | null, text: string }>}
 */
export function formatScoreBreakdown(scoreComponents) {
  if (!scoreComponents || typeof scoreComponents !== "object") return [];
  const entries = [];
  for (const [key, rawValue] of Object.entries(scoreComponents)) {
    if (key.endsWith("_weight")) continue;
    const value = Number(rawValue);
    if (!Number.isFinite(value)) continue;
    const label = SCORE_COMPONENT_LABELS[key] ?? key;
    const rawWeight = scoreComponents[`${key}_weight`];
    const weight = Number.isFinite(Number(rawWeight)) ? Number(rawWeight) : null;
    const weightText = weight !== null ? ` (peso ${formatNumber(weight * 100)} %)` : "";
    entries.push({
      key,
      label,
      value,
      weight,
      text: `${label}: ${value.toFixed(3)}${weightText}`,
    });
  }
  return entries;
}

function extractUniformThickness(descriptor) {
  if (!descriptor || typeof descriptor !== "object") return null;
  if (Array.isArray(descriptor.thicknesses_mm) && descriptor.thicknesses_mm.length) {
    const nums = descriptor.thicknesses_mm.map(Number).filter(Number.isFinite);
    if (nums.length) return formatThicknessList(nums);
  }
  if (Array.isArray(descriptor.components) && descriptor.components.length) {
    const unique = [...new Set(descriptor.components.map((c) => Number(c?.thickness_mm)).filter(Number.isFinite))];
    if (unique.length === 1) return `${formatNumber(unique[0])} mm`;
  }
  return null;
}

function sameDimensions(left, right) {
  if (!left?.dimensions || !right?.dimensions) return false;
  const fields = ["width_mm", "depth_mm", "height_mm"];
  const hasKnown = fields.some((field) => Number.isFinite(Number(left.dimensions[field])) && Number.isFinite(Number(right.dimensions[field])));
  return hasKnown && fields.every((field) => left.dimensions[field] === right.dimensions[field]);
}

/**
 * Derives Spanish human-readable coincidence bullets from a SimilarityMatch
 * and optional query/candidate descriptors.
 * @param {object} match
 * @param {{ queryDescriptor?: object | null, candidateDescriptor?: object | null }} [options]
 * @returns {string[]}
 */
export function collectCoincidences(match, options = {}) {
  const { queryDescriptor = null, candidateDescriptor = null } = options;
  const diffs = Array.isArray(match?.differences) ? match.differences : [];
  const diffFields = new Set(diffs.map((d) => String(d?.field ?? "")));
  const components = match?.score_components ?? {};
  const coincidences = [];
  const add = (text) => {
    if (text && !coincidences.includes(text)) coincidences.push(text);
  };

  const hasDimDiff = [...diffFields].some((field) => field.startsWith("dimensions."));
  if (!hasDimDiff && (Number(components.dimensions) >= 0.999 || sameDimensions(queryDescriptor, candidateDescriptor) || (candidateDescriptor?.dimensions && !hasDimDiff && queryDescriptor === null && Number(components.dimensions) >= 0.999))) {
    add("Mismas dimensiones generales");
  }

  const thicknessText = extractUniformThickness(candidateDescriptor) ?? extractUniformThickness(queryDescriptor);
  const sameThicknessByDesc = queryDescriptor && candidateDescriptor && extractUniformThickness(queryDescriptor) !== null && extractUniformThickness(queryDescriptor) === extractUniformThickness(candidateDescriptor);
  if (!diffFields.has("thicknesses_mm") && (Number(components.thickness) >= 0.999 || sameThicknessByDesc || (candidateDescriptor && thicknessText && !diffFields.has("components")))) {
    add(thicknessText ? `Mismo espesor (${thicknessText})` : "Mismo espesor");
  }

  const structureVal = candidateDescriptor?.structure ?? queryDescriptor?.structure;
  const bothKnownStructure = queryDescriptor && candidateDescriptor
    ? !isUnknownValue(queryDescriptor.structure) && queryDescriptor.structure === candidateDescriptor.structure
    : !isUnknownValue(structureVal) && !diffFields.has("structure") && Boolean(candidateDescriptor);
  if (bothKnownStructure) {
    add(`Misma estructura (${formatStructureValue(structureVal)})`);
  }

  const hasRoleDiff = [...diffFields].some((field) => field.startsWith("roles."));
  if (!hasRoleDiff && Number(components.roles) >= 0.999) {
    add("Misma distribución de piezas");
  }

  if (!diffFields.has("material")) {
    const material = candidateDescriptor?.material ?? queryDescriptor?.material;
    if (!isUnknownValue(material) && (candidateDescriptor || (queryDescriptor && material))) {
      add(`Mismo material (${String(material).trim()})`);
    }
  }

  if (!diffFields.has("finish")) {
    const finish = candidateDescriptor?.finish ?? queryDescriptor?.finish;
    if (!isUnknownValue(finish) && (candidateDescriptor || (queryDescriptor && finish))) {
      add(`Mismo acabado (${String(finish).trim()})`);
    }
  }

  return coincidences;
}

/**
 * Transforms a SimilarityMatch (and optional query/candidate descriptors) into
 * structured Spanish human-readable comparison bullets and score breakdown.
 * @param {object} match
 * @param {{ queryDescriptor?: object | null, candidateDescriptor?: object | null }} [options]
 * @returns {{
 *   methodLabel: string,
 *   scoreText: string | null,
 *   coincidences: string[],
 *   differences: string[],
 *   scoreBreakdown: Array<{ key: string, label: string, value: number, weight: number | null, text: string }>,
 *   technical: string[],
 * }}
 */
export function explainSimilarityMatch(match, options = {}) {
  const methodLabel = match?.method === "semantic" ? "Semántico" : "Geométrico offline";
  const scoreText = Number.isFinite(match?.score) ? Number(match.score).toFixed(3) : null;
  const rawDifferences = Array.isArray(match?.differences) ? match.differences : [];
  const formatted = rawDifferences.map(formatDifference);
  return {
    methodLabel,
    scoreText,
    coincidences: collectCoincidences(match, options),
    differences: formatted.map((entry) => entry.summary),
    scoreBreakdown: formatScoreBreakdown(match?.score_components),
    technical: formatted.map((entry) => entry.technical),
  };
}
