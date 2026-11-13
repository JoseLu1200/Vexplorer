import { createApiClient, ApiError } from "./api/client.js";
import { normaliseDrawing, selectionForComponent, svgPath } from "./core/drawing.js";
import { createEventLedger, eventLabel } from "./core/events.js";
import { formatMeasurement, sourceLabel } from "./core/format.js";
import { availableModes, componentsForSnapshot, presentEstimate } from "./core/presentation.js";
import { buildScenarioReviewPayload } from "./core/review.js";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const api = createApiClient();
const state = { runId: null, snapshot: null, drawing: null, ledger: null, eventLedger: null, eventSource: null, selected: null };

function text(node, value) { if (node) node.textContent = String(value ?? ""); }
function unlock(id) { $(`#${id}`)?.classList.remove("is-locked"); }
function setMessage(value, error = false) { const node = $("#global-message"); text(node, value); node.classList.toggle("is-error", error); }

function configureModes(config = {}) {
  availableModes(config.capabilities ?? config).forEach((mode) => {
    const input = $(`input[name="mode"][value="${mode.id}"]`);
    if (input) input.disabled = !mode.enabled;
  });
  if (config.live_available || config.capabilities?.live_available) text($("#live-note"), "Proveedor real configurado");
  if (config.replay_available || config.capabilities?.replay_available) text($("#replay-note"), "Grabación real disponible");
}

function extractComponents() {
  return componentsForSnapshot(state.snapshot, state.ledger);
}

