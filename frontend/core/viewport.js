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
  const inset = typeof padding === "number"
    ? { left: padding, right: padding, top: padding, bottom: padding }
    : { left: padding.left ?? 0, right: padding.right ?? 0, top: padding.top ?? 0, bottom: padding.bottom ?? 0 };
  const rawWidth = Math.max(1, bounds.maxX - bounds.minX);
  const rawHeight = Math.max(1, bounds.maxY - bounds.minY);
  const contentWidth = Math.max(1, viewportWidth - inset.left - inset.right);
  const contentHeight = Math.max(1, viewportHeight - inset.top - inset.bottom);
  const ratio = Math.max(rawWidth / contentWidth, rawHeight / contentHeight);
  const width = Math.max(rawWidth, viewportWidth * ratio);
  const height = Math.max(rawHeight, viewportHeight * ratio);
  const horizontalSlack = contentWidth * ratio - rawWidth;
  const verticalSlack = contentHeight * ratio - rawHeight;
  return {
    x: bounds.minX - inset.left * ratio - horizontalSlack / 2,
    y: bounds.minY - inset.top * ratio - verticalSlack / 2,
    width,
    height,
  };
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

export function svgUnitPerPixel(viewport, pixelWidth, pixelHeight) {
  if (!viewport || pixelWidth <= 0 || pixelHeight <= 0) return 1;
  return Math.max(viewport.width / pixelWidth, viewport.height / pixelHeight);
}
