import test from "node:test";
import assert from "node:assert/strict";

import { fitImageViewport, panImageViewport, zoomImageViewport } from "../core/image-viewport.js";

test("derived drawing zoom keeps the chosen screen anchor fixed", () => {
  const fitted = fitImageViewport();
  const zoomed = zoomImageViewport(fitted, 2, { x: 300, y: 120 });

  assert.deepEqual(fitted, { scale: 1, x: 0, y: 0 });
  assert.deepEqual(zoomed, { scale: 2, x: -300, y: -120 });
  assert.deepEqual(panImageViewport(zoomed, 45, -20), { scale: 2, x: -255, y: -140 });
});

test("derived drawing zoom stays within useful legibility bounds", () => {
  assert.equal(zoomImageViewport({ scale: 1, x: 0, y: 0 }, 0.01, { x: 0, y: 0 }).scale, 0.5);
  assert.equal(zoomImageViewport({ scale: 4, x: 0, y: 0 }, 10, { x: 0, y: 0 }).scale, 8);
});
