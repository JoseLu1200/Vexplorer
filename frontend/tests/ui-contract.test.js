import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const css = await readFile(new URL("../styles.css", import.meta.url), "utf8");
const app = await readFile(new URL("../app.js", import.meta.url), "utf8");

test("upload defaults to mounted table views and keeps parts and legacy opt-ins", () => {
  assert.match(html, /name="input_kind"/);
  assert.match(html, /value="mounted_orthographic_views" selected/);
  assert.match(html, /value="separated_part_views"/);
  assert.match(html, /value="mounted_views_legacy"/);
  assert.match(html, /name="table_template_id"/);
  assert.match(html, /value="side_supports_v1"/);
  assert.match(html, /value="corner_supports_v1"/);
});

test("empty workspace mirrors the selected input and names every supported document format",()=>{
  assert.match(app,/Entrada: mueble general/);
  assert.match(app,/Abre un plano DXF, DWG o PDF/);
  assert.match(app,/published\.selected=true/);
  assert.match(app,/con coste o presupuesto/);
  assert.match(app,/con horas publicadas/);
});

test("technical viewer exposes source and derived drawing tabs without replacing the source", () => {
  assert.match(html, /id="artifact-tabs"/);
  assert.match(html, /data-artifact-view="source"[^>]*aria-selected="true"/);
  assert.match(html, /data-artifact-view="general"/);
  assert.match(html, /data-artifact-view="components"/);
  assert.match(html, /data-artifact-view="cut_sheet"/);
  assert.match(html, /id="derived-drawing-view"/);
  assert.match(html, /id="derived-drawing-canvas"/);
  assert.match(html, /id="derived-drawing-expand"/);
  assert.match(html, /id="derived-drawing-downloads"/);
  assert.match(css, /\.derived-drawing-canvas\{[^}]*overflow:hidden/);
  assert.match(css, /\.derived-drawing-view\.is-expanded\{[^}]*position:fixed/);
  assert.match(app, /event\.target\.closest\("button,a,select,input"\)/);
});

