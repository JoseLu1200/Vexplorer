import test from "node:test";
import assert from "node:assert/strict";
import { boundsForPoints, fitViewport, panViewport, svgUnitPerPixel, zoomViewport } from "../core/viewport.js";

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

test("SVG labels preserve a constant apparent pixel size across zoom", () => {
  assert.equal(svgUnitPerPixel({ width: 900, height: 450 }, 900, 450), 1);
  assert.equal(svgUnitPerPixel({ width: 450, height: 225 }, 900, 450), .5);
});

test("asymmetric label padding does not consume the short viewport axis", () => {
  const fitted = fitViewport({ minX: 0, minY: 0, maxX: 100, maxY: 50 }, 200, 100, { left: 20, right: 60, top: 10, bottom: 10 });
  assert.equal(Number(fitted.width.toFixed(3)), 166.667);
  assert.equal(Number(fitted.height.toFixed(3)), 83.333);
  assert.equal(Number(fitted.x.toFixed(3)), -16.667);
  assert.equal(Number(fitted.y.toFixed(3)), -16.667);
});
