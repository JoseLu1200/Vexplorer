const TABLE_MEASURE_LABELS = Object.freeze({
  overall_width: "ancho total",
  overall_height: "alto total",
  overall_depth: "fondo total",
  tabletop_thickness: "grosor de la tapa",
  support_width: "ancho del soporte",
  support_depth: "fondo del soporte",
  support_thickness: "grosor del soporte",
});

const TABLE_DIAGNOSTIC_LABELS = Object.freeze({
  "Catalog alternatives are explicit hypotheses and are never selected from drawing appearance.": "Las alternativas de catálogo son hipótesis explícitas; no se eligen por la apariencia del plano.",
  "Observed geometric sections remain measurements; their component assignment is proposed.": "Las secciones geométricas observadas siguen siendo medidas; asignarlas a un componente es una propuesta.",
  "No joinery, material, strength, or manufacturing readiness is inferred.": "No se infieren uniones, material, resistencia ni aptitud para fabricar.",
  "Supports and tabletop use the versioned flush placement rule.": "Los soportes y la tapa usan la regla de colocación enrasada versionada.",
  "Proposed components are rectangular solids without hidden joinery.": "Los componentes propuestos son sólidos rectangulares; no se presuponen uniones ocultas.",
  "Observed section gaps are assigned to component fields by hypothesis.": "Asignar los huecos de sección observados a componentes es una hipótesis.",
});

export function activateWorkspacePanel(buttons, panels, target, { compact = false, reducedMotion = false } = {}) {
  const name = target?.dataset?.panel;
  if (!name) return null;
  let selected = null;
  panels.forEach((panel) => {
    const active = panel.dataset.panelContent === name;
    panel.classList.toggle("is-active", active);
    panel.setAttribute("aria-hidden", String(!active));
    if (active) {
      panel.id ||= `tool-panel-${name}`;
      selected = panel;
    }
  });
  buttons.forEach((button) => {
    const active = button === target;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
    const panel = panels.find((item) => item.dataset.panelContent === button.dataset.panel);
    if (panel) {
      panel.id ||= `tool-panel-${button.dataset.panel}`;
      button.setAttribute("aria-controls", panel.id);
    }
  });
  if (compact && selected) {
    selected.tabIndex = -1;
    selected.focus?.({ preventScroll: true });
    selected.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  }
  return selected;
}

export function tableResourcesReady(workspace, snapshot) {
  return Boolean(
    workspace?.isTable
    && workspace.evaluated?.state === "completed"
    && snapshot?.result?.state === "completed"
    && Number.isInteger(snapshot?.result_revision),
  );
}

export function publicFeatureAvailability(config = {}) {
  const history = config.capabilities?.history?.available !== false;
  const library = config.capabilities?.library?.available !== false;
  const costs = config.capabilities?.costs?.available ?? history;
  const semanticCapability = config.semantic ?? config.capabilities?.semantic ?? {};
  const semantic = Boolean(semanticCapability.available || semanticCapability.cached_search_available);
  const publicCad = config.environment === "production" && config.authenticated === false && !history;
  const semanticExplorer = config.capabilities?.semantic_explorer?.available === true;
  const recentCapability = config.capabilities?.recent ?? {};
  return {
    history,
    library,
    semantic,
    costs,
    publicCad,
    semanticExplorer,
    recent: recentCapability.available === true,
    sessionLabel: publicCad ? "Acceso público · CAD disponible" : null,
  };
}
export function tableDiagnosticLabel(value) {
  const raw = String(value ?? "");
  const missing = raw.match(/^profile_measure_unknown:([a-z_]+)$/);
  if (missing) return `Falta la medida requerida: ${TABLE_MEASURE_LABELS[missing[1]] ?? missing[1]}.`;
  const topology = raw.match(/^The (side_supports_v1|corner_supports_v1) topology is a design hypothesis\.$/);
  if (topology) return `La topología de ${topology[1] === "side_supports_v1" ? "dos soportes laterales" : "cuatro patas de esquina"} es una hipótesis de diseño.`;
  return TABLE_DIAGNOSTIC_LABELS[raw] ?? raw;
}

export function inputKindLabel(value) {
  return ({
    general_furniture: "Entrada: mueble general",
    mounted_orthographic_views: "Entrada: mesa · vistas montadas",
    separated_part_views: "Entrada: piezas separadas",
    mounted_views_legacy: "Entrada: vistas montadas legacy",
  })[value] ?? "Entrada pendiente";
}

export function restoredSourceLabel(drawing = {}) {
  const unit = drawing.coordinate_unit ?? drawing.source_unit;
  return unit && unit !== "unknown" ? `Plano restaurado · unidad ${unit}` : "Plano restaurado · unidad sin resolver";
}

export function formControlName(...parts) {
  return parts.map((part) => String(part ?? "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")).filter(Boolean).join("-");
}

const LIBRARY_FIELD_LABELS = Object.freeze({
  "dimensions.width_mm": "Ancho",
  "dimensions.depth_mm": "Fondo",
  "dimensions.height_mm": "Alto",
});
const LIBRARY_NUMBER = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

function libraryValue(value, metric = false) {
  if (value === null || value === undefined || value === "") return "desconocido";
  const number = Number(value);
  if (metric && Number.isFinite(number)) return LIBRARY_NUMBER.format(number);
  return String(value);
}

export function presentLibraryDifferences(differences = []) {
  const summary = [];
  const technical = [];
  differences.forEach((difference) => {
    if (typeof difference === "string") {
      technical.push(difference);
      return;
    }
    const field = String(difference?.field ?? "campo");
    const label = LIBRARY_FIELD_LABELS[field];
    if (label) summary.push(`${label}: ${libraryValue(difference.query_value, true)} ↔ ${libraryValue(difference.candidate_value, true)} mm`);
    else if (field === "components") summary.push("Cambios en componentes");
    else if (!/^(part_features\[\d+\]|components\.)/.test(field)) summary.push(`Cambio en ${field}`);
    technical.push(`${field}: ${libraryValue(difference?.query_value)} ↔ ${libraryValue(difference?.candidate_value)}`);
  });
  if (technical.length && !summary.length) summary.push("Datos técnicos de comparación disponibles");
  return { summary, technical };
}

export function librarySavePayload({ resultRevision, label, semantic = false }) {
  return {
    result_revision: resultRevision,
    label,
    embedding_mode: semantic ? "embeddinggemma2" : "offline",
  };
}

export function sceneContextLabel(snapshot, scene = {}) {
  if (snapshot?.result?.state !== "completed") return "3D provisional · colocación hipotética · revisión pendiente";
  return `3D revisado · colocación ${(scene.assumptions ?? []).length ? "esquemática" : "según revisión"}`;
}