function renderDrawing() {
  if (!state.drawing) return;
  const model = normaliseDrawing(state.drawing);
  text($("#unit-label"), model.unitLabel);
  text($("#drawing-id"), model.drawingId ?? "Dibujo procesado");
  $("#drawing-empty").hidden = model.paths.length > 0;
  const svg = $("#drawing-viewer");
  svg.replaceChildren();
  const allPoints = model.paths.flatMap((path) => path.points);
  if (allPoints.length) {
    const xs = allPoints.map((point) => point[0]);
    const ys = allPoints.map((point) => -point[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const pad = Math.max(12, Math.max(maxX - minX, maxY - minY) * .08);
    svg.setAttribute("viewBox", `${minX-pad} ${minY-pad} ${Math.max(1,maxX-minX)+2*pad} ${Math.max(1,maxY-minY)+2*pad}`);
  }
  model.paths.forEach((path) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
    node.setAttribute("d", svgPath(path.points, path.closed));
    node.setAttribute("class", "drawing-path");
    node.dataset.contourId = path.id;
    node.setAttribute("tabindex", "0");
    node.setAttribute("role", "button");
    node.setAttribute("aria-label", `Contorno ${path.id}`);
    const select = () => selectContour(path.id);
    node.addEventListener("click", select);
    node.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") select(); });
    svg.append(node);
  });
  const tabs = $("#view-tabs");
  tabs.replaceChildren();
  (model.views ?? []).forEach((view, index) => {
    const button = document.createElement("button");
    button.type = "button"; button.className = "view-tab"; button.role = "tab";
    button.setAttribute("aria-selected", index === 0 ? "true" : "false");
    button.textContent = ({ FRONT: "Frente", TOP: "Planta", SIDE: "Lateral", UNKNOWN: "Sin orientar" })[view.label] ?? view.label;
    button.addEventListener("click", () => filterView(view.id, button));
    tabs.append(button);
  });
  renderEvidence(null);
  unlock("drawing-stage");
}

function filterView(viewId, button) {
  $$(".view-tab").forEach((tab) => tab.setAttribute("aria-selected", String(tab === button)));
  const allowed = new Set((state.drawing?.contours ?? []).filter((c) => (c.view_id ?? c.view) === viewId).map((c) => c.id));
  $$(".drawing-path").forEach((path) => path.classList.toggle("is-dimmed", !allowed.has(path.dataset.contourId)));
}

function selectContour(contourId) {
  const { components } = extractComponents();
  const component = components.find((item) => (item.source_contour_ids ?? item.contour_ids ?? []).includes(contourId));
  if (component) return selectComponent(component);
  state.selected = { contourIds: new Set([contourId]), evidenceIds: new Set(), entityIds: new Set() };
  applySelection();
  renderEvidence(null, contourId);
}

function selectComponent(component) {
  state.selected = selectionForComponent(component, state.drawing);
  applySelection();
  renderEvidence(component);
}

function applySelection() {
  $$(".drawing-path").forEach((path) => {
    const selected = state.selected?.contourIds?.has(path.dataset.contourId);
    path.classList.toggle("is-selected", Boolean(selected));
    path.classList.toggle("is-dimmed", Boolean(state.selected) && !selected);
  });
  $$("#parts-body tr[data-component-id]").forEach((row) => row.classList.toggle("is-selected", row.dataset.componentId === state.selected?.componentId));
}

function renderEvidence(component, contourId) {
  text($("#evidence-title"), component?.name ?? (contourId ? "Contorno del plano" : "Sin selección"));
  const root = $("#evidence-detail"); root.replaceChildren();
  const ids = component?.evidence_ids ?? [];
  const evidences = (state.drawing?.evidence ?? state.ledger?.evidence ?? []).filter((item) => ids.includes(item.id));
  let records = evidences.length ? evidences : [{ id: contourId ?? "sin evidencia", description: component ? "Propuesta pendiente de evidencia enlazada." : "Contorno geométrico seleccionado." }];
  if (!component && !contourId && state.drawing?.dimensions?.length) records = state.drawing.dimensions.map((dimension) => ({ id: dimension.id, description: `${sourceLabel(dimension.origin)} · ${formatMeasurement(dimension.value_mm, "mm")}` }));
  records.forEach((record) => {
    const card = document.createElement("div"); card.className = "detail-item";
    const strong = document.createElement("b"); strong.textContent = record.id;
    const description = document.createElement("span"); description.textContent = record.description ?? record.kind ?? "Evidencia geométrica";
    card.append(strong, description); root.append(card);
  });
}

function renderPartsAndReview() {
  const { scenarios, components } = extractComponents();
  const body = $("#parts-body"); body.replaceChildren();
  if (!components.length) {
    const row = document.createElement("tr"); row.className = "empty-row";
    const cell = document.createElement("td"); cell.colSpan = 6; cell.textContent = "No hay piezas confirmadas. La geometría permanece disponible y el sistema conserva la abstención.";
    row.append(cell); body.append(row);
  }
  components.forEach((component) => {
    const row = document.createElement("tr"); row.dataset.componentId = component.id; row.tabIndex = 0;
    const dimensions = component.dimensions_mm ?? component.dimensions ?? { length: component.length_mm, width: component.width_mm, thickness: component.thickness_mm };
    const origin = component.human_confirmation ? "human_confirmed" : (component.origin ?? component.information_class ?? component.status ?? "hypothesis");
    const values = [component.name ?? component.label ?? "Componente propuesto", sourceLabel(origin), component.quantity, dimensions.length, dimensions.width, dimensions.thickness];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      if (index >= 2) cell.textContent = index === 2 ? (value ?? "Desconocida") : formatMeasurement(value, "mm"); else cell.textContent = value;
      if (value === null || value === undefined) cell.className = "unknown";
      if (index === 1) cell.dataset.origin = origin;
      row.append(cell);
    });
    row.addEventListener("click", () => selectComponent(component));
    row.addEventListener("keydown", (event) => { if (event.key === "Enter") selectComponent(component); });
    body.append(row);
  });
  text($("#scenario-status"), scenarios.length ? "Hipótesis pendiente" : (state.snapshot?.result?.state === "completed" ? "Resultado revisado" : "Sin propuesta respaldada"));
  const options = $("#scenario-options"); options.replaceChildren();
  const legend = document.createElement("legend"); legend.textContent = "Escenario respaldado"; options.append(legend);
  scenarios.forEach((scenario, index) => {
    const label = document.createElement("label"); label.className = "scenario-option";
    const input = document.createElement("input"); input.type = "radio"; input.name = "scenario"; input.value = scenario.id; input.checked = index === 0;
    const content = document.createElement("span");
    const title = document.createElement("b"); title.textContent = scenario.title ?? scenario.name ?? scenario.label ?? `Escenario ${index + 1}`;
    const detail = document.createElement("small"); detail.textContent = (scenario.assumptions ?? []).join(" · ") || scenario.description || scenario.rationale || "Interpretación de montaje pendiente de confirmación";
    content.append(title, detail); label.append(input, content); options.append(label);
  });
  if (!scenarios.length) { const empty = document.createElement("p"); empty.className = "empty-copy"; empty.textContent = "No hay una alternativa de montaje disponible para confirmar."; options.append(empty); }
  $("#review-submit").disabled = !scenarios.length;
  text($("#revision-label"), Number.isInteger(state.snapshot?.result_revision) ? `Revisión ${state.snapshot.result_revision}` : "Revisión pendiente");
  unlock("parts-stage"); unlock("review-stage");
}

