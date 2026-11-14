/**
 * Modelo de vista de la mesa de trabajo: un único formato para un mueble, venga de la vía general
 * en vivo, de un caso congelado (src/casos) o de un run de la vía legacy (demo procesada).
 *
 * Lo produce src/general/adaptador.ts. La interfaz solo lee este formato y no necesita conocer el
 * contrato del backend. Unidades siempre en mm.
 *
 * MesaTrabajo
 *   id, titulo            identificador estable y nombre para mostrar.
 *   via                   "general" (muebles generales) | "legacy" (vistas montadas, sin modelo)
 *                         | "tabla" (vistas montadas de mesa con programa de catálogo, láminas y coste).
 *   origen                de dónde salió: caso congelado, run en vivo o trabajo en vivo.
 *   sintetico             true si el plano es un control o fixture propio, no de cliente.
 *   estado                resumen: "listo" (nada pendiente) | "incompleto" (hay pendientes, estimaciones
 *                         o archivos incompletos) | "en_revision" | "sin_propuesta" | "error".
 *   plano                 PlanoVista: contornos con id para pintar el lienzo y seleccionar.
 *   piezas                PiezaVista[]: cada pieza enlaza a los ids de `plano.contornos`.
 *   laminas               LaminaVista[]: láminas de construcción con primitivas en mm (piezas y conjunto).
 *   escena                Escena3D: cajas en mm para three.js y lo que no tiene caja con su motivo.
 *   avisos                Aviso[]: avisos del backend (validación, construcción, escena), sin reescribir.
 *   pendientes            Pendiente[]: lo que falta medir, confirmar o pedir al modo con modelo.
 *   artefactos            ArchivoVista[]: BOM, SVG y DXF. Se descarga `contenido` si viene en el caso y si no `url`;
 *                         sin ninguno de los dos, el archivo no está disponible.
 *   original              ArchivoVista del DXF de entrada para «Abrir en CAD», o null.
 *   traza                 PasoTraza[] de src/general/traza.ts: eventos del pipeline agrupados, o [] si no hay.
 *   coste                 CosteVista del backend (solo vía tabla con coste guardado), o null.
 *   atribucion            licencia o atribución de la fuente del plano (p. ej. PlankAssembly), o null.
 *   versiones             versiones del mismo mueble (Construcción 3D padre e hija); [] si solo hay una.
 *   imagenOriginal        URL de la imagen fuente cuando el mueble no parte de un DXF, o null.
 *   evaluacion            solo casos congelados con evaluador offline; null en vivo.
 *   notas                 fallos documentados del caso (de docs/ y *.evaluation.json).
 *
 * Reglas que garantiza el adaptador:
 *   - Una medida sin valor tiene `valor_mm: null`, `estado: "sin_medida"` y texto «sin medida».
 *   - `estimada: true` en lo estimado o hipotético; el texto lleva «≈» delante y el rango si lo hay.
 *   - Los estados del backend no se colapsan: deducida, derivada y calculada son distintas de observada.
 *     `estadoOrigen` conserva el literal del backend.
 *   - `PiezaVista.contornos` solo contiene ids que existen en `plano.contornos`. Los que no existen
 *     van a `contornosAusentes`. Una pieza sin contorno de origen es `inferida: true` y no se le asigna ninguno.
 *   - Escena: "montaje" solo si el backend trae colocaciones 3D, también si el validador lo rechaza
 *     (`validacion.estado`, cajas con `conflicto` en las penetraciones). Si no, "piezas_separadas" es una
 *     distribución por tipos para inspección: cada tipo en una pila, a escala, sin posición real.
 *     Junto a un montaje general, la distribución por tipos va en `escena.alternativa`.
 *     Una pieza con alguna medida desconocida no recibe caja y aparece en `escena.sinCaja`.
 */

export type Via = "general" | "legacy" | "tabla" | "reconstruccion";

