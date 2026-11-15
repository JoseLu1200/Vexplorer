import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const ui = await import("../core/ui.js").catch(() => ({}));
const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const css = await readFile(new URL("../styles.css", import.meta.url), "utf8");
const reviewSource = await readFile(new URL("../core/review.js", import.meta.url), "utf8");

function element(dataset = {}) {
  const attributes = new Map();
  const classes = new Set();
  return {
    dataset,
    id: "",
    classList: {
      toggle(name, force) { if (force) classes.add(name); else classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
    getAttribute(name) { return attributes.get(name) ?? null; },
    scrollIntoView(options) { this.scrolled = options; },
  };
}

test("panel navigation exposes the current tool and brings its mobile panel into view", () => {
  assert.equal(typeof ui.activateWorkspacePanel, "function");
  const inspectButton = element({ panel: "inspect" });
  const reviewButton = element({ panel: "review" });
  const inspectPanel = element({ panelContent: "inspect" });
  const reviewPanel = element({ panelContent: "review" });

  const selected = ui.activateWorkspacePanel(
    [inspectButton, reviewButton],
    [inspectPanel, reviewPanel],
    reviewButton,
    { compact: true },
  );

  assert.equal(selected, reviewPanel);
  assert.equal(reviewButton.getAttribute("aria-current"), "page");
  assert.equal(inspectButton.getAttribute("aria-current"), null);
  assert.equal(reviewButton.getAttribute("aria-controls"), reviewPanel.id);
  assert.equal(reviewPanel.getAttribute("aria-hidden"), "false");
  assert.equal(inspectPanel.getAttribute("aria-hidden"), "true");
  assert.deepEqual(reviewPanel.scrolled, { behavior: "smooth", block: "start" });
});

test("pending table reviews do not request derived drawings or costs", () => {
  assert.equal(typeof ui.tableResourcesReady, "function");
  const snapshot = { result_revision: 2, result: { state: "needs_review" } };
  const workspace = { isTable: true, evaluated: null };
  assert.equal(ui.tableResourcesReady(workspace, snapshot), false);
  assert.equal(ui.tableResourcesReady({ ...workspace, evaluated: { state: "needs_review" } }, snapshot), false);
  assert.equal(ui.tableResourcesReady(
    { ...workspace, evaluated: { state: "completed" } },
    { ...snapshot, result: { state: "completed" } },
  ), true);
});

test("public CAD capability hides private history but exposes offline library actions", () => {
  assert.equal(typeof ui.publicFeatureAvailability, "function");
  assert.deepEqual(ui.publicFeatureAvailability({
    environment: "production",
    authenticated: false,
    capabilities: { history: { available: false }, library: { available: true } },
    semantic: { available: false, unavailable_reason: "private_feature_unavailable" },
  }), {
    history: false,
    library: true,
    semantic: false,
    costs: false,
    publicCad: true,
    semanticExplorer: false,
    recent: false,
    sessionLabel: "Acceso público · CAD disponible",
  });
  assert.match(app, /publicFeatureAvailability/);
  assert.match(app, /data-panel="library"/);
  assert.match(app, /if\(state\.features\.library\).*api\.getLibrary/s);
  assert.match(app, /if\(!state\.features\.library\)return/);
});
test("known table diagnostics are readable Spanish while unknown evidence remains available", () => {
  assert.equal(typeof ui.tableDiagnosticLabel, "function");
  assert.equal(ui.tableDiagnosticLabel("profile_measure_unknown:tabletop_thickness"), "Falta la medida requerida: grosor de la tapa.");
  assert.equal(
    ui.tableDiagnosticLabel("Catalog alternatives are explicit hypotheses and are never selected from drawing appearance."),
    "Las alternativas de catálogo son hipótesis explícitas; no se eligen por la apariencia del plano.",
  );
  assert.equal(ui.tableDiagnosticLabel("custom-code:raw"), "custom-code:raw");
  assert.equal(ui.tableDiagnosticLabel("Supports and tabletop use the versioned flush placement rule."), "Los soportes y la tapa usan la regla de colocación enrasada versionada.");
});

test("a pending upload immediately reflects its selected workflow and source preview", () => {
  assert.equal(typeof ui.inputKindLabel, "function");
  assert.equal(ui.inputKindLabel("general_furniture"), "Entrada: mueble general");
  assert.match(app, /text\(\$\("#input-kind-label"\),inputKindLabel\(inputKind\)\)/);
  assert.match(app, /ingestion\.format==="PDF"[^}]*state\.activeView="original"[^}]*drawing-empty/s);
});

