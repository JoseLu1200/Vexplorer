/**
 * Miniatura del montaje 3D para las tarjetas: proyección isométrica de las cajas de la escena en polígonos 2D,
 * con las tres caras visibles de cada caja (arriba, frente y lado derecho). Pura, sin three.js.
 * Devuelve contornos con la misma forma que la miniatura de un plano (id, puntos con y hacia arriba, cerrado).
 */
import type { Escena3D } from "./modelo";

export interface ContornoMiniatura { id: string; points: { x: number; y: number }[]; closed: boolean }

const C = Math.cos(Math.PI / 6), S = Math.sin(Math.PI / 6);

/** Punto de vista (a = ancho, h = altura, d = profundidad hacia el observador) a pantalla, mirando desde arriba a la derecha. */
const P = (a: number, h: number, d: number) => ({ x: (a - d) * C, y: h - (a + d) * S });

/**
 * `frente` indica dónde está el frente del mueble en el eje de profundidad: 1 si está en +profundidad
 * (montaje general), -1 si está en profundidad 0 (escenas de vistas montadas y mesas).
 */
export function miniaturaMontaje(escena: Escena3D, frente: 1 | -1): ContornoMiniatura[] {
  if (escena.disposicion !== "montaje" || !escena.cajas.length) return [];
  const zUp = escena.ejeVertical === "z";
  const cajas = escena.cajas.map((caja) => {
    const { x, y, z } = caja.posicion_mm;
    const { x: sx, y: sy, z: sz } = caja.tamano_mm;
    const h0 = zUp ? z : y, h1 = zUp ? z + sz : y + sy;
    // Con la altura en z, la profundidad es y; el alzado mira hacia -y.
    const p0 = zUp ? -(y + sy) : z, p1 = zUp ? -y : z + sz;
    const [d0, d1] = frente === 1 ? [p0, p1] : [-p1, -p0];
    return { id: caja.id, a0: x, a1: x + sx, h0, h1, d0, d1 };
  });
  // De atrás adelante, para que el trazo de lo cercano quede encima.
  cajas.sort((p, q) => p.d1 + p.a1 - (q.d1 + q.a1));
  return cajas.flatMap(({ id, a0, a1, h0, h1, d0, d1 }) => [
    { id: `${id}:arriba`, closed: true, points: [P(a0, h1, d0), P(a1, h1, d0), P(a1, h1, d1), P(a0, h1, d1)] },
    { id: `${id}:frente`, closed: true, points: [P(a0, h0, d1), P(a1, h0, d1), P(a1, h1, d1), P(a0, h1, d1)] },
    { id: `${id}:lado`, closed: true, points: [P(a1, h0, d0), P(a1, h0, d1), P(a1, h1, d1), P(a1, h1, d0)] },
  ]);
}