export type OrigenVista =
  | { tipo: "caso"; casoId: string; fuentes: Record<string, string> }
  | { tipo: "run"; runId: string; proposalRevision?: number; reviewRevision?: number; resultRevision?: number }
  | { tipo: "trabajo"; jobId: string; runId: string | null };

export type EstadoMesa = "listo" | "incompleto" | "en_revision" | "sin_propuesta" | "error";

export type EstadoMedida =
  | "observada" | "deducida" | "derivada" | "calculada" | "estimada" | "hipotesis"
  | "confirmada" | "sin_medida" | "conflicto";

export type EstadoRevision = "aceptada" | "rechazada" | "conflicto" | "abstencion" | "sin_revisar";

export interface Medida {
  valor_mm: number | null;
  estado: EstadoMedida;
  /** Literal del backend (observed, deduced, calculated…). */
  estadoOrigen: string;
  /** Revisión automática o humana de ese campo, si el backend la da. */
  revision: EstadoRevision | null;
  estimada: boolean;
  rango_mm: { min: number; max: number } | null;
  formula: string | null;
  explicacion: string | null;
  /** «1200 mm», «≈ 22 mm (18-30 mm)» o «sin medida». */
  texto: string;
}

export interface Cantidad {
  valor: number | null;
  estado: EstadoMedida;
  estadoOrigen: string;
  revision: EstadoRevision | null;
  estimada: boolean;
  rango: { min: number; max: number } | null;
  /** «4», «≈ 4» o «sin dato». */
  texto: string;
}

export interface PiezaVista {
  id: string;
  nombre: string;
  /** Nombre para listas («Laterales», «Baldas»); el largo va a la ficha de la pieza. */
  nombreCorto: string;
  rol: string;
  cantidad: Cantidad;
  largo: Medida;
  ancho: Medida;
  grueso: Medida;
  /** Contornos de origen de la pieza, todos presentes en el plano. */
  contornos: string[];
  /** Otros contornos del plano citados como evidencia (vistas, cantos). No son el origen. */
  contornosEvidencia: string[];
  /** Ids de contorno citados que no existen en el plano (debería estar vacío). */
  contornosAusentes: string[];
  /** Sin contorno de origen en el plano: pieza deducida o estimada por el sistema. */
  inferida: boolean;
  laminas: string[];
  /** Referencias de procedencia tal cual (bindings, cotas, premisas). */
  referencias: string[];
  material: string | null;
  acabado: string | null;
  notas: string[];
  /**
   * Solo Construcción 3D: confianza de las medidas según los supuestos de proposal.json, un nivel menos si
   * checks.json marca la pieza. `motivo` es el supuesto que decide el nivel, tal cual.
   */
  confianza?: { nivel: "alta" | "media" | "baja"; motivo: string } | null;
}

export type Punto = [number, number];

export interface ContornoVista {
  id: string;
  vista: string;
  puntos: Punto[];
  cerrado: boolean;
  entidades: string[];
  /** Piezas que lo tienen como contorno de origen. */
  piezas: string[];
  /** Piezas que lo citan como evidencia. */
  piezasEvidencia: string[];
}

export interface TrazoVista { id: string; tipo: string; capa: string; puntos: Punto[]; circulo: { centro: Punto; radio: number } | null }
/** `origen`: "dxf" si viene del plano; "calculada" si se mide sobre la geometría (solo en «Limpio», ver cotas.ts). */
export interface CotaVista { id: string; vista: string; texto: string; valor_mm: number | null; lineas: [Punto, Punto][]; posicionTexto: Punto; origen?: "dxf" | "calculada" }
export interface TextoVista { id: string; vista: string; texto: string; posicion: Punto }