test("restored runs replace the pending source badge with honest recovered metadata", () => {
  assert.equal(typeof ui.restoredSourceLabel, "function");
  assert.equal(ui.restoredSourceLabel({ coordinate_unit: "mm" }), "Plano restaurado · unidad mm");
  assert.equal(ui.restoredSourceLabel({ source_unit: "unknown" }), "Plano restaurado · unidad sin resolver");
});

test("restoring a run never posts historical calculations until the user asks",()=>{
  const refreshRun=app.slice(app.indexOf("async function refreshRun()"),app.indexOf("async function loadRevisionContext()"));
  assert.doesNotMatch(refreshRun,/await loadHistoricalScenarios\(\)/);
  assert.doesNotMatch(refreshRun,/await loadHistoricalComparables\(\)/);
  assert.match(app,/#historical-scenarios-button"\)\.addEventListener\("click",loadHistoricalScenarios\)/);
});

test("derived drawings expose separate reading controls and fullscreen semantics",()=>{
  assert.match(html,/id="derived-drawing-zoom-out"[^>]*aria-label="Reducir plano"/);
  assert.match(html,/id="derived-drawing-zoom-in"[^>]*aria-label="Ampliar plano"/);
  assert.match(html,/id="derived-drawing-fit"[^>]*>Encajar</);
  assert.match(html,/id="derived-drawing-pan-left"[^>]*aria-label="Ver zona izquierda del plano"/);
  assert.match(html,/id="derived-drawing-pan-right"[^>]*aria-label="Ver zona derecha del plano"/);
  assert.match(html,/id="derived-drawing-expand"[^>]*>Pantalla completa</);
  assert.match(app,/derived-drawing-zoom-in/);
  assert.match(app,/derived-drawing-fit/);
  assert.match(app,/panDerivedDrawing\("left"\)/);
  assert.match(app,/panImageViewportByDirection/);
});

test("recovery action keeps a readable flex size instead of collapsing word by word",()=>{
  assert.match(html,/class="button"[^>]*id="job-retry"/);
  assert.match(css,/\.navigator__head>\.button\{[^}]*flex\s*:\s*0 0 auto[^}]*white-space\s*:\s*normal/s);
  assert.match(css,/\.navigator\{[^}]*display\s*:\s*grid[^}]*grid-template-columns\s*:\s*minmax\(0,1fr\)/s);
});

test("restored interrupted runs expose checkpoint phase and only the server safe recovery action",()=>{
  assert.match(app,/runRecord\.latest_job/);
  assert.match(app,/presentJobRecovery\(latestJob\)/);
  assert.match(app,/recovery\.safeAction/);
  assert.match(app,/api\.resumeJob\(sourceJobId\)/);
});

test("general review panel reuses resume review instead of proposing a new provider run",()=>{
  assert.match(app,/state\.jobRecovery\?\.safeAction==="resume_review"/);
  assert.match(app,/Reanudar revisión guardada/);
  assert.match(app,/failureReasonCode==="provider_credit_balance_exhausted"\?state\.jobRecovery\.actionLabel:"Reanudar revisión guardada"/);
  assert.match(app,/retryCurrentJob\(\)/);
});

test("dynamic review controls receive stable form names", () => {
  assert.equal(typeof ui.formControlName, "function");
  assert.equal(ui.formControlName("table", "component", "component:top"), "table-component-component-top");
  assert.match(app, /select\.name=formControlName\("table-decision",kind,id\)/);
  assert.match(app, /input\.name=formControlName\("table-correction",measure\.id\)/);
});

test("reset clears provisional 3D controls before a pending document is shown", () => {
  assert.match(app, /toggleHidden\(\$\("#explode-control"\),true\)/);
  assert.match(app, /\$\("#explode-scene"\)\.checked=false/);
  assert.match(app, /sceneViewer\?\.setExploded\(false\)/);
  assert.match(app, /toggleHidden\(\$\("#scene-warning"\),true\)/);
});

test("scripted tabs expose tab semantics and the closed trace drawer is inert", () => {
  assert.match(app, /button\.role="tab"/);
  assert.match(app, /drawer\.inert=!open/);
});

