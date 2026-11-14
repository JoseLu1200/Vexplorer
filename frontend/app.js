import { createApiClient, ApiError } from "./api/client.js";
import { normaliseDrawing, selectionForComponent, svgCircularPath, svgPath } from "./core/drawing.js";
import { createEventLedger, eventLabel, eventTimestamp, parseEventStream } from "./core/events.js";
import { formatMeasurement, sourceLabel } from "./core/format.js";
import { availableModes, componentsForSnapshot, executionModeLabel, fieldOrigin, normaliseRunPayload, presentEstimate, presentReplaySource, snapshotStatusPresentation } from "./core/presentation.js";
import { normalisePartsWorkspace, partSelectionViewIds, preferredCandidateId, presentDescriptorV2, presentReviewedUse, resolveAssemblyOperand, translateAssumption } from "./core/parts.js";
import { buildAssemblyReviewPayload, buildScenarioReviewPayload, changedReviewDecisionValues } from "./core/review.js";
import { clearRunSession, persistJob, persistRunId, restoredRunRecovery, restoreJob, restoreRunId } from "./core/session.js";
import { boundsForPoints, fitViewport, panViewport, svgUnitPerPixel, zoomViewport } from "./core/viewport.js";
import { fitImageViewport, imageViewportStyle, panImageViewport, zoomImageViewport } from "./core/image-viewport.js";
import { createRequestFence } from "./core/request-fence.js";
import { jobStatusLabel, pollJob } from "./core/jobs.js";
import { nextFocusTarget } from "./core/focus.js";
import { artifactRequestIdentity, buildTableCostScope, buildTableReviewPayload, componentMaterialOverrides, normaliseTableCostCatalog, normaliseTableDrawingManifest, normaliseTableWorkspace, presentTableComponentExplanation, presentTableCosts, tableExportFormat, tableMaterialScopeSelection, tableRunOptions } from "./core/table.js";
import { buildGeneralReviewPayload, buildGeneralReviewedComponent, buildManualGeneralProposal, completeGeneralReviewSnapshot, generalMachineStatusPresentation, generalRunOptions, normaliseGeneralWorkspace, presentGeneralConstructionDimension, presentGeneralConstructionQuantity, presentGeneralDerived, serialiseGeneralBom } from "./core/general.js";
import { presentHistoricalComparables, presentHistoricalEstimate, presentHistoricalRecord, presentHistoryImport, presentProvisionalScenarios } from "./core/history.js";
import { canStartDocumentAnalysis, presentDocumentIngestion } from "./core/ingestion.js";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const api = createApiClient();
const state = { documentId: null, documentIngestion: null, runId: null, jobId: null, jobAbort: null, config: {}, session: null, snapshot: null, drawing: null, drawingModel: null, partsWorkspace: null, tableWorkspace: null, generalWorkspace: null, generalDerived: null, tableDrawings: null, tableCostCatalog: null, ledger: null, eventLedger: null, selected: null, viewport: null, fittedViewport: null, activeView: "all", activeArtifact: "source", derivedImageViewport: fitImageViewport(), explanations: null, scene: null, libraryItems: new Map() };
let sceneViewer;
const runFence=createRequestFence(), contextFence=createRequestFence(), sceneFence=createRequestFence(), artifactFence=createRequestFence(), uploadFence=createRequestFence(), actionFence=createRequestFence();
const actionIdentity=()=>`${state.runId}:${state.snapshot?.result_revision}`;

function text(node, value) { if (node) node.textContent = String(value ?? ""); }
function unlock(id) { $(`#${id}`)?.classList.remove("is-locked"); }
function setMessage(value, error = false) { const node = $("#global-message"); text(node, value); node.classList.toggle("is-error", error); }

function emptyParagraph(value) { const node = document.createElement("p"); node.className = "empty-copy"; node.textContent = value; return node; }
function toggleHidden(node, hidden) { node?.toggleAttribute("hidden", Boolean(hidden)); }

function resetEstimateUi() {
  $("#estimate-lines").replaceChildren(emptyParagraph("La revisión actual todavía no tiene estimación. Calcula una nueva para evitar reutilizar importes anteriores."));
  text($("#estimate-revision"), state.snapshot?.result_revision ? `Revisión ${state.snapshot.result_revision} · Sin estimación` : "Sin revisión");
  text($("#estimate-total"), "Pendiente");
  text($("#estimate-uncertainty"), "");
  $("#estimate-missing-data")?.replaceChildren();
  $$("[data-export]").filter((button)=>!["bom_csv","bom_json"].includes(button.dataset.export)).forEach((button) => { button.disabled = true; });
}

function configureExportActions(){const table=state.tableWorkspace?.isTable===true; text($("#csv-export"),table?"Lista de corte CSV":"Ficha CSV"); if(table){const ready=state.snapshot?.result?.state==="completed"; $$('[data-export]').forEach((button)=>button.disabled=!ready);}}

function resetRunUi() {
  runFence.invalidate(); contextFence.invalidate(); sceneFence.invalidate(); uploadFence.invalidate(); actionFence.invalidate();
  state.jobAbort?.abort();
  Object.assign(state, { documentId: null, documentIngestion: null, runId: null, jobId: null, jobAbort: null, snapshot: null, drawing: null, drawingModel: null, partsWorkspace: null, tableWorkspace: null, generalWorkspace: null, generalDerived: null, tableDrawings: null, tableCostCatalog: null, ledger: null, eventLedger: null, selected: null, viewport: null, fittedViewport: null, activeView: "all", activeArtifact: "source", derivedImageViewport: fitImageViewport(), explanations: null, scene: null, libraryItems: new Map() });
  clearRunSession(localStorage, location, history);
  $("#drawing-viewer").replaceChildren(); $("#view-tabs").replaceChildren(); $("#drawing-empty").hidden = false;
  $("#original-preview").removeAttribute("src"); $("#original-view").hidden = true; $("#scene-viewer").hidden = true;
  $("#derived-drawing-image").removeAttribute("src"); $("#derived-drawing-view").hidden=true; $("#derived-drawing-sheet").replaceChildren(); $("#derived-drawing-downloads").replaceChildren(); artifactFence.invalidate();
  $("#derived-drawing-view").classList.remove("is-expanded"); $("#derived-drawing-expand").setAttribute("aria-pressed","false"); text($("#derived-drawing-expand"),"Ampliar");
  toggleHidden($("#table-cost-scope"),true); $$('[data-artifact-view]').forEach((tab)=>{if(tab.dataset.artifactView!=="source")tab.disabled=true;});
  text($("#drawing-id"), "Sin dibujo"); text($("#unit-label"), "Pendiente"); text($("#document-provenance"), "Fuente pendiente"); text($("#run-mode-label"), "Sin ejecución"); text($("#replay-source"),""); toggleHidden($("#replay-source"),true);
  text($("#evidence-title"), "Sin selección"); $("#evidence-detail").replaceChildren(emptyParagraph("Selecciona una fila o un contorno para consultar su procedencia."));
  const row = document.createElement("tr"); row.className = "empty-row"; const cell = document.createElement("td"); cell.colSpan = 7; cell.textContent = "Todavía no hay observaciones. El plano seguirá disponible aunque el análisis quede vacío."; row.append(cell); $("#parts-body").replaceChildren(row);
  text($("#parts-summary"), "Sin observaciones"); text($("#classification-summary"), "Las hipótesis aparecerán después de analizar las piezas."); text($("#scene-context"), "2D fuente · sin montaje inferido");
  toggleHidden($("#scene-premises"),true); $("#scene-premises-list").replaceChildren();
  text($("#scenario-status"), "Pendiente de análisis"); text($("#revision-label"), "Sin revisión");
  const legend = document.createElement("legend"); legend.textContent = "Escenario respaldado"; $("#scenario-options").replaceChildren(legend, emptyParagraph("Las alternativas aparecerán cuando el backend las proponga."));
  $("#review-form").reset(); if(state.session?.authenticated&&state.session.username)$("#reviewer-name").value=state.session.username; $("#review-submit").disabled = true; text($("#review-message"), "");
  $("#comparables-list").replaceChildren(emptyParagraph("Sin comparables disponibles."));
  toggleHidden($("#historical-scenarios"),true);$("#historical-scenarios-list")?.replaceChildren(emptyParagraph("La auto-revisión aún no tiene un snapshot consultable."));
  if($("#historical-confirmed-details"))$("#historical-confirmed-details").open=true;if($("#historical-confirmed-details > summary"))$("#historical-confirmed-details > summary").hidden=true;
  $$('[data-export="bom_csv"],[data-export="bom_json"]').forEach((button)=>button.disabled=true);resetEstimateUi(); $("#estimate-button").disabled = true;
  $("#trace-export").disabled = true;
  $("#trace-list").replaceChildren(emptyParagraph("No hay eventos todavía."));
  text($("#trace-gap-status"), ""); text($("#job-status"), "");
}

function configureModes(config = {}) {
  state.config = config;
  availableModes(config.capabilities ?? config).forEach((mode) => {
    const input = $(`[name="mode"] [value="${mode.id}"]`) ?? $(`[name="mode"][value="${mode.id}"]`);
    if (input) input.disabled = !mode.enabled;
  });
  if (config.live_available || config.capabilities?.live_available) text($("#live-note"), "Proveedor real configurado");
  if (config.recorded_replay_available || config.replay_available || config.capabilities?.replay_available) text($("#replay-note"), "Grabación real disponible");
  const semantic = config.semantic ?? config.capabilities?.semantic ?? {};
  const semanticOption = $("#similarity-mode option[value='semantic']");
  const semanticAvailable = Boolean(semantic.available ?? config.semantic_available);
  if (semanticOption) semanticOption.disabled = !semanticAvailable;
  const historySemanticOption = $('#history-retrieval-method option[value="semantic"]');
  if(historySemanticOption)historySemanticOption.disabled=!semanticAvailable;
  text($("#semantic-note"), semanticAvailable ? `Semántico real · ${semantic.model ?? config.semantic_model ?? "modelo configurado"}` : "Semántico no disponible: usa el descriptor geométrico offline.");
  const historyNote=$("#history-retrieval-note");if(historyNote)text(historyNote,semanticAvailable?`Registros empresariales y fuentes públicas por defecto; sin fixtures · embeddings disponibles: ${semantic.model??"modelo configurado"} · ${semantic.dimensions??"dimensiones no publicadas"}.`: `Registros empresariales y fuentes públicas por defecto; sin fixtures · embeddings no disponibles${semantic.unavailable_reason?`: ${semantic.unavailable_reason}`:""}.`);
  const generalCapability=config.general_furniture??config.capabilities?.general_furniture??{},liveAvailable=Boolean(config.live_available??config.capabilities?.live_available),autonomousReview=generalCapability.autonomous_review,automaticAvailable=typeof autonomousReview==="object"?autonomousReview.available!==false:autonomousReview!==false;
  if(liveAvailable&&automaticAvailable&&!$("#upload-form").dataset.userConfigured){$("#upload-form").elements.input_kind.value="general_furniture";$("#upload-form").elements.mode.value="live";updateTableRunControls();text($("#global-message"),"Modo recomendado: mueble general con revisión visual automática de hipótesis.");}
}

function createHistoryEstimateControls(){
  if($("#history-estimate-controls"))return;const root=document.createElement("fieldset"),legend=document.createElement("legend"),methodLabel=document.createElement("label"),method=document.createElement("select"),attribute=document.createElement("option"),semantic=document.createElement("option"),syntheticLabel=document.createElement("label"),synthetic=document.createElement("input"),syntheticText=document.createElement("span"),note=document.createElement("p");root.id="history-estimate-controls";root.className="history-estimate-controls";root.hidden=true;legend.textContent="Origen y método";methodLabel.textContent="Método";method.id="history-retrieval-method";attribute.value="attribute";attribute.textContent="Atributos verificables";semantic.value="semantic";semantic.textContent="Embeddings reales";method.append(attribute,semantic);methodLabel.append(method);syntheticLabel.className="check-field";synthetic.id="history-include-synthetic";synthetic.type="checkbox";syntheticText.textContent="Incluir datos sintéticos para prueba";syntheticLabel.append(synthetic,syntheticText);note.id="history-retrieval-note";note.className="field-note";note.setAttribute("role","status");note.textContent="Solo datos reales · comparación por atributos.";root.append(legend,methodLabel,syntheticLabel,note);$("#comparables-list").before(root);
  const scenarios=document.createElement("section"),heading=document.createElement("h3"),description=document.createElement("p"),button=document.createElement("button"),cards=document.createElement("div");scenarios.id="historical-scenarios";scenarios.className="historical-scenarios";scenarios.hidden=true;heading.textContent="Estimaciones por escenario";description.id="historical-scenarios-note";description.className="field-note";description.textContent="Condiciones automáticas sobre comparables publicados; no son cotizaciones ni hechos confirmados.";button.id="historical-scenarios-button";button.type="button";button.className="button";button.textContent="Consultar escenarios";button.disabled=true;cards.id="historical-scenarios-list";cards.className="scenario-estimate-list";cards.append(emptyParagraph("La auto-revisión aún no tiene un snapshot consultable."));scenarios.append(heading,description,button,cards);root.before(scenarios);
  const confirmed=document.createElement("details"),confirmedSummary=document.createElement("summary"),comparables=$("#comparables-list"),comparablesHeading=[...$("#estimate-stage").querySelectorAll("h3")].find((item)=>item.textContent==="Comparables");confirmed.id="historical-confirmed-details";confirmed.open=true;confirmedSummary.hidden=true;confirmedSummary.textContent="Histórico confirmado (avanzado)";confirmed.append(confirmedSummary,$(".estimate-total"),$("#table-cost-scope"),$("#estimate-lines"),root,$("#estimate-button"),comparablesHeading,comparables);scenarios.after(confirmed);
}

function historicalRetrievalOptions(){return{retrievalMethod:$("#history-retrieval-method")?.value??"attribute",includeSynthetic:Boolean($("#history-include-synthetic")?.checked)};}

function renderDocumentIngestion(record) {
  const presented=presentDocumentIngestion(record); state.documentIngestion=presented;
  text($("#document-provenance"),`${presented.format} · ${presented.summary}`); $("#document-provenance").title=[presented.summary,...presented.warnings].join(" · ");
  const controls=$("#pdf-page-controls"),select=$("#pdf-page-select"); toggleHidden(controls,presented.format!=="PDF"); select.replaceChildren();
  presented.pages.forEach((page)=>{const option=document.createElement("option");option.value=String(page.page);option.textContent=`Página ${page.page} · ${page.content_kind??"contenido sin clasificar"}${page.previewOnly?" · solo vista previa":" · vector disponible"}`;option.dataset.previewPath=page.previewUrl??"";select.append(option);});
  const showPagePreview=()=>{const path=select.selectedOptions[0]?.dataset.previewPath??presented.previewUrl;if(path)$("#original-preview").src=api.resourceUrl(path);}; select.onchange=showPagePreview;
  if(presented.format==="PDF"&&presented.pages.length)showPagePreview();
  return presented;
}

function extractComponents() {
  return componentsForSnapshot(state.snapshot, state.ledger);
}

function renderDrawing() {
  if (!state.drawing) return;
  const model = normaliseDrawing(state.drawing);
  state.drawingModel = model;
  text($("#unit-label"), model.unitLabel);
  text($("#drawing-id"), model.drawingId ?? "Dibujo procesado");
  $("#drawing-empty").hidden = model.paths.length > 0;
  const svg = $("#drawing-viewer"); svg.replaceChildren();
  const allPoints = model.pointsForViews(null).map(([x,y]) => [x,-y]);
  const rect = $("#cad-viewport").getBoundingClientRect();
  state.fittedViewport = fitViewport(boundsForPoints(allPoints), rect.width || 900, rect.height || 520, model.fitPaddingForViews(null));
  state.viewport = { ...state.fittedViewport }; applyViewport();
  model.paths.forEach((path) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
    node.setAttribute("d", path.circular?svgCircularPath(path.circular):svgPath(path.points, path.closed));
    node.setAttribute("class", "drawing-path");
    node.dataset.contourId = path.id; node.dataset.viewId = path.viewId ?? ""; node._entityIds = path.entityIds; node.classList.add("layer-entities");
    node.setAttribute("tabindex", "0");
    node.setAttribute("role", "button");
    node.setAttribute("aria-label", `Contorno ${path.id}`);
    const select = () => selectContour(path.id);
    node.addEventListener("click", select);
    node.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") select(); });
    svg.append(node);
  });
  model.dimensions.forEach((dimension) => {
    dimension.segments.forEach((segment) => { const line = document.createElementNS("http://www.w3.org/2000/svg", "path"); line.setAttribute("d", svgPath(segment)); line.setAttribute("class", "dimension-line layer-dimensions"); line.dataset.viewId = dimension.viewId ?? ""; svg.append(line); });
    if (dimension.position && dimension.label) { const label = document.createElementNS("http://www.w3.org/2000/svg", "text"); label.setAttribute("x", dimension.position[0]); label.setAttribute("y", -dimension.position[1]); label.setAttribute("class", "dimension-text layer-dimensions"); label.dataset.viewId = dimension.viewId ?? ""; label.textContent = dimension.label; svg.append(label); }
  });
  model.texts.forEach((item) => { const label = document.createElementNS("http://www.w3.org/2000/svg", "text"); label.setAttribute("x", item.position[0]); label.setAttribute("y", -item.position[1]); label.setAttribute("class", "drawing-text layer-texts"); label.dataset.viewId = item.viewId ?? ""; label.textContent = item.text; svg.append(label); });
  const tabs = $("#view-tabs");
  tabs.replaceChildren();
  const all = document.createElement("button"); all.type = "button"; all.className = "view-tab"; all.dataset.view = "all"; all.setAttribute("aria-selected", "true"); all.textContent = state.partsWorkspace?.isPartsOnly ? "Todas las piezas" : "Todas"; all.addEventListener("click", () => activateView("all", all)); tabs.append(all);
  const viewTabs = state.partsWorkspace?.isPartsOnly ? state.partsWorkspace.observations.map((observation) => ({ id: `part:${observation.id}`, label: `${observation.label} · ${observation.viewIds.length} ${observation.viewIds.length === 1 ? "vista" : "vistas"}`, observation })) : (model.views ?? []);
  viewTabs.forEach((view) => {
    const button = document.createElement("button");
    button.type = "button"; button.className = "view-tab"; button.role = "tab";
    button.setAttribute("aria-selected", "false");
    button.textContent = view.observation ? view.label : (({ FRONT: "Alzado", TOP: "Planta", SIDE: "Lateral", UNKNOWN: "Sin orientar" })[view.label] ?? view.label);
    button.addEventListener("click", () => { activateView(view.id, button); if (view.observation) selectPartObservation(view.observation); });
    tabs.append(button);
  });
  if (state.documentId) { const original = document.createElement("button"); original.type="button"; original.className="view-tab"; original.textContent="CAD original"; original.setAttribute("aria-selected","false"); original.addEventListener("click",()=>activateView("original",original)); tabs.append(original); }
  const three = document.createElement("button"); three.type="button"; three.className="view-tab"; three.textContent="3D"; three.setAttribute("aria-selected","false"); three.addEventListener("click",()=>activateView("3d",three)); tabs.append(three);
  applySvgTextScale();
  applyLayerVisibility();
  renderEvidence(null);
  unlock("drawing-stage");
}

