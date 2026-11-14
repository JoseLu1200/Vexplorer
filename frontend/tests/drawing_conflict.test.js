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

function realDimensionPayload({
  entityId = "2A",
  displayText = "1200",
  metric = true,
  warnings = [],
} = {}) {
  const pointSuffix = metric ? "mm" : "source";
  const unitScale = metric ? 1 : null;
  return {
    ...baseMetricDrawing,
    source_unit: metric ? "mm" : "unknown",
    unit_scale_to_mm: unitScale,
    coordinate_unit: metric ? "mm" : "source",
    warnings,
    dimensions: [{
      id: `dimension-${entityId}`,
      kind: "annotation",
      value_mm: null,
      source_entity_ids: [entityId],
      evidence_ids: [`evidence-dimension-${entityId}`],
      origin: "observed",
      view_id: "view-1",
      graphic_id: `graphic-${entityId}`,
    }],
    dimension_graphics: [{
      id: `graphic-${entityId}`,
      dimension_id: `dimension-${entityId}`,
      source_entity_id: entityId,
      view_id: "view-1",
      layer: "0",
      display_text: displayText,
      raw_text: "",
      [`extension_start_a_${pointSuffix}`]: [0, 0],
      [`extension_start_b_${pointSuffix}`]: [600, 0],
      [`dimension_start_${pointSuffix}`]: [0, 50],
      [`dimension_end_${pointSuffix}`]: [600, 50],
      [`text_position_${pointSuffix}`]: [300, 55],
    }],
  };
}

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

test("real extraction payload maps DIMLFAC warning to the source dimension geometry", () => {
  const model = normaliseDrawing(realDimensionPayload({
    warnings: ["dimension_scale_conflict:2A:scale=2"],
  }));

  assert.equal(model.dimensions.length, 1);
  assert.equal(model.dimensions[0].label, "1200 [conflicto: geom 600 mm]");
  assert.equal(model.dimensions[0].conflict, true);
  assert.equal(model.dimensions[0].geometryValue, 600);
  assert.match(model.dimensions[0].conflictReason, /DIMLFAC.*2/i);
});

test("real unknown-unit extraction payload reports conflicting source geometry", () => {
  const model = normaliseDrawing(realDimensionPayload({
    entityId: "3B",
    metric: false,
    warnings: ["dimension_text_conflict:3B:geometry=600:text=1200"],
  }));

  assert.equal(model.coordinateUnit, "source");
  assert.equal(model.dimensions.length, 1);
  assert.equal(model.dimensions[0].label, "1200 [conflicto: geom 600 source-unit]");
  assert.equal(model.dimensions[0].conflict, true);
  assert.equal(model.dimensions[0].geometryValue, 600);
});

test("conflict warning without complete dimension geometry falls back to conflict label", () => {
  const payload = realDimensionPayload({
    entityId: "4C",
    warnings: ["dimension_text_override:4C:text=REF"],
    displayText: "REF",
  });
  delete payload.dimension_graphics[0].dimension_end_mm;
  const model = normaliseDrawing(payload);

  assert.equal(model.dimensions.length, 1);
  assert.equal(model.dimensions[0].label, "REF [conflicto]");
  assert.equal(model.dimensions[0].conflict, true);
  assert.equal(model.dimensions[0].geometryValue, null);
});
