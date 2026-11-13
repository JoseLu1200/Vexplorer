import test from "node:test";
import assert from "node:assert/strict";
import { boundsForPoints, fitViewport, panViewport, zoomViewport } from "../core/viewport.js";

test("viewport fits, pans and zooms around an anchor", () => {
  const bounds = boundsForPoints([[0, 0], [100, 50]]);
  assert.deepEqual(bounds, { minX: 0, minY: 0, maxX: 100, maxY: 50 });
  const fitted = fitViewport(bounds, 200, 200, 20);
  assert.equal(fitted.width, 125);
  assert.equal(fitted.height, 125);
  assert.deepEqual(panViewport(fitted, 10, -5), { ...fitted, x: fitted.x + 10, y: fitted.y - 5 });
  const zoomed = zoomViewport(fitted, .5, { x: 50, y: 25 });
  assert.equal(zoomed.width, 62.5);
  assert.equal(zoomed.x, 18.75);
});
