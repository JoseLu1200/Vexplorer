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

test("0.3 drawing text and dimension graphics use explicit safe anchors", () => {
  const model = normaliseDrawing({
    ...unknownDrawing,
    source_unit: "mm",
    unit_scale_to_mm: 1,
    texts: [{ id: "txt-1", view_id: "view-1", text: "900 <script>", position_mm: { x: 60, y: 90 } }],
    dimension_graphics: [{
      id: "dg-1", dimension_id: "dim-1", view_id: "view-1", display_text: "900 mm",
      extension_start_a_mm: { x: 0, y: 80 }, extension_start_b_mm: { x: 0, y: 90 },
      dimension_start_mm: { x: 0, y: 90 }, dimension_end_mm: { x: 120, y: 90 }, text_position_mm: { x: 60, y: 94 },
    }],
  });
  assert.deepEqual(model.texts[0], { id: "txt-1", viewId: "view-1", text: "900 <script>", position: [60, 90] });
  assert.equal(model.dimensions[0].label, "900 mm");
  assert.deepEqual(model.dimensions[0].segments[2], [[0, 90], [120, 90]]);
});

test("dimension entities are not drawn as defpoint zigzags when graphics exist", () => {
  const model = normaliseDrawing({
    ...unknownDrawing,
    entities: [...unknownDrawing.entities, { id: "dim-entity", kind: "DIMENSION", source_points: [[0,0],[10,20],[30,40]] }],
    dimension_graphics: [{ id: "dg", source_entity_id: "dim-entity", dimension_id: "dim", view_id: "view-1", display_text: "120", dimension_start_source: [0,0], dimension_end_source: [120,0], text_position_source: [60,5] }],
  });
  assert.equal(model.paths.some((path)=>path.id === "entity:dim-entity"), false);
});
