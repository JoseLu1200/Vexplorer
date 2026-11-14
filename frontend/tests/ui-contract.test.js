import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
const css = await readFile(new URL("../styles.css", import.meta.url), "utf8");

test("upload defaults explicitly to separated part views and keeps legacy opt-in", () => {
  assert.match(html, /name="input_kind"/);
  assert.match(html, /value="separated_part_views" selected/);
  assert.match(html, /value="mounted_views_legacy"/);
});

test("responsive header never hides the active execution mode", () => {
  assert.doesNotMatch(css, /\.session-meta span:not\(:last-child\)\{display:none\}/);
  assert.match(css, /#run-mode-label\{display:inline-flex/);
});

test("responsive upload controls reflow instead of widening the document", () => {
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
