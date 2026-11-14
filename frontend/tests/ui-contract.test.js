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
  assert.match(html, /id="table-edge-scope"/);
  assert.match(html, /id="table-operation-tariffs"/);
});