function renderTrace() {
  const root = $("#trace-list"); root.replaceChildren();
  const events = state.eventLedger?.events() ?? [];
  if (!events.length) { const item = document.createElement("li"); item.className = "empty-copy"; item.textContent = "No hay eventos todavía."; root.append(item); return; }
  events.forEach((event) => {
    const item = document.createElement("li");
    const title = document.createElement("b"); title.textContent = eventLabel(event);
    const summary = document.createElement("span"); summary.textContent = event.data?.summary ?? event.data?.reason_code ?? `Secuencia ${event.sequence}`;
    const time = document.createElement("time"); time.dateTime = event.timestamp ?? ""; time.textContent = event.timestamp ? new Date(event.timestamp).toLocaleTimeString("es-ES") : `Evento ${event.sequence}`;
    item.append(title, summary, time); root.append(item);
  });
  $("#trace-export").disabled = false;
}

function connectEvents(runId) {
  state.eventSource?.close(); state.eventLedger = createEventLedger(runId);
  const source = new EventSource(`/api/v1/runs/${encodeURIComponent(runId)}/events`); state.eventSource = source;
  ["run_state_changed","tool_started","tool_completed","validation_issue","result_committed","run_finished","provenance"].forEach((type) => source.addEventListener(type, (message) => {
    try { const envelope = JSON.parse(message.data); if (state.eventLedger.append(envelope)) renderTrace(); if (type === "run_finished") { source.close(); refreshRun(); } } catch { setMessage("La traza recibió un evento no válido.", true); }
  }));
  source.onerror = () => { if (!state.snapshot || !["completed","needs_review","failed","cancelled","timed_out"].includes(state.snapshot.state)) text($("#service-status"), "Reconectando la traza"); };
}

async function refreshRun() {
  if (!state.runId) return;
  state.snapshot = await api.getRun(state.runId);
  try { state.drawing = await api.getDrawing(state.runId); renderDrawing(); } catch (error) { if (!(error instanceof ApiError) || error.status !== 409) throw error; }
  try { state.ledger = await api.getLedger(state.runId); } catch (error) { if (!(error instanceof ApiError) || error.status !== 409) throw error; }
  renderPartsAndReview();
  if (["completed","needs_review"].includes(state.snapshot.state)) { await loadComparables(); unlock("estimate-stage"); }
}

async function loadComparables() {
  try {
    const response = await api.getComparables(state.runId); const items = response.comparables ?? response.items ?? response ?? [];
    const root = $("#comparables-list"); root.replaceChildren();
    if (!items.length) { const empty = document.createElement("p"); empty.className = "empty-copy"; empty.textContent = "No hay comparables admitidos para esta revisión."; root.append(empty); return; }
    items.forEach((item) => {
      const card = document.createElement("div"); card.className = "comparable";
      const top = document.createElement("div"); top.className = "comparable__top";
      const name = document.createElement("b"); name.textContent = item.name ?? item.project_id ?? "Proyecto histórico";
      const score = document.createElement("span"); score.textContent = item.similarity_label ?? "Comparable explicado";
      const diff = document.createElement("small"); diff.textContent = (item.differences ?? []).join(" · ") || item.explanation || "Sin diferencias documentadas";
      top.append(name, score); card.append(top, diff); root.append(card);
    });
    $("#estimate-button").disabled = false;
  } catch (error) { text($("#comparables-list"), error.message); }
}

