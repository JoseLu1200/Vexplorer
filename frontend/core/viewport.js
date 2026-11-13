export function boundsForPoints(points = []) {
  const valid = points.filter((point) => Array.isArray(point) && point.length >= 2 && point.slice(0, 2).every(Number.isFinite));
  if (!valid.length) return null;
  return {
    minX: Math.min(...valid.map(([x]) => x)), minY: Math.min(...valid.map(([, y]) => y)),
    maxX: Math.max(...valid.map(([x]) => x)), maxY: Math.max(...valid.map(([, y]) => y)),
  };
}

export function fitViewport(bounds, viewportWidth, viewportHeight, padding = 20) {
  if (!bounds) return { x: 0, y: 0, width: 1, height: 1 };
  const rawWidth = Math.max(1, bounds.maxX - bounds.minX);
  const rawHeight = Math.max(1, bounds.maxY - bounds.minY);
  const ratio = Math.max(rawWidth / Math.max(1, viewportWidth - padding * 2), rawHeight / Math.max(1, viewportHeight - padding * 2));
  const width = Math.max(rawWidth, viewportWidth * ratio);
  const height = Math.max(rawHeight, viewportHeight * ratio);
  return { x: bounds.minX - (width - rawWidth) / 2, y: bounds.minY - (height - rawHeight) / 2, width, height };
}

export function panViewport(viewport, dx, dy) { return { ...viewport, x: viewport.x + dx, y: viewport.y + dy }; }

export function zoomViewport(viewport, factor, anchor) {
  const clamped = Math.min(4, Math.max(.08, factor));
  return {
    x: anchor.x - (anchor.x - viewport.x) * clamped,
    y: anchor.y - (anchor.y - viewport.y) * clamped,
    width: viewport.width * clamped,
    height: viewport.height * clamped,
  };
}
