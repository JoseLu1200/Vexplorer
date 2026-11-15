/**
 * Muebles ya procesados, de solo lectura, generados por scripts/build_casos.py desde archivos en git
 * de Vexplorer. Primero los que tienen montaje 3D y después los que no («Sin montaje»).
 *
 *   CASOS                 metadatos para listar sin cargar los datos.
 *   cargarCaso(id)        carga el JSON (import dinámico, un chunk por caso) y lo pasa por el adaptador.
 *   RUNS_PLANK            run_id del pipeline guardado (data/plank_pipeline_demo), para abrirlos en modo real.
 *   RUNS_DEMO             run_id de la demo procesada restaurada en el backend, para abrirlos en modo real.
 *   ATRIBUCION_PLANK      atribución obligatoria de los planos de PlankAssembly.
 */
import type {
  DrawingExtraction, GeneralAssemblyState, GeneralConstructionPlan, GeneralConstructionValidation, GeneralDerivedArtifact,
  GeneralDerivedResponse, GeneralFurnitureRecord, ReconstructionScene,
} from "../api/general.gen";
import type { ExplanationBundle, Result } from "../api/types";
import { desdeGeneral, desdeLegacy, desdeReconstruccion, desdeTabla, type TablaCoste, type TablaLaminas, type TablaRespuesta, type TrabajoReconstruccion } from "../general/adaptador";
import type { ArchivoVista, MesaTrabajo } from "../general/modelo";
import type { EventoRun } from "../general/traza";

export type CasoId =
  | "plank_030" | "plank_016" | "mesa_coste" | "mesa_002"
  | "piezas_6ddf" | "piezas_c321" | "pdf_raster"
  | "recon_mesa" | "recon_caso01" | "recon_caso02" | "recon_caso03" | "recon_caso04" | "recon_caso05" | "recon_caso06" | "recon_control"
  | "F02" | "F03" | "F01" | "estanteria_900" | "estanteria_variante" | "mueble_bajo" | "espesor_desconocido";

export const ATRIBUCION_PLANK = "PlankAssembly, manycore-research, CC BY-NC-ND 4.0";

export interface CasoMeta {
  id: CasoId;
  titulo: string;
  via: "general" | "legacy" | "tabla" | "reconstruccion";
  /** Con modelo (vía general, GPT) o sin modelo (geometry_only). */
  conModelo: boolean;
  /** Tiene montaje 3D (escena montada o montaje con colocaciones, aunque esté rechazado). */
  montaje: boolean;
  /** Sin montaje pero en la carpeta principal, porque demuestra la PoC (la cajonera). */
  principal?: boolean;
  piezas: number;
  /** Por qué está en la lista y qué falla, en una frase. */
  resumen: string;
}