function activateView(viewId, button) {
  showSourceArtifact();
  state.activeView = viewId;
  $$(".view-tab").forEach((tab) => tab.setAttribute("aria-selected", String(tab === button)));
  toggleHidden($("#drawing-viewer"), viewId === "original" || viewId === "3d");
  toggleHidden($("#original-view"), viewId !== "original");
  toggleHidden($("#scene-viewer"), viewId !== "3d");
  toggleHidden($("#explode-control"), viewId !== "3d");
  const partId=viewId.startsWith("part:")?viewId.slice(5):null;
  const allowed=partId?partSelectionViewIds(state.partsWorkspace,partId):null;
  $$('[data-view-id]', $("#drawing-viewer")).forEach((node) => node.classList.toggle("is-view-hidden", viewId!=="all" && (allowed ? !allowed.has(node.dataset.viewId) : node.dataset.viewId!==viewId)));
  if (viewId === "3d") loadScene();
  else { text($("#scene-context"),viewId==="original"?"CAD original · representación visual":"2D fuente · evidencia observada"); if (!["original"].includes(viewId)) fitDrawing(); }
}

function showSourceArtifact(){
  state.activeArtifact="source";
  $("#derived-drawing-view").classList.remove("is-expanded"); $("#derived-drawing-expand").setAttribute("aria-pressed","false"); text($("#derived-drawing-expand"),"Ampliar");
  $$('[data-artifact-view]').forEach((tab)=>tab.setAttribute("aria-selected",String(tab.dataset.artifactView==="source")));
  toggleHidden($("#derived-drawing-view"),true);
  const viewId=state.activeView;
  toggleHidden($("#drawing-viewer"),viewId==="original"||viewId==="3d"); toggleHidden($("#original-view"),viewId!=="original"); toggleHidden($("#scene-viewer"),viewId!=="3d");
  ["#zoom-out","#zoom-in","#fit-view","#reset-view","#toggle-entities","#toggle-texts","#toggle-dimensions"].forEach((selector)=>$(selector).disabled=false);
}

function applyDerivedImageViewport(){Object.assign($("#derived-drawing-image").style,imageViewportStyle(state.derivedImageViewport??fitImageViewport()));}
function fitDerivedDrawing(){state.derivedImageViewport=fitImageViewport();applyDerivedImageViewport();}
function toggleDerivedExpanded(){const view=$("#derived-drawing-view"),expanded=view.classList.toggle("is-expanded"),button=$("#derived-drawing-expand"); button.setAttribute("aria-pressed",String(expanded)); text(button,expanded?"Reducir":"Ampliar"); requestAnimationFrame(fitDerivedDrawing);}

function tableDrawingSheets(kind){return state.tableDrawings?.byKind?.[kind]??[];}
function selectDerivedSheet(sheet){
  if(!sheet||!state.runId)return;
  const format=sheet.formats.includes("svg")?"svg":sheet.formats[0], identity=artifactRequestIdentity({runId:state.runId,revision:sheet.revision,programHash:sheet.programHash,sheetId:sheet.id,format}),token=artifactFence.issue(identity),image=$("#derived-drawing-image");
  text($("#derived-drawing-title"),sheet.title); text($("#derived-drawing-meta"),`Revisión ${sheet.revision} · ${sheet.status==="ready"?"lista":"incompleta"} · programa ${sheet.programHash.slice(0,10)}`); text($("#derived-drawing-warning"),sheet.warnings.join(" · ")||"Plano técnico derivado; no certifica fabricación.");
  const source=sheet.formatLinks?.[format]?api.resourceUrl(sheet.formatLinks[format]):api.tableDrawingUrl(state.runId,sheet.id,format,sheet.revision,sheet.programHash); image.alt=`${sheet.title}, revisión ${sheet.revision}`; fitDerivedDrawing(); image.onload=async()=>{try{await image.decode();}catch{} if(artifactFence.isCurrent(token,identity)){fitDerivedDrawing();text($("#derived-drawing-warning"),sheet.warnings.join(" · ")||"Plano técnico derivado; no certifica fabricación.");}}; image.onerror=()=>{if(artifactFence.isCurrent(token,identity))text($("#derived-drawing-warning"),"No se pudo cargar esta lámina. Puedes descargar el DXF si está disponible.");}; image.src=source;
  const downloads=$("#derived-drawing-downloads"); downloads.replaceChildren(); sheet.formats.forEach((itemFormat)=>{const link=document.createElement("a"); link.className="button"; link.textContent=`${itemFormat.toUpperCase()}`; link.href=sheet.formatLinks?.[itemFormat]?api.resourceUrl(sheet.formatLinks[itemFormat]):api.tableDrawingUrl(state.runId,sheet.id,itemFormat,sheet.revision,sheet.programHash); link.download=""; downloads.append(link);});
}
function renderDerivedSheetKind(kind){
  const sheets=tableDrawingSheets(kind),select=$("#derived-drawing-sheet"); select.replaceChildren(); sheets.forEach((sheet)=>{const option=document.createElement("option"); option.value=sheet.id; option.textContent=`${sheet.page}. ${sheet.title}${sheet.status==="incomplete"?" · incompleto":""}`; select.append(option);}); select.disabled=sheets.length<2; select.onchange=()=>selectDerivedSheet(sheets.find((sheet)=>sheet.id===select.value)); if(sheets[0])selectDerivedSheet(sheets[0]); else {$("#derived-drawing-image").removeAttribute("src"); text($("#derived-drawing-warning"),"La revisión no contiene una lámina de este tipo.");}
}
function activateGeneralArtifactView(button,kind="general"){
  const derived=state.generalDerived,construction=derived?.construction,sheetKind=kind==="components"?"piece":"assembly",sheets=construction?.sheets.filter((item)=>item.kind===sheetKind)??[];if(!derived)return;
  const renderSheet=(sheet)=>{const svgKind=sheetKind==="piece"?"piece_sheet_svg":"construction_overview_svg",dxfKind=sheetKind==="piece"?"piece_sheet_dxf":"construction_overview_dxf",matches=(item,itemKind)=>item.kind===itemKind&&(!sheet||item.sheetId===sheet.sheetId),svg=derived.artifacts.find((item)=>matches(item,svgKind))??(sheetKind==="assembly"?derived.artifacts.find((item)=>item.kind==="drawing_svg"):null),dxf=derived.artifacts.find((item)=>matches(item,dxfKind))??(sheetKind==="assembly"?derived.artifacts.find((item)=>item.kind==="drawing_dxf"):null);if(!svg){$("#derived-drawing-image").removeAttribute("src");text($("#derived-drawing-warning"),"Esta propuesta no publicó una lámina SVG utilizable.");return;}text($("#derived-drawing-title"),sheet?.title??(sheetKind==="piece"?"Plano acotado de pieza":"Propuesta de construcción"));text($("#derived-drawing-meta"),`Propuesta ${derived.proposalRevision} · revisión ${derived.reviewRevision} · ${svg.status==="ready"?"lista":"incompleta"}`);const warnings=[...(sheet?.warnings??[]).map((item)=>item.message),...svg.incompleteReasons];text($("#derived-drawing-warning"),warnings.join(" · ")||"Plano provisional con cotas observadas, deducidas y estimadas diferenciadas; no certifica fabricación.");const image=$("#derived-drawing-image");image.src=api.generalArtifactUrl(state.runId,svg.id,derived.proposalRevision,derived.reviewRevision);image.alt=sheet?.title??"Plano derivado de construcción";fitDerivedDrawing();const downloads=$("#derived-drawing-downloads");downloads.replaceChildren();[svg,dxf].filter(Boolean).forEach((artifact)=>{const link=document.createElement("a");link.className="button";link.textContent=artifact.kind.endsWith("svg")?"SVG":"DXF";link.href=api.generalArtifactUrl(state.runId,artifact.id,derived.proposalRevision,derived.reviewRevision);link.download=artifact.filename??"";downloads.append(link);});};
  state.activeArtifact=kind;$$('[data-artifact-view]').forEach((tab)=>tab.setAttribute("aria-selected",String(tab===button)));toggleHidden($("#drawing-viewer"),true);toggleHidden($("#original-view"),true);toggleHidden($("#scene-viewer"),true);toggleHidden($("#derived-drawing-view"),false);["#zoom-out","#zoom-in","#fit-view","#reset-view"].forEach((selector)=>$(selector).disabled=false);["#toggle-entities","#toggle-texts","#toggle-dimensions"].forEach((selector)=>$(selector).disabled=true);const select=$("#derived-drawing-sheet");select.replaceChildren();sheets.forEach((sheet)=>{const option=document.createElement("option");option.value=sheet.sheetId;option.textContent=sheet.title;select.append(option);});select.disabled=sheets.length<2;select.onchange=()=>renderSheet(sheets.find((item)=>item.sheetId===select.value));renderSheet(sheets[0]);text($("#scene-context"),`${sheetKind==="piece"?"Plano acotado por pieza":"Propuesta de construcción"} · revisión ${derived.reviewRevision}`);
}
async function activateArtifactView(kind,button){
  if(kind==="source"){showSourceArtifact();return;}
  if(state.generalWorkspace?.isGeneral&&["general","components"].includes(kind)){activateGeneralArtifactView(button,kind);return;}
  const runId=state.runId,revision=state.snapshot?.result_revision; if(!runId||!Number.isInteger(revision))return;
  let manifest=state.tableDrawings;
  if(!manifest){const identity=`${runId}:${revision}:manifest:${kind}`,token=artifactFence.issue(identity); text($("#derived-drawing-warning"),"Generando planos técnicos de esta revisión…"); try{const raw=await api.generateTableDrawings(runId,{result_revision:revision}); if(!artifactFence.isCurrent(token,`${state.runId}:${state.snapshot?.result_revision}:manifest:${kind}`))return; manifest=normaliseTableDrawingManifest(raw); state.tableDrawings=manifest;}catch(error){if(artifactFence.isCurrent(token,`${state.runId}:${state.snapshot?.result_revision}:manifest:${kind}`))setMessage(error.message,true);return;}}
  state.activeArtifact=kind; $$('[data-artifact-view]').forEach((tab)=>tab.setAttribute("aria-selected",String(tab===button))); toggleHidden($("#drawing-viewer"),true); toggleHidden($("#original-view"),true); toggleHidden($("#scene-viewer"),true); toggleHidden($("#derived-drawing-view"),false); ["#zoom-out","#zoom-in","#fit-view","#reset-view"].forEach((selector)=>$(selector).disabled=false); ["#toggle-entities","#toggle-texts","#toggle-dimensions"].forEach((selector)=>$(selector).disabled=true); renderDerivedSheetKind(kind); text($("#scene-context"),`Plano derivado · revisión ${manifest.revision}`);
}

function updateArtifactTabs(){
  const tableAvailable=state.tableWorkspace?.isTable&&Boolean(state.tableWorkspace.evaluated),generalAvailable=Boolean(state.generalDerived?.artifacts.some((item)=>["drawing_svg","construction_overview_svg"].includes(item.kind))),pieceAvailable=Boolean(state.generalDerived?.artifacts.some((item)=>item.kind==="piece_sheet_svg")); $$('[data-artifact-view]').forEach((tab)=>{if(tab.dataset.artifactView==="source")return;if(tab.dataset.artifactView==="general")tab.disabled=!(tableAvailable||generalAvailable);else if(tab.dataset.artifactView==="components")tab.disabled=!(tableAvailable||pieceAvailable);else tab.disabled=!tableAvailable;});
}

function applyViewport() { if (state.viewport) { $("#drawing-viewer").setAttribute("viewBox", `${state.viewport.x} ${state.viewport.y} ${state.viewport.width} ${state.viewport.height}`); applySvgTextScale(); } }
function applySvgTextScale() {
  if (!state.viewport) return;
  const rect=$("#cad-viewport").getBoundingClientRect(); if(!rect.width||!rect.height)return;
  const unitPerPixel=svgUnitPerPixel(state.viewport,rect.width,rect.height);
  $$(".drawing-text,.dimension-text").forEach((node)=>{ node.style.fontSize=`${unitPerPixel*12}px`; node.style.strokeWidth=`${unitPerPixel*2.5}px`; });
}
function fitDrawing() {
  if(state.activeArtifact!=="source"){fitDerivedDrawing();return;}
  if(state.activeView==="3d"){sceneViewer?.fit(); sceneViewer?.draw(); return;}
  if (!state.drawingModel) return;
  const partId=state.activeView.startsWith("part:")?state.activeView.slice(5):null;
  const viewIds=partId?partSelectionViewIds(state.partsWorkspace,partId):(state.activeView==="all"?null:new Set([state.activeView]));
  const points=state.drawingModel.pointsForViews(viewIds).map(([x,y])=>[x,-y]);
  if (!points.length) return;
  const rect=$("#cad-viewport").getBoundingClientRect();
  state.viewport=fitViewport(boundsForPoints(points),rect.width||900,rect.height||520,state.drawingModel.fitPaddingForViews(viewIds));
  if(state.activeView==="all")state.fittedViewport={...state.viewport};
  applyViewport();
}
function applyLayerVisibility() { [["entities","#toggle-entities"],["texts","#toggle-texts"],["dimensions","#toggle-dimensions"]].forEach(([name,id]) => $$(`.layer-${name}`).forEach((node)=>node.classList.toggle("is-layer-hidden", !$(id).checked))); }

function selectContour(contourId) {
  if(state.partsWorkspace?.isPartsOnly){
    const path=state.drawingModel?.paths.find((item)=>item.id===contourId);
    const observation=state.partsWorkspace.observations.find((item)=>item.views.some((view)=>view.contourIds.includes(contourId))||path?.entityIds.some((id)=>item.sourceEntityIds.includes(id)));
    if(observation)return selectPartObservation(observation);
  }
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
  sceneViewer?.select(component.id);
}

function selectPartObservation(observation) {
  const contourIds=new Set(observation.views.flatMap((view)=>view.contourIds));
  state.selected={ componentId:observation.id, contourIds, evidenceIds:new Set(observation.evidenceIds), entityIds:new Set(observation.sourceEntityIds) };
  applySelection();
  renderPartEvidence(observation);
}

function selectTableComponent(component){
  const program=state.tableWorkspace?.programs.find((item)=>item.id===(state.snapshot.preview_table_program_id??state.tableWorkspace.selectedProgramId??state.tableWorkspace.evaluated?.programId))??state.tableWorkspace?.programs[0], spec=program?.components.find((item)=>item.id===component.id)??component, evidenceIds=new Set(spec.evidenceIds??component.evidence_ids??[]);
  state.selected={componentId:component.id,contourIds:new Set(),evidenceIds,entityIds:new Set()}; applySelection(); text($("#evidence-title"),TABLE_ROLE_LABELS[component.role]??component.role);
  const summary=$("#piece-summary"); summary.replaceChildren(); [["Largo",component.length],["Ancho",component.width],["Grosor",component.thickness]].forEach(([label,field])=>{const line=document.createElement("p"); line.textContent=`${label}: ${field?.value==null?"Desconocido":formatMeasurement(field.value,"mm")} · ${tableStateLabel(field?.state)}`; summary.append(line); if(field?.dependencyRefs?.length){const formula=document.createElement("code"); formula.textContent=`Dependencias: ${field.dependencyRefs.join(" · ")}`; summary.append(formula);}}); const quantity=document.createElement("p"); quantity.textContent=`Cantidad: ${component.quantity??spec.quantity??"Desconocida"} · regla ${component.quantity_rule_id??spec.quantity_rule_id??"sin resolver"}`; summary.append(quantity);
  const root=$("#evidence-detail"); root.replaceChildren(); const evidences=(state.drawing?.evidence??state.ledger?.evidence??[]).filter((item)=>evidenceIds.has(item.id)); evidences.forEach((item)=>{const card=document.createElement("div"); card.className="detail-item"; const title=document.createElement("b"); title.textContent="Evidencia de fuente"; const copy=document.createElement("span"); copy.textContent=item.description??item.kind??"Evidencia vinculada"; const id=document.createElement("code"); id.textContent=item.id; card.append(title,copy,id); root.append(card);}); (program?.premises??[]).filter((premise)=>spec.premiseIds?.includes(premise.id)).forEach((premise)=>{const card=document.createElement("div"); card.className="detail-item"; const title=document.createElement("b"); title.textContent="Premisa propuesta"; const copy=document.createElement("span"); copy.textContent=premise.description; card.append(title,copy); root.append(card);}); if(!evidences.length)root.append(emptyParagraph("El rol es una propuesta; las medidas conservan sus dependencias del ledger."));
  const explanation=$("#explanation-detail"); explanation.replaceChildren(); const backed=presentTableComponentExplanation(state.explanations,component.id); if(backed.formulas.length){const heading=document.createElement("h3"); heading.textContent="Cálculo ejecutado por el servidor"; explanation.append(heading); backed.formulas.forEach((formula)=>{const card=document.createElement("div"); card.className="detail-item"; const title=document.createElement("b"); title.textContent=`${formula.fieldLabel}: ${formula.resultLabel}`; const expression=document.createElement("code"); expression.textContent=formula.expression; const operands=document.createElement("span"); operands.textContent=formula.operandsLabel||"Sin operandos métricos publicados"; card.append(title,expression,operands); explanation.append(card);});} [...new Set([...backed.premises,...(program?.assumptions??[])])].forEach((assumption)=>{const line=document.createElement("p"); line.textContent=`Premisa: ${assumption}`; explanation.append(line);}); backed.unknownLabels.forEach((field)=>{const line=document.createElement("p"); line.className="unknown"; line.textContent=`Desconocido: ${field}`; explanation.append(line);}); backed.warnings.forEach((warning)=>{const line=document.createElement("p"); line.className="unknown"; line.textContent=warning; explanation.append(line);}); sceneViewer?.select(component.id);
}

