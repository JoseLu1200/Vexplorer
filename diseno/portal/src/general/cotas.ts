/**
 * Cotas medidas sobre la geometría del plano, para la vista «Limpio». Funciones puras, solo con planos en mm.
 *
 *   cotasCalculadas(plano)        por cada vista (grupo de contornos): ancho y alto generales y, si salen limpias,
 *                                 las cadenas de paneles horizontales (alturas) y de montantes (anchos).
 *   cotasDeContornos(plano, ids)  ancho y alto de cada contorno de una pieza seleccionada.
 *
 * Las vistas se forman agrupando contornos cuyas cajas se tocan o quedan a menos de un 1,5 % del tamaño del plano;
 * así sirven también para planos con una sola vista «UNKNOWN» que en realidad dibujan alzado, planta y perfil.
 * Una vista que ya trae cotas del DXF no recibe cotas calculadas, para no solaparlas.
 * Las cadenas llevan id «cadena:…»: el lienzo las oculta cuando su rótulo no cabe a ese zoom.
 */
import type { CotaVista, PlanoVista, Punto } from "./modelo";

interface Caja { minX: number; minY: number; maxX: number; maxY: number }

const cajaDe = (puntos: Punto[]): Caja => {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of puntos) { minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); }
  return { minX, minY, maxX, maxY };
};
const une = (a: Caja, b: Caja): Caja => ({ minX: Math.min(a.minX, b.minX), minY: Math.min(a.minY, b.minY), maxX: Math.max(a.maxX, b.maxX), maxY: Math.max(a.maxY, b.maxY) });
const cerca = (a: Caja, b: Caja, tol: number) => a.minX - tol <= b.maxX && b.minX - tol <= a.maxX && a.minY - tol <= b.maxY && b.minY - tol <= a.maxY;
const texto = (valor: number) => `${Math.round(valor)}`;

/** Cota horizontal entre x0 y x1, con las líneas de extensión desde yBase hasta yCota. */
function horizontal(id: string, vista: string, x0: number, x1: number, yBase: number, yCota: number): CotaVista {
  const a: Punto = [x0, yBase], b: Punto = [x1, yBase], s: Punto = [x0, yCota], e: Punto = [x1, yCota];
  return { id, vista, texto: texto(x1 - x0), valor_mm: x1 - x0, lineas: [[a, s], [b, e], [s, e]], posicionTexto: [(x0 + x1) / 2, yCota], origen: "calculada" };
}
/** Cota vertical entre y0 e y1, con las líneas de extensión desde xBase hasta xCota. */
function vertical(id: string, vista: string, y0: number, y1: number, xBase: number, xCota: number): CotaVista {
  const a: Punto = [xBase, y0], b: Punto = [xBase, y1], s: Punto = [xCota, y0], e: Punto = [xCota, y1];
  return { id, vista, texto: texto(y1 - y0), valor_mm: y1 - y0, lineas: [[a, s], [b, e], [s, e]], posicionTexto: [xCota, (y0 + y1) / 2], origen: "calculada" };
}

/** Niveles fusionados: valores a menos de `tol` cuentan como uno; se descartan tramos menores que `minimo`. */
function niveles(valores: number[], tol: number, minimo: number): number[] {
  const orden = [...valores].sort((a, b) => a - b);
  const fusion: number[] = [];
  for (const v of orden) {
    if (fusion.length && v - fusion[fusion.length - 1] < Math.max(tol, minimo)) continue;
    fusion.push(v);
  }
  return fusion;
}

