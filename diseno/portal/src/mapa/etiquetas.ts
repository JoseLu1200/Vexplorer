// Etiquetas que explican en qué se parece o se diferencia un vecino del punto fijado.
// Geometría: diferencias calculadas del vector, sin puntuación suelta. Embeddings: categoría y coseno guardado.
import { type DatosEmb, type DatosGeo, type DatosMapa, ROLES, medidas, rolesDe } from "./datos";

const NOMBRE: Record<(typeof ROLES)[number], [string, string]> = {
  laterales: ["lateral", "laterales"],
  divisores: ["divisor", "divisores"],
  tapas: ["tapa", "tapas"],
  bases: ["base", "bases"],
  baldas: ["balda", "baldas"],
  traseras: ["trasera", "traseras"],
  puertas: ["puerta", "puertas"],
  cajones: ["cajón", "cajones"],
  patas: ["pata", "patas"],
  otras: ["pieza intermedia", "piezas intermedias"],
};
const EJES = ["ancho", "fondo", "alto"] as const;
const UMBRAL_MM = 10;

const fmtMm = (v: number) => Math.abs(v).toLocaleString("es-ES");

const fmtCos = (c: number) => c.toLocaleString("es-ES", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

function etiquetasEmb(d: DatosEmb, a: number, b: number): string[] {
  const m = Array.from(d.vecinos.subarray(a * d.k, (a + 1) * d.k)).indexOf(b);
  const out = [d.categorias[d.puntos[b].cat]];
  if (m >= 0) out.push(`coseno ${fmtCos(d.cos[a * d.k + m])}`);
  return out;
}

export function etiquetas(d: DatosMapa, a: number, b: number): string[] {
  return d.tipo === "embedding" ? etiquetasEmb(d, a, b) : etiquetasGeo(d, a, b);
}

function etiquetasGeo(d: DatosGeo, a: number, b: number): string[] {
  const ra = rolesDe(d, a);
  const rb = rolesDe(d, b);
  const roles = ROLES.map((r, k) => ({ r, k, dif: rb[k] - ra[k] }))
    .filter((x) => x.dif !== 0)
    .sort((x, y) => Math.abs(y.dif) - Math.abs(x.dif) || x.k - y.k)
    .map(({ r, dif }) => `${Math.abs(dif)} ${NOMBRE[r][Math.abs(dif) === 1 ? 0 : 1]} ${dif > 0 ? "más" : "menos"}`);
  const ma = medidas(d, a);
  const mb = medidas(d, b);
  const ejes = EJES.map((e, k) => ({ e, dif: mb[k] - ma[k] }))
    .filter((x) => Math.abs(x.dif) >= UMBRAL_MM)
    .sort((x, y) => Math.abs(y.dif) - Math.abs(x.dif))
    .map(({ e, dif }) => `${dif > 0 ? "+" : "−"}${fmtMm(dif)} mm de ${e}`);
  const out = [roles[0] ?? "misma estructura", ejes[0] ?? "mismas medidas"];
  if (roles[1]) out.push(roles[1]);
  else if (ejes[1]) out.push(ejes[1]);
  else if (d.grosor[a] !== d.grosor[b]) out.push(`tablero de ${d.grosor[b]} mm`);
  return out;
}

/** Composición por rol, p. ej. «2 laterales · 3 puertas · 1 balda». */
export function composicion(d: DatosGeo, i: number): string {
  const r = rolesDe(d, i);
  return ROLES.filter((_, k) => r[k] > 0 && ROLES[k] !== "otras")
    .map((rol) => {
      const c = r[ROLES.indexOf(rol)];
      return `${c} ${NOMBRE[rol][c === 1 ? 0 : 1]}`;
    })
    .join(" · ");
}
