import test from "node:test";
import assert from "node:assert/strict";

import { normaliseDrawing, selectionForComponent, safeText } from "../core/drawing.js";

const unknownDrawing = {
  drawing_id: "d-1",
  source_unit: "unknown",
  unit_scale_to_mm: null,
  entities: [{ id: "entity-1", kind: "LINE", source_points: [[0, 0], [120, 0]], points_mm: null }],
  views: [{ id: "view-1", label: "FRONT", entity_ids: ["entity-1"], bounds_source: [0, 0, 120, 80], bounds_mm: null }],
  contours: [{ id: "contour-1", view_id: "view-1", source_entity_ids: ["entity-1"], source_points: [[0, 0], [120, 0]], points_mm: null, closed: false }],
  evidence: [{ id: "ev-1", source_entity_ids: ["entity-1"] }],
};

test("unknown units use source coordinates and do not expose metric coordinates", () => {
  const model = normaliseDrawing(unknownDrawing);
  assert.equal(model.coordinateUnit, "source");
  assert.deepEqual(model.paths[0].points, [[0, 0], [120, 0]]);
  assert.equal(model.unitLabel, "Unidad sin resolver");
});

test("Pydantic point objects become safe numeric SVG points", () => {
  const model = normaliseDrawing({
    ...unknownDrawing,
    contours: [{ ...unknownDrawing.contours[0], source_points: undefined, points_source: [{ x: 0, y: 10 }, { x: 120, y: 10 }] }],
  });
  assert.deepEqual(model.paths[0].points, [[0, 10], [120, 10]]);
});

test("unclaimed source entities remain visible as construction evidence", () => {
  const model = normaliseDrawing({
    ...unknownDrawing,
    entities: [
      ...unknownDrawing.entities,
      { id: "inner-shelf", kind: "LINE", source_points: [{ x: 0, y: 40 }, { x: 120, y: 40 }], points_mm: null },
    ],
  });
  const shelf = model.paths.find((path) => path.id === "entity:inner-shelf");
  assert.deepEqual(shelf.points, [[0, 40], [120, 40]]);
  assert.deepEqual(shelf.entityIds, ["inner-shelf"]);
});

test("component selection follows stable contour and evidence identifiers", () => {
  const selected = selectionForComponent({
    id: "component-1",
    source_contour_ids: ["contour-1"],
    evidence_ids: ["ev-1"],
  }, unknownDrawing);
  assert.deepEqual([...selected.entityIds], ["entity-1"]);
  assert.deepEqual([...selected.contourIds], ["contour-1"]);
  assert.deepEqual([...selected.evidenceIds], ["ev-1"]);
});

test("hostile DXF text remains plain text", () => {
  assert.equal(safeText('<img src=x onerror="globalThis.pwned=true">'), '<img src=x onerror="globalThis.pwned=true">');
});
