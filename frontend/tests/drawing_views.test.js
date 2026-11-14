import test from "node:test";
import assert from "node:assert/strict";

import { normaliseDrawing, pathMatchesView } from "../core/drawing.js";
import { boundsForPoints, fitViewport } from "../core/viewport.js";

const twoViewDrawing = {
  drawing_id: "d-views",
  source_unit: "mm",
  unit_scale_to_mm: 1,
  views: [
    {
      id: "view-front",
      label: "FRONT",
      entity_ids: ["front-outer", "shared-shelf", "shared-hole"],
      bounds_source: [0, 0, 120, 80],
      bounds_mm: { min_x: 0, min_y: 0, max_x: 120, max_y: 80 },
    },
    {
      id: "view-side",
      label: "SIDE",
      entity_ids: ["side-outer", "shared-shelf", "shared-hole"],
      bounds_source: [1000, 0, 1060, 80],
      bounds_mm: { min_x: 1000, min_y: 0, max_x: 1060, max_y: 80 },
    },
  ],
  contours: [
    {
      id: "c-front",
      view_id: "view-front",
      source_entity_ids: ["front-outer"],
      points_mm: [[0, 0], [120, 0], [120, 80], [0, 80]],
      closed: true,
    },
    {
      id: "c-side",
      view_id: "view-side",
      source_entity_ids: ["side-outer"],
      points_mm: [[1000, 0], [1060, 0], [1060, 80], [1000, 80]],
      closed: true,
    },
  ],
  entities: [
    { id: "front-outer", kind: "LINE", points_mm: [[0, 0], [120, 0]] },
    { id: "side-outer", kind: "LINE", points_mm: [[1000, 0], [1060, 0]] },
    { id: "shared-shelf", kind: "LINE", points_mm: [[10, 40], [110, 40]] },
    {
      id: "shared-hole",
      kind: "CIRCLE",
      points_mm: [[60, 20]],
      circular: { kind: "circle", center_mm: { x: 60, y: 20 }, radius_mm: 8 },
    },
  ],
};

test("multi-view unclaimed entities preserve viewIds alongside viewId", () => {
  const model = normaliseDrawing(twoViewDrawing);
  const shelf = model.paths.find((path) => path.id === "entity:shared-shelf");
  const hole = model.paths.find((path) => path.id === "entity:shared-hole");

  assert.equal(shelf.viewId, null);
  assert.deepEqual(shelf.viewIds, ["view-front", "view-side"]);
  assert.equal(hole.viewId, null);
  assert.deepEqual(hole.viewIds, ["view-front", "view-side"]);
});

test("single-view filtering retains multi-view interior lines and hides other views", () => {
  const model = normaliseDrawing(twoViewDrawing);
  const frontVisible = model.paths.filter((path) => pathMatchesView(path, "view-front"));
  const sideVisible = model.paths.filter((path) => pathMatchesView(path, "view-side"));
  const allVisible = model.paths.filter((path) => pathMatchesView(path, "all"));

  assert.deepEqual(
    frontVisible.map((path) => path.id),
    ["c-front", "entity:shared-shelf", "entity:shared-hole"],
  );
  assert.deepEqual(
    sideVisible.map((path) => path.id),
    ["c-side", "entity:shared-shelf", "entity:shared-hole"],
  );
  assert.equal(allVisible.length, model.paths.length);
  assert.equal(pathMatchesView({ viewId: null, viewIds: ["view-front", "view-side"] }, new Set(["view-front"])), true);
  assert.equal(pathMatchesView({ viewId: null, viewIds: [] }, "view-front"), false);
});

test("unclaimed entity without explicit viewId inherits single containing view bounds", () => {
  const model = normaliseDrawing({
    drawing_id: "d-bounds",
    source_unit: "unknown",
    unit_scale_to_mm: null,
    views: [
      { id: "view-front", label: "FRONT", entity_ids: [], bounds_source: [0, 0, 120, 80], bounds_mm: null },
      { id: "view-side", label: "SIDE", entity_ids: [], bounds_source: [200, 0, 260, 80], bounds_mm: null },
    ],
    contours: [],
    entities: [
      { id: "interior-line", kind: "LINE", source_points: [[10, 40], [110, 40]] },
      {
        id: "interior-circle",
        kind: "CIRCLE",
        source_points: [[230, 40]],
        circular: { kind: "circle", center_source: [230, 40], radius_source: 10 },
      },
      { id: "outside-line", kind: "LINE", source_points: [[130, 10], [190, 10]] },
    ],
  });

  const interiorLine = model.paths.find((path) => path.id === "entity:interior-line");
  const interiorCircle = model.paths.find((path) => path.id === "entity:interior-circle");
  const outsideLine = model.paths.find((path) => path.id === "entity:outside-line");

  assert.equal(interiorLine.viewId, "view-front");
  assert.deepEqual(interiorLine.viewIds, ["view-front"]);
  assert.equal(interiorCircle.viewId, "view-side");
  assert.deepEqual(interiorCircle.viewIds, ["view-side"]);
  assert.equal(outsideLine.viewId, null);
  assert.deepEqual(outsideLine.viewIds, []);
});

test("view-scoped fit bounds include multi-view interior points and exclude other views", () => {
  const model = normaliseDrawing(twoViewDrawing);
  const toSvg = ([x, y]) => [x, y === 0 ? 0 : -y];
  const frontPoints = model.pointsForViews(new Set(["view-front"])).map(toSvg);
  const allPoints = model.pointsForViews(null).map(toSvg);

  const frontBounds = boundsForPoints(frontPoints);
  const globalBounds = boundsForPoints(allPoints);

  assert.deepEqual(frontBounds, { minX: 0, minY: -80, maxX: 120, maxY: 0 });
  assert.deepEqual(globalBounds, { minX: 0, minY: -80, maxX: 1060, maxY: 0 });

  const frontViewport = fitViewport(frontBounds, 900, 520, model.fitPaddingForViews(new Set(["view-front"])));
  const globalViewport = fitViewport(globalBounds, 900, 520, model.fitPaddingForViews(null));

  assert.ok(frontViewport.width < 300, `expected tight front viewport width, got ${frontViewport.width}`);
  assert.ok(globalViewport.width >= 1060, `expected global viewport to span both views, got ${globalViewport.width}`);

  const emptyViewPoints = model.pointsForViews(new Set(["view-empty"]));
  assert.deepEqual(emptyViewPoints, []);
});
