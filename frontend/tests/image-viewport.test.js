import test from "node:test";
import assert from "node:assert/strict";

import { fitImageViewport, imageViewportStyle, panImageViewport, panImageViewportByDirection, zoomImageViewport } from "../core/image-viewport.js";

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

test("directional controls pan the drawing without requiring a drag gesture",()=>{
  const viewport={scale:2,x:-120,y:-80};
  assert.deepEqual(panImageViewportByDirection(viewport,"left"),{scale:2,x:-72,y:-80});
  assert.deepEqual(panImageViewportByDirection(viewport,"right"),{scale:2,x:-168,y:-80});
  assert.deepEqual(panImageViewportByDirection(viewport,"up"),{scale:2,x:-120,y:-32});
  assert.deepEqual(panImageViewportByDirection(viewport,"down"),{scale:2,x:-120,y:-128});
});

test("derived SVG is rerasterized at its enlarged size instead of scaling a small bitmap", () => {
  assert.deepEqual(imageViewportStyle({ scale: 2.25, x: -80, y: 15 }), {
    width: "225%",
    height: "225%",
    left: "-80px",
    top: "15px",
  });
});
