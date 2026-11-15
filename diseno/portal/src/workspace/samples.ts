/**
 * Los seis DXF de ejemplo de data/planos_demo, empaquetados tal cual (texto ASCII) para «Abrir en CAD»
 * y para volver a analizarlos en modo de ejemplo. Se cargan bajo demanda.
 */
const LOADERS: Record<string, () => Promise<string>> = {
  "piezas_espesor_desconocido.dxf": () => import("../assets/dxf/piezas_espesor_desconocido.dxf?raw").then((m) => m.default),
  "piezas_qty_desconocida.dxf": () => import("../assets/dxf/piezas_qty_desconocida.dxf?raw").then((m) => m.default),
  "piezas_ambigua_sin_id.dxf": () => import("../assets/dxf/piezas_ambigua_sin_id.dxf?raw").then((m) => m.default),
  "piezas_completo.dxf": () => import("../assets/dxf/piezas_completo.dxf?raw").then((m) => m.default),
  "piezas_dimensiones_variante.dxf": () => import("../assets/dxf/piezas_dimensiones_variante.dxf?raw").then((m) => m.default),
  "piezas_espesor_36.dxf": () => import("../assets/dxf/piezas_espesor_36.dxf?raw").then((m) => m.default),
};

export const SAMPLE_ASSETS = Object.keys(LOADERS);

export async function sampleFile(name: string): Promise<File | null> {
  const load = LOADERS[name];
  if (!load) return null;
  try {
    return new File([await load()], name, { type: "application/dxf" });
  } catch {
    return null;
  }
}

/** Carpeta de la siembra anterior del modo real. La siembra de «Muebles procesados» la retira si se queda vacía. */
export const PROCESSED_FOLDER = "Demo procesada";

/** Carpetas y reparto de la siembra inicial (solo en modo de ejemplo). Nombres genéricos de oficina técnica. */
export const SEED_FOLDERS = [
  { key: "recibidos", name: "Recibidos" },
  { key: "e900", name: "Serie E-900" },
  { key: "e1000", name: "Serie E-1000" },
] as const;

export const SEED_PLANS: { file: string; folder: (typeof SEED_FOLDERS)[number]["key"] }[] = [
  { file: "piezas_espesor_desconocido.dxf", folder: "e900" },
  { file: "piezas_completo.dxf", folder: "e900" },
  { file: "piezas_espesor_36.dxf", folder: "e900" },
  { file: "piezas_dimensiones_variante.dxf", folder: "e1000" },
  { file: "piezas_qty_desconocida.dxf", folder: "recibidos" },
  { file: "piezas_ambigua_sin_id.dxf", folder: "recibidos" },
];