function renderPartEvidence(observation) {
  text($("#evidence-title"), observation.label);
  const summary=$("#piece-summary"); summary.replaceChildren();
  const dimensionLabel=(name)=>({length:"Largo",width:"Ancho",thickness:"Grosor"})[name];
  Object.entries(observation.dimensions).forEach(([name,dimension])=>{
    const line=document.createElement("p"); line.textContent=`${dimensionLabel(name)}: ${dimension.value==null?"Desconocido":formatMeasurement(dimension.value,"mm")} · ${sourceLabel(dimension.state)}`; summary.append(line);
  });
  const quantity=document.createElement("p"); quantity.textContent=`Cantidad: ${observation.quantity.value??"Desconocida"} · ${sourceLabel(observation.quantity.state)}`; summary.append(quantity);
  const views=document.createElement("p"); views.textContent=`Vistas asociadas: ${observation.views.map((view)=>({FRONT:"Alzado",TOP:"Planta",SIDE:"Lateral",UNKNOWN:"Sin orientar"})[view.role]??view.role).join(" · ")}`; summary.append(views);
  const root=$("#evidence-detail"); root.replaceChildren();
  const basis=document.createElement("div"); basis.className="detail-item"; const title=document.createElement("b"); title.textContent="Asociación de vistas"; const detail=document.createElement("span"); detail.textContent=observation.associationBasis==="explicit_key"?"Clave PART explícita del plano":observation.associationBasis==="ambiguous"?"Asociación ambigua conservada":"Vista sin asociación; no se agrupó por proximidad"; basis.append(title,detail); root.append(basis);
  const evidence=(state.drawing?.evidence??state.ledger?.evidence??[]).filter((item)=>observation.evidenceIds.includes(item.id));
  evidence.forEach((item)=>{const card=document.createElement("div"); card.className="detail-item"; const heading=document.createElement("b"); heading.textContent=({geometry:"Geometría de respaldo",annotation:"Anotación del plano",view_association:"Asociación de vista"})[item.kind]??"Evidencia vinculada"; const copy=document.createElement("span"); copy.textContent=item.description??item.kind??"Evidencia geométrica"; const id=document.createElement("code"); id.textContent=item.id; card.append(heading,copy,id); root.append(card);});
  observation.warnings.forEach((warning)=>{ const card=document.createElement("div"); card.className="detail-item detail-item--warning"; const heading=document.createElement("b"); heading.textContent="Advertencia"; const copy=document.createElement("span"); copy.textContent=warning; card.append(heading,copy); root.append(card); });
  if(!evidence.length&&!observation.warnings.length)root.append(emptyParagraph("Sin advertencias; la procedencia se conserva en los IDs de entidades y vistas."));
  const explanationRoot=$("#explanation-detail"); explanationRoot.replaceChildren();
  const note=document.createElement("p"); note.textContent="Esta ficha describe la pieza observada. Familia, rol y montaje se revisan aparte como hipótesis."; explanationRoot.append(note);
  const explanations=state.explanations?.pieces??state.explanations?.items??[];
  const explanation=explanations.find((item)=>item.part_observation_id===observation.id);
  if(explanation){[explanation.summary,...(explanation.premises??[]),...(explanation.unknown_fields??[]).map((field)=>`Desconocido: ${unknownFieldLabel(field)}`)].filter(Boolean).forEach((value)=>{const line=document.createElement("p"); line.textContent=String(value); explanationRoot.append(line);});}
}

function applySelection() {
  $$(".drawing-path").forEach((path) => {
    const selected = state.selected?.contourIds?.has(path.dataset.contourId) || path._entityIds?.some((id)=>state.selected?.entityIds?.has(id));
    path.classList.toggle("is-selected", Boolean(selected));
    path.classList.toggle("is-dimmed", Boolean(state.selected) && !selected);
  });
  $$("#parts-body tr[data-component-id]").forEach((row) => row.classList.toggle("is-selected", row.dataset.componentId === state.selected?.componentId));
}

function renderEvidence(component, contourId) {
  text($("#evidence-title"), component?.label ?? component?.name ?? (contourId ? "Contorno del plano" : "Sin selección"));
  const root = $("#evidence-detail"); root.replaceChildren();
  const summary = $("#piece-summary"); summary.replaceChildren();
  if (component) {
    const dims = component.dimensions_mm ?? component.dimensions ?? {};
    const value=(item)=>item&&typeof item==="object"&&"value" in item?item.value:item;
    const details = document.createElement("p");
    const typedDimensions=dims.length&&typeof dims.length==="object";
    details.textContent = typedDimensions?`Largo ${generalDimensionText(dims.length)} · Ancho ${generalDimensionText(dims.width)} · Grosor ${generalDimensionText(dims.thickness)} · Cantidad ${component.constructionPiece?generalQuantityText(component.quantity):(value(component.quantity) ?? "desconocida")}`:`Largo ${formatMeasurement(value(dims.length ?? component.length_mm),"mm")} · Ancho ${formatMeasurement(value(dims.width ?? component.width_mm),"mm")} · Grosor ${formatMeasurement(value(dims.thickness ?? component.thickness_mm),"mm")} · Cantidad ${value(component.quantity) ?? "desconocida"}`;
    summary.append(details);
    if(typedDimensions)Object.entries({Largo:dims.length,Ancho:dims.width,Grosor:dims.thickness}).forEach(([label,dimension])=>{const item=generalDimensionPresentation(dimension);if(item.value==null&&!item.explanation)return;const card=document.createElement("div");card.className="detail-item";const title=document.createElement("b"),copy=document.createElement("span"),refs=document.createElement("code");title.textContent=`${label} · ${item.stateLabel}`;copy.textContent=[item.display,item.rangeDisplay&&`rango ${item.rangeDisplay}`,item.method&&`método ${item.method}`,item.formula&&`fórmula ${item.formula}`,item.explanation].filter(Boolean).join(" · ");refs.textContent=[...item.sourceRefs,...item.operandRefs,...item.assumptionRefs].join(" · ")||"Sin referencias publicadas";card.append(title,copy,refs);root.append(card);});
    if(component.constructionPiece){const item=presentGeneralConstructionQuantity(component.quantity),card=document.createElement("div"),title=document.createElement("b"),copy=document.createElement("span"),refs=document.createElement("code");card.className="detail-item";title.textContent=`Cantidad · ${item.approximate?"Estimada":"Propuesta"}`;copy.textContent=[item.display,item.rangeDisplay&&`rango ${item.rangeDisplay}`,item.method&&`método ${item.method}`,item.explanation].filter(Boolean).join(" · ");refs.textContent=[...item.sourceRefs,...item.assumptionRefs].join(" · ")||"Sin referencias publicadas";card.append(title,copy,refs);root.append(card);}
    if(component.rawHypothesis){const raw=component.rawHypothesis,rawLine=document.createElement("p");rawLine.textContent=`Hipótesis original, conservada solo para inspección: largo ${formatMeasurement(raw.dimensions.length.value,"mm")} · ancho ${formatMeasurement(raw.dimensions.width.value,"mm")} · grosor ${formatMeasurement(raw.dimensions.thickness.value,"mm")} · cantidad ${raw.quantity.value??"desconocida"}. Los valores rechazados, conflictivos o no revisados no se usan en la tabla ni en las exportaciones.`;summary.append(rawLine);}
    const formula = component.length_derivation ?? component.formula ?? component.derivation;
    if (formula) { const note = document.createElement("p"); note.textContent = `Fórmula: ${formula}`; summary.append(note); }
    (component.assumptions ?? component.premises ?? []).forEach((value)=>{ const note=document.createElement("p"); note.textContent=`Premisa: ${value}`; summary.append(note); });
  } else summary.append(emptyParagraph(contourId ? "Evidencia geométrica sin pieza asociada." : "Selecciona una pieza o evidencia."));
  const ids = component?.evidence_ids ?? [];
  const evidences = (state.drawing?.evidence ?? state.ledger?.evidence ?? []).filter((item) => ids.includes(item.id));
  let records = evidences.length ? evidences : [{ id: contourId ?? "sin evidencia", description: component ? "Propuesta pendiente de evidencia enlazada." : "Contorno geométrico seleccionado." }];
  if (!component && !contourId && state.drawing?.dimensions?.length) records = state.drawing.dimensions.map((dimension) => {
    const view = state.drawing.views?.find((item)=>item.id===dimension.view_id);
    const viewLabel=({FRONT:"Alzado",TOP:"Planta",SIDE:"Lateral",UNKNOWN:"Vista sin orientar"})[view?.label]??"Vista asociada";
    return { id: dimension.id, title: `Cota ${sourceLabel(dimension.origin).toLowerCase()} · ${viewLabel}`, description: formatMeasurement(dimension.value_mm, "mm") };
  });
  records.forEach((record) => {
    const card = document.createElement("div"); card.className = "detail-item";
    const strong = document.createElement("b"); strong.textContent = record.title ?? ({geometry:"Geometría de respaldo",annotation:"Anotación del plano",view_association:"Asociación de vista"})[record.kind] ?? (contourId ? "Contorno geométrico" : "Evidencia vinculada");
    const description = document.createElement("span"); description.textContent = record.description ?? record.kind ?? "Evidencia geométrica";
    const identifier=document.createElement("code"); identifier.textContent=record.id;
    card.append(strong, description, identifier); root.append(card);
  });
  const explanations = state.explanations?.pieces ?? state.explanations?.items ?? state.explanations?.explanations ?? [];
  const explanation = explanations.find((item)=>[item.piece_id,item.proposal_id,item.component_id].includes(component?.id));
  const explanationRoot = $("#explanation-detail"); explanationRoot.replaceChildren();
  if (explanation) {
    const heading=document.createElement("h3"); heading.textContent="Explicación respaldada"; explanationRoot.append(heading);
    const fieldLabel=(value)=>({length_mm:"Largo",width_mm:"Ancho",thickness_mm:"Grosor",quantity:"Cantidad",material:"Material",finish:"Acabado"})[value]??value;
    [explanation.summary, explanation.formula, ...(explanation.formulas ?? []).map((item)=>`${fieldLabel(item.field)}: ${item.expression} = ${formatMeasurement(item.result_mm,"mm")}`), ...(explanation.premises ?? explanation.assumptions ?? []), ...(explanation.unknown_fields ?? []).map((item)=>`Desconocido: ${fieldLabel(item)}`)].filter(Boolean).forEach((value)=>{ const p=document.createElement("p"); p.textContent=String(value); explanationRoot.append(p); });
  }
}

async function loadScene() {
  const warning = $("#scene-warning"); warning.hidden = true;
  if (!state.runId || !Number.isInteger(state.snapshot?.result_revision)) { warning.hidden = false; text(warning, "3D no disponible: registra una revisión con medidas completas."); return; }
  const identity=`${state.runId}:${state.snapshot.result_revision}`, token=sceneFence.issue(identity);
  try {
    const raw = await api.getScene(state.runId, state.snapshot.result_revision);
    if (!sceneFence.isCurrent(token, `${state.runId}:${state.snapshot?.result_revision}`)) return;
    state.scene = raw;
    if (!sceneViewer) { const module = await import("./components/SceneViewer.js"); if (!sceneFence.isCurrent(token, `${state.runId}:${state.snapshot?.result_revision}`)) return; sceneViewer = new module.SceneViewer($("#scene-viewer"), { onSelect: (item) => { const observation=state.partsWorkspace?.observations.find((entry)=>entry.id===item.partObservationId); if(observation)return selectPartObservation(observation); const tableComponent=state.tableWorkspace?.evaluated?.components.find((entry)=>[item.pieceId,item.proposalId].includes(entry.id)); if(tableComponent)return selectTableComponent(tableComponent); const { components } = extractComponents(); const component = components.find((entry)=>[item.pieceId,item.proposalId].includes(entry.id)); if (component) selectComponent(component); } }); }
    const model = sceneViewer.setScene(raw); $("#explode-control").hidden = false;
    const assumptions=(raw.assumptions??model.assumptions??[]).map(translateAssumption);
    text($("#scene-context"),`3D revisado · colocación ${assumptions.length?"esquemática":"según candidato"}`);
    const premises=$("#scene-premises-list"); premises.replaceChildren(); assumptions.forEach((value)=>{const line=document.createElement("p"); line.textContent=value; premises.append(line);}); toggleHidden($("#scene-premises"),!assumptions.length);
    const messages = [...model.warnings, ...(model.collisionStatus === "not_evaluated" ? ["Colisiones no evaluadas."] : [])];
    warning.hidden = !messages.length; text(warning, messages.join(" · "));
  } catch (error) { if(!sceneFence.isCurrent(token,`${state.runId}:${state.snapshot?.result_revision}`))return; state.scene = null; warning.hidden = false; text(warning, `3D no disponible para la revisión ${state.snapshot.result_revision}: ${error.message}`); }
}

const partStateLabel=(value)=>({observed:"Observado",unknown:"Desconocido",conflict:"Conflicto",ambiguous:"Ambigua",complete:"Completa",partial:"Parcial",hypothesis:"Hipótesis",human_confirmed:"Confirmado"})[value]??value;
const roleLabel=(value)=>({side_panel:"Lateral",shelf:"Balda",top_panel:"Tapa",base_panel:"Base",back_panel:"Trasera",door:"Puerta",divider:"Divisor",unknown:"Rol desconocido"})[value]??value;
const unknownFieldLabel=(value)=>({quantity:"cantidad",length:"largo",length_mm:"largo",width:"ancho",width_mm:"ancho",thickness:"grosor",thickness_mm:"grosor",material:"material",finish:"acabado",family:"familia",layout:"montaje"})[value]??value;

function renderDerivedDimensions(candidate, root) {
  const axisLabel={width:"Ancho",height:"Alto",depth:"Fondo"};
  candidate.derivedDimensions.forEach((dimension)=>{
    const constraint=candidate.constraints.find((item)=>item.id===dimension.constraint_id), refs=constraint?.operand_refs??dimension.operand_refs??[], values=refs.map((reference)=>resolveAssemblyOperand(reference,state.partsWorkspace,candidate)?.value??null), known=values.length&&values.every(Number.isFinite);
    const card=document.createElement("div"); card.className="derived-dimension"; const heading=document.createElement("b"); heading.textContent=`${axisLabel[dimension.axis]??dimension.axis}: ${formatMeasurement(dimension.value_mm,"mm")} · ${dimension.state==="derived"?"Calculado":partStateLabel(dimension.state)}`;
    const explanation=document.createElement("code"); const symbol=constraint?.operation==="sum"?" + ":constraint?.operation==="difference"?" − ":" = "; explanation.textContent=known?`${values.map((value)=>formatMeasurement(value,"mm")).join(symbol)} = ${formatMeasurement(dimension.value_mm,"mm")}`:`Operación ${constraint?.operation??"documentada"} · ${refs.join(" · ")}`;
    card.append(heading,explanation); root.append(card);
  });
}

function renderPartDecisionFields(candidate) {
  const root=$("#part-decisions"); root.replaceChildren();
  const uncertain=candidate?.uses.filter((use)=>{const observation=state.partsWorkspace.observations.find((item)=>item.id===use.partObservationId); return use.allocatedQuantity.value==null||Object.values(observation?.dimensions??{}).some((dimension)=>dimension.value==null);})??[];
  if(!uncertain.length)return;
  const unresolved=uncertain.some((use)=>{const observation=state.partsWorkspace.observations.find((item)=>item.id===use.partObservationId); return (use.allocatedQuantity.value==null&&use.effective?.quantity.value==null)||Object.entries(observation?.dimensions??{}).some(([name,dimension])=>dimension.value==null&&use.effective?.dimensions?.[name]?.value==null);});
  const heading=document.createElement("p"); heading.className="eyebrow"; heading.textContent=unresolved?"Datos que requieren confirmación":"Valores humanos vigentes"; root.append(heading);
  uncertain.forEach((use)=>{
    const observation=state.partsWorkspace.observations.find((item)=>item.id===use.partObservationId);
    const block=document.createElement("fieldset"); block.className="allocation-decision"; block.dataset.useId=use.id; block.dataset.role=use.role;
    const legend=document.createElement("legend"); legend.textContent=`${observation?.label??"Pieza"} como ${roleLabel(use.role).toLowerCase()}`;
    const numericField=(labelText,field,step,effective)=>{const label=document.createElement("label"); label.textContent=effective?.value!=null?`${labelText.replace("confirmad", "vigente confirmad")}`:labelText; const input=document.createElement("input"); input.type="number"; input.min=step; input.step=step; input.dataset.decisionField=field; input.dataset.originalValue=effective?.value??""; if(effective?.value!=null){input.value=effective.value; input.classList.add("is-reviewed"); input.setAttribute("aria-label",`${labelText}: valor vigente editable`);} label.append(input); return label;};
    const fields=[];
    if(use.allocatedQuantity.value==null)fields.push(numericField("Cantidad confirmada","quantity","1",use.effective?.quantity));
    if(observation?.dimensions.length.value==null)fields.push(numericField("Largo confirmado (mm)","length",".1",use.effective?.dimensions.length));
    if(observation?.dimensions.width.value==null)fields.push(numericField("Ancho confirmado (mm)","width",".1",use.effective?.dimensions.width));
    if(observation?.dimensions.thickness.value==null)fields.push(numericField("Grosor confirmado (mm)","thickness",".1",use.effective?.dimensions.thickness));
    const note=document.createElement("small"); note.textContent=fields.some((field)=>field.querySelector("input")?.dataset.originalValue==="")?"Deja vacío lo que no esté comprobado; el sistema conservará el desconocido.":"Valores vigentes: edítalos solo para registrar una nueva corrección justificada.";
    block.append(legend,...fields,note); root.append(block);
  });
}

function renderSeparatedPartsAndReview() {
  const workspace=state.partsWorkspace, body=$("#parts-body"); body.replaceChildren();
  $("#parts-head").innerHTML="<tr><th>Pieza</th><th>Asociación</th><th>Vistas</th><th>Cant.</th><th>Largo</th><th>Ancho</th><th>Grosor</th></tr>";
  text($("#parts-summary"),`${workspace.observations.length} ${workspace.observations.length===1?"observación":"observaciones"} · varias vistas no aumentan la cantidad`);
  workspace.observations.forEach((observation)=>{
    const row=document.createElement("tr"); row.dataset.componentId=observation.id; row.tabIndex=0;
    const association=observation.associationBasis==="explicit_key"?"Clave explícita":observation.associationBasis==="ambiguous"?"Ambigua":"Sin asociar";
    const views=observation.views.map((view)=>({FRONT:"Alzado",TOP:"Planta",SIDE:"Lateral",UNKNOWN:"Sin orientar"})[view.role]??view.role).join(" · ");
    const fields=[observation.label,association,views,observation.quantity,...Object.values(observation.dimensions)];
    fields.forEach((field,index)=>{ const cell=document.createElement("td"); if(index<3)cell.textContent=field; else { const isQuantity=index===3; cell.textContent=field.value==null?(isQuantity?"Desconocida":"Desconocido"):(isQuantity?field.value:formatMeasurement(field.value,"mm")); const badge=document.createElement("small"); badge.className="cell-origin"; badge.dataset.origin=field.state==="observed"?"observed":field.state==="human_confirmed"?"human_confirmed":"hypothesis"; badge.textContent=partStateLabel(field.state); cell.append(badge); if(field.value==null)cell.classList.add("unknown"); } row.append(cell); });
    row.addEventListener("click",()=>selectPartObservation(observation)); row.addEventListener("keydown",(event)=>{if(event.key==="Enter")selectPartObservation(observation);}); body.append(row);
  });
  if(!workspace.observations.length){ const row=document.createElement("tr"); row.className="empty-row"; const cell=document.createElement("td"); cell.colSpan=7; cell.textContent="No se observaron piezas. No se inventa un despiece."; row.append(cell); body.append(row); }
  text($("#scenario-status"),workspace.selectedCandidateId?"Montaje revisado":workspace.candidates.length?"Clasificación hipotética":"Sin hipótesis de montaje");
  const options=$("#scenario-options"); options.replaceChildren(); const legend=document.createElement("legend"); legend.textContent="Hipótesis de familia y montaje"; options.append(legend);
  const selectedId=preferredCandidateId(workspace,state.snapshot.preview_assembly_candidate_id);
  workspace.candidates.forEach((candidate)=>{
    const label=document.createElement("label"); label.className="scenario-option"; const input=document.createElement("input"); input.type="radio"; input.name="assembly-candidate"; input.value=candidate.id; input.checked=candidate.id===selectedId;
    input.addEventListener("change",()=>{state.snapshot.preview_assembly_candidate_id=candidate.id; renderSeparatedPartsAndReview();});
    const content=document.createElement("span"); const title=document.createElement("b"); title.textContent=candidate.assignmentLabel||`${candidate.familyLabel} · ${candidate.layoutLabel}`; const detail=document.createElement("small"); const unknown=candidate.unknownFields.length?`Desconocidos: ${candidate.unknownFields.map(unknownFieldLabel).join(", ")}`:"Sin faltantes dimensionales o de cantidad"; detail.textContent=`${candidate.familyLabel} · ${candidate.layoutLabel} · Hipótesis · ${candidate.assumptions.join(" · ")} · ${unknown}`; content.append(title,detail); label.append(input,content); options.append(label);
  });
  if(!workspace.candidates.length)options.append(emptyParagraph("No hay una clasificación o montaje respaldado para revisar."));
  const selected=workspace.candidates.find((item)=>item.id===selectedId);
  const summary=$("#classification-summary"); summary.replaceChildren();
  if(selected){ const title=document.createElement("b"); title.textContent=`${selected.familyLabel} · ${selected.layoutLabel}`; const status=document.createElement("p"); const reviewed=workspace.selectedCandidateId===selected.id; status.textContent=reviewed?`Hipótesis seleccionada en revisión ${state.snapshot.result_revision}; reconstrucción condicionada a sus premisas.`:"Clasificación y roles: hipótesis pendientes de decisión humana."; summary.append(title,status); selected.uses.forEach((use)=>{const observation=workspace.observations.find((item)=>item.id===use.partObservationId); const line=document.createElement("p"); const source=use.sourceQuantity.value??"desconocida", allocated=use.allocatedQuantity.value??"desconocida", occurrences=use.occurrenceIndices.length?` · ocurrencias ${use.occurrenceIndices.join(", ")}`:""; line.textContent=`${observation?.label??use.partObservationId} → ${roleLabel(use.role)} · fuente ${source} · asignadas ${allocated}${occurrences} · ${partStateLabel(use.roleState)}`; summary.append(line);}); const effective=selected.uses.filter((use)=>use.effective); if(effective.length){const reviewedValues=document.createElement("div"); reviewedValues.className="review-values"; const heading=document.createElement("b"); heading.textContent=`Valores de revisión ${workspace.revisionNumber}`; reviewedValues.append(heading); effective.forEach((use)=>{const observation=workspace.observations.find((item)=>item.id===use.partObservationId), values=presentReviewedUse(use); const line=document.createElement("p"); line.textContent=`${observation?.label??use.partObservationId} → ${roleLabel(use.role)} · Cantidad ${values.quantity} · Largo ${values.length} · Ancho ${values.width} · Grosor ${values.thickness}`; reviewedValues.append(line);}); summary.append(reviewedValues);} renderDerivedDimensions(selected,summary); if(selected.unassignedObservationIds.length){const warning=document.createElement("p"); warning.className="unknown"; warning.textContent=`Sin asignar: ${selected.unassignedObservationIds.join(", ")}`; summary.append(warning);} }
  else summary.append(emptyParagraph("Las observaciones siguen disponibles sin clasificación de montaje."));
  renderPartDecisionFields(selected);
  toggleHidden($("#legacy-review-fields"),true); $("#review-thickness").required=false; $("#review-submit").disabled=!workspace.candidates.length;
  text($("#input-kind-label"),"Entrada: piezas separadas"); text($("#revision-label"),Number.isInteger(state.snapshot?.result_revision)?`Revisión ${state.snapshot.result_revision}`:"Revisión pendiente");
  unlock("parts-stage"); unlock("review-stage");
}