export const CASOS: readonly CasoMeta[] = [
  { id: "plank_030", titulo: "Armario plank-030", via: "general", conModelo: true, montaje: true, piezas: 10,
    resumen: "10 tipos y 16 piezas; el validador rechaza el montaje con 47 incidencias." },
  { id: "recon_mesa", titulo: "Mesa de trabajo", via: "reconstruccion", conModelo: true, montaje: true, piezas: 4,
    resumen: "Construcción 3D con GLB, versión inicial y refinamiento." },
  { id: "mesa_coste", titulo: "Mesa con revisión y coste", via: "tabla", conModelo: false, montaje: true, piezas: 2,
    resumen: "Mesa de catálogo revisada, con 4 láminas, montaje 3D y estimación de coste." },
  { id: "mesa_002", titulo: "Mesa de dimensiones distintas", via: "tabla", conModelo: false, montaje: true, piezas: 2,
    resumen: "Mesa de catálogo revisada, con montaje 3D, sin láminas ni coste guardados." },
  { id: "estanteria_900", titulo: "Estantería de 900 mm", via: "legacy", conModelo: false, montaje: true, piezas: 4,
    resumen: "Demo procesada sin modelo, con montaje 3D esquemático." },
  { id: "estanteria_variante", titulo: "Estantería de otras dimensiones", via: "legacy", conModelo: false, montaje: true, piezas: 4,
    resumen: "Demo procesada sin modelo, con montaje 3D esquemático." },
  { id: "mueble_bajo", titulo: "Mueble bajo", via: "legacy", conModelo: false, montaje: true, piezas: 4,
    resumen: "Demo procesada sin modelo, con montaje 3D esquemático." },
  { id: "piezas_6ddf", titulo: "Piezas separadas, revisión 2", via: "legacy", conModelo: false, montaje: true, piezas: 4,
    resumen: "Vía de piezas separadas revisada, con montaje 3D." },
  { id: "piezas_c321", titulo: "Piezas separadas, otra ejecución", via: "legacy", conModelo: false, montaje: true, piezas: 4,
    resumen: "Vía de piezas separadas revisada, con montaje 3D." },
  { id: "recon_caso01", titulo: "Mesa con bastidor (estudio)", via: "reconstruccion", conModelo: true, montaje: true, piezas: 9,
    resumen: "Construcción 3D del estudio, caso 01." },
  { id: "recon_caso02", titulo: "Estantería de tres huecos", via: "reconstruccion", conModelo: true, montaje: true, piezas: 7,
    resumen: "Construcción 3D del estudio, caso 02." },
  { id: "recon_caso03", titulo: "Mueble bajo con dos huecos", via: "reconstruccion", conModelo: true, montaje: true, piezas: 6,
    resumen: "Construcción 3D del estudio, caso 03." },
  { id: "recon_caso04", titulo: "Escritorio con armario", via: "reconstruccion", conModelo: true, montaje: true, piezas: 12,
    resumen: "Construcción 3D del estudio, caso 04." },
  { id: "recon_caso05", titulo: "Envolvente alta", via: "reconstruccion", conModelo: true, montaje: true, piezas: 3,
    resumen: "Construcción 3D del estudio, caso 05." },
  { id: "recon_caso06", titulo: "Mueble bajo con puerta", via: "reconstruccion", conModelo: true, montaje: true, piezas: 12,
    resumen: "Construcción 3D del estudio, caso 06." },
  { id: "recon_control", titulo: "Mesa sin escala", via: "reconstruccion", conModelo: true, montaje: true, piezas: 5,
    resumen: "Abstención en la versión 1; la versión 2, con aclaraciones, construye el mueble." },
  { id: "F02", titulo: "Cajonera de tres cajones", via: "general", conModelo: true, montaje: false, principal: true, piezas: 8,
    resumen: "7 tipos de tablero y guías sin medida; el evaluador estricto da 16/21 cotas." },
  { id: "pdf_raster", titulo: "Tornillo de banco (PDF raster)", via: "general", conModelo: true, montaje: false, piezas: 6,
    resumen: "PDF raster sin geometría métrica: propuesta desde la imagen de la página." },
  { id: "plank_016", titulo: "Mueble plank-016", via: "general", conModelo: true, montaje: false, piezas: 11,
    resumen: "11 tipos; el montaje no tiene colocaciones porque falta confirmar la cantidad." },
  { id: "F03", titulo: "Estantería de cuatro baldas", via: "general", conModelo: true, montaje: false, piezas: 3,
    resumen: "9/9 cotas, anclaje a pared propuesto y condicionado; 2/9 bases coinciden con la referencia." },
  { id: "F01", titulo: "Mesa con bastidor", via: "general", conModelo: true, montaje: false, piezas: 4,
    resumen: "Pasa el evaluador estricto (12/12 cotas); grueso de faldones estimado." },
  { id: "espesor_desconocido", titulo: "Control con espesor desconocido", via: "legacy", conModelo: false, montaje: false, piezas: 0,
    resumen: "Sin piezas: el grueso no está en el plano y el caso sigue en revisión." },
];

export interface RunGuardado { casoId: CasoId; runId: string; resultRevision: number; atribucion?: string }

/** Pipeline guardado (data/plank_pipeline_demo/manifest.json), servido por el backend en 18864. */
export const RUNS_PLANK: readonly RunGuardado[] = [
  { casoId: "plank_030", runId: "run-9eb5e3aca8a04331ac0b0d3e5e2f2f40", resultRevision: 1, atribucion: ATRIBUCION_PLANK },
  { casoId: "plank_016", runId: "run-dbf758e4fbcd4b19bff8552201a48d4a", resultRevision: 1, atribucion: ATRIBUCION_PLANK },
  { casoId: "mesa_coste", runId: "run-161fc0b9bf7c46f499ddf84abe105d9b", resultRevision: 2 },
  { casoId: "mesa_002", runId: "run-d5b7fce18fee4c699bc49a5110c75240", resultRevision: 2 },
  { casoId: "piezas_6ddf", runId: "run-6ddf07a4229b40949f5b8d1b1b128e31", resultRevision: 2 },
  { casoId: "piezas_c321", runId: "run-c321bf839d8c4dda9e279b172c10992d", resultRevision: 2 },
  { casoId: "pdf_raster", runId: "run-7267675e450042d7af5ad956fdc0593b", resultRevision: 1 },
];

