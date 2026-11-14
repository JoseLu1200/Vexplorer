import test from "node:test";
import assert from "node:assert/strict";

import { formatMeasurement, sourceLabel } from "../core/format.js";

test("unknown measurements are explicit and never acquire a metric suffix", () => {
  assert.equal(formatMeasurement(null, "mm"), "Desconocido");
  assert.equal(formatMeasurement(undefined, "mm"), "Desconocido");
  assert.equal(formatMeasurement(600, "source"), "600 u. fuente");
});

test("source classes remain distinct in Spanish", () => {
  assert.equal(sourceLabel("observed"), "Observado");
  assert.equal(sourceLabel("derived"), "Calculado");
  assert.equal(sourceLabel("hypothesis"), "Hipótesis");
  assert.equal(sourceLabel("human_confirmed"), "Confirmado por persona");
});

test("measurement display removes floating noise without mutating the source value", () => {
  const length=1443.000000835382,thickness=17.999933;
  assert.equal(formatMeasurement(length,"mm"),"1443 mm");
  assert.equal(formatMeasurement(thickness,"mm"),"18 mm");
  assert.equal(length,1443.000000835382);
  assert.equal(formatMeasurement(12.3456,"mm",{tolerance:0.001}),"12,346 mm");
});