const TABLE_ROLE_LABELS={tabletop:"Tapa",side_support:"Soportes laterales",corner_support:"Patas de esquina"};
const TABLE_MEASURE_LABELS={overall_width:"Ancho general",overall_height:"Alto general",overall_depth:"Fondo general",tabletop_thickness:"Grosor de tapa",support_width:"Sección de soporte",support_depth:"Fondo de soporte",support_thickness:"Grosor de soporte",unknown:"Medida sin clasificar"};
const TABLE_STATE_LABELS={observed:"Observado",calculated:"Calculado",confirmed:"Confirmado",proposed:"Propuesto",unknown:"Desconocido",conflict:"Conflicto",hypothesis:"Hipótesis",needs_review:"Revisión necesaria",completed:"Revisado",rejected:"Rechazado"};
function tableStateLabel(value){return TABLE_STATE_LABELS[value]??value??"Desconocido";}
function tableValueCell(field,quantity=false){const cell=document.createElement("td"),value=field?.value; cell.textContent=value==null?(quantity?"Desconocida":"Desconocido"):(quantity?value:formatMeasurement(value,"mm")); const badge=document.createElement("small"); badge.className="cell-origin"; badge.dataset.origin=field?.state==="confirmed"?"human_confirmed":field?.state==="calculated"?"derived":field?.state==="observed"?"observed":"hypothesis"; badge.textContent=tableStateLabel(field?.state); cell.append(badge); if(value==null)cell.classList.add("unknown"); return cell;}
function tableDecisionControl(kind,id,labelText,workspace){const block=document.createElement("fieldset"); block.className="detail-item table-decision"; block.dataset.targetKind=kind; block.dataset.targetId=id; const legend=document.createElement("legend"); legend.textContent=labelText; block.append(legend); [["accept","Aceptar"],["reject","Rechazar"]].forEach(([value,label])=>{const choice=document.createElement("label"),radio=document.createElement("input"); radio.type="radio"; radio.name=`table-${kind}-${id}`; radio.value=value; radio.checked=value==="accept"?workspace.evaluated?.acceptedTargetIds.includes(id):workspace.evaluated?.rejectedTargetIds.includes(id); choice.append(radio,document.createTextNode(` ${label}`)); block.append(choice);}); return block;}

function renderTableAndReview(){
  const workspace=state.tableWorkspace, selectedId=state.snapshot.preview_table_program_id??workspace.selectedProgramId??workspace.evaluated?.programId??workspace.programs[0]?.id, program=workspace.programs.find((item)=>item.id===selectedId)??workspace.programs[0], evaluated=workspace.evaluated?.programId===program?.id?workspace.evaluated:null;
  state.snapshot.preview_table_program_id=program?.id;
  text($("#input-kind-label"),"Entrada: mesa · vistas montadas"); text($("#parts-title"),"Componentes propuestos"); text($("#parts-summary"),`${workspace.measures.length} medidas del ledger · ${program?.originLabel??"sin propuesta"}`); text($("#scenario-status"),tableStateLabel(evaluated?.state??"hypothesis"));
  $("#parts-head").innerHTML="<tr><th>Componente</th><th>Origen</th><th>Cant.</th><th>Largo</th><th>Ancho</th><th>Grosor</th></tr>";
  const body=$("#parts-body"); body.replaceChildren();
  (program?.components??[]).forEach((component)=>{const effective=evaluated?.components.find((item)=>item.id===component.id),row=document.createElement("tr"); row.dataset.componentId=component.id; row.tabIndex=0; const name=document.createElement("td"); name.textContent=TABLE_ROLE_LABELS[component.role]??component.role; const origin=document.createElement("td"); origin.textContent=program.originLabel; origin.dataset.origin="hypothesis"; const quantity={value:effective?.quantity??component.quantity,state:effective?.accepted?"confirmed":"proposed"}; row.append(name,origin,tableValueCell(quantity,true),tableValueCell(effective?.length),tableValueCell(effective?.width),tableValueCell(effective?.thickness)); row.addEventListener("click",()=>selectTableComponent(effective??component)); row.addEventListener("keydown",(event)=>{if(event.key==="Enter")selectTableComponent(effective??component);}); body.append(row);});
  if(!program){const row=document.createElement("tr"); row.className="empty-row"; const cell=document.createElement("td"); cell.colSpan=6; cell.textContent="No hay propuesta de componentes. El plano fuente permanece disponible."; row.append(cell); body.append(row);}
  const options=$("#scenario-options"); options.replaceChildren(); const legend=document.createElement("legend"); legend.textContent="Programa de descomposición"; options.append(legend); workspace.programs.forEach((item)=>{const label=document.createElement("label"); label.className="scenario-option"; const input=document.createElement("input"); input.type="radio"; input.name="table-program"; input.value=item.id; input.checked=item.id===program?.id; input.addEventListener("change",()=>{state.snapshot.preview_table_program_id=item.id;renderTableAndReview();}); const content=document.createElement("span"),title=document.createElement("b"),detail=document.createElement("small"); title.textContent=item.originLabel; detail.textContent=`${item.components.map((component)=>`${TABLE_ROLE_LABELS[component.role]??component.role} × ${component.quantity}`).join(" · ")} · ${item.assumptions.join(" · ")}`; content.append(title,detail); label.append(input,content); options.append(label);}); if(!workspace.programs.length)options.append(emptyParagraph("No hay programa válido para revisar."));
  const summary=$("#classification-summary"); summary.replaceChildren(); const source=document.createElement("b"); source.textContent=program?.originLabel??"Sin propuesta"; summary.append(source); workspace.measures.forEach((measure)=>{const line=document.createElement("p"),sourceValue=measure.value==null?"Desconocido":formatMeasurement(measure.value,"mm"),effective=measure.effectiveValue==null?"":` · ${measure.effectivePrefix} ${formatMeasurement(measure.effectiveValue,"mm")} · ${measure.effectiveLabel}`; line.textContent=`${TABLE_MEASURE_LABELS[measure.semantic]??measure.semantic}: ${sourceValue} · ${measure.sourceLabel} · ${tableStateLabel(measure.state)}${effective}`; if(measure.state!=="observed"&&measure.effectiveValue==null)line.className="unknown"; summary.append(line);}); workspace.warnings.forEach((warning)=>{const line=document.createElement("p"); line.className="unknown"; line.textContent=warning; summary.append(line);});
  const decisions=$("#part-decisions"); decisions.replaceChildren(); if(program){decisions.append(tableDecisionControl("program",program.id,"Programa completo",workspace)); program.components.forEach((component)=>decisions.append(tableDecisionControl("component",component.id,TABLE_ROLE_LABELS[component.role]??component.role,workspace))); program.premises.forEach((premise)=>decisions.append(tableDecisionControl("premise",premise.id,premise.description,workspace))); workspace.measures.filter((measure)=>measure.confirmable).forEach((measure)=>{const label=document.createElement("label"); label.className="table-confirmed-value"; label.dataset.measureId=measure.id; const action=measure.humanEffective?"Valor vigente editable":measure.effectiveValue==null?"Confirmar":"Confirmar propuesta"; label.textContent=`${action} ${TABLE_MEASURE_LABELS[measure.semantic]??measure.semantic} (mm)`; const input=document.createElement("input"); input.type="number"; input.min="0.1"; input.step="0.1"; input.value=measure.effectiveValue??""; input.placeholder=measure.state==="conflict"?"Resolver conflicto":"Dato faltante"; label.append(input); decisions.append(label);}); evaluated?.issues.forEach((issue)=>{const note=document.createElement("p"); note.className=issue.severity==="warning"?"field-note":"unknown"; note.textContent=issue.message; decisions.append(note);});}
  $$(".table-confirmed-value",decisions).forEach((label)=>{const measure=workspace.measures.find((item)=>item.id===label.dataset.measureId),input=$("input",label); input.dataset.originalValue=measure?.effectiveValue??""; if(measure?.confirmation){const note=document.createElement("small"); note.textContent=`Confirmación vigente: ${measure.confirmation.reason}. Editar crea una nueva revisión sin borrar la anterior.`; label.append(note);}});
  workspace.measures.filter((measure)=>measure.correctable).forEach((measure)=>{const label=document.createElement("label"); label.className="table-observed-correction"; label.dataset.measureId=measure.id; label.textContent=`Corregir valor observado · ${TABLE_MEASURE_LABELS[measure.semantic]??measure.semantic} (mm)`; const input=document.createElement("input"); input.type="number"; input.min="0.1"; input.step="0.1"; input.value=measure.effectiveValue??measure.value??""; input.dataset.originalValue=measure.effectiveValue??measure.value??""; const note=document.createElement("small"); note.textContent=`Original CAD ${formatMeasurement(measure.value,"mm")} · evidencia ${measure.evidenceIds.join(", ")}. Una contradicción superior a tolerancia seguirá bloqueando.`; label.append(input,note); decisions.append(label);});
  workspace.sourceWarnings.forEach((warning)=>{const block=document.createElement("fieldset"); block.className="table-source-review"; block.dataset.warningId=warning.id; block.dataset.warningCode=warning.code; const legend=document.createElement("legend"); legend.textContent=warning.currentAction?"Decisión de recuperación DXF rectificable":"Revisión obligatoria de recuperación DXF"; block.append(legend); [["accept","Fuente comprobada"],["reject","Fuente rechazada"]].forEach(([value,labelText])=>{const label=document.createElement("label"),radio=document.createElement("input"); radio.type="radio"; radio.name=`source-${warning.id}`; radio.value=value; radio.checked=warning.currentAction===value; label.append(radio,document.createTextNode(` ${labelText}`)); block.append(label);}); const note=document.createElement("small"); note.textContent=`${warning.message} · ${warning.code}${warning.currentReason?` · Motivo vigente: ${warning.currentReason}`:""}`; block.append(note); decisions.append(block);});
  toggleHidden($("#legacy-review-fields"),true); $("#review-thickness").required=false; toggleHidden($("#review-material").closest("label"),true); toggleHidden($("#review-finish").closest("label"),true); $("#review-submit").disabled=!program; text($("#revision-label"),Number.isInteger(state.snapshot?.result_revision)?`Revisión ${state.snapshot.result_revision}`:"Revisión pendiente"); unlock("parts-stage"); unlock("review-stage");
}

function generalFieldValue(field) { return field?.value == null ? "Desconocido" : `${field.value}${field.unit ? ` ${field.unit}` : ""}`; }
function generalDimensionPresentation(field){return presentGeneralConstructionDimension(field??{});}
function generalDimensionText(field){const value=generalDimensionPresentation(field);return[value.display,value.stateLabel,value.rangeDisplay?`rango ${value.rangeDisplay}`:null].filter(Boolean).join(" · ");}
function generalQuantityText(field){const value=presentGeneralConstructionQuantity(field??{});return[value.display,value.rangeDisplay?`rango ${value.rangeDisplay}`:null].filter(Boolean).join(" · ");}
function generalUnknownSummary(component){const labels={length:"largo",width:"ancho",thickness:"grosor",quantity:"cantidad",material:"material",finish:"acabado"},fields={length:component.dimensions.length,width:component.dimensions.width,thickness:component.dimensions.thickness,quantity:component.quantity,...(component.constructionPiece?{}:{material:component.material,finish:component.finish})};return Object.entries(fields).filter(([,field])=>field?.value==null).map(([name,field])=>{const review=field?.machineReview,status=({rejected:"rechazado",conflict:"en conflicto",abstained:"abstención",unreviewed:"sin revisar"})[field?.reviewStatus??review?.status];return status?`${labels[name]} (${status}${review?.reason?`: ${review.reason}`:""})`:labels[name];}).join(", ")||"Ninguno";}
function generalStatusLabel(value){return({needs_review:"Revisión necesaria",reviewed_incomplete:"Revisado con datos pendientes",approved:"Aprobado",ready:"Listo",incomplete:"Incompleto",complete:"Completa",partial:"Parcial",unavailable:"No disponible"})[value]??String(value??"Desconocido");}
function generalArtifactLabel(value){return({bom_csv:"BOM CSV",bom_json:"BOM JSON",drawing_svg:"Esquema SVG",drawing_dxf:"Esquema DXF",construction_overview_svg:"Construcción SVG",construction_overview_dxf:"Construcción DXF",piece_sheet_svg:"Pieza SVG",piece_sheet_dxf:"Pieza DXF"})[value]??String(value??"Artefacto");}

function appendGeneralResultEditor(root, component={}) {
  const card=document.createElement("fieldset");card.className="general-component-editor";card.dataset.resultId=component.resultId??`${component.id??"component"}-reviewed-${root.children.length+1}`;
  card._sourceComponent=component;
  const title=document.createElement("legend");title.textContent=component.label??"Nuevo componente";card.append(title);
  [["label","Nombre",component.label,"text",null],["kind","Tipo",component.kind??"unknown","text",null],["role","Rol",component.role??"unknown","text",null],["quantity","Cantidad",component.quantity?.value,"number",component.quantity],["length","Largo mm",component.dimensions?.length?.value,"number",component.dimensions?.length],["width","Ancho mm",component.dimensions?.width?.value,"number",component.dimensions?.width],["thickness","Grosor mm",component.dimensions?.thickness?.value,"number",component.dimensions?.thickness],["material","Material",component.material?.value,"text",component.material],["finish","Acabado",component.finish?.value,"text",component.finish]].forEach(([name,labelText,value,type,original])=>{const label=document.createElement("label"),input=document.createElement("input");label.textContent=labelText;input.type=type;input.dataset.generalField=name;input.dataset.originalValue=value??"";input.dataset.originalState=original?.state??"unknown";input.value=value??"";if(type==="number"){input.min="0";input.step=name==="quantity"?"1":"0.1";}label.append(input);card.append(label);});
  const remove=document.createElement("button");remove.type="button";remove.className="button";remove.textContent="Quitar resultado";remove.addEventListener("click",()=>card.remove());card.append(remove);root.append(card);
}

function appendGeneralScopeControls(root,workspace){
  const choices=[["fixed","Fijo"],["material","Material"],["labor","Mano de obra"],["machining","Mecanizado"],["finish","Acabado"],["other","Otro"]];
  [["cost",workspace.requiredCostScope,"Alcance requerido de coste"],["hours",workspace.requiredHoursScope,"Alcance requerido de horas"]].forEach(([kind,current,title])=>{const fieldset=document.createElement("fieldset"),legend=document.createElement("legend");legend.textContent=title;fieldset.append(legend);choices.forEach(([value,labelText])=>{const label=document.createElement("label"),input=document.createElement("input");input.type="checkbox";input.value=value;input.dataset.historyScope=kind;input.checked=current.includes(value);label.append(input,document.createTextNode(` ${labelText}`));fieldset.append(label);});const customLabel=document.createElement("label"),custom=document.createElement("input");customLabel.textContent="Identificadores adicionales (separados por coma)";custom.dataset.historyScopeCustom=kind;custom.value=current.filter((item)=>!choices.some(([value])=>value===item)).join(", ");customLabel.append(custom);fieldset.append(customLabel);root.append(fieldset);});
}
function generalScopeValues(kind){const checked=$$(`[data-history-scope="${kind}"]:checked`).map((input)=>input.value),custom=($(`[data-history-scope-custom="${kind}"]`)?.value??"").split(",").map((item)=>item.trim()).filter(Boolean);return[...new Set([...checked,...custom])];}
function renderGeneralOperationEditors(workspace,root){
  root.replaceChildren();
  const furniture=document.createElement("label"),furnitureInput=document.createElement("input");furniture.textContent="Unidades del mueble terminado (no piezas BOM)";furnitureInput.id="general-furniture-quantity";furnitureInput.type="number";furnitureInput.min="1";furnitureInput.step="1";furnitureInput.value=workspace.furnitureQuantity?.value??"";furniture.append(furnitureInput);
  const currency=document.createElement("label"),currencySelect=document.createElement("select");currency.textContent="Moneda explícita para el histórico";currencySelect.id="general-review-currency";[["","Sin seleccionar"],["EUR","EUR"],["USD","USD"],["GBP","GBP"]].forEach(([value,label])=>{const option=document.createElement("option");option.value=value;option.textContent=label;option.selected=value===workspace.currency;currencySelect.append(option);});currency.append(currencySelect);root.append(furniture,currency);appendGeneralScopeControls(root,workspace);
  const sources=document.createElement("fieldset"),legend=document.createElement("legend");sources.className="general-source-list";legend.textContent="Componentes de origen";sources.append(legend);workspace.components.forEach((component,index)=>{const label=document.createElement("label"),input=document.createElement("input");input.type="checkbox";input.checked=index===0;input.dataset.generalSource=component.id;label.append(input,document.createTextNode(` ${component.label} · ${component.id}`));sources.append(label);});root.append(sources);
  const results=document.createElement("div");results.className="general-results";results.dataset.generalResults="";if(workspace.components[0])appendGeneralResultEditor(results,workspace.components[0]);root.append(results);const add=document.createElement("button");add.type="button";add.className="button";add.textContent="Añadir componente resultante";add.addEventListener("click",()=>appendGeneralResultEditor(results,{}));root.append(add);
}