test("responsive header never hides the active execution mode", () => {
  assert.doesNotMatch(css, /\.session-meta span:not\(:last-child\)\{display:none\}/);
  assert.match(css, /#run-mode-label\{display:inline-flex/);
});

test("responsive upload controls reflow instead of widening the document", () => {
  assert.match(css, /@media\(max-width:1180px\) and \(min-width:981px\).*\.topbar\{[^}]*flex-wrap:wrap/s);
  assert.match(css, /@media\(max-width:1180px\) and \(min-width:981px\).*\.quick-upload\{[^}]*flex-basis:100%/s);
  assert.match(css, /@media\(max-width:980px\).*\.quick-upload\{[^}]*display:grid;[^}]*grid-template-columns:minmax\(0,1fr\) minmax\(0,1fr\) auto/s);
  assert.match(css, /@media\(max-width:980px\).*\.quick-upload\{[^}]*flex:1 0 100%/s);
  assert.match(css, /@media\(max-width:980px\).*\.workbench\{[^}]*grid-template-columns:minmax\(0,1fr\)/s);
  assert.match(css, /@media\(max-width:620px\).*\.quick-upload>\.button\{grid-column:1\/-1/s);
  assert.match(css, /@media\(max-width:620px\).*\.navigator__head\{[^}]*flex:1 0 100%/s);
});

test("technical workspace has dedicated parts, classification and scene premise regions", () => {
  assert.match(html, /id="parts-summary"/);
  assert.match(html, /id="classification-summary"/);
  assert.match(html, /id="scene-context"/);
  assert.match(html, /id="legacy-review-fields"/);
  assert.match(html, /id="part-decisions"/);
});

test("table cost scope is explicit and never hides a partial known subtotal as a total", () => {
  assert.match(html, /id="table-cost-scope"/);
  assert.match(html, /id="table-material-tariff"/);
  assert.match(html, /id="table-component-material-tariffs"/);
  assert.match(html, /id="table-material-scope-warning"[^>]*role="status"/);
  assert.match(html, /id="table-edge-scope"/);
  assert.match(html, /id="table-operation-tariffs"/);
  assert.match(html, /id="table-catalog-provenance"/);
  assert.match(html, /id="table-labor-hours"/);
  assert.match(html, /id="table-finish-quantity"/);
  assert.match(html, /id="table-exclusion-controls"/);
  assert.match(html, /id="table-margin"/);
});

test("private identity, job progress and event gap status are announced", () => {
  assert.match(html, /id="session-user"/);
  assert.match(html, /id="job-status"[^>]*role="status"/);
  assert.match(html, /id="trace-gap-status"[^>]*role="status"/);
  assert.match(html, /id="trace-drawer"[^>]*role="dialog"[^>]*aria-modal="true"/);
  assert.match(html, /id="replay-source"[^>]*role="status"/);
  assert.match(html, /id="restore-run-retry"[^>]*type="button"[^>]*hidden/);
});

test("static assets remain relative for a prefixed private deployment", () => {
  assert.match(html, /href="\.\/styles\.css"/);
  assert.match(html, /src="\.\/app\.js"/);
  assert.match(html, /"three":"\.\/vendor\/three\/three\.module\.js"/);
  assert.doesNotMatch(html, /(?:href|src)="\/(?:styles\.css|app\.js|vendor\/)/);
});

test("upload exposes supported drawing formats and an honest general furniture workflow", () => {
  assert.match(html, /accept="[^"]*\.dxf[^"]*\.dwg[^"]*\.pdf/);
  assert.match(html, /value="general_furniture"/);
  assert.match(html, /id="document-provenance"[^>]*role="status"/);
  assert.match(html, /id="general-review-operations"/);
  assert.match(html, /id="general-derived-status"[^>]*role="status"/);
  assert.match(html, /data-export="bom_csv"/);
  assert.match(html, /data-export="bom_json"/);
});

test("real history import and estimates are reachable without presenting synthetic data as actual", () => {
  assert.match(html, /id="history-import-form"/);
  assert.match(html, /id="history-file"[^>]*accept="\.csv"/);
  assert.match(html, /id="history-provenance"/);
  assert.match(html, /value="actual"/);
  assert.match(html, /id="history-import-status"[^>]*role="status"/);
  assert.match(html, /id="estimate-uncertainty"/);
  assert.match(html, /id="estimate-missing-data"/);
  assert.doesNotMatch(html, /data-panel="evaluation"/);
});

test("historical estimates expose explicit retrieval and synthetic-data choices", () => {
  assert.match(app,/history-retrieval-method/);
  assert.match(app,/Atributos verificables/);
  assert.match(app,/Embeddings reales/);
  assert.match(app,/history-include-synthetic/);
  assert.match(app,/Incluir datos sintéticos para prueba/);
  assert.match(app,/history-retrieval-note/);
});

test("general furniture leads with automatic visual review and keeps human edits optional", () => {
  assert.match(app,/Revisión visual automática/);
  assert.match(app,/No confirma la hipótesis como hecho/);
  assert.match(app,/auto-revisión del mismo modelo/);
  assert.match(app,/Corrección humana avanzada/);
  assert.match(app,/generalRunOptions/);
  assert.match(app,/general-auto-review/);
});

test("automatic general review exposes conditional historical scenarios separately from confirmed estimates",()=>{
  assert.match(app,/Estimaciones por escenario/);
  assert.match(app,/historical-scenarios-button/);
  assert.match(app,/no son cotizaciones ni hechos confirmados/);
  assert.match(app,/Estimar desde histórico confirmado/);
});

test("PDF pages require an explicit page and optional confirmed scale before analysis", () => {
  assert.match(html, /id="pdf-page-controls"[^>]*hidden/);
  assert.match(html, /id="pdf-page-select"/);
  assert.match(html, /id="pdf-mm-per-point"[^>]*min="0"/);
  assert.match(html, /id="pdf-scale-reason"[^>]*required/);
  assert.match(html, /id="pdf-normalize"/);
});
