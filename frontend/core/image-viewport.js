const MIN_SCALE = 0.5;
const MAX_SCALE = 8;

export function fitImageViewport() {
  return { scale: 1, x: 0, y: 0 };
}

export function zoomImageViewport(viewport, multiplier, anchor) {
  const previous = viewport?.scale || 1;
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, previous * multiplier));
  const ratio = scale / previous;
  return {
    scale,
    x: anchor.x - (anchor.x - (viewport?.x || 0)) * ratio,
    y: anchor.y - (anchor.y - (viewport?.y || 0)) * ratio,
  };
}

export function panImageViewport(viewport, dx, dy) {
  return { ...viewport, x: viewport.x + dx, y: viewport.y + dy };
}
