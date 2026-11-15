/**
 * Muebles raros de PlankAssembly sin procesar, solo en local: los genera scripts/build_raros.py en public/local/raros
 * (ignorado por git, licencia CC BY-NC-ND 4.0). Si la carpeta no existe, el catálogo no los muestra.
 * Se abren como «solo plano»: geometría del DXF y el resto pendiente del modelo.
 */
import type { DrawingExtraction } from "../api/general.gen";
import { desdeGeneral } from "../general/adaptador";
import type { MesaTrabajo } from "../general/modelo";
import { ATRIBUCION_PLANK } from "./index";

export interface RaroMeta { id: string; titulo: string; piezas: number | null; tipos: number | null; medidas_mm: { ancho: number | null; fondo: number | null; alto: number | null } }

const BASE = "./local/raros";
export const PREFIJO_RARO = "raro:";

export async function indiceRaros(): Promise<RaroMeta[]> {
  try {
    const response = await fetch(`${BASE}/index.json`);
    if (!response.ok) return [];
    const value = await response.json();
    return Array.isArray(value) ? value as RaroMeta[] : [];
  } catch {
    return [];
  }
}

export async function cargarRaro(id: string, titulo: string): Promise<MesaTrabajo> {
  const response = await fetch(`${BASE}/${encodeURIComponent(id)}.json`);
  if (!response.ok) throw new Error(`No está el plano ${id} en public/local/raros.`);
  const { drawing } = await response.json() as { drawing: DrawingExtraction };
  const meta = (await indiceRaros()).find((item) => item.id === id);
  const m = meta?.medidas_mm;
  const extension = m ? Math.max(m.ancho ?? 0, m.fondo ?? 0, m.alto ?? 0) || null : null;
  const mesa = desdeGeneral({
    id: `${PREFIJO_RARO}${id}`, titulo, origen: { tipo: "caso", casoId: id, fuentes: { raros: `${BASE}/${id}.json` } }, sintetico: false,
    drawing, atribucion: ATRIBUCION_PLANK,
    pendientes: [{ id: "modelo", tipo: "modelo", piezaId: null, campos: [], texto: "Pendiente: requiere modelo" }],
  });
  return mesa.plano ? { ...mesa, plano: { ...mesa.plano, extensionMaxima_mm: extension } } : mesa;
}