/** Demo procesada restaurada en el backend (data/muebles_procesados_demo/manifest.json). */
export const RUNS_DEMO: readonly RunGuardado[] = [
  { casoId: "estanteria_900", runId: "run-37671509ad734b64ba80e0f5ae3b5d73", resultRevision: 2 },
  { casoId: "estanteria_variante", runId: "run-939b010819244d97b40a4f806779b1c3", resultRevision: 2 },
  { casoId: "mueble_bajo", runId: "run-6c689b556df4484b9887436eafe7a7fa", resultRevision: 2 },
  { casoId: "espesor_desconocido", runId: "run-4af4c91059af4e3fa05d3f08d3cd5df7", resultRevision: 1 },
];

/**
 * SHA-256 del DXF de entrada de los muebles generales con ejecución con modelo guardada (14 nov). El backend no
 * reproduce la vía general: si un plano subido coincide, se lee su geometría en vivo y el resto sale de lo guardado.
 */
export const GENERALES_GUARDADOS: Readonly<Record<string, CasoId>> = {
  a235d1053b6f045161c0ea2544804d348ebf74e1674d7fa08ba6ade1e0717ed2: "plank_030",
  "91a1f89c04b31f35a5ef73828fb920134cebcce684f638c45184d7b7ca6459e7": "plank_016",
  "314bc7d108c3fd5199be3c80f0482da88c83c229516d144a4a3d1cbb116e6bb8": "F01",
  "971fa577a95f855ff374c37be6db9b8ade3d544965df770a02f164fabb0276f5": "F02",
  b9b0713828553f109d407c8d55fb715aa60837b0e8b1611785dfcdd655c330ff: "F03",
};

/** SHA-256 del source.png de cada trabajo de Construcción 3D: subir ese PNG abre su caso con «Ver el proceso». */
export const RECONSTRUCCIONES_PNG: Readonly<Record<string, CasoId>> = {
  "7cfa538c40532eaab4adef2126fac979c4b12282cca6560eba62635733a36c42": "recon_caso01",
  "1fbd9a1e2cfb63a921ae9d0aca189102762dbf4a54b9ba15586d47ad68eb7f0f": "recon_caso02",
  "21a079d86c3a9e03e3b0e61e8ed60376eb410f73ce0a1148fad76b7c59e65fee": "recon_caso03",
  a90e715e21b448cff318682a82c520949711384640c2954bc760bf56fdad838d: "recon_caso04",
  "959000cac5f5bb43cc264299b76c410df941dea4c647def33581d60fb59f9ac7": "recon_caso05",
  "1cc474a686f0140524ffd86ff501a9fdff865821e4943309366c5c01fb42cfbb": "recon_caso06",
  ff7d3f39fa2d03747d39259c2fe5c87910acfaaa8de6802ce03dc1c493e1d4b8: "recon_control",
  f64bd99dcd90cc347c61917d2d409935460a212e0203fa857f9b8f34e3685890: "recon_mesa",
};

/** Run del backend con el que se abre cada caso en modo real, si existe. */
export const runDeCaso = (casoId: CasoId): RunGuardado | undefined =>
  RUNS_PLANK.find((item) => item.casoId === casoId) ?? RUNS_DEMO.find((item) => item.casoId === casoId);

