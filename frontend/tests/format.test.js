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