test("saving a reviewed table uses only fields accepted by LibrarySaveRequest", () => {
  assert.equal(typeof ui.librarySavePayload, "function");
  assert.deepEqual(ui.librarySavePayload({ resultRevision: 2, label: "Mesa demo", semantic: false }), {
    result_revision: 2,
    label: "Mesa demo",
    embedding_mode: "offline",
  });
  assert.equal("descriptor_version" in ui.librarySavePayload({ resultRevision: 2, label: "Mesa demo", semantic: false }), false);
  assert.equal(ui.librarySavePayload({ resultRevision: 2, label: "Mesa demo", semantic: true }).embedding_mode,"embeddinggemma2");
});

test("pending table revisions cannot invoke descriptor-backed library actions", () => {
  assert.match(app, /const supportedDescriptor=!state\.generalWorkspace\?\.isGeneral/);
  assert.match(app, /const libraryReady=supportedDescriptor&&\(!state\.tableWorkspace\?\.isTable\|\|tableResourcesReady/);
  assert.match(app, /save-library"\)\.disabled = !libraryReady/);
  assert.match(app, /find-similar"\)\.disabled = !libraryReady/);
});

test("a provisional 3D scene is never labeled as reviewed", () => {
  assert.equal(typeof ui.sceneContextLabel, "function");
  assert.equal(
    ui.sceneContextLabel({ result: { state: "needs_review" } }, { assumptions: ["assembly_review_required"] }),
    "3D provisional · colocación hipotética · revisión pendiente",
  );
  assert.equal(
    ui.sceneContextLabel({ result: { state: "completed" } }, { assumptions: ["shelf placement is schematic"] }),
    "3D revisado · colocación esquemática",
  );
});

test("table review keeps evidence behind progressive disclosure and uses one decision control per target", () => {
  assert.match(app, /table-diagnostics/);
  assert.match(app, /table-advanced-review/);
  assert.match(app, /document\.createElement\("select"\)/);
  assert.doesNotMatch(app, /\[\["accept","Aceptar"\],\["reject","Rechazar"\]\]\.forEach\(\(\[value,label\]\)/);
});

test("library similarities summarize known dimensions without exposing descriptor repr walls", () => {
  assert.equal(typeof ui.presentLibraryDifferences, "function");
  const componentRepr = "TableDescriptorComponentFeature(role='tabletop', quantity=1, material_tariff_id=None, field_states={'quantity': 'calculated'})";
  const result = ui.presentLibraryDifferences([
    { field: "dimensions.width_mm", query_value: "1400.0", candidate_value: "1200.0" },
    { field: "dimensions.depth_mm", query_value: null, candidate_value: "700.0" },
    { field: "components", query_value: componentRepr, candidate_value: componentRepr },
  ]);

  assert.deepEqual(result.summary, ["Ancho: 1400 ↔ 1200 mm", "Fondo: desconocido ↔ 700 mm", "Cambios en componentes"]);
  assert.equal(result.summary.join(" ").includes("TableDescriptorComponentFeature"), false);
  assert.equal(result.technical.length, 3);
  assert.match(result.technical[2], /TableDescriptorComponentFeature/);
  assert.match(app, /Datos de comparación/);
});

test("semantic explorer is capability gated with enablement guidance", () => {
  assert.match(app, /link\.id="semantic-explorer-link";link\.hidden=true/);
  assert.match(app, /guidance\.id="semantic-explorer-guidance"/);
  assert.match(app, /state\.features\.semanticExplorer/);
  assert.match(app, /semantic-explorer-link/);
});

test("review drafts expose a dirty signal and guard destructive navigation", () => {
  assert.match(app, /createReviewDraftGuard/);
  assert.match(reviewSource, /beforeunload/);
  assert.match(app, /canDiscard/);
  assert.match(app, /review-form/);
  assert.match(app, /function libraryRunLink\(item\)[\s\S]*recentRunLink/);
  assert.match(app, /setupGuardedNavigation[\s\S]*\.brand/);
  const rendered=app.indexOf("renderPartsAndReview();"),cleaned=app.indexOf("reviewDraftGuard?.markClean();",rendered),awaited=app.indexOf("await loadRevisionContext();",rendered);
  assert.ok(rendered>=0&&cleaned>rendered&&cleaned<awaited,"review baseline is captured before awaited context work");
});

test("recent projects are separate from Library and active jobs can be cancelled", () => {
  assert.match(html, /data-panel="projects"/);
  assert.match(html, /data-panel-content="projects"/);
  assert.match(html, /id="recent-projects"/);
  assert.match(html, /id="recent-executions"/);
  assert.match(html, /id="job-cancel"/);
  assert.match(app, /api\.getProjects/);
  assert.match(app, /api\.getExecutions/);
  assert.match(app, /api\.cancelJob/);
});
