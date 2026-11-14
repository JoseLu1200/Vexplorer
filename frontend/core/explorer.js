export function filterPoints(points, query = '', category = '') {
  const needle = query.trim().toLocaleLowerCase('es');
  return points.filter(p => (!category || p.category === category) && (!needle || `${p.label} ${p.id} ${p.category ?? ''}`.toLocaleLowerCase('es').includes(needle)));
}

export function mapCoordinates(points) {
  if (!points.length) return [];
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const scale = Math.min(672 / (maxX - minX || 1), 392 / (maxY - minY || 1));
  return points.map(p => ({...p, position:[400 + (p.x - (minX + maxX) / 2) * scale, 260 - (p.y - (minY + maxY) / 2) * scale]}));
}

export function createRequestGate() {
  let version = 0;
  return { next: () => ++version, current: ticket => ticket === version };
}

export function counterpart(point, points) {
  return point.content_hash ? points.find(p => p.content_hash === point.content_hash) ?? null : null;
}

export function overlap(left, right) {
  const a = new Set(left.map(p => p.content_hash).filter(Boolean));
  const b = new Set(right.map(p => p.content_hash).filter(Boolean));
  return {shared:[...a].filter(x => b.has(x)).length, total:new Set([...a,...b]).size};
}