interface Original { filename: string; media_type: string; sha256: string; content: string }
interface CasoBase {
  schema: "vexplorer-caso-1"; id: CasoId; label: string; synthetic: boolean; control_kind: string | null;
  sources: Record<string, string>; execution: Record<string, unknown>; notes: string[]; drawing: DrawingExtraction | null;
  /** DXF de entrada; falta en los exports que no lo traen (piezas separadas, PDF). */
  original?: Original; events?: EventoRun[]; attribution?: string | null;
  /** Imagen de la página cuando el plano no tiene geometría (PDF raster). */
  preview?: string;
}
export interface CasoGeneralDatos extends CasoBase {
  lane: "general";
  /** F01-F03: outcome congelado con plan de construcción y evaluador. */
  evaluation?: {
    utility_pass: boolean; dimensions_correct: number; dimensions_basis_correct: number; dimensions_required: number;
    estimates_declared: number; estimates_required: number; piece_types_matched: number; piece_types_required: number;
    unmatched_predicted_piece_types: number; construction_missing: string[]; server_validation: string; limitations: string[];
  };
  construction?: GeneralConstructionPlan;
  validation?: GeneralConstructionValidation;
  artifacts?: Omit<GeneralDerivedArtifact, "content">[];
  /** Pipeline guardado: respuestas de GET general, general/derived y general/assembly. */
  record?: GeneralFurnitureRecord;
  derived?: GeneralDerivedResponse;
  assembly?: GeneralAssemblyState;
}
export interface CasoLegacyDatos extends CasoBase {
  lane: "legacy";
  result: Result;
  scene: ReconstructionScene;
  explanations: ExplanationBundle | null;
  estimate: unknown;
}
export interface CasoTablaDatos extends CasoBase {
  lane: "tabla";
  result: { state: string; result_revision: number };
  table: TablaRespuesta;
  scene: ReconstructionScene;
  table_drawings: TablaLaminas | null;
  table_costs: TablaCoste | null;
}
/** Construcción 3D: los trabajos de GET /reconstruction/{job}; GLB e imagen fuente en public/local/reconstruccion. */
export interface CasoReconDatos {
  schema: "vexplorer-caso-1"; id: CasoId; label: string; lane: "reconstruccion"; synthetic: boolean; control_kind: string | null;
  sources: Record<string, string>; execution: Record<string, unknown>; notes: string[]; jobs: TrabajoReconstruccion[];
}
export type CasoDatos = CasoGeneralDatos | CasoLegacyDatos | CasoTablaDatos | CasoReconDatos;

/** Archivos de un trabajo de reconstrucción. En mock, la copia local; en real, cargarCaso recibe las URL del backend. */
export type UrlReconstruccion = (jobId: string, archivo: string) => string;
const URL_LOCAL: UrlReconstruccion = (jobId, archivo) => `./local/reconstruccion/${jobId}/${archivo}`;

const LOADERS: Record<CasoId, () => Promise<{ default: unknown }>> = {
  plank_030: () => import("./datos/plank_030.json"),
  plank_016: () => import("./datos/plank_016.json"),
  mesa_coste: () => import("./datos/mesa_coste.json"),
  mesa_002: () => import("./datos/mesa_002.json"),
  piezas_6ddf: () => import("./datos/piezas_6ddf.json"),
  piezas_c321: () => import("./datos/piezas_c321.json"),
  pdf_raster: () => import("./datos/pdf_raster.json"),
  recon_mesa: () => import("./datos/recon_mesa.json"),
  recon_caso01: () => import("./datos/recon_caso01.json"),
  recon_caso02: () => import("./datos/recon_caso02.json"),
  recon_caso03: () => import("./datos/recon_caso03.json"),
  recon_caso04: () => import("./datos/recon_caso04.json"),
  recon_caso05: () => import("./datos/recon_caso05.json"),
  recon_caso06: () => import("./datos/recon_caso06.json"),
  recon_control: () => import("./datos/recon_control.json"),
  F01: () => import("./datos/F01.json"),
  F02: () => import("./datos/F02.json"),
  F03: () => import("./datos/F03.json"),
  estanteria_900: () => import("./datos/estanteria_900.json"),
  estanteria_variante: () => import("./datos/estanteria_variante.json"),
  mueble_bajo: () => import("./datos/mueble_bajo.json"),
  espesor_desconocido: () => import("./datos/espesor_desconocido.json"),
};

export async function cargarDatosCaso(id: CasoId): Promise<CasoDatos> {
  return (await LOADERS[id]()).default as CasoDatos;
}

/** El DXF de entrada del caso, para «Abrir en CAD». */
export function originalDeCaso(datos: Exclude<CasoDatos, CasoReconDatos>): ArchivoVista | null {
  const o = datos.original;
  if (!o) return null;
  return {
    id: "original", tipo: "dxf_original", formato: "dxf", nombre: o.filename, estado: "listo", motivosIncompleto: [],
    laminaId: null, piezaId: null, url: null, contenido: o.content, mediaType: o.media_type,
  };
}