async function createManualGeneralProposal(){try{const label=$("#general-manual-label").value,kind=$("#general-manual-kind").value,role=$("#general-manual-role").value,reason=$("#general-manual-reason").value,proposal=buildManualGeneralProposal({drawingId:state.drawing?.drawing_id??state.generalWorkspace?.drawingId,ledgerRevision:state.snapshot?.candidate_revision??state.generalWorkspace?.ledgerRevision,label,kind,role,reason});await api.createGeneralProposal(state.runId,{mode:"manual",base_proposal_revision:state.generalWorkspace?.proposalRevision??0,proposal});text($("#review-message"),"Propuesta manual opcional creada con medidas desconocidas. Puedes corregirla o lanzar la verificación automática.");await refreshRun();}catch(error){text($("#review-message"),error.message);}}

function setGeneralManualCorrectionVisible(visible){toggleHidden($("#general-review-operations"),!visible);toggleHidden($("#review-form > .form-grid"),!visible);toggleHidden($("#review-submit"),!visible);}
async function requestGeneralAutoReview(){if(!state.documentId)return;const button=$("#general-auto-review"),prior=button?.textContent;if(button){button.disabled=true;button.textContent="Iniciando nueva ejecución…";}try{text($("#review-message"),"Se inicia otra ejecución durable; el snapshot actual permanece consultable hasta que termine.");await startRunForDocument({documentId:state.documentId,mode:"live",inputKind:"general_furniture",runOptions:generalRunOptions("live")});}catch(error){text($("#review-message"),error.message);}finally{if(button){button.disabled=false;button.textContent=prior;}}}

function renderGeneralFurniture() {
  const workspace=state.generalWorkspace,derived=state.generalDerived,components=derived?.construction?.pieces.length?derived.construction.pieces.map((piece)=>({id:piece.componentId,pieceId:piece.pieceId,label:piece.label,kind:piece.role,role:piece.role,dimensions:{length:piece.length,width:piece.width,thickness:piece.thickness},quantity:piece.quantity,geometry:piece.geometry,details:derived.construction.details.filter((item)=>piece.detailIds.includes(item.id)),sourceRefs:piece.sourceRefs,sheetIds:piece.sheetIds,constructionPiece:true})):derived?.bom.length?derived.bom.map((row)=>({id:row.componentId,label:row.label??row.componentId,kind:row.role??"pieza",role:row.role,dimensions:{length:row.length,width:row.width,thickness:row.thickness},quantity:row.quantity,material:row.material,finish:row.finish,bomRow:row})):workspace.components;
  text($("#review-stage > .eyebrow"),"Revisión automática"); text($("#input-kind-label"),"Entrada: mueble general · revisión visual automática"); text($("#parts-title"),"Propuesta de construcción · lista de piezas"); text($("#parts-summary"),`${components.length} ${components.length===1?"pieza":"piezas"} · escenario ${workspace.constructionScenarioId??"base"}`); text($("#scenario-status"),workspace.reviewerKind==="machine"?`Coherencia ${({accepted:"aceptada",incomplete:"incompleta",conflict:"en conflicto",abstained:"no evaluada por abstención"})[workspace.autoReviewStatus]??"sin estado"}`:generalStatusLabel(workspace.status));
  const constructionSummary=$("#general-construction-summary"),estimated=components.flatMap((item)=>Object.values(item.dimensions??{})).filter((item)=>item?.state==="estimated"&&item?.value!=null).length;constructionSummary.hidden=!components.length;constructionSummary.replaceChildren();if(components.length){const line=document.createElement("p");line.textContent=`${derived?.construction?.summary.label??"Propuesta provisional"}: ${components.length} tipos de pieza · ${estimated} cotas estimadas aceptadas. Las cifras con ≈ incluyen rango y fundamento en el inspector.`;constructionSummary.append(line);}
  const impact=$("#general-impact-decisions"),impactList=$("#general-impact-decisions > div"),decisions=derived?.construction?.topDecisions.length?derived.construction.topDecisions:[...workspace.constructionDecisions].sort((a,b)=>({high:0,medium:1,low:2}[a.impact]??3)-({high:0,medium:1,low:2}[b.impact]??3)).slice(0,3);impact.hidden=!decisions.length;impactList.replaceChildren();decisions.forEach((decision)=>{const card=document.createElement("article");card.className="impact-decision";const title=document.createElement("b"),copy=document.createElement("p");title.textContent=`${({high:"Impacto alto",medium:"Impacto medio",low:"Impacto bajo"})[decision.impact]??"Decisión"} · ${decision.summary}`;copy.textContent=decision.rationale;card.append(title,copy);if(decision.alternatives.length){const alternatives=document.createElement("small");alternatives.textContent=`Alternativas consideradas: ${decision.alternatives.join(" · ")}`;card.append(alternatives);}impactList.append(card);});
  $("#parts-head").innerHTML="<tr><th>Componente</th><th>Tipo</th><th>Cant.</th><th>Largo</th><th>Ancho</th><th>Grosor</th><th>Desconocidos</th></tr>";
  const body=$("#parts-body"); body.replaceChildren();
  components.forEach((component)=>{const row=document.createElement("tr");row.dataset.componentId=component.id;row.tabIndex=0;const values=[component.label,component.kind,component.constructionPiece?generalQuantityText(component.quantity):generalFieldValue(component.quantity),generalDimensionText(component.dimensions.length),generalDimensionText(component.dimensions.width),generalDimensionText(component.dimensions.thickness),generalUnknownSummary(component)];values.forEach((value,index)=>{const cell=document.createElement("td");cell.textContent=value;if(index===2&&component.constructionPiece){cell.dataset.origin=component.quantity.state;cell.title=component.quantity.explanation??"";}if(index>=3&&index<=5){const dimension=[component.dimensions.length,component.dimensions.width,component.dimensions.thickness][index-3],presentation=generalDimensionPresentation(dimension);cell.dataset.origin=presentation.state;cell.title=[presentation.explanation,presentation.method&&`Método: ${presentation.method}`].filter(Boolean).join(" · ");}if(index>1&&(value.startsWith("Desconocid")||index===6&&value!=="Ninguno"))cell.classList.add("unknown");row.append(cell);});row.addEventListener("click",()=>{state.selected={type:"general",id:component.id};renderEvidence(component);});body.append(row);});
  if(!components.length){const row=document.createElement("tr"),cell=document.createElement("td");row.className="empty-row";cell.colSpan=7;cell.textContent="La propuesta constructiva no contiene piezas utilizables; el plano fuente y los avisos siguen disponibles.";row.append(cell);body.append(row);}
  const options=$("#scenario-options"); options.replaceChildren(); const legend=document.createElement("legend");legend.textContent="Revisión visual automática de hipótesis";options.append(legend);const provenance=workspace.machineProvenance,autoStatus=({accepted:"coherencia aceptada",incomplete:"coherencia incompleta",conflict:"coherencia en conflicto",abstained:"abstención"})[workspace.autoReviewStatus]??"sin estado publicado",reviewRelation=({separate_model:"modelo revisor separado",self_review:"auto-revisión del mismo modelo"})[provenance?.review_relation]??"relación entre modelos no publicada",summary=emptyParagraph(workspace.reviewerKind==="machine"?`Revisión de máquina · ${autoStatus} · ${provenance?.model??workspace.reviewerName??"modelo configurado"} · ${reviewRelation} · política ${provenance?.policy_version??"no publicada"}. No confirma la hipótesis como hecho.`:`La revisión automática no publicó un resultado. Las incógnitas permanecen visibles y no bloquean el plano fuente.`);options.append(summary);workspace.autoChecks.forEach((check)=>{const item=document.createElement("p");item.textContent=`Comprobación de coherencia (${check.method==="model_visual"?"modelo visual":"determinista"}): ${check.summary??check.id??check.kind} · ${check.outcome??"sin resultado"}`;options.append(item);});const actions=document.createElement("div");actions.className="library-actions";const retry=document.createElement("button");retry.type="button";retry.id="general-auto-review";retry.className="button button--primary";retry.textContent="Nueva ejecución con auto-revisión";retry.disabled=!state.documentId;retry.addEventListener("click",requestGeneralAutoReview);const advanced=document.createElement("button");advanced.type="button";advanced.className="button";advanced.textContent="Corrección humana avanzada";advanced.setAttribute("aria-expanded","false");advanced.addEventListener("click",()=>{const visible=advanced.getAttribute("aria-expanded")!=="true";advanced.setAttribute("aria-expanded",String(visible));advanced.textContent=visible?"Ocultar corrección humana":"Corrección humana avanzada";setGeneralManualCorrectionVisible(visible);});actions.append(retry,advanced);options.append(actions);
  const controls=$("#general-operation-components");if(workspace.components.length)renderGeneralOperationEditors(workspace,controls);else{controls.replaceChildren();const manual=document.createElement("fieldset");manual.className="general-manual-proposal";const title=document.createElement("legend");title.textContent="Crear propuesta manual sin inventar medidas";manual.append(title);[["general-manual-label","Nombre del componente","text",""],["general-manual-kind","Tipo","text","panel"],["general-manual-role","Rol","text","unknown"],["general-manual-reason","Motivo técnico","text",""]].forEach(([id,labelText,type,value])=>{const label=document.createElement("label"),input=document.createElement("input");label.textContent=labelText;input.id=id;input.type=type;input.value=value;label.append(input);manual.append(label);});const create=document.createElement("button");create.type="button";create.className="button button--primary";create.textContent="Crear propuesta manual";create.addEventListener("click",createManualGeneralProposal);manual.append(create);controls.append(manual);}
  setGeneralManualCorrectionVisible(false); toggleHidden($("#legacy-review-fields"),true); toggleHidden($("#review-material").closest("label"),true); toggleHidden($("#review-finish").closest("label"),true); $("#review-thickness").required=false; $("#review-submit").disabled=!workspace.components.length;text($("#review-message"),workspace.status==="reviewed_incomplete"?"El modelo se abstuvo en los campos sin respaldo suficiente. BOM, esquema y descargas conservan esas incógnitas; la corrección humana es opcional.":"La revisión automática publicó el resultado de coherencia actual. La corrección humana sigue disponible como opción avanzada.");
  text($("#revision-label"),Number.isInteger(workspace.proposalRevision)?`Propuesta ${workspace.proposalRevision}`:"Propuesta pendiente");
  const derivedStatus=$("#general-derived-status");toggleHidden(derivedStatus,!derived);if(derived){derivedStatus.replaceChildren(document.createTextNode(`${derived.bom.length} filas BOM · ${derived.artifacts.filter((item)=>item.status==="incomplete").length} artefactos incompletos · base de coste ${generalStatusLabel(derived.costBasis.status)}. `));derived.artifacts.forEach((artifact)=>{const link=document.createElement("a");link.className="button";link.href=api.generalArtifactUrl(state.runId,artifact.id,derived.proposalRevision,derived.reviewRevision);link.download=artifact.filename??"";link.textContent=`${generalArtifactLabel(artifact.kind)} · ${generalStatusLabel(artifact.status)}`;derivedStatus.append(link);});}
  $("#integral-controls").hidden=false; const exportActions=$(".export-actions"); if(exportActions&&!$("#general-export-actions",exportActions))exportActions.append($("#general-export-actions")); $("#general-export-actions").hidden=false; $$('[data-export="bom_csv"],[data-export="bom_json"]').forEach((button)=>button.disabled=!derived?.bom.length);
  unlock("parts-stage");unlock("review-stage");
}