export interface PlanoVista {
  id: string;
  unidad: string;
  /** "mm" si las coordenadas están en mm; "origen" si el plano no declara escala. */
  coordenadas: "mm" | "origen";
  limites: { minX: number; minY: number; maxX: number; maxY: number } | null;
  vistas: { id: string; etiqueta: string; limites: { minX: number; minY: number; maxX: number; maxY: number } }[];
  contornos: ContornoVista[];
  /** Entidades que no forman contorno (líneas sueltas, ejes, cotas sin gráfico). */
  trazos: TrazoVista[];
  cotas: CotaVista[];
  textos: TextoVista[];
  avisos: string[];
  /** Mayor medida conocida del mueble (mm), para no acotar grupos de contornos mayores que él. */
  extensionMaxima_mm?: number | null;
}

export interface PrimitivaLamina {
  tipo: "linea" | "polilinea" | "circulo" | "arco" | "cota" | "texto" | "llamada";
  puntos: Punto[];
  texto: string | null;
  estado: EstadoMedida;
  referencias: string[];
}

export interface ArchivoVista {
  id: string;
  tipo: string;
  formato: "svg" | "dxf" | "csv" | "json" | "glb" | "otro";
  nombre: string;
  estado: "listo" | "incompleto";
  motivosIncompleto: string[];
  laminaId: string | null;
  piezaId: string | null;
  /** URL de descarga en vivo, o null. */
  url: string | null;
  /** Contenido del archivo cuando viaja con los datos (casos congelados con artefactos en git). */
  contenido: string | null;
  mediaType: string | null;
}

export interface LaminaVista {
  id: string;
  tipo: "pieza" | "conjunto";
  titulo: string;
  piezaId: string | null;
  primitivas: PrimitivaLamina[];
  limites: { minX: number; minY: number; maxX: number; maxY: number } | null;
  archivos: ArchivoVista[];
  avisos: Aviso[];
  /** SVG del backend cuando la lámina no trae primitivas (mesas y esquema general). Se pinta como imagen. */
  svg: string | null;
}

export interface Caja {
  id: string;
  piezaId: string;
  ocurrencia: number;
  posicion_mm: { x: number; y: number; z: number };
  tamano_mm: { x: number; y: number; z: number };
  /** Alguna medida de la caja es estimada o la colocación es una hipótesis. */
  estimada: boolean;
  base: string;
  /** La caja aparece en una incidencia de penetración del validador de montaje. */
  conflicto: boolean;
}

export interface Escena3D {
  disposicion: "montaje" | "piezas_separadas" | "no_disponible";
  /** Literal del backend cuando existe (ready, mounted_hypothesis, accepted…). */
  estadoOrigen: string | null;
  sistema: string;
  /** Eje vertical de las coordenadas: "y" en legacy (x=width,y=height,z=depth) y en piezas separadas
   *  (las pilas crecen en y). En montaje general el backend no lo declara: puede venir en z (caso plank-030). */
  ejeVertical: "y" | "z" | "sin_declarar";
  cajas: Caja[];
  sinCaja: { piezaId: string; motivo: string }[];
  limites: { min: { x: number; y: number; z: number }; max: { x: number; y: number; z: number } } | null;
  avisos: string[];
  /** URL de un GLB del backend (reconstrucción 3D), si existe. */
  glbUrl: string | null;
  /** Informe del validador cuando la escena es un montaje general propuesto (p. ej. «rejected»). */
  validacion: {
    estado: string;
    penetracionMax_mm: number;
    incidencias: { codigo: string; etiqueta: string; veces: number; piezas: string[]; ocurrencias: string[] }[];
  } | null;
  /** Otra disposición de las mismas piezas: «Por tipos» junto a un montaje. */
  alternativa: Escena3D | null;
}

export interface Aviso {
  nivel: "info" | "aviso" | "error";
  codigo: string;
  mensaje: string;
  piezas: string[];
  fuente: "construccion" | "validacion" | "artefacto" | "escena" | "plano" | "trabajo" | "resultado";
}

export interface Pendiente {
  id: string;
  tipo: "medir" | "confirmar" | "revisar" | "modelo";
  texto: string;
  piezaId: string | null;
  campos: string[];
}

