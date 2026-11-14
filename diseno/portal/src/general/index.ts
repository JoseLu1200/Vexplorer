/** Punto de entrada de la vía general para la interfaz. Formato documentado en ./modelo.ts. */
export * from "./modelo";
export { desdeGeneral, desdeLegacy, desdeReconstruccion, desdeTabla, planoDesde, escenaSeparada, comprobarEnlaces, etiquetaIncidencia } from "./adaptador";
export { trazaDesdeEventos } from "./traza";
export type { EventoRun } from "./traza";
export type { EntradaGeneral, EntradaLegacy } from "./adaptador";
export { abrirRun, analizarPlano } from "./vivo";
export type { ResultadoAnalisis } from "./vivo";
export { CASOS, RUNS_DEMO, RUNS_PLANK, ATRIBUCION_PLANK, runDeCaso, cargarCaso, cargarDatosCaso, mesaDeCaso, originalDeCaso, conNombresCortos } from "../casos";
export type { CasoId, CasoMeta, CasoDatos, RunGuardado, UrlReconstruccion } from "../casos";