function renderPartsAndReview() {
  text($("#review-stage > .eyebrow"),"Decisión humana");
  toggleHidden($("#review-form > .form-grid"),false);toggleHidden($("#review-submit"),false);
  toggleHidden($("#review-material").closest("label"),false); toggleHidden($("#review-finish").closest("label"),false);
  if(state.generalWorkspace?.isGeneral)return renderGeneralFurniture();
  toggleHidden($("#general-review-operations"),true); toggleHidden($("#general-derived-status"),true);
  if(state.tableWorkspace?.isTable)return renderTableAndReview();
  if(state.partsWorkspace?.isPartsOnly)return renderSeparatedPartsAndReview();
  $("#parts-head").innerHTML="<tr><th>Pieza</th><th>Origen</th><th>Cant.</th><th>Largo</th><th>Ancho</th><th>Grosor</th></tr>";
  toggleHidden($("#legacy-review-fields"),false); $("#review-thickness").required=true; $("#part-decisions").replaceChildren(); text($("#input-kind-label"),"Entrada: vistas montadas legacy");
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
    const fieldNames = [null, null, "quantity", "length_mm", "width_mm", "thickness_mm"];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      const valueText = index >= 2 ? (index === 2 ? (value ?? "Desconocida") : formatMeasurement(value, "mm")) : value;
      cell.textContent = valueText;
      const fieldState = component.field_states?.[fieldNames[index]];
      if (fieldState) {
        const source = document.createElement("small"); source.className = "cell-origin"; source.dataset.origin = fieldOrigin(fieldState); source.textContent = sourceLabel(fieldOrigin(fieldState)); cell.append(source);
      }
      if (value === null || value === undefined) cell.className = "unknown";
      if (index === 1) cell.dataset.origin = origin;
      row.append(cell);
    });
    row.addEventListener("click", () => selectComponent(component));
    row.addEventListener("keydown", (event) => { if (event.key === "Enter") selectComponent(component); });
    body.append(row);
  });
  text($("#scenario-status"), state.snapshot?.result?.pieces?.length ? "Resultado revisado" : (scenarios.length ? "Hipótesis pendiente" : "Sin propuesta respaldada"));
  const options = $("#scenario-options"); options.replaceChildren();
  const legend = document.createElement("legend"); legend.textContent = "Escenario respaldado"; options.append(legend);
  scenarios.forEach((scenario, index) => {
    const label = document.createElement("label"); label.className = "scenario-option";
    const input = document.createElement("input"); input.type = "radio"; input.name = "scenario"; input.value = scenario.id; input.checked = scenario.id === (state.snapshot.preview_scenario_id ?? state.snapshot.result?.review?.selected_scenario_id ?? scenarios[0]?.id);
    input.addEventListener("change", () => { state.snapshot.preview_scenario_id = scenario.id; renderPartsAndReview(); });
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
  const gaps = state.eventLedger?.gaps() ?? [];
  text($("#trace-gap-status"), gaps.length ? `Historial incompleto: faltan ${gaps.map((gap) => `${gap.after + 1}–${gap.before - 1}`).join(", ")}. Se volverá a consultar.` : events.length ? "Historial completo para las secuencias recibidas." : "");
  if (!events.length) { const item = document.createElement("li"); item.className = "empty-copy"; item.textContent = "No hay eventos todavía."; root.append(item); return; }
  events.forEach((event) => {
    const item = document.createElement("li");
    const title = document.createElement("b"); title.textContent = eventLabel(event);
    const summary = document.createElement("span"); summary.textContent = event.data?.summary ?? event.data?.reason_code ?? `Secuencia ${event.sequence}`;
    const timestamp = eventTimestamp(event); const time = document.createElement("time"); time.dateTime = timestamp ?? ""; time.textContent = timestamp ? new Date(timestamp).toLocaleTimeString("es-ES") : `Evento ${event.sequence}`;
    item.append(title, summary, time); root.append(item);
  });
  $("#trace-export").disabled = false;
}

async function refreshTraceHistory(attempts = 1) {
  if (!state.runId) return;
  const runId=state.runId; if (!state.eventLedger) state.eventLedger = createEventLedger(runId);
  const ledger=state.eventLedger, body = await api.getEventHistory(runId); if(state.runId!==runId||state.eventLedger!==ledger)return;
  parseEventStream(body).forEach((event) => ledger.append(event));
  renderTrace();
  if(attempts>1&&ledger.gaps().length){await new Promise((resolve)=>setTimeout(resolve,250));if(state.runId===runId&&state.eventLedger===ledger)await refreshTraceHistory(attempts-1);}
}

async function refreshRun() {
  if (!state.runId) return;
  const requestedRun=state.runId, token=runFence.issue(requestedRun);
  const snapshot=normaliseRunPayload(await api.getRun(requestedRun));
  if (!runFence.isCurrent(token,state.runId)) return;
  state.snapshot = snapshot;
  state.partsWorkspace = normalisePartsWorkspace(snapshot);
  state.tableWorkspace = normaliseTableWorkspace(snapshot);
  state.generalWorkspace=null; state.generalDerived=null;
  state.tableDrawings=null; showSourceArtifact(); updateArtifactTabs();
  state.documentId = state.snapshot.document_id ?? state.snapshot.document?.document_id ?? state.documentId;
  if(state.documentId&&!state.documentIngestion){const provenance=$("#document-provenance");text(provenance,"Documento restaurado · fuente persistida en servidor");provenance.title="La ejecución restaurada conserva el documento fuente en el servidor; abre la vista Fuente para inspeccionarlo.";}
  if (state.documentId) $("#original-preview").src = state.documentIngestion?.previewUrl ? api.resourceUrl(state.documentIngestion.previewUrl) : api.documentPreviewUrl(state.documentId);
  const status = snapshotStatusPresentation(state.snapshot);
  text($("#upload-status"), status.label); setMessage(status.message, state.snapshot.state === "failed");
  text($("#run-mode-label"), executionModeLabel(state.snapshot.mode));
  const replay=presentReplaySource(state.snapshot),replaySource=$("#replay-source"),replayText=replay.available?`${replay.summary} · ${replay.detail}`:""; toggleHidden(replaySource,!replay.available); text(replaySource,replayText); replaySource.title=replayText;
  try { const drawing=await api.getDrawing(requestedRun); if(!runFence.isCurrent(token,state.runId))return; state.drawing=drawing; renderDrawing(); } catch (error) { if(!runFence.isCurrent(token,state.runId))return; if (!(error instanceof ApiError) || ![404,409].includes(error.status)) throw error; }
  try { const ledger=await api.getLedger(requestedRun); if(!runFence.isCurrent(token,state.runId))return; state.ledger=ledger; } catch (error) { if(!runFence.isCurrent(token,state.runId))return; if (!(error instanceof ApiError) || ![404,409].includes(error.status)) throw error; }
  if(snapshot.input_kind==="general_furniture"){
    let general;
    try{general=await api.getGeneralFurniture(requestedRun);}catch(error){if(!(error instanceof ApiError)||error.status!==404)throw error;general={run_id:requestedRun,status:"reviewed_incomplete",proposal_revision:null,review_revision:0,draft:{drawing_id:state.drawing?.drawing_id??snapshot.document_id,ledger_revision:state.ledger?.ledger_revision??state.ledger?.revision??"pending",components:[]},automatic_review_unavailable:true};} if(!runFence.isCurrent(token,state.runId))return;
    state.generalWorkspace=normaliseGeneralWorkspace(general);
    const machineStatus=generalMachineStatusPresentation(state.generalWorkspace);if(machineStatus){text($("#upload-status"),machineStatus.label);setMessage(machineStatus.message);}
    if(Number.isInteger(state.generalWorkspace.proposalRevision)&&state.generalWorkspace.reviewRevision>0){try{state.generalDerived=presentGeneralDerived(await api.getGeneralDerived(requestedRun,state.generalWorkspace.proposalRevision,state.generalWorkspace.reviewRevision));}catch(error){if(!(error instanceof ApiError)||![404,409].includes(error.status))throw error;}}
  }
  renderPartsAndReview(); updateArtifactTabs();
  if(state.tableWorkspace.isTable&&Number.isInteger(state.snapshot.result_revision)){try{const raw=await api.getTableDrawings(requestedRun,state.snapshot.result_revision); if(!runFence.isCurrent(token,state.runId))return; state.tableDrawings=normaliseTableDrawingManifest(raw);}catch(error){if(!runFence.isCurrent(token,state.runId))return;if(!(error instanceof ApiError)||![404,409].includes(error.status))throw error;}}
  await loadRevisionContext();
  if(!runFence.isCurrent(token,state.runId))return;
  if (state.activeView === "3d") await loadScene();
  const scenarioReady=Boolean(state.generalWorkspace?.isGeneral&&state.generalWorkspace.reviewerKind==="machine"&&Number.isInteger(state.generalWorkspace.proposalRevision)&&state.generalWorkspace.reviewRevision>0),confirmedDetails=$("#historical-confirmed-details"),confirmedSummary=$("#historical-confirmed-details > summary");toggleHidden($("#historical-scenarios"),!scenarioReady);$("#historical-scenarios-button").disabled=!scenarioReady;confirmedDetails.open=!scenarioReady;confirmedSummary.hidden=!scenarioReady;
  toggleHidden($("#table-cost-scope"),!state.tableWorkspace.isTable); text($("#estimate-button"),state.tableWorkspace.isTable?"Calcular costes de mesa":"Calcular estimación");
  if(state.tableWorkspace.isTable){toggleHidden($("#history-estimate-controls"),true);resetEstimateUi(); $("#table-component-material-tariffs").replaceChildren(emptyParagraph("Cargando componentes…")); try{const catalog=await api.getTableCostCatalog(); if(!runFence.isCurrent(token,state.runId))return; renderTableCostCatalog(catalog);}catch(error){if(!runFence.isCurrent(token,state.runId))return;text($("#estimate-lines"),error.message);} try{const costs=await api.getTableCosts(requestedRun,state.snapshot.result_revision); if(!runFence.isCurrent(token,state.runId))return;renderTableCosts(costs);}catch(error){if(!runFence.isCurrent(token,state.runId))return;if(!(error instanceof ApiError)||![404,409].includes(error.status))throw error;} $("#estimate-button").disabled=state.snapshot.result?.state!=="completed"||state.tableWorkspace.evaluated?.state!=="completed"; configureExportActions(); unlock("estimate-stage");}
  else if(state.generalWorkspace?.isGeneral){toggleHidden($("#history-estimate-controls"),false);resetEstimateUi();const target=state.generalDerived?.historicalTarget,scopeReady=Boolean(target?.required_cost_scope?.length||target?.required_hours_scope?.length),ready=Boolean(target?.currency&&scopeReady);$("#estimate-button").disabled=!ready;text($("#estimate-button"),"Estimar desde histórico confirmado");text($("#estimate-uncertainty"),ready?`Base confirmada ${target.basis_revision} · moneda ${target.currency} · alcance de coste ${target.required_cost_scope.join(", ")||"ninguno"} · alcance de horas ${target.required_hours_scope.join(", ")||"ninguno"}.`:`El histórico confirmado requiere moneda y alcance humanos. Los escenarios condicionales automáticos se muestran por separado.`);if(scenarioReady)await loadHistoricalScenarios();if(ready)await loadHistoricalComparables();unlock("estimate-stage");}
  else {toggleHidden($("#history-estimate-controls"),true);if (state.snapshot.estimate) renderEstimate(state.snapshot.estimate); else resetEstimateUi(); if (["completed","needs_review"].includes(state.snapshot.state)) { await loadComparables(requestedRun,state.snapshot.result_revision); if(!runFence.isCurrent(token,state.runId))return; unlock("estimate-stage"); }}
}

async function loadRevisionContext() {
  if (!state.runId) return;
  sceneFence.invalidate();
  const runId=state.runId, revision = state.snapshot?.result_revision, identity=`${runId}:${revision}`, token=contextFence.issue(identity);
  try {
    const raw = await api.getRevisions(runId); if(!contextFence.isCurrent(token,`${state.runId}:${state.snapshot?.result_revision}`))return; const revisions = raw.revisions ?? raw.items ?? raw ?? [];
    const root = $("#revisions-list"); root.replaceChildren();
    revisions.forEach((item) => { const card=document.createElement("div"); card.className="detail-item"; const title=document.createElement("b"); title.textContent=`Revisión ${item.result_revision ?? item.revision ?? "—"}`; const detail=document.createElement("span"); detail.textContent=`${item.review?.reviewer_name ?? "Sistema"} · ${item.selected_table_program_id??item.review?.selected_assembly_candidate_id??item.review?.selected_scenario_id??item.state??"sin propuesta seleccionada"}`; card.append(title,detail); root.append(card); });
    if (!revisions.length) root.append(emptyParagraph("Sin revisiones registradas."));
  } catch { /* endpoint aditivo: el resto del visor sigue operativo */ }
  try { const library=await api.getLibrary(); if(!contextFence.isCurrent(token,`${state.runId}:${state.snapshot?.result_revision}`))return; renderLibraryEntries(library); } catch { /* biblioteca aditiva */ }
  if (Number.isInteger(revision)) {
    try { const explanations=await api.getExplanations(runId, revision); if(!contextFence.isCurrent(token,`${state.runId}:${state.snapshot?.result_revision}`))return; state.explanations = explanations; } catch { if(contextFence.isCurrent(token,`${state.runId}:${state.snapshot?.result_revision}`))state.explanations = null; }
    $("#save-library").disabled = false; $("#find-similar").disabled = false;
  } else { state.explanations = null; $("#save-library").disabled = true; $("#find-similar").disabled = true; }
  state.scene = null;
  toggleHidden($("#scene-premises"),true); $("#scene-premises-list").replaceChildren(); text($("#scene-context"),"2D fuente · sin reconstrucción cargada");
  sceneViewer?.setScene({ state: "unavailable", objects: [], warnings: ["Esperando reconstrucción de la revisión actual."] });
}

async function loadComparables(requestedRun=state.runId, requestedRevision=state.snapshot?.result_revision) {
  try {
    const response = await api.getComparables(requestedRun); if(state.runId!==requestedRun||state.snapshot?.result_revision!==requestedRevision)return; const items = response.comparables ?? response.items ?? response ?? [];
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
    $("#estimate-button").disabled = state.snapshot?.result?.state !== "completed";
  } catch (error) { text($("#comparables-list"), error.message); }
}

async function loadHistoricalComparables(){const target=state.generalDerived?.historicalTarget;if(!target)return null;const {retrievalMethod,includeSynthetic}=historicalRetrievalOptions(),raw=await api.getHistoricalComparables({target,limit:5,retrieval_method:retrievalMethod,include_synthetic:includeSynthetic}),result=presentHistoricalComparables(raw),root=$("#comparables-list");text($("#history-retrieval-note"),`${includeSynthetic?"Registros empresariales, fuentes públicas y fixtures sintéticos":"Registros empresariales y fuentes públicas; sin fixtures sintéticos"} · ${result.methodLabel}${result.embeddingLabel?` · ${result.embeddingLabel}`:""}.`);root.replaceChildren();result.items.forEach((item)=>{const card=document.createElement("div");card.className="comparable";const title=document.createElement("b"),method=document.createElement("small"),difference=document.createElement("small");title.textContent=item.project_id??item.record_id??"Proyecto histórico";method.textContent=`${item.provenanceLabel} · ${result.methodLabel} · puntuación ${Number(item.score).toFixed(3)}`;difference.textContent=item.differences.join(" · ")||"Sin diferencias publicadas";card.append(title,method,difference);root.append(card);});if(!result.items.length)root.append(emptyParagraph(includeSynthetic?"No hay registros empresariales, fuentes públicas ni fixtures comparables para esta base.":"No hay registros empresariales ni fuentes públicas comparables. Activa los sintéticos solo para una prueba explícita."));return result;}

function renderHistoricalScenarios(raw){const result=presentProvisionalScenarios(raw),root=$("#historical-scenarios-list");text($("#historical-scenarios-note"),`${result.labelText} · ${result.statusLabel}. Los fixtures sintéticos quedan excluidos.`);root.replaceChildren();result.assumptions.forEach((item)=>root.append(emptyParagraph(`Supuesto global (${item.state}): ${item.displayLabel} [${item.code}] — ${item.displayDetail}`)));result.scenarios.forEach((item)=>{const card=document.createElement("article"),title=document.createElement("b"),source=document.createElement("small"),condition=document.createElement("p"),metrics=document.createElement("div"),cost=document.createElement("p"),costValue=document.createElement("strong"),costDetail=document.createElement("span"),hours=document.createElement("p"),hoursValue=document.createElement("strong"),hoursDetail=document.createElement("span"),details=document.createElement("div");card.className="scenario-estimate-card";title.textContent=`${item.labelText} · comparable ${item.comparable_id}`;source.textContent=`Fuente: ${item.provenanceLabel} · fecha efectiva ${item.source_effective_date}`;condition.textContent=`Condición: ${item.conditionLabel}. ${item.scopeLabel}.`;metrics.className="scenario-estimate-metrics";costValue.textContent=item.costLabel;costDetail.textContent=`${item.costRangeLabel} · ${item.costUncertaintyLabel}`;cost.append(costValue,costDetail);hoursValue.textContent=item.hoursLabel;hoursDetail.textContent=`${item.hoursRangeLabel} · ${item.hoursUncertaintyLabel}`;hours.append(hoursValue,hoursDetail);metrics.append(cost,hours);details.className="scenario-estimate-details";item.assumptions.forEach((assumption)=>details.append(emptyParagraph(`Supuesto (${assumption.state}): ${assumption.displayLabel} [${assumption.code}] — ${assumption.displayDetail}`)));item.contributors.forEach((contributor)=>details.append(emptyParagraph(`Fórmula ${contributor.concept_id??contributor.kind??"contribuidor"}: ${contributor.formula??"no publicada"}`)));item.missingData.forEach((missing)=>details.append(emptyParagraph(`Dato ausente: ${missing.label} [${missing.code}]`)));card.append(title,source,condition,metrics,details);root.append(card);});result.missingData.forEach((missing)=>root.append(emptyParagraph(`No estimable: ${missing.label} [${missing.code}]`)));if(!result.scenarios.length&&!result.missingData.length)root.append(emptyParagraph("No hay comparables publicados suficientes para construir escenarios condicionales."));}

async function loadHistoricalScenarios(){const workspace=state.generalWorkspace,button=$("#historical-scenarios-button");if(!state.runId||!Number.isInteger(workspace?.proposalRevision)||!(workspace.reviewRevision>0))return;button.disabled=true;text(button,"Consultando…");try{const method=$("#history-retrieval-method")?.value??"attribute",raw=await api.getHistoricalScenarios({run_id:state.runId,proposal_revision:workspace.proposalRevision,review_revision:workspace.reviewRevision,limit:3,retrieval_method:method});renderHistoricalScenarios(raw);}catch(error){$("#historical-scenarios-list").replaceChildren(emptyParagraph(error.message));text($("#historical-scenarios-note"),"No se sustituyó el escenario por una estimación inventada.");}finally{button.disabled=false;text(button,"Consultar escenarios");}}

function renderHistoricalEstimate(raw){const estimate=presentHistoricalEstimate(raw);text($("#estimate-revision"),`${raw.basis_revision??"Revisión histórica"} · ${estimate.hoursLabel}`);text($("#estimate-total"),estimate.totalLabel);text($("#estimate-uncertainty"),`Coste — ${estimate.costUncertaintyLabel} · ${estimate.costProvenanceLabel} · ${estimate.costBasisLabel} · ${estimate.costScopeLabel} · ${estimate.costDateLabel}\nHoras — ${estimate.hoursUncertaintyLabel} · ${estimate.hoursProvenanceLabel} · ${estimate.hoursBasisLabel} · ${estimate.hoursDateLabel}`);const missing=$("#estimate-missing-data");missing.replaceChildren();estimate.missingData.forEach((item)=>missing.append(emptyParagraph(`Dato pendiente: ${item}`)));const root=$("#estimate-lines");root.replaceChildren();estimate.lines.forEach((item)=>{const row=document.createElement("div");row.className="estimate-line";const detail=document.createElement("span"),title=document.createElement("b"),formula=document.createElement("small"),amount=document.createElement("b");title.textContent=item.concept_id??item.kind??"Contribuidor";formula.textContent=`${item.formula??"Sin fórmula"}${item.missing_data?.length?` · faltan ${item.missing_data.join(", ")}`:""}`;amount.textContent=item.estimated_cost==null?"Coste desconocido":`${item.estimated_cost} ${raw.currency??"EUR"}`;detail.append(title,formula);row.append(detail,amount);root.append(row);});if(!estimate.lines.length)root.append(emptyParagraph("El histórico no permite desglosar una estimación."));}

function renderEstimate(raw) {
  const estimate = presentEstimate(raw); text($("#estimate-revision"), `${estimate.revisionLabel} · Horas ${estimate.hoursLabel}`); text($("#estimate-total"), estimate.totalLabel);
  const root = $("#estimate-lines"); root.replaceChildren();
  estimate.items.forEach((item) => { const row = document.createElement("div"); row.className = "estimate-line"; const left = document.createElement("span"); const name = document.createElement("b"); name.textContent = item.label ?? item.name ?? "Concepto"; const detail = document.createElement("small"); detail.textContent = `${item.quantityLabel} × ${item.rateLabel}`; const explanation = document.createElement("small"); explanation.textContent = item.explanation ?? "Sin explicación adicional"; left.append(name, detail, explanation); const amount = document.createElement("b"); amount.textContent = item.amountLabel; row.append(left, amount); root.append(row); });
  [...estimate.assumptions, ...estimate.exclusions].forEach((value) => { const note = document.createElement("p"); note.className = "estimate-note"; note.textContent = value; root.append(note); });
  $$("[data-export]").forEach((button) => { button.disabled = false; }); unlock("estimate-stage");
}

function renderTableCostCatalog(raw){
  const catalog=normaliseTableCostCatalog(raw); state.tableCostCatalog=catalog;
  text($("#table-material-scope-warning"),""); toggleHidden($("#table-material-scope-warning"),true);
  text($("#table-catalog-provenance"),`${catalog.synthetic?"Catálogo demo":"Catálogo real"} · ${catalog.version??"sin versión"}${catalog.source?` · ${catalog.source}`:""}${catalog.effectiveDate?` · vigente ${catalog.effectiveDate}`:""}`);
  const fillSelect=(selector,tariffs)=>{const select=$(selector);select.replaceChildren();const empty=document.createElement("option");empty.value="";empty.textContent="Sin seleccionar";select.append(empty);tariffs.forEach((tariff)=>{const option=document.createElement("option");option.value=tariff.id;option.textContent=`${tariff.label} · ${tariff.rate} ${tariff.rateUnit}`;select.append(option);});};
  fillSelect("#table-material-tariff",catalog.materials);fillSelect("#table-edge-tariff",catalog.edges);fillSelect("#table-labor-tariff",catalog.labor);fillSelect("#table-finish-tariff",catalog.finishing);
  const componentMaterials=$("#table-component-material-tariffs"); componentMaterials.replaceChildren(); (state.tableWorkspace?.evaluated?.components??[]).forEach((component)=>{const label=document.createElement("label"),name=document.createElement("span"),select=document.createElement("select"),inherited=document.createElement("option"); label.dataset.componentId=component.id; name.textContent=`${TABLE_ROLE_LABELS[component.role]??component.role} · ${component.id}`; inherited.value=""; inherited.textContent="Usar tarifa general"; select.append(inherited); catalog.materials.forEach((tariff)=>{const option=document.createElement("option");option.value=tariff.id;option.textContent=`${tariff.label} · ${tariff.rate} ${tariff.rateUnit}`;select.append(option);});label.append(name,select);componentMaterials.append(label);}); if(!componentMaterials.children.length)componentMaterials.append(emptyParagraph("Sin componentes evaluados."));
  text($("#table-edge-rate"),catalog.edges.length?catalog.edges.map((tariff)=>`${tariff.rate} ${tariff.rateUnit}`).join(" · "):"Tarifa no disponible");
  const operations=$("#table-operation-tariffs"); operations.replaceChildren(); catalog.operations.forEach((tariff)=>{const row=document.createElement("label"),input=document.createElement("input"),hours=document.createElement("input");input.type="checkbox";input.value=tariff.id;hours.type="number";hours.min="0";hours.step="0.25";hours.placeholder="Horas";hours.dataset.operationHours=tariff.id;hours.disabled=true;input.addEventListener("change",()=>{hours.disabled=!input.checked;if(!input.checked)hours.value="";});row.append(input,document.createTextNode(` ${tariff.label} · ${tariff.rate} ${tariff.rateUnit}`),hours);operations.append(row);}); if(!catalog.operations.length)operations.append(emptyParagraph("Sin operaciones disponibles."));
  const exclusions=$("#table-exclusion-controls");exclusions.replaceChildren();[["material","Material"],["edge","Canteado"],["operation","Operaciones"],["labor","Mano de obra"],["finishing","Acabado"]].forEach(([scope,labelText])=>{const row=document.createElement("label"),check=document.createElement("input"),reason=document.createElement("input");check.type="checkbox";check.dataset.exclusionScope=scope;reason.type="text";reason.placeholder="Motivo obligatorio";reason.dataset.exclusionReason=scope;reason.disabled=true;check.addEventListener("change",()=>{reason.disabled=!check.checked;if(!check.checked)reason.value="";});row.append(check,document.createTextNode(` ${labelText} no aplica`),reason);exclusions.append(row);});
}
function renderTableCosts(raw){
  const estimate=presentTableCosts(raw),materialScope=tableMaterialScopeSelection(raw.scope??{},state.tableWorkspace?.evaluated?.components??[],state.tableCostCatalog?.materials??[]); text($("#estimate-revision"),`Revisión ${estimate.revision} · ${estimate.catalogLabel} · Horas ${estimate.hoursLabel}`); text($("#estimate-total"),estimate.totalLabel); const materialSelect=$("#table-material-tariff"); if(materialSelect)materialSelect.value=materialScope.materialTariffId; $$('#table-component-material-tariffs [data-component-id]').forEach((label)=>{const select=$("select",label);if(select)select.value=materialScope.componentMaterialTariffIds[label.dataset.componentId]??"";}); const scopeWarning=$("#table-material-scope-warning"); text(scopeWarning,materialScope.warnings.join(" ")); toggleHidden(scopeWarning,!materialScope.warnings.length); const root=$("#estimate-lines"); root.replaceChildren(); if(estimate.largestContribution){const lead=document.createElement("p"); lead.className="cost-lead"; lead.textContent=`Mayor contribución calculada: ${estimate.largestContribution.label} · ${estimate.largestContribution.amountLabel}`; root.append(lead);} estimate.items.forEach((item)=>{const row=document.createElement("div"); row.className="estimate-line"; const left=document.createElement("span"),title=document.createElement("b"),detail=document.createElement("small"),formula=document.createElement("small"),amount=document.createElement("b"); title.textContent=item.label; detail.textContent=`${item.component_id?`Pieza ${item.component_id} · `:""}${item.quantityLabel} × ${item.rateLabel} · ${item.stateLabel}`; formula.textContent=item.formula; amount.textContent=item.amountLabel; left.append(title,detail,formula); row.append(left,amount); root.append(row);}); const sale=document.createElement("p");sale.className=estimate.complete?"cost-lead":"estimate-note unknown";sale.textContent=estimate.complete?`Precio provisional ${estimate.salePriceLabel} · margen explícito ${estimate.marginLabel}`:"Presupuesto parcial: no se publica precio provisional.";root.append(sale); estimate.warnings.forEach((warning)=>{const note=document.createElement("p"); note.className="estimate-note unknown"; note.textContent=warning; root.append(note);}); $$('[data-export]').forEach((button)=>button.disabled=false);
}

async function estimateTableRevision(){
  const identity=actionIdentity(),token=actionFence.issue(identity); try{const operations=$$('#table-operation-tariffs input[type="checkbox"]:checked').map((input)=>({id:input.value,hours:$(`[data-operation-hours="${CSS.escape(input.value)}"]`)?.value??""})),exclusions=$$('#table-exclusion-controls [data-exclusion-scope]:checked').map((input)=>({scope:input.dataset.exclusionScope,reason:$(`[data-exclusion-reason="${input.dataset.exclusionScope}"]`)?.value??""})),selectedComponentMaterials=Object.fromEntries($$('#table-component-material-tariffs [data-component-id]').map((label)=>[label.dataset.componentId,$("select",label)?.value??""])),componentMaterialTariffIds=componentMaterialOverrides(state.tableWorkspace?.evaluated?.components??[],selectedComponentMaterials,state.tableCostCatalog?.materials??[]),scope=buildTableCostScope({materialTariffId:$("#table-material-tariff").value,componentMaterialTariffIds,edgeScope:$("#table-edge-scope").checked?"all_exposed":"none",edgeTariffId:$("#table-edge-tariff").value,operations,laborTariffId:$("#table-labor-tariff").value,laborHours:$("#table-labor-hours").value,finishTariffId:$("#table-finish-tariff").value,finishQuantity:$("#table-finish-quantity").value,exclusions,marginPercent:$("#table-margin").value}); const estimate=await api.generateTableCosts(state.runId,{result_revision:state.snapshot.result_revision,scope}); if(!actionFence.isCurrent(token,actionIdentity()))return; renderTableCosts(estimate); await refreshTraceHistory();}catch(error){if(actionFence.isCurrent(token,actionIdentity()))setMessage(error.message,true);}
}

function runRequest(documentId, mode, inputKind, table = {}) {
  return {
    document_id: documentId,
    mode,
    ...(inputKind ? { input_kind: inputKind } : {}),
    ...(table.table_profile ? { table_profile: table.table_profile } : {}),
    ...(table.proposal_mode ? { proposal_mode: table.proposal_mode } : {}),
    ...(table.table_template_id ? { table_template_id: table.table_template_id } : {}),
  };
}

async function startRunForDocument({ documentId, mode, inputKind, runOptions = {}, stillCurrent = () => true }) {
  try{state.drawing=await api.getDocumentDrawing(documentId,inputKind);if(!stillCurrent())return;renderDrawing();}
  catch(error){if(!stillCurrent())return;if(inputKind!=="general_furniture"||!(error instanceof ApiError)||error.code!=="normalized_dxf_unavailable")throw error;state.drawing=null;state.activeView="original";showSourceArtifact();toggleHidden($("#drawing-viewer"),true);toggleHidden($("#original-view"),false);unlock("drawing-stage");text($("#scene-context"),"Vista previa fuente · geometría y escala desconocidas");}
  setMessage("Plano disponible. Iniciando análisis…");
  const request=runRequest(documentId,mode,inputKind,runOptions);
  if(mode==="recorded_replay"){
    const availability=await api.getReplayAvailability(request); if(!stillCurrent())return;
    if(availability?.available!==true)throw new ApiError(availability?.message??"No hay una grabación live compatible con este documento y configuración.",{status:409,code:"recorded_replay_unavailable"});
    setMessage("Grabación compatible localizada. Se reproducirá offline sin una inferencia nueva.");
  }
  if(state.config?.run_submission?.jobs===true){const job=await api.createJob(request);if(!stillCurrent())return;setMessage("Plano aceptado. El trabajo queda guardado y puede recuperarse tras recargar.");await followJob(job);}
  else {setMessage("Modo local manual: esta instalación usa la ejecución síncrona compatible.");const runPayload=await api.createRun(documentId,mode,inputKind,runOptions);if(!stillCurrent())return;state.snapshot=normaliseRunPayload(runPayload);state.runId=state.snapshot.id;persistRunId(state.runId,localStorage,location,history);text($("#upload-status"),"En proceso");await refreshRun();await refreshTraceHistory();}
}

async function followJob(initialJob) {
  state.jobAbort?.abort();
  const controller = new AbortController(); state.jobAbort = controller; state.jobId = initialJob.id;
  persistJob(initialJob, localStorage);
  const intervalMs = Number(state.config?.run_submission?.poll_interval_ms) || 500;
  const result = await pollJob(initialJob.id, {
    signal: controller.signal,
    intervalMs,
    getJob: api.getJob,
    onUpdate: async (job) => {
      persistJob({ id: job.id, run_id: job.runId, state: job.state }, localStorage);
      const automatic=$("#upload-form").elements.input_kind.value==="general_furniture"&&$("#upload-form").elements.mode.value==="live",label=automatic&&["queued","running"].includes(job.state)?`Revisión visual automática · ${jobStatusLabel(job)}`:jobStatusLabel(job);text($("#job-status"), `${label} · ${job.id}`);
      text($("#upload-status"), label);
      if (job.runId) {
        if (state.runId !== job.runId) { state.runId = job.runId; state.eventLedger = createEventLedger(job.runId); }
        try { await refreshTraceHistory(); } catch { text($("#trace-gap-status"), "La traza aún no está disponible; se volverá a consultar."); }
      }
    },
  });
  if (controller.signal.aborted) return null;
  state.jobAbort = null;
  if (result.state !== "succeeded" || !result.runId) {
    const error = new ApiError(result.error?.message ?? "El trabajo no terminó correctamente.", { code: result.error?.code ?? result.state, retryable: Boolean(result.error?.retryable) });
    throw error;
  }
  state.runId = result.runId; persistRunId(result.runId, localStorage, location, history);
  await refreshRun(); await refreshTraceHistory(3);
  return result;
}

async function runUpload(event) {
  event.preventDefault(); const file = $("#drawing-file").files[0]; if (!file) return setMessage("Selecciona un plano DXF, DWG o PDF.", true);
  if (file.size > 20 * 1024 * 1024) return setMessage("El archivo supera 20 MiB. Selecciona un plano más pequeño.", true);
  const formData = new FormData(event.currentTarget);
  const mode = formData.get("mode");
  const inputKind=formData.get("input_kind");
  const runOptions=inputKind==="mounted_orthographic_views"?tableRunOptions(mode,formData.get("table_template_id")):inputKind==="general_furniture"?generalRunOptions(mode):{};
  let uploadToken;
  try {
    resetRunUi();
    uploadToken=uploadFence.issue(file);
    setMessage("Guardando el plano…"); text($("#upload-status"), "Cargando");
    const documentRecord = await api.upload(file); if(!uploadFence.isCurrent(uploadToken,file))return; state.documentId = documentRecord.document_id ?? documentRecord.id; const ingestion=renderDocumentIngestion(documentRecord);
    $("#original-preview").src = ingestion.previewUrl ? api.resourceUrl(ingestion.previewUrl) : api.documentPreviewUrl(state.documentId);
    if(ingestion.format==="PDF"){setMessage("Selecciona una página PDF y confirma la escala solo si está documentada. Sin escala se conservará como desconocida.");text($("#upload-status"),"Revisión PDF");return;}
    await startRunForDocument({documentId:state.documentId,mode,inputKind,runOptions,stillCurrent:()=>uploadFence.isCurrent(uploadToken,file)});
  } catch (error) { if(uploadToken&&!uploadFence.isCurrent(uploadToken,file))return; setMessage(error.message, true); text($("#upload-status"), "Error"); }
}

async function normalizePdfPage(event) {
  event.preventDefault(); if(!state.documentId)return;
  const page=Number($("#pdf-page-select").value),rawScale=$("#pdf-mm-per-point").value.trim(),reason=$("#pdf-scale-reason").value.trim();
  if(!Number.isInteger(page)||page<1)return setMessage("Selecciona una página PDF válida.",true);
  if(!reason)return setMessage("Explica por qué se prepara esta página y de dónde procede la escala.",true);
  const mmPerPoint=rawScale===""?null:Number(rawScale); if(mmPerPoint!==null&&(!Number.isFinite(mmPerPoint)||mmPerPoint<=0))return setMessage("La escala debe ser positiva o quedar vacía si es desconocida.",true);
  const identity=`pdf:${state.documentId}:${page}`,token=actionFence.issue(identity); text($("#upload-status"),"Preparando PDF");
  try{const record=await api.normalizePdfPage(state.documentId,page,{...(mmPerPoint===null?{}:{mm_per_pdf_point:mmPerPoint}),...(state.session?.username?{confirmed_by:state.session.username}:{}),reason});if(!actionFence.isCurrent(token,identity))return;state.documentId=record.document_id??record.id;const ingestion=renderDocumentIngestion(record);toggleHidden($("#pdf-page-controls"),true);if(ingestion.previewUrl)$("#original-preview").src=api.resourceUrl(ingestion.previewUrl);const form=$("#upload-form"),inputKind=form.elements.input_kind.value,mode=form.elements.mode.value;if(!canStartDocumentAnalysis(ingestion,{inputKind,mode}))throw new ApiError("La página conserva escala desconocida o no contiene geometría vectorial normalizable. Selecciona mueble general live para revisar visualmente la vista previa sin afirmar medidas.",{status:409,code:"normalized_dxf_unavailable"});const runOptions=inputKind==="mounted_orthographic_views"?tableRunOptions(mode,form.elements.table_template_id.value):inputKind==="general_furniture"?generalRunOptions(mode):{};await startRunForDocument({documentId:state.documentId,mode,inputKind,runOptions,stillCurrent:()=>actionFence.isCurrent(token,identity)});}catch(error){if(actionFence.isCurrent(token,identity)){setMessage(error.message,true);text($("#upload-status"),"Revisión PDF");toggleHidden($("#pdf-page-controls"),false);}}
}

function renderHistoryRecords(raw) {
  const root=$("#history-list"); if(!root)return; root.replaceChildren(); const items=raw.records??raw.items??raw??[];
  const costRecords=items.filter((item)=>item.actual_cost!=null).length,hourRecords=items.filter((item)=>item.manufacturing_hours!=null).length,summary=document.createElement("p");summary.className="field-note";summary.textContent=`${raw.total??items.length} registros en esta procedencia · ${costRecords} con coste o presupuesto · ${hourRecords} con horas publicadas`;root.append(summary);
  items.forEach((item)=>{const presented=presentHistoricalRecord(item),card=document.createElement("div");card.className="detail-item";const title=document.createElement("b"),detail=document.createElement("span"),source=document.createElement("span");title.textContent=item.name??item.project_name??item.project_id??item.record_id??item.id??"Registro histórico";detail.textContent=presented.provenanceLabel;source.textContent=`Fuente: ${item.provenance?.source??"sin fuente"}${item.provenance?.source_date?` · ${item.provenance.source_date}`:""}`;card.append(title,detail,source);root.append(card);}); if(!items.length)root.append(emptyParagraph("No hay registros con esta procedencia."));
}

async function refreshHistoryRecords(){try{const raw=await api.getHistory({origin:$("#history-provenance").value,limit:25,offset:0});renderHistoryRecords(raw);}catch(error){$("#history-list")?.replaceChildren(emptyParagraph(error.message));}}

async function importHistory(event){event.preventDefault();const file=$("#history-file").files[0];if(!file)return text($("#history-import-status"),"Selecciona un CSV. Cada registro debe declarar su origen y su fuente.");try{const raw=await api.importHistory(file,{dryRun:false}),result=presentHistoryImport(raw);text($("#history-import-status"),`${result.summary}${result.errors.length?` · ${result.errors.join(" ")}`:""}`);await refreshHistoryRecords();}catch(error){text($("#history-import-status"),error.message);}}

function tableReviewPayload(scenario, values) {
  const newId=(prefix)=>`${prefix}-${globalThis.crypto?.randomUUID?.()??`${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
  const decisions=$$('.table-decision').flatMap((block)=>{const selected=$("input:checked",block);return selected?[{targetKind:block.dataset.targetKind,targetId:block.dataset.targetId,action:selected.value,reason:values.notes}]:[];});
  const confirmedValues=$$('.table-confirmed-value').flatMap((label)=>{const input=$("input",label);if(!input.value||String(input.value)===String(input.dataset.originalValue??""))return[];return[{targetId:label.dataset.measureId,valueMm:input.value,reason:values.notes,confirmationId:newId("confirmation")}];});
  const observedCorrections=$$('.table-observed-correction').flatMap((label)=>{const input=$("input",label);if(!input.value||String(input.value)===String(input.dataset.originalValue??""))return[];return[{targetId:label.dataset.measureId,valueMm:input.value,reason:values.notes,correctionId:newId("correction")}];});
  const sourceDecisions=$$('.table-source-review').flatMap((block)=>{const selected=$("input:checked",block);return selected?[{warningId:block.dataset.warningId,warningCode:block.dataset.warningCode,action:selected.value,reason:values.notes}]:[];});
  return buildTableReviewPayload(state.snapshot,state.tableWorkspace,{reviewerName:values.reviewer_name,programId:scenario.value,notes:values.notes,decisions,confirmedValues,observedCorrections,sourceDecisions});
}

async function submitReview(event) {
  event.preventDefault(); const general=state.generalWorkspace?.isGeneral,table=state.tableWorkspace?.isTable,parts=state.partsWorkspace?.isPartsOnly; const scenario = general?null:table?$("input[name='table-program']:checked"):$(parts?"input[name='assembly-candidate']:checked":"input[name='scenario']:checked"); if (!general&&!scenario) return;
  const identity=actionIdentity(), token=actionFence.issue(identity);
  try {
    if(general){
      const kind=$("#general-operation-type").value,sourceIds=$$("[data-general-source]:checked").map((input)=>input.dataset.generalSource),reason=$("#review-reason").value.trim(),resultCards=kind==="drop"?[]:$$('[data-general-results] .general-component-editor');
      if((kind==="replace"&&(sourceIds.length!==1||resultCards.length!==1))||(kind==="split"&&(sourceIds.length!==1||resultCards.length<2))||(kind==="merge"&&(sourceIds.length<2||resultCards.length!==1))||(kind==="drop"&&(sourceIds.length!==1||resultCards.length)))throw new TypeError("La cantidad de componentes de origen y resultado no coincide con la operación seleccionada.");
      const sourceComponents=sourceIds.map((id)=>state.generalWorkspace.components.find((item)=>item.id===id)).filter(Boolean),humanRef=`human:${$("#reviewer-name").value.trim()||"review"}`;
      const components=resultCards.map((card)=>{const value=(name)=>$(`[data-general-field="${name}"]`,card)?.value.trim()??"";return buildGeneralReviewedComponent({sourceComponents,resultId:card.dataset.resultId,values:{label:value("label"),kind:value("kind"),role:value("role"),quantity:value("quantity"),length:value("length"),width:value("width"),thickness:value("thickness"),material:value("material"),finish:value("finish")},reason,humanRef});});
      const complete=completeGeneralReviewSnapshot(state.generalWorkspace,{operations:[{kind,sourceComponentIds:sourceIds,resultComponentIds:components.map((item)=>item.id),reason}],components,reason,humanRef});
      const payload=buildGeneralReviewPayload(state.generalWorkspace,{reviewerName:$("#reviewer-name").value,reason,operations:complete.operations,components:complete.components,furnitureQuantity:$("#general-furniture-quantity")?.value??"",currency:$("#general-review-currency")?.value??"",requiredCostScope:generalScopeValues("cost"),requiredHoursScope:generalScopeValues("hours"),humanRef});
      const result=await api.reviewGeneralFurniture(state.runId,payload);if(!actionFence.isCurrent(token,actionIdentity()))return;state.generalWorkspace=normaliseGeneralWorkspace(result);text($("#review-message"),"Componentes guardados en una nueva propuesta versionada.");await refreshRun();await refreshTraceHistory();return;
    }
    const decisions=parts?$$(".allocation-decision").flatMap((block)=>{const inputs=$$("[data-decision-field]",block), current=Object.fromEntries(inputs.map((input)=>[input.dataset.decisionField,input.value])), original=Object.fromEntries(inputs.map((input)=>[input.dataset.decisionField,input.dataset.originalValue??""])), changed=changedReviewDecisionValues(current,original); if(!changed)return[]; return [{use_id:block.dataset.useId,role:block.dataset.role,quantity:changed.quantity??"",length_mm:changed.length??"",width_mm:changed.width??"",thickness_mm:changed.thickness??"",material:$("#review-material").value,finish:$("#review-finish").value,notes:$("#review-reason").value}];}):[];
    const values = {
      scenario_id: scenario.value,
      assembly_candidate_id: scenario.value,
      reviewer_name: $("#reviewer-name").value,
      confirmed_thickness_mm: $("#review-thickness").value,
      material: $("#review-material").value,
      finish: $("#review-finish").value,
      notes: $("#review-reason").value,
      decisions,
    };
    const payload = table?tableReviewPayload(scenario,values):parts?buildAssemblyReviewPayload(state.snapshot,values):buildScenarioReviewPayload(state.snapshot, values);
    const result = await api.review(state.runId, payload); if(!actionFence.isCurrent(token,actionIdentity()))return; state.snapshot = { ...state.snapshot, ...result };
    text($("#review-message"), "Decisión registrada en una nueva revisión."); await refreshRun(); await refreshTraceHistory();
  } catch (error) {
    if(!actionFence.isCurrent(token,actionIdentity()))return;
    text($("#review-message"), error.code === "stale_result_revision" ? "La revisión cambió. Se han recargado los datos antes de sobrescribir." : error.message);
    if (error.code === "stale_result_revision") await refreshRun();
  }
}

function downloadBlob(blob, filename) { const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename.replace(/[^a-z0-9._-]/gi,"_"); document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url); }

async function exportResult(format) {
  if(state.generalDerived&&(format==="bom_csv"||format==="bom_json")){const extension=format.endsWith("csv")?"csv":"json",type=extension==="csv"?"text/csv":"application/json";downloadBlob(new Blob([serialiseGeneralBom(state.generalDerived.bom,extension)],{type}),`vexplorer_${state.runId}_bom.${extension}`);return;}
  const requestedFormat=state.tableWorkspace?.isTable?tableExportFormat(format):format;
  try { const response = await fetch(api.exportUrl(state.runId, requestedFormat)); if (!response.ok) throw new Error("La exportación no está disponible."); downloadBlob(await response.blob(), `vexplorer_${state.runId}.${format}`); } catch (error) { setMessage(error.message, true); }
}

let traceReturnFocus = null;
function toggleTrace(open) {
  const drawer = $("#trace-drawer");
  if (open) traceReturnFocus = document.activeElement;
  drawer.classList.toggle("is-open", open); drawer.setAttribute("aria-hidden", String(!open)); $("#trace-toggle").setAttribute("aria-expanded", String(open)); $("#scrim").hidden = !open;
  if (open) $("#trace-close").focus(); else traceReturnFocus?.focus?.();
}

function setupWorkspaceControls() {
  $$('[data-artifact-view]').forEach((button)=>button.addEventListener("click",()=>activateArtifactView(button.dataset.artifactView,button)));
  $$('[data-panel]').forEach((button)=>button.addEventListener("click",()=>{ $$('[data-panel]').forEach((item)=>item.classList.toggle("is-active",item===button)); $$('[data-panel-content]').forEach((panel)=>panel.classList.toggle("is-active",panel.dataset.panelContent===button.dataset.panel)); }));
  ["entities","texts","dimensions"].forEach((name)=>$(`#toggle-${name}`).addEventListener("change",applyLayerVisibility));
  $("#fit-view").addEventListener("click",fitDrawing); $("#reset-view").addEventListener("click",fitDrawing);
  const zoom=(factor)=>{ if(state.activeArtifact!=="source"){const rect=$("#derived-drawing-canvas").getBoundingClientRect();state.derivedImageViewport=zoomImageViewport(state.derivedImageViewport,1/factor,{x:rect.width/2,y:rect.height/2});applyDerivedImageViewport();return;} if(state.activeView==="3d"){sceneViewer?.zoom(factor); return;} if (!state.viewport) return; state.viewport=zoomViewport(state.viewport,factor,{x:state.viewport.x+state.viewport.width/2,y:state.viewport.y+state.viewport.height/2}); applyViewport(); };
  $("#zoom-in").addEventListener("click",()=>zoom(.8)); $("#zoom-out").addEventListener("click",()=>zoom(1.25));
  const viewport=$("#cad-viewport"); let drag=null;
  new ResizeObserver(()=>{applySvgTextScale();if(state.activeArtifact!=="source")fitDerivedDrawing();}).observe(viewport);
  viewport.addEventListener("wheel",(event)=>{ if(state.activeArtifact!=="source"){event.preventDefault();const rect=$("#derived-drawing-canvas").getBoundingClientRect();state.derivedImageViewport=zoomImageViewport(state.derivedImageViewport,event.deltaY>0?.9:1.12,{x:event.clientX-rect.left,y:event.clientY-rect.top});applyDerivedImageViewport();return;} if (state.activeView==="3d"||state.activeView==="original"||!state.viewport) return; event.preventDefault(); const rect=viewport.getBoundingClientRect(); const anchor={x:state.viewport.x+(event.clientX-rect.left)/rect.width*state.viewport.width,y:state.viewport.y+(event.clientY-rect.top)/rect.height*state.viewport.height}; state.viewport=zoomViewport(state.viewport,event.deltaY>0?1.12:.89,anchor); applyViewport(); },{passive:false});
  viewport.addEventListener("pointerdown",(event)=>{ if(event.target.closest("button,a,select,input"))return; if(state.activeArtifact!=="source"){drag={kind:"derived",x:event.clientX,y:event.clientY,viewport:{...state.derivedImageViewport}};viewport.setPointerCapture(event.pointerId);return;} if (state.activeView==="3d"||state.activeView==="original"||!state.viewport) return; drag={kind:"source",x:event.clientX,y:event.clientY,viewport:{...state.viewport}}; viewport.setPointerCapture(event.pointerId); });
  viewport.addEventListener("pointermove",(event)=>{ if(!drag)return; if(drag.kind==="derived"){state.derivedImageViewport=panImageViewport(drag.viewport,event.clientX-drag.x,event.clientY-drag.y);applyDerivedImageViewport();return;} const rect=viewport.getBoundingClientRect(); state.viewport=panViewport(drag.viewport,-(event.clientX-drag.x)/rect.width*drag.viewport.width,-(event.clientY-drag.y)/rect.height*drag.viewport.height); applyViewport(); });
  viewport.addEventListener("pointerup",()=>{drag=null;}); viewport.addEventListener("pointercancel",()=>{drag=null;});
  $("#derived-drawing-expand").addEventListener("click",toggleDerivedExpanded);
  document.addEventListener("keydown",(event)=>{
    const drawer=$("#trace-drawer");
    if(drawer.classList.contains("is-open")){
      if(event.key==="Escape"){event.preventDefault();toggleTrace(false);return;}
      if(event.key==="Tab"){
        const focusables=$$('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',drawer).filter((node)=>!node.hidden);
        const target=nextFocusTarget(focusables,document.activeElement,event.shiftKey);
        if(target&&(document.activeElement===focusables.at(event.shiftKey?0:-1)||!drawer.contains(document.activeElement))){event.preventDefault();target.focus();}
      }
      return;
    }
    if(event.key==="Escape"&&$("#derived-drawing-view").classList.contains("is-expanded"))toggleDerivedExpanded();
  });
  $("#explode-scene").addEventListener("change",(event)=>sceneViewer?.setExploded(event.target.checked));
}

function updateTableRunControls() {
  const form=$("#upload-form"), inputKind=form.elements.input_kind.value, mode=form.elements.mode.value;
  toggleHidden($("#table-template-field"),inputKind!=="mounted_orthographic_views"||mode!=="geometry_only");
  if(!state.runId)text($("#input-kind-label"),({general_furniture:"Entrada: mueble general",mounted_orthographic_views:"Entrada: mesa · vistas montadas",separated_part_views:"Entrada: piezas separadas",mounted_views_legacy:"Entrada: vistas montadas legacy"})[inputKind]??"Entrada pendiente");
}

function renderLibraryResults(raw, mode) {
  const root=$("#library-list"); root.replaceChildren(); const items=raw.matches??raw.items??raw.groups??raw??[];
  items.forEach((item)=>{ const candidate=state.libraryItems.get(item.library_item_id); const card=document.createElement("div"); card.className="detail-item"; const title=document.createElement("b"); title.textContent=candidate?.label??item.label??item.name??item.run_id??item.library_item_id??(item.id?`Grupo ${item.id}`:"Elemento de biblioteca"); const detail=document.createElement("span"); const score=Number.isFinite(item.score)?` · puntuación ${item.score.toFixed(3)}`:""; const members=item.member_ids?.length?` · ${item.member_ids.length} miembros`:""; const threshold=Number.isFinite(item.threshold)?` · umbral ${item.threshold.toFixed(2)}`:""; detail.textContent=`${mode === "semantic" ? `Semántico real · ${item.embedding?.model ?? candidate?.embedding?.model ?? "modelo configurado"}` : `Geométrico offline · ${item.descriptor_version ?? item.descriptor?.descriptor_version ?? candidate?.descriptor?.descriptor_version ?? "furniture-v1"}`}${score}${members}${threshold}`; const differences=document.createElement("span"); differences.textContent=(item.differences??[]).map((value)=>typeof value==="string"?value:`${value.field}: ${value.query_value} ↔ ${value.candidate_value}`).join(" · ")||item.explanation||"Sin diferencias documentadas"; card.append(title,detail,differences); const linked=item.member_ids?.map((id)=>state.libraryItems.get(id)).filter(Boolean)??(candidate?[candidate]:[]); if(linked.length){ const links=document.createElement("div"); links.className="library-members"; linked.forEach((entry)=>links.append(libraryRunLink(entry))); card.append(links); } root.append(card); });
  if(!items.length)root.append(emptyParagraph("No hay elementos compatibles en la biblioteca."));
  if(Number.isInteger(raw.excluded_count)&&raw.excluded_count>0)root.append(emptyParagraph(`${raw.excluded_count} elementos de otra versión de descriptor se excluyeron de la comparación.`));
}

function renderLibraryEntries(raw) {
  const items=raw.items??raw??[]; state.libraryItems=new Map(items.map((item)=>[item.id,item])); const root=$("#library-list"); root.replaceChildren();
  items.forEach((item)=>{ const card=document.createElement("div"); card.className="detail-item"; const title=document.createElement("b"); title.textContent=item.label; const descriptor=item.descriptor??{}; const detail=document.createElement("span"); if(descriptor.descriptor_version==="furniture-v2"){const presented=presentDescriptorV2(descriptor); detail.textContent=`Revisión ${item.result_revision} · ${presented.familyLabel} · ${presented.structureLabel} · ${presented.thicknessLabel} · Clasificación ${presented.classificationLabel.toLowerCase()}${presented.unknownLabels.length?` · Desconocidos: ${presented.unknownLabels.join(", ")}`:""}`;} else if(descriptor.descriptor_version==="furniture-v3")detail.textContent=`Revisión ${item.result_revision} · Mesa rectangular · ${descriptor.structure==="side_support_table"?"dos soportes laterales":"cuatro patas"} · ${descriptor.components?.map((component)=>`${TABLE_ROLE_LABELS[component.role]??component.role} × ${component.quantity}`).join(" · ")??"sin componentes"} · Clasificación confirmada`; else detail.textContent=`Revisión ${item.result_revision} · ${descriptor.family??"familia desconocida"} · ${descriptor.descriptor_version??"descriptor sin versión"}`; const embedding=document.createElement("span"); embedding.textContent=item.embedding?`Embedding real: ${item.embedding.model} (${item.embedding.dimensions})`:`Solo descriptor geométrico offline`; card.append(title,detail,embedding); root.append(card); });
  if(!items.length)root.append(emptyParagraph("La biblioteca técnica está vacía."));
  if(Number.isInteger(raw.excluded_count)&&raw.excluded_count>0)root.append(emptyParagraph(`${raw.excluded_count} elementos incompatibles quedaron fuera de este espacio de descriptor.`));
}

function libraryRunLink(item) {
  const link=document.createElement("a"), url=new URL(location.href); url.searchParams.set("run",item.run_id); link.href=url; link.className="library-link";
  const label=document.createElement("span"); label.textContent=item.label; const action=document.createElement("b"); action.textContent=`Abrir rev. ${item.result_revision}`; link.append(label,action); return link;
}

async function estimateCurrentRevision(){ if(state.tableWorkspace?.isTable)return estimateTableRevision(); const identity=actionIdentity(), token=actionFence.issue(identity); try{if(state.generalWorkspace?.isGeneral){const target=state.generalDerived?.historicalTarget;if(!target)throw new TypeError("La revisión general no tiene una base histórica autoritativa.");const {includeSynthetic}=historicalRetrievalOptions(),comparableResult=await loadHistoricalComparables();if(!actionFence.isCurrent(token,actionIdentity()))return;const comparableIds=(comparableResult?.items??[]).map((item)=>item.record_id);const estimate=await api.estimateFromHistory({target,comparable_ids:comparableIds,include_synthetic:includeSynthetic});if(!actionFence.isCurrent(token,actionIdentity()))return;renderHistoricalEstimate(estimate);return;}const estimate=await api.estimate(state.runId,{result_revision:state.snapshot?.result_revision}); if(!actionFence.isCurrent(token,actionIdentity()))return; renderEstimate(estimate); await refreshTraceHistory();}catch(error){if(actionFence.isCurrent(token,actionIdentity()))setMessage(error.message,true);} }
async function saveCurrentToLibrary(){ const identity=actionIdentity(), token=actionFence.issue(identity); try{const label=state.drawing?.drawing_id??`Revisión ${state.snapshot.result_revision}`,descriptor=state.tableWorkspace?.isTable?"furniture-v3":undefined; await api.saveToLibrary(state.runId,{result_revision:state.snapshot.result_revision,label,embedding_mode:$("#similarity-mode").value==="semantic"?"openai":"offline",...(descriptor?{descriptor_version:descriptor}:{})}); if(!actionFence.isCurrent(token,actionIdentity()))return; const library=await api.getLibrary(); if(!actionFence.isCurrent(token,actionIdentity()))return; renderLibraryEntries(library); await refreshTraceHistory(); if(actionFence.isCurrent(token,actionIdentity()))text($("#semantic-note"),"Revisión guardada en la biblioteca técnica.");}catch(error){if(actionFence.isCurrent(token,actionIdentity()))text($("#semantic-note"),error.message);} }
async function findSimilarCurrent(){const identity=actionIdentity(),token=actionFence.issue(identity),mode=$("#similarity-mode").value,descriptor=state.tableWorkspace?.isTable?"furniture-v3":undefined; try{const result=await api.findSimilar(state.runId,{result_revision:state.snapshot.result_revision,mode,limit:6,...(descriptor?{descriptor_version:descriptor}:{})}); if(actionFence.isCurrent(token,actionIdentity()))renderLibraryResults(result,mode);}catch(error){if(actionFence.isCurrent(token,actionIdentity()))$("#library-list").replaceChildren(emptyParagraph(error.message));}}
async function groupCurrentLibrary(){const identity=actionIdentity(),token=actionFence.issue(identity),selected=$("#similarity-mode").value,mode=selected==="semantic"?"semantic":"geometric",threshold=Number($("#group-threshold").value),descriptor=state.tableWorkspace?.isTable?"furniture-v3":undefined; try{const result=await api.groupLibrary({mode,threshold,...(descriptor?{descriptor_version:descriptor}:{})}); if(actionFence.isCurrent(token,actionIdentity()))renderLibraryResults(result,mode);}catch(error){if(actionFence.isCurrent(token,actionIdentity()))$("#library-list").replaceChildren(emptyParagraph(error.message));}}

async function restoreRunReference(runId) {
  const retry=$("#restore-run-retry"), initial=restoredRunRecovery(runId);
  if(initial.discard){clearRunSession(localStorage,location,history);state.runId=null;toggleHidden(retry,true);setMessage("La referencia de ejecución guardada no es válida y se ha descartado.",true);return;}
  state.runId=runId; retry.disabled=true; toggleHidden(retry,true); text($("#upload-status"),"Recuperando");
  let runConfirmed=false;
  try {
    await refreshRun(); runConfirmed=true; await refreshTraceHistory(); toggleHidden(retry,true);
  } catch(error) {
    const recovery=runConfirmed?{discard:false,retry:true}:restoredRunRecovery(runId,error);
    if(recovery.discard){clearRunSession(localStorage,location,history);state.runId=null;toggleHidden(retry,true);text($("#upload-status"),"Listo");setMessage("La ejecución guardada ya no existe en el servidor.",true);return;}
    toggleHidden(retry,false); text($("#upload-status"),"Recuperación pendiente"); setMessage(`No se pudo restaurar la ejecución. La referencia se conserva: ${error.message}`,true);
  } finally { retry.disabled=false; }
}

async function boot() {
  setupWorkspaceControls();
  createHistoryEstimateControls();
  text($("#drawing-empty strong"),"Abre un plano DXF, DWG o PDF");
  if(!$('#history-provenance option[value="published"]')){const published=document.createElement("option");published.value="published";published.textContent="Fuentes públicas publicadas";published.selected=true;$("#history-provenance").insertBefore(published,$('#history-provenance option[value="synthetic"]'));}
  const estimateTotal=$(".estimate-total"),uncertainty=$("#estimate-uncertainty"),missing=$("#estimate-missing-data"); estimateTotal.after(uncertainty,missing);
  const historyList=document.createElement("div");historyList.id="history-list";historyList.className="detail-stack";historyList.append(emptyParagraph("Cargando registros históricos…"));$("#history-import-form").after(historyList);
  $("#upload-form").addEventListener("submit", runUpload); $("#review-form").addEventListener("submit", submitReview);
  $("#pdf-page-controls").addEventListener("submit",normalizePdfPage); $("#history-import-form").addEventListener("submit",importHistory); $("#history-provenance").addEventListener("change",refreshHistoryRecords); [$("#history-retrieval-method"),$("#history-include-synthetic")].forEach((control)=>control.addEventListener("change",async()=>{const target=state.generalDerived?.historicalTarget;if(!target?.currency||!(target.required_cost_scope?.length||target.required_hours_scope?.length))return;try{await loadHistoricalComparables();}catch(error){text($("#history-retrieval-note"),error.message);$("#comparables-list").replaceChildren(emptyParagraph("No se cambió automáticamente a otro método."));}}));
  $("#upload-form").elements.input_kind.addEventListener("change",()=>{$("#upload-form").dataset.userConfigured="true";updateTableRunControls();}); $("#upload-form").elements.mode.addEventListener("change",()=>{$("#upload-form").dataset.userConfigured="true";updateTableRunControls();}); updateTableRunControls();
  $("#drawing-file").addEventListener("change", (event) => text($("#file-name"), event.target.files[0]?.name ?? "Ningún archivo seleccionado"));
  $("#trace-toggle").addEventListener("click", () => toggleTrace(true)); $("#trace-close").addEventListener("click", () => toggleTrace(false)); $("#scrim").addEventListener("click", () => toggleTrace(false));
  $("#estimate-button").addEventListener("click", estimateCurrentRevision);
  $("#historical-scenarios-button").addEventListener("click",loadHistoricalScenarios);
  $$("[data-export]").forEach((button) => button.addEventListener("click", () => exportResult(button.dataset.export)));
  $("#trace-export").addEventListener("click", () => downloadBlob(new Blob([JSON.stringify(state.eventLedger?.events() ?? [], null, 2)], { type: "application/json" }), `vexplorer_${state.runId}_traza.json`));
  $("#save-library").addEventListener("click",saveCurrentToLibrary);
  $("#find-similar").addEventListener("click",findSimilarCurrent);
  $("#group-library").addEventListener("click",groupCurrentLibrary);
  $("#restore-run-retry").addEventListener("click",()=>{if(state.runId)restoreRunReference(state.runId);});
  try { configureModes(await api.getConfig()); $(".signal").classList.add("is-online"); text($("#service-status"), "Servicio disponible"); } catch { configureModes({}); text($("#service-status"), "Servicio sin configuración"); }
  try {
    state.session=await api.getSession();
    const authenticated=state.session.authenticated===true&&Boolean(state.session.username), reviewer=$("#reviewer-name");
    text($("#session-user"),authenticated?`${state.session.username} · identidad del servidor`:"Local · identidad manual");
    if(authenticated){reviewer.value=state.session.username;reviewer.readOnly=true;}
  } catch { text($("#session-user"),"Local · identidad manual"); }
  await refreshHistoryRecords();
  const restoredRunId = restoreRunId(location, localStorage);
  const restoredJob=new URLSearchParams(location.search).has("run")?null:restoreJob(localStorage);
  if (restoredJob) {
    try { await followJob(restoredJob); } catch (error) { setMessage(`No se pudo restaurar el trabajo: ${error.message}`,true); }
  } else if (restoredRunId) {
    await restoreRunReference(restoredRunId);
  }
}

boot();