export interface EvaluacionCaso {
  aprobado: boolean;
  cotasCorrectas: number;
  basesCorrectas: number;
  cotasRequeridas: number;
  estimacionesDeclaradas: number;
  estimacionesRequeridas: number;
  tiposEmparejados: number;
  tiposRequeridos: number;
  tiposSobrantes: number;
  construccionPendiente: string[];
  validacionServidor: string;
  limitaciones: string[];
}

export interface PasoTraza {
  id: string;
  /** Hora local HH:MM del primer evento del grupo, y del último si hay varios. */
  hora: string;
  horaFin: string | null;
  /** Etiqueta corta en español del evento o de la herramienta. */
  etiqueta: string;
  /** tool_name tal cual, si el evento lo trae. */
  herramienta: string | null;
  modelo: string | null;
  /** "ok" o el código de fallo; en un grupo, cada resultado distinto con sus veces. */
  resultados: { resultado: string; veces: number }[];
  /** Estado que declara el payload (p. ej. revisión «incompleta»), traducido. */
  estado: string | null;
  /** Veces que se repite el evento en el grupo. */
  veces: number;
  ok: boolean;
}

export interface CosteVista {
  moneda: string;
  total: number | null;
  /** "complete", "partial"… tal cual del backend. */
  estadoTotal: string;
  horas: number | null;
  precioProvisional: number | null;
  margenPorcentaje: number | null;
  sintetico: boolean;
  conceptos: { id: string; etiqueta: string; importe: number | null; estado: string }[];
  avisos: string[];
}

/** Pipeline de Construcción 3D de un trabajo: archivos reales de cada paso (URL) y datos ya leídos. */
export interface ReconstruccionVista {
  jobId: string;
  revision: number;
  /** Vistas renderizadas del montaje (view-NN.png). */
  vistas: string[];
  /** Siluetas por vista (mask-NN.png), en blanco sobre negro; no separan piezas. */
  mascaras: string[];
  despiece: string | null;
  bomUrl: string | null;
  bom: { id: string; nombre: string; x: number; y: number; z: number; cantidad: number }[];
  laminas: string[];
  comprobaciones: { contactos: number; solapes: number; sinApoyo: number; apoyadas: number };
  /** Unidad con la que entra el plano ("mm" o "relative"). */
  unidad: string | null;
  /** Modelos que razonaron (outcome.trace). */
  modelos: string[];
  /** Estado de la propuesta: "proposed", "insufficient_evidence"… */
  estado: string;
  /** Lectura del modelo: uso interpretado y supuestos del conjunto (sin los de revisión). */
  uso: string;
  supuestos: string[];
  /** Conclusión de la revisión contra el plano original (supuestos que empiezan por «Revisión contra el plano»). */
  conclusionRevision: string[];
  /** Información que falta o preguntas abiertas (missing_information). */
  preguntas: string[];
  /** Render de la propuesta que el modelo compara con el plano (view-00). */
  render: string | null;
}

export interface MesaTrabajo {
  id: string;
  titulo: string;
  via: Via;
  origen: OrigenVista;
  sintetico: boolean;
  estado: EstadoMesa;
  plano: PlanoVista | null;
  piezas: PiezaVista[];
  laminas: LaminaVista[];
  escena: Escena3D;
  avisos: Aviso[];
  pendientes: Pendiente[];
  artefactos: ArchivoVista[];
  evaluacion: EvaluacionCaso | null;
  notas: string[];
  original: ArchivoVista | null;
  traza: PasoTraza[];
  coste: CosteVista | null;
  atribucion: string | null;
  /** Versiones del mismo mueble (Construcción 3D con revisión padre e hija), de la primera a la última. */
  versiones: { id: string; etiqueta: string; mesa: MesaTrabajo }[];
  /** Imagen de la que parte el mueble cuando no hay DXF (Construcción 3D). */
  imagenOriginal: string | null;
  /** Pipeline de Construcción 3D; null en las demás vías. */
  reconstruccion: ReconstruccionVista | null;
}