/** Nombres cortos fijados a mano donde la regla general no basta (componentes de plank-030). */
const NOMBRES_CORTOS: Partial<Record<CasoId, Record<string, string>>> = {
  plank_030: {
    sides: "Laterales", top: "Panel superior", bottom: "Base", divisions: "Paneles horizontales", shelves: "Baldas",
    back_low: "Trasera inferior", back_high: "Trasera superior", fronts: "Frentes", fascias: "Fajas frontales", plinths: "Fajas del zócalo",
  },
};

/** Aplica los nombres cortos del caso a una mesa (también a la que llega del backend en modo real). */
export function conNombresCortos(mesa: MesaTrabajo, casoId: CasoId): MesaTrabajo {
  const mapa = NOMBRES_CORTOS[casoId];
  if (!mapa) return mesa;
  return { ...mesa, piezas: mesa.piezas.map((p) => (mapa[p.id] ? { ...p, nombreCorto: mapa[p.id] } : p)) };
}

/** Convierte los datos congelados al modelo de vista. */
export function mesaDeCaso(datos: CasoDatos, opciones: { reconUrl?: UrlReconstruccion } = {}): MesaTrabajo {
  if (datos.lane === "reconstruccion") {
    return desdeReconstruccion({
      id: datos.id, titulo: datos.label, origen: { tipo: "caso", casoId: datos.id, fuentes: datos.sources }, sintetico: datos.synthetic,
      trabajos: datos.jobs, notas: datos.notes,
      // En mock y en el HTML suelto, el archivo incrustado en el caso; si falta, la copia local.
      url: opciones.reconUrl ?? ((job, archivo) => datos.jobs.find((t) => t.job_id === job)?.media?.[archivo] ?? URL_LOCAL(job, archivo)),
    });
  }
  return conNombresCortos(mesaDeCasoBase(datos), datos.id);
}

function mesaDeCasoBase(datos: CasoGeneralDatos | CasoLegacyDatos | CasoTablaDatos): MesaTrabajo {
  const comun = {
    id: datos.id, titulo: datos.label, origen: { tipo: "caso" as const, casoId: datos.id, fuentes: datos.sources },
    sintetico: datos.synthetic, drawing: datos.drawing, notas: datos.notes,
    original: originalDeCaso(datos), eventos: datos.events ?? null, atribucion: datos.attribution ?? null,
    imagenOriginal: datos.preview ?? null,
  };
  if (datos.lane === "legacy") {
    return desdeLegacy({ ...comun, result: datos.result, scene: datos.scene, explanations: datos.explanations });
  }
  if (datos.lane === "tabla") {
    return desdeTabla({
      ...comun, resultState: datos.result.state, table: datos.table, scene: datos.scene,
      drawings: datos.table_drawings, costs: datos.table_costs,
    });
  }
  if (datos.derived) {
    const pkg = datos.derived.package;
    return desdeGeneral({
      ...comun, record: datos.record ?? null, construction: pkg.construction, validation: datos.record?.review?.construction_validation ?? null,
      bomRows: pkg.bom_rows, packageScene: pkg.scene, packageStatus: pkg.status, assembly: datos.assembly ?? null, artifacts: pkg.artifacts,
    });
  }
  // Propuesta revisada sin derivado exportado (PDF raster): las piezas salen de la propuesta.
  if (datos.record) return desdeGeneral({ ...comun, record: datos.record });
  const ev = datos.evaluation;
  return desdeGeneral({
    ...comun, construction: datos.construction ?? null, validation: datos.validation ?? null, artifacts: datos.artifacts ?? [],
    evaluacion: ev ? {
      aprobado: ev.utility_pass, cotasCorrectas: ev.dimensions_correct, basesCorrectas: ev.dimensions_basis_correct,
      cotasRequeridas: ev.dimensions_required, estimacionesDeclaradas: ev.estimates_declared, estimacionesRequeridas: ev.estimates_required,
      tiposEmparejados: ev.piece_types_matched, tiposRequeridos: ev.piece_types_required, tiposSobrantes: ev.unmatched_predicted_piece_types,
      construccionPendiente: ev.construction_missing, validacionServidor: ev.server_validation, limitaciones: ev.limitations,
    } : null,
  });
}

export async function cargarCaso(id: CasoId, opciones: { reconUrl?: UrlReconstruccion } = {}): Promise<MesaTrabajo> {
  return mesaDeCaso(await cargarDatosCaso(id), opciones);
}
