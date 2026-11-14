import test from "node:test";
import assert from "node:assert/strict";

import { normaliseDrawing } from "../core/drawing.js";

const baseMetricDrawing = {
  drawing_id: "d-conflict",
  source_unit: "mm",
  unit_scale_to_mm: 1,
  entities: [],
  views: [{ id: "view-1", label: "FRONT", entity_ids: [] }],
  contours: [],
};

test("normal non-conflicting dimension preserves exact label and conflict false", () => {
  const model = normaliseDrawing({
    ...baseMetricDrawing,
    dimensions: [{ id: "dim-1", value_mm: 900, source_value: 900, conflict: false }],
    dimension_graphics: [{
      id: "dg-1",
      dimension_id: "dim-1",
      view_id: "view-1",
      display_text: "900 mm",
      dimension_start_mm: [0, 90],
      dimension_end_mm: [900, 90],
      text_position_mm: [450, 95],
    }],
  });

  assert.equal(model.dimensions.length, 1);
  assert.equal(model.dimensions[0].label, "900 mm");
  assert.equal(model.dimensions[0].conflict, false);
  assert.equal(model.dimensions[0].conflictReason, null);
  assert.equal(model.dimensions[0].geometryValue, null);
});

test("DIMLFAC != 1 / conflict dimension formats metric geometry value and sets conflict true", () => {
  const model = normaliseDrawing({
    ...baseMetricDrawing,
    dimensions: [{
      id: "dim-conflict",
      value_mm: 600,
      source_value: 600,
      conflict: true,
      conflict_reason: "DIMLFAC=2.0 difiere de la geometría",
    }],
    dimension_graphics: [{
      id: "dg-conflict",
      dimension_id: "dim-conflict",
      view_id: "view-1",
      display_text: "1200",
      dimension_start_mm: [0, 50],
      dimension_end_mm: [600, 50],
      text_position_mm: [300, 55],
    }],
  });

  assert.equal(model.dimensions.length, 1);
  assert.equal(model.dimensions[0].label, "1200 [conflicto: geom 600 mm]");
  assert.equal(model.dimensions[0].conflict, true);
  assert.equal(model.dimensions[0].geometryValue, 600);
  assert.equal(model.dimensions[0].conflictReason, "DIMLFAC=2.0 difiere de la geometría");
});

test("unknown-unit conflicting dimension uses source-unit", () => {
  const model = normaliseDrawing({
    ...baseMetricDrawing,
    source_unit: "unknown",
    unit_scale_to_mm: null,
    dimensions: [{
      id: "dim-src",
      value_mm: null,
      source_value: 600,
      state: "conflict",
    }],
    dimension_graphics: [{
      id: "dg-src",
      dimension_id: "dim-src",
      view_id: "view-1",
      display_text: "1200",
      dimension_start_source: [0, 50],
      dimension_end_source: [600, 50],
      text_position_source: [300, 55],
    }],
  });

  assert.equal(model.coordinateUnit, "source");
  assert.equal(model.dimensions.length, 1);
  assert.equal(model.dimensions[0].label, "1200 [conflicto: geom 600 source-unit]");
  assert.equal(model.dimensions[0].conflict, true);
  assert.equal(model.dimensions[0].geometryValue, 600);
});

test("conflicting dimension without finite geometry value falls back to [conflicto]", () => {
  const model = normaliseDrawing({
    ...baseMetricDrawing,
    dimensions: [],
    dimension_graphics: [{
      id: "dg-fallback",
      dimension_id: "dim-missing",
      view_id: "view-1",
      raw_text: "1200",
      conflict: true,
      dimension_start_mm: [0, 50],
      dimension_end_mm: [600, 50],
      text_position_mm: [300, 55],
    }],
  });

  assert.equal(model.dimensions.length, 1);
  assert.equal(model.dimensions[0].label, "1200 [conflicto]");
  assert.equal(model.dimensions[0].conflict, true);
  assert.equal(model.dimensions[0].geometryValue, null);
});