export function cotasCalculadas(plano: PlanoVista, extensionMaxima: number | null = null): CotaVista[] {
  if (plano.coordenadas !== "mm" || !plano.limites) return [];
  const tamano = Math.max(plano.limites.maxX - plano.limites.minX, plano.limites.maxY - plano.limites.minY);
  const tol = tamano * 0.015;
  // 1. Grupos de contornos (vistas reales del dibujo).
  const items = plano.contornos.filter((c) => c.puntos.length > 1).map((c) => ({ c, caja: cajaDe(c.puntos) }));
  const grupos: { caja: Caja; miembros: typeof items }[] = [];
  for (const item of items) {
    const tocados = grupos.filter((g) => cerca(g.caja, item.caja, tol));
    if (!tocados.length) { grupos.push({ caja: item.caja, miembros: [item] }); continue; }
    const base = tocados[0];
    base.miembros.push(item);
    base.caja = une(base.caja, item.caja);
    for (const otro of tocados.slice(1)) {
      base.miembros.push(...otro.miembros);
      base.caja = une(base.caja, otro.caja);
      grupos.splice(grupos.indexOf(otro), 1);
    }
  }
  // Un grupo puede tocar a otro tras crecer: segunda pasada de fusión.
  for (let i = 0; i < grupos.length; i++) {
    for (let j = i + 1; j < grupos.length; j++) {
      if (cerca(grupos[i].caja, grupos[j].caja, tol)) {
        grupos[i].miembros.push(...grupos[j].miembros);
        grupos[i].caja = une(grupos[i].caja, grupos[j].caja);
        grupos.splice(j, 1);
        j = i;
      }
    }
  }
  const conCotasDxf = (g: Caja) => plano.cotas.some((c) => c.origen !== "calculada" && c.lineas.flat().some(([x, y]) => x >= g.minX - tol * 3 && x <= g.maxX + tol * 3 && y >= g.minY - tol * 3 && y <= g.maxY + tol * 3));
  const out: CotaVista[] = [];
  grupos.forEach((g, n) => {
    const { minX, minY, maxX, maxY } = g.caja;
    const w = maxX - minX, h = maxY - minY;
    if (w < 1 || h < 1 || conCotasDxf(g.caja)) return;
    // Un grupo más grande que el mueble junta dos vistas que se tocan: sus cotas serían de ruido.
    if (extensionMaxima && Math.max(w, h) > extensionMaxima * 1.15) return;
    // Huecos hasta los grupos vecinos: las cotas no invaden el dibujo de al lado.
    const solapaV = (o: Caja) => o.minY < maxY && o.maxY > minY;
    const solapaH = (o: Caja) => o.minX < maxX && o.maxX > minX;
    const otros = grupos.filter((o) => o !== g).map((o) => o.caja);
    const hueco = (d: number[]) => (d.length ? Math.min(...d) : Infinity);
    const izq = hueco(otros.filter(solapaV).map((o) => minX - o.maxX).filter((d) => d > 0));
    const der = hueco(otros.filter(solapaV).map((o) => o.minX - maxX).filter((d) => d > 0));
    const abajo = hueco(otros.filter(solapaH).map((o) => minY - o.maxY).filter((d) => d > 0));
    const arriba = hueco(otros.filter(solapaH).map((o) => o.minY - maxY).filter((d) => d > 0));
    // Hacia un vecino, como mucho un cuarto del hueco: el rótulo de enfrente necesita el resto.
    const sep = (libre: number) => Math.max(18, Math.min(Math.max(w, h) * 0.05, libre * 0.25, 90));
    const vista = `grupo-${n}`;
    const delgado = (v: number, total: number) => v <= Math.max(60, total * 0.08);
    // Cadena de alturas (paneles horizontales delgados que cruzan la vista) y de anchos (montantes verticales).
    const paneles = g.miembros.filter(({ caja }) => caja.maxX - caja.minX >= w * 0.6 && delgado(caja.maxY - caja.minY, h)).map(({ caja }) => (caja.minY + caja.maxY) / 2);
    const alturas = niveles([minY, maxY, ...paneles], h * 0.02, 40);
    const montantes = g.miembros.filter(({ caja }) => caja.maxY - caja.minY >= h * 0.6 && delgado(caja.maxX - caja.minX, w)).map(({ caja }) => (caja.minX + caja.maxX) / 2);
    const anchos = niveles([minX, maxX, ...montantes], w * 0.02, 40);
    const cadenaAlto = alturas.length >= 3 && alturas.length <= 12;
    const cadenaAncho = anchos.length >= 3 && anchos.length <= 12;
    // Cada cadena va al lado con más sitio libre; si coincide con la cota general, la general se aparta el doble.
    const altoIzq = izq >= der;
    const anchoAbajo = abajo >= arriba;
    const sepIzq = sep(izq), sepDer = sep(der), sepAbajo = sep(abajo), sepArriba = sep(arriba);
    out.push(horizontal(`calc:${n}:ancho`, vista, minX, maxX, minY, minY - sepAbajo * (cadenaAncho && anchoAbajo ? 2 : 1)));
    out.push(vertical(`calc:${n}:alto`, vista, minY, maxY, minX, minX - sepIzq * (cadenaAlto && altoIzq ? 2 : 1)));
    if (cadenaAlto) {
      const [base, x] = altoIzq ? [minX, minX - sepIzq] : [maxX, maxX + sepDer];
      for (let i = 0; i < alturas.length - 1; i++) out.push(vertical(`cadena:${n}:alto:${i}`, vista, alturas[i], alturas[i + 1], base, x));
    }
    if (cadenaAncho) {
      const [base, y] = anchoAbajo ? [minY, minY - sepAbajo] : [maxY, maxY + sepArriba];
      for (let i = 0; i < anchos.length - 1; i++) out.push(horizontal(`cadena:${n}:ancho:${i}`, vista, anchos[i], anchos[i + 1], base, y));
    }
  });
  return out;
}

/** Ancho y alto de cada contorno de la pieza seleccionada, pegados a su contorno. */
export function cotasDeContornos(plano: PlanoVista, ids: string[]): CotaVista[] {
  if (plano.coordenadas !== "mm") return [];
  const out: CotaVista[] = [];
  for (const c of plano.contornos.filter((item) => ids.includes(item.id))) {
    const { minX, minY, maxX, maxY } = cajaDe(c.puntos);
    const sep = Math.max(12, Math.min(maxX - minX, maxY - minY) * 0.15, 0);
    if (maxX - minX >= 1) out.push(horizontal(`pieza:${c.id}:ancho`, c.vista, minX, maxX, minY, minY - Math.min(sep, 40)));
    if (maxY - minY >= 1) out.push(vertical(`pieza:${c.id}:alto`, c.vista, minY, maxY, minX, minX - Math.min(sep, 40)));
  }
  return out;
}