function renderEstimate(raw) {
  const estimate = presentEstimate(raw); text($("#estimate-revision"), estimate.revisionLabel); text($("#estimate-total"), estimate.totalLabel);
  const root = $("#estimate-lines"); root.replaceChildren();
  estimate.items.forEach((item) => { const row = document.createElement("div"); row.className = "estimate-line"; const left = document.createElement("span"); const name = document.createElement("b"); name.textContent = item.label ?? item.name ?? "Concepto"; const detail = document.createElement("small"); detail.textContent = `${item.quantityLabel} × ${item.rateLabel}`; left.append(name, detail); const amount = document.createElement("b"); amount.textContent = item.amountLabel; row.append(left, amount); root.append(row); });
  $$("[data-export]").forEach((button) => { button.disabled = false; }); unlock("estimate-stage");
}

async function runUpload(event) {
  event.preventDefault(); const file = $("#drawing-file").files[0]; if (!file) return setMessage("Selecciona un archivo DXF.", true);
  if (file.size > 20 * 1024 * 1024) return setMessage("El archivo supera 20 MiB. Selecciona un DXF más pequeño.", true);
  const mode = new FormData(event.currentTarget).get("mode");
  try {
    setMessage("Guardando el plano…"); text($("#upload-status"), "Cargando");
    const documentRecord = await api.upload(file); const run = await api.createRun(documentRecord.document_id ?? documentRecord.id, mode);
    state.runId = run.run_id ?? run.id; state.snapshot = run; text($("#upload-status"), "En proceso"); setMessage("Plano aceptado. Extrayendo geometría y evidencia.");
    connectEvents(state.runId); await refreshRun();
  } catch (error) { setMessage(error.message, true); text($("#upload-status"), "Error"); }
}

async function submitReview(event) {
  event.preventDefault(); const scenario = $("input[name='scenario']:checked"); if (!scenario) return;
  try {
    const payload = buildScenarioReviewPayload(state.snapshot, {
      scenario_id: scenario.value,
      reviewer_name: $("#reviewer-name").value,
      confirmed_thickness_mm: $("#review-thickness").value,
      material: $("#review-material").value,
      finish: $("#review-finish").value,
      notes: $("#review-reason").value,
    });
    const result = await api.review(state.runId, payload); state.snapshot = { ...state.snapshot, ...result };
    text($("#review-message"), "Decisión registrada en una nueva revisión."); await refreshRun();
  } catch (error) {
    text($("#review-message"), error.code === "stale_result_revision" ? "La revisión cambió. Se han recargado los datos antes de sobrescribir." : error.message);
    if (error.code === "stale_result_revision") await refreshRun();
  }
}

function downloadBlob(blob, filename) { const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename.replace(/[^a-z0-9._-]/gi,"_"); document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url); }

async function exportResult(format) {
  try { const response = await fetch(api.exportUrl(state.runId, format)); if (!response.ok) throw new Error("La exportación no está disponible."); downloadBlob(await response.blob(), `vexplorer_${state.runId}.${format}`); } catch (error) { setMessage(error.message, true); }
}

function toggleTrace(open) { const drawer = $("#trace-drawer"); drawer.classList.toggle("is-open", open); drawer.setAttribute("aria-hidden", String(!open)); $("#trace-toggle").setAttribute("aria-expanded", String(open)); $("#scrim").hidden = !open; if (open) $("#trace-close").focus(); }

async function boot() {
  $("#upload-form").addEventListener("submit", runUpload); $("#review-form").addEventListener("submit", submitReview);
  $("#drawing-file").addEventListener("change", (event) => text($("#file-name"), event.target.files[0]?.name ?? "Ningún archivo seleccionado"));
  $("#trace-toggle").addEventListener("click", () => toggleTrace(true)); $("#trace-close").addEventListener("click", () => toggleTrace(false)); $("#scrim").addEventListener("click", () => toggleTrace(false));
  $("#estimate-button").addEventListener("click", async () => { try { renderEstimate(await api.estimate(state.runId, { result_revision: state.snapshot?.result_revision })); } catch (error) { setMessage(error.message, true); } });
  $$("[data-export]").forEach((button) => button.addEventListener("click", () => exportResult(button.dataset.export)));
  $("#trace-export").addEventListener("click", () => downloadBlob(new Blob([JSON.stringify(state.eventLedger?.events() ?? [], null, 2)], { type: "application/json" }), `vexplorer_${state.runId}_traza.json`));
  try { configureModes(await api.getConfig()); $(".signal").classList.add("is-online"); text($("#service-status"), "Servicio disponible"); } catch { configureModes({}); text($("#service-status"), "Servicio sin configuración"); }
}

boot();
