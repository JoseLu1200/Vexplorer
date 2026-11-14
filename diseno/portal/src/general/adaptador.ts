/**
 * Adaptador al modelo de vista de src/general/modelo.ts. Funciones puras, sin red ni import.meta,
 * para poder usarlas igual en la interfaz y en scripts de Node.
 *
 *   desdeGeneral(entrada)  vía general: plano + construcción/derivado/propuesta + montaje.
 *   desdeLegacy(entrada)   vía legacy: plano + Result + ReconstructionScene (+ explicaciones).
 *   desdeTabla(entrada)    vía de mesa: plano + programa evaluado + escena + láminas SVG/DXF + coste.
 *
 * Los casos congelados (src/casos) y las respuestas en vivo (src/general/vivo.ts) pasan por aquí.
 */
import type {
  DrawingExtraction, GeneralAssemblyState, GeneralBomRow, GeneralConstructionDimension, GeneralConstructionPiece,
  GeneralConstructionPlan, GeneralConstructionQuantity, GeneralConstructionValidation, GeneralDerivedArtifact,
  GeneralAssemblyFrame, GeneralDraftComponent, GeneralFurnitureRecord, GeneralQuantity, GeneralScene, GeneralValue, Point2D,
  ReconstructionScene,
} from "../api/general.gen";
import type { ExplanationBundle, Result } from "../api/types";
import type {
  ArchivoVista, Aviso, Caja, Cantidad, ContornoVista, CosteVista, EstadoMedida, EstadoMesa, EstadoRevision, EvaluacionCaso,
  Escena3D, LaminaVista, Medida, MesaTrabajo, OrigenVista, Pendiente, PiezaVista, PlanoVista, PrimitivaLamina, Punto,
} from "./modelo";
import { trazaDesdeEventos, type EventoRun } from "./traza";

// ---------- Medidas ----------

const ESTADOS: Record<string, EstadoMedida> = {
  observed: "observada", deduced: "deducida", derived: "derivada", calculated: "calculada",
  estimated: "estimada", hypothesis: "hipotesis", confirmed: "confirmada", unknown: "sin_medida",
  conflict: "conflicto", proposed: "hipotesis",
};
const REVISIONES: Record<string, EstadoRevision> = {
  accepted: "aceptada", rejected: "rechazada", conflict: "conflicto", abstained: "abstencion", unreviewed: "sin_revisar",
};
const mm = (value: number) => `${Number.isInteger(value) ? value : Number(value.toFixed(1))} mm`;
const esEstimado = (estado: EstadoMedida) => estado === "estimada" || estado === "hipotesis";

function medida(
  valor: number | null, estadoOrigen: string, extra: Partial<Pick<Medida, "revision" | "rango_mm" | "formula" | "explicacion">> = {},
): Medida {
  const estado: EstadoMedida = valor == null ? (estadoOrigen === "conflict" ? "conflicto" : "sin_medida") : ESTADOS[estadoOrigen] ?? "hipotesis";
  const estimada = valor != null && esEstimado(estado);
  const rango = extra.rango_mm ?? null;
  const texto = valor == null
    ? (estado === "conflicto" ? "en conflicto" : "sin medida")
    : `${estimada ? "≈ " : ""}${mm(valor)}${rango ? ` (${rango.min}-${rango.max} mm)` : ""}`;
  return { valor_mm: valor, estado, estadoOrigen, revision: extra.revision ?? null, estimada, rango_mm: rango, formula: extra.formula ?? null, explicacion: extra.explicacion ?? null, texto };
}

const medidaConstruccion = (d: GeneralConstructionDimension): Medida =>
  medida(d.value_mm, d.state, {
    revision: REVISIONES[d.review_status] ?? null,
    rango_mm: d.range_mm ? { min: d.range_mm.min_mm, max: d.range_mm.max_mm } : null,
    formula: d.formula, explicacion: d.explanation || null,
  });

const medidaValor = (v: GeneralValue): Medida =>
  medida(v.value_mm, v.state, { rango_mm: v.range_mm ? { min: v.range_mm.min_mm, max: v.range_mm.max_mm } : null, formula: v.formula });

function cantidad(valor: number | null, estadoOrigen: string, extra: { revision?: EstadoRevision | null; rango?: { min: number; max: number } | null } = {}): Cantidad {
  const estado: EstadoMedida = valor == null ? "sin_medida" : ESTADOS[estadoOrigen] ?? "hipotesis";
  const estimada = valor != null && esEstimado(estado);
  const rango = extra.rango && extra.rango.min !== extra.rango.max ? extra.rango : null;
  const texto = valor == null ? "sin dato" : `${estimada ? "≈ " : ""}${valor}${rango ? ` (${rango.min}-${rango.max})` : ""}`;
  return { valor, estado, estadoOrigen, revision: extra.revision ?? null, estimada, rango, texto };
}
const cantidadConstruccion = (q: GeneralConstructionQuantity) =>
  cantidad(q.value, q.state, {
    revision: REVISIONES[q.review_status] ?? null,
    rango: q.min_value != null && q.max_value != null ? { min: q.min_value, max: q.max_value } : null,
  });
const cantidadValor = (q: GeneralQuantity) => cantidad(q.value, q.state);

// ---------- Plano ----------

type Limites = { minX: number; minY: number; maxX: number; maxY: number };
const pt = (mmPoint: Point2D | null | undefined, source: Point2D): Punto => {
  const p = mmPoint ?? source;
  return [p.x, p.y];
};
function limitesDe(puntos: Punto[]): Limites | null {
  if (!puntos.length) return null;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of puntos) {
    if (x < minX) minX = x; if (y < minY) minY = y; if (x > maxX) maxX = x; if (y > maxY) maxY = y;
  }
  return { minX, minY, maxX, maxY };
}

export function planoDesde(drawing: DrawingExtraction): PlanoVista {
  const usaMm = drawing.coordinate_unit === "mm";
  const contornoDeEntidad = new Set(drawing.contours.flatMap((c) => c.source_entity_ids));
  const graficoDeEntidad = new Set(drawing.dimension_graphics.map((g) => g.source_entity_id));
  const textoDeEntidad = new Set(drawing.texts.map((t) => t.source_entity_id));
  const contornos: ContornoVista[] = drawing.contours.map((c) => ({
    id: c.id, vista: c.view_id, cerrado: c.closed, entidades: [...c.source_entity_ids],
    puntos: (usaMm && c.points_mm ? c.points_mm : c.points_source).map((p) => [p.x, p.y] as Punto),
    piezas: [], piezasEvidencia: [],
  }));
  const trazos = drawing.entities
    .filter((e) => !contornoDeEntidad.has(e.id) && !graficoDeEntidad.has(e.id) && !textoDeEntidad.has(e.id))
    .map((e) => ({
      id: e.id, tipo: e.kind, capa: e.layer,
      puntos: (usaMm && e.points_mm ? e.points_mm : e.source_points).map((p) => [p.x, p.y] as Punto),
      circulo: e.circular
        ? { centro: pt(usaMm ? e.circular.center_mm : null, e.circular.center_source), radio: (usaMm ? e.circular.radius_mm : null) ?? e.circular.radius_source }
        : null,
    }));
  const valorCota = new Map(drawing.dimensions.map((d) => [d.id, d.value_mm]));
  const cotas = drawing.dimension_graphics.map((g) => {
    const a = pt(usaMm ? g.extension_start_a_mm : null, g.extension_start_a_source);
    const b = pt(usaMm ? g.extension_start_b_mm : null, g.extension_start_b_source);
    const s = pt(usaMm ? g.dimension_start_mm : null, g.dimension_start_source);
    const e = pt(usaMm ? g.dimension_end_mm : null, g.dimension_end_source);
    return {
      id: g.id, vista: g.view_id, texto: g.display_text, valor_mm: valorCota.get(g.dimension_id) ?? null,
      lineas: [[a, s], [b, e], [s, e]] as [Punto, Punto][],
      posicionTexto: pt(usaMm ? g.text_position_mm : null, g.text_position_source),
      origen: "dxf" as const,
    };
  });
  const textos = drawing.texts.map((t) => ({ id: t.id, vista: t.view_id, texto: t.text, posicion: pt(usaMm ? t.position_mm : null, t.position_source) }));
  const todos = [...contornos.flatMap((c) => c.puntos), ...trazos.flatMap((t) => t.puntos), ...cotas.flatMap((c) => c.lineas.flat())];
  return {
    id: drawing.drawing_id,
    unidad: drawing.source_unit,
    coordenadas: usaMm ? "mm" : "origen",
    limites: limitesDe(todos),
    vistas: drawing.views.map((v) => {
      const b = (usaMm ? v.bounds_mm : null) ?? v.bounds_source;
      return { id: v.id, etiqueta: v.label, limites: { minX: b.min_x, minY: b.min_y, maxX: b.max_x, maxY: b.max_y } };
    }),
    contornos, trazos, cotas, textos,
    avisos: [...drawing.warnings],
  };
}

/** Separa los ids de contorno de una pieza en origen, evidencia y ausentes, y anota el vínculo inverso. */
function enlazar(pieza: PiezaVista, origen: string[], citados: string[], plano: PlanoVista | null): void {
  const porId = new Map((plano?.contornos ?? []).map((c) => [c.id, c]));
  const unico = (xs: string[]) => [...new Set(xs)];
  for (const id of unico(origen)) {
    const c = porId.get(id);
    if (c) { pieza.contornos.push(id); c.piezas.push(pieza.id); } else pieza.contornosAusentes.push(id);
  }
  for (const id of unico(citados)) {
    if (pieza.contornos.includes(id) || pieza.contornosAusentes.includes(id)) continue;
    const c = porId.get(id);
    if (c) { pieza.contornosEvidencia.push(id); c.piezasEvidencia.push(pieza.id); }
  }
  pieza.inferida = pieza.contornos.length === 0;
}
/** "contour-entity-8E" o "contour:contour-entity-8E" → "contour-entity-8E". */
const idsContorno = (refs: string[]) =>
  refs.map((r) => (r.startsWith("contour:") ? r.slice("contour:".length) : r)).filter((r) => r.startsWith("contour-"));

// ---------- Láminas y archivos ----------

const FORMATO: Record<string, ArchivoVista["formato"]> = {
  bom_csv: "csv", bom_json: "json", drawing_svg: "svg", drawing_dxf: "dxf",
  construction_overview_svg: "svg", construction_overview_dxf: "dxf", piece_sheet_svg: "svg", piece_sheet_dxf: "dxf",
};
type ArtefactoMeta = Omit<GeneralDerivedArtifact, "content"> & { content?: string };

function archivos(artifacts: ArtefactoMeta[], url: ((id: string) => string) | null): ArchivoVista[] {
  return artifacts.map((a) => ({
    id: a.id, tipo: a.kind, formato: FORMATO[a.kind] ?? "otro", nombre: a.filename,
    estado: a.status === "ready" ? "listo" : "incompleto", motivosIncompleto: [...a.incomplete_reasons],
    laminaId: a.sheet_id, piezaId: a.component_id, url: url ? url(a.id) : null,
    contenido: typeof a.content === "string" && a.content ? a.content : null, mediaType: a.media_type,
  }));
}

const PRIMITIVA: Record<string, PrimitivaLamina["tipo"]> = {
  line: "linea", polyline: "polilinea", circle: "circulo", arc: "arco", dimension: "cota", text: "texto", detail_callout: "llamada",
};
const avisoConstruccion = (w: { severity: string; code: string; message: string; component_refs: string[] }, fuente: Aviso["fuente"]): Aviso => ({
  nivel: w.severity === "error" ? "error" : w.severity === "warning" ? "aviso" : "info",
  codigo: w.code, mensaje: w.message, piezas: [...w.component_refs], fuente,
});

function laminasDesde(plan: GeneralConstructionPlan, ficheros: ArchivoVista[]): LaminaVista[] {
  return plan.sheets.map((s) => {
    const primitivas = s.primitives.map((p) => ({
      tipo: PRIMITIVA[p.kind] ?? "linea", puntos: p.points_mm.map((q) => [q.x, q.y] as Punto),
      texto: p.text, estado: ESTADOS[p.state] ?? "hipotesis", referencias: [...p.source_refs],
    }));
    return {
      id: s.sheet_id, tipo: s.kind === "piece" ? "pieza" : "conjunto", titulo: s.title, piezaId: s.piece_id,
      primitivas, limites: limitesDe(primitivas.flatMap((p) => p.puntos)),
      archivos: ficheros.filter((f) => f.laminaId === s.sheet_id),
      avisos: s.warnings.map((w) => avisoConstruccion(w, "construccion")),
      svg: null,
    };
  });
}

// ---------- Escena ----------

const SISTEMA_GENERAL = "x, y, z en mm del montaje propuesto por el backend";
const SISTEMA_SEPARADAS = "presentación: x = largo, y = grueso, z = ancho; cada tipo en su pila, sin posición real";

function limites3d(cajas: Caja[]): Escena3D["limites"] {
  if (!cajas.length) return null;
  const min = { x: Infinity, y: Infinity, z: Infinity }, max = { x: -Infinity, y: -Infinity, z: -Infinity };
  for (const c of cajas) {
    for (const k of ["x", "y", "z"] as const) {
      min[k] = Math.min(min[k], c.posicion_mm[k]);
      max[k] = Math.max(max[k], c.posicion_mm[k] + c.tamano_mm[k]);
    }
  }
  return { min, max };
}

const escenaVacia = (sistema: string): Escena3D => ({
  disposicion: "no_disponible", estadoOrigen: null, sistema, ejeVertical: "y", cajas: [], sinCaja: [], limites: null,
  avisos: [], glbUrl: null, validacion: null, alternativa: null,
});

/** Piezas por tipos, a escala. Solo se dibuja lo que tiene las tres medidas; el resto va a sinCaja. */
export function escenaSeparada(piezas: PiezaVista[], avisos: string[] = []): Escena3D {
  const cajas: Caja[] = [];
  const sinCaja: Escena3D["sinCaja"] = [];
  const HUECO_X = 120, HUECO_Y = 12;
  let x = 0;
  for (const p of piezas) {
    const faltan = (["largo", "ancho", "grueso"] as const).filter((k) => p[k].valor_mm == null);
    if (faltan.length) { sinCaja.push({ piezaId: p.id, motivo: `sin medida: ${faltan.join(", ")}` }); continue; }
    const largo = p.largo.valor_mm!, ancho = p.ancho.valor_mm!, grueso = p.grueso.valor_mm!;
    const n = p.cantidad.valor ?? 1;
    if (p.cantidad.valor == null) sinCaja.push({ piezaId: p.id, motivo: "cantidad sin dato: se dibuja una sola" });
    for (let i = 0; i < n; i++) {
      cajas.push({
        id: `${p.id}#${i + 1}`, piezaId: p.id, ocurrencia: i + 1,
        posicion_mm: { x, y: i * (grueso + HUECO_Y), z: 0 }, tamano_mm: { x: largo, y: grueso, z: ancho },
        estimada: p.largo.estimada || p.ancho.estimada || p.grueso.estimada, base: "disposición de presentación", conflicto: false,
      });
    }
    x += largo + HUECO_X;
  }
  return { ...escenaVacia(SISTEMA_SEPARADAS), disposicion: cajas.length ? "piezas_separadas" : "no_disponible", cajas, sinCaja, limites: limites3d(cajas), avisos };
}

/** Códigos del validador de montaje con una etiqueta fija en español. El código original se conserva. */
const INCIDENCIA: Record<string, string> = {
  aabb_penetration: "Penetración entre piezas",
  shared_evidence_identity: "Evidencia compartida por dos piezas",
  shared_contour_identity: "Contorno compartido por dos piezas",
  contour_box_fit_residual: "Contorno no rectangular para una caja",
  assembly_confirmed_quantity_required: "Falta confirmar la cantidad",
  assembly_reviewed_dimensions_required: "Faltan medidas revisadas",
};
export const etiquetaIncidencia = (codigo: string) => INCIDENCIA[codigo] ?? codigo;

/** Eje vertical declarado por el marco de alzado del candidato ("front", vertical_axis). */
function ejeDeMarcos(frames: GeneralAssemblyFrame[] | undefined): Escena3D["ejeVertical"] {
  const front = frames?.find((f) => f.id === "front") ?? frames?.[0];
  const axis = front?.vertical_axis.slice(1);
  return axis === "z" ? "z" : axis === "y" ? "y" : "sin_declarar";
}

type Incidencia = NonNullable<Escena3D["validacion"]>["incidencias"][number];

/** Incidencias del informe de montaje agrupadas por código, con las piezas implicadas. */
function incidencias(assembly: GeneralAssemblyState): Incidencia[] {
  const report = assembly.current.report;
  const piezaDe = new Map<string, string>();
  for (const p of report.placements) piezaDe.set(p.occurrence_id, p.component_id);
  for (const p of assembly.current.candidate?.placements ?? []) piezaDe.set(p.occurrence_id, p.component_id);
  const grupos = new Map<string, { codigo: string; etiqueta: string; veces: number; piezas: Set<string>; ocurrencias: Set<string> }>();
  for (const issue of report.issues) {
    const g = grupos.get(issue.code) ?? { codigo: issue.code, etiqueta: etiquetaIncidencia(issue.code), veces: 0, piezas: new Set<string>(), ocurrencias: new Set<string>() };
    g.veces += 1;
    for (const o of issue.occurrence_ids) {
      g.ocurrencias.add(o);
      const pieza = piezaDe.get(o);
      if (pieza) g.piezas.add(pieza);
    }
    grupos.set(issue.code, g);
  }
  return [...grupos.values()].sort((a, b) => b.veces - a.veces).map((g) => ({ ...g, piezas: [...g.piezas], ocurrencias: [...g.ocurrencias] }));
}

function escenaMontajeGeneral(assembly: GeneralAssemblyState | null, scene: GeneralScene | null, piezas: PiezaVista[]): Escena3D | null {
  const deEstimada = (componentId: string) => {
    const p = piezas.find((x) => x.id === componentId);
    return p ? p.largo.estimada || p.ancho.estimada || p.grueso.estimada : true;
  };
  const placements = assembly?.current.report.placements ?? [];
  if (assembly && placements.length) {
    const report = assembly.current.report;
    const grupos = incidencias(assembly);
    const penetran = new Set(grupos.find((g) => g.codigo === "aabb_penetration")?.ocurrencias ?? []);
    const cajas = placements.map((pl) => ({
      id: pl.occurrence_id, piezaId: pl.component_id, ocurrencia: pl.occurrence_index,
      posicion_mm: { ...pl.position_mm }, tamano_mm: { ...pl.size_mm },
      estimada: assembly.status !== "accepted" || deEstimada(pl.component_id), base: `montaje ${assembly.status}`,
      conflicto: penetran.has(pl.occurrence_id),
    }));
    return {
      ...escenaVacia(SISTEMA_GENERAL), disposicion: "montaje", estadoOrigen: assembly.status, ejeVertical: ejeDeMarcos(assembly.current.candidate?.frames),
      cajas, limites: limites3d(cajas), avisos: [...(report.scene?.warnings ?? [])],
      validacion: { estado: report.status, penetracionMax_mm: report.max_penetration_mm, incidencias: grupos },
    };
  }
  const placed = (scene?.items ?? []).filter((i) => i.status === "placed_hypothesis" && i.position_mm && i.size_mm);
  if (placed.length) {
    const cajas = placed.map((i) => ({
      id: i.id, piezaId: i.component_id, ocurrencia: i.occurrence_index ?? 1,
      posicion_mm: { ...i.position_mm! }, tamano_mm: { ...i.size_mm! }, estimada: true, base: "placed_hypothesis", conflicto: false,
    }));
    return { ...escenaVacia(SISTEMA_GENERAL), disposicion: "montaje", estadoOrigen: scene!.status, ejeVertical: "sin_declarar", cajas, limites: limites3d(cajas), avisos: [...scene!.warnings] };
  }
  return null;
}

// ---------- Pendientes ----------

const CAMPO: Record<string, string> = { largo: "largo", ancho: "ancho", grueso: "grueso" };
function pendientesDePieza(p: PiezaVista): Pendiente[] {
  const out: Pendiente[] = [];
  const medidas = (["largo", "ancho", "grueso"] as const);
  const sin = medidas.filter((k) => p[k].valor_mm == null);
  if (sin.length) out.push({ id: `${p.id}:medir`, tipo: "medir", piezaId: p.id, campos: sin.map((k) => CAMPO[k]), texto: `${p.nombre}: sin medida de ${sin.join(", ")}.` });
  const est = medidas.filter((k) => p[k].estimada);
  if (est.length) out.push({ id: `${p.id}:confirmar`, tipo: "confirmar", piezaId: p.id, campos: est.map((k) => CAMPO[k]), texto: `${p.nombre}: ${est.join(", ")} estimado, falta confirmarlo.` });
  if (p.cantidad.valor == null) out.push({ id: `${p.id}:cantidad`, tipo: "medir", piezaId: p.id, campos: ["cantidad"], texto: `${p.nombre}: cantidad sin dato.` });
  const rev = medidas.filter((k) => p[k].revision && p[k].revision !== "aceptada");
  if (rev.length) out.push({ id: `${p.id}:revision`, tipo: "revisar", piezaId: p.id, campos: rev.map((k) => CAMPO[k]), texto: `${p.nombre}: la revisión no aceptó ${rev.join(", ")}.` });
  return out;
}

/** Campos comunes a las tres vías que vienen de fuera del contrato de piezas. */
interface Extras {
  original?: ArchivoVista | null;
  eventos?: EventoRun[] | null;
  atribucion?: string | null;
  imagenOriginal?: string | null;
}
const extras = (e: Extras): Pick<MesaTrabajo, "original" | "traza" | "atribucion" | "versiones" | "imagenOriginal" | "reconstruccion"> => ({
  original: e.original ?? null, traza: e.eventos ? trazaDesdeEventos(e.eventos) : [], atribucion: e.atribucion ?? null,
  versiones: [], imagenOriginal: e.imagenOriginal ?? null, reconstruccion: null,
});

// ---------- Vía general ----------

export interface EntradaGeneral extends Extras {
  id: string;
  titulo: string;
  origen: OrigenVista;
  sintetico: boolean;
  drawing: DrawingExtraction | null;
  /** Plan de construcción (derived.package.construction). Prioritario si existe. */
  construction?: GeneralConstructionPlan | null;
  validation?: GeneralConstructionValidation | null;
  /** Filas BOM del derivado, si no hay plan de construcción. */
  bomRows?: GeneralBomRow[] | null;
  /** Propuesta sin derivado (sin revisión todavía). */
  record?: GeneralFurnitureRecord | null;
  packageScene?: GeneralScene | null;
  packageStatus?: "ready" | "incomplete" | null;
  assembly?: GeneralAssemblyState | null;
  artifacts?: ArtefactoMeta[];
  artifactUrl?: ((artifactId: string) => string) | null;
  glbUrl?: string | null;
  evaluacion?: EvaluacionCaso | null;
  notas?: string[];
  /** Avisos externos (estado del trabajo, falta de modelo). */
  avisos?: Aviso[];
  pendientes?: Pendiente[];
}

/** Nombre corto por regla: hasta el primer «;» y sin complementos de lugar («del cuerpo», «entre laterales»…). */
export function acortarNombre(nombre: string): string {
  let corto = nombre.split(";")[0].trim();
  for (const sep of [" entre ", " sobre ", " del ", " de los ", " de las ", " de la ", " de ", " candidat"]) {
    const i = corto.indexOf(sep);
    if (i > 2) corto = corto.slice(0, i);
  }
  return corto;
}

function piezaVacia(id: string, nombre: string, rol: string, q: Cantidad, l: Medida, w: Medida, t: Medida): PiezaVista {
  return { id, nombre, nombreCorto: acortarNombre(nombre), rol, cantidad: q, largo: l, ancho: w, grueso: t, contornos: [], contornosEvidencia: [], contornosAusentes: [], inferida: true, laminas: [], referencias: [], material: null, acabado: null, notas: [] };
}

function piezasConstruccion(plan: GeneralConstructionPlan, plano: PlanoVista | null): PiezaVista[] {
  return plan.pieces.map((p: GeneralConstructionPiece) => {
    const pieza = piezaVacia(p.piece_id, p.label, p.role, cantidadConstruccion(p.quantity), medidaConstruccion(p.length), medidaConstruccion(p.width), medidaConstruccion(p.thickness));
    pieza.laminas = [...p.sheet_ids];
    pieza.referencias = [...p.source_refs];
    if (p.geometry.rationale) pieza.notas.push(p.geometry.rationale);
    if (p.quantity.explanation) pieza.notas.push(p.quantity.explanation);
    enlazar(pieza, p.geometry.source_contour_ids, [...idsContorno(p.source_refs), ...idsContorno(p.geometry.basis_refs)], plano);
    return pieza;
  });
}

function piezasValores(
  rows: { id: string; label: string; role: string; quantity: GeneralQuantity; length: GeneralValue; width: GeneralValue; thickness: GeneralValue; source_contour_ids: string[]; refs: string[]; material?: string | null; finish?: string | null }[],
  plano: PlanoVista | null,
): PiezaVista[] {
  return rows.map((r) => {
    const pieza = piezaVacia(r.id, r.label, r.role, cantidadValor(r.quantity), medidaValor(r.length), medidaValor(r.width), medidaValor(r.thickness));
    pieza.referencias = [...r.refs];
    pieza.material = r.material ?? null;
    pieza.acabado = r.finish ?? null;
    enlazar(pieza, r.source_contour_ids, idsContorno(r.refs), plano);
    return pieza;
  });
}

export function desdeGeneral(e: EntradaGeneral): MesaTrabajo {
  const plano = e.drawing ? planoDesde(e.drawing) : null;
  const ficheros = archivos(e.artifacts ?? [], e.artifactUrl ?? null);
  const avisos: Aviso[] = [...(e.avisos ?? [])];
  const pendientes: Pendiente[] = [...(e.pendientes ?? [])];
  let piezas: PiezaVista[] = [];
  let laminas: LaminaVista[] = [];

  if (e.construction) {
    piezas = piezasConstruccion(e.construction, plano);
    laminas = laminasDesde(e.construction, ficheros);
    avisos.push(...e.construction.warnings.map((w) => avisoConstruccion(w, "construccion")));
  } else if (e.bomRows?.length) {
    piezas = piezasValores(e.bomRows.map((r) => ({
      id: r.component_id, label: r.label, role: r.role, quantity: r.quantity, length: r.length, width: r.width, thickness: r.thickness,
      source_contour_ids: r.source_contour_ids, refs: [...r.source_evidence_ids, ...r.source_dimension_ids],
      material: r.material.value, finish: r.finish.value,
    })), plano);
  } else if (e.record) {
    piezas = piezasValores(e.record.draft.components.map((c: GeneralDraftComponent) => ({
      id: c.id, label: c.label, role: c.role, quantity: c.quantity, length: c.length, width: c.width, thickness: c.thickness,
      source_contour_ids: c.source_contour_ids, refs: [...c.source_evidence_ids, ...c.source_dimension_ids, ...c.geometry.basis_refs],
    })), plano);
    pendientes.push({ id: "propuesta:revisar", tipo: "revisar", piezaId: null, campos: [], texto: "La propuesta todavía no tiene revisión ni despiece derivado." });
  }
  // Sin plan de construcción, el esquema general del backend (drawing_svg) es la lámina del conjunto.
  const esquema = ficheros.find((f) => f.tipo === "drawing_svg" && f.contenido);
  if (!laminas.length && esquema) {
    laminas = [{
      id: esquema.id, tipo: "conjunto", titulo: "Esquema de componentes", piezaId: null, primitivas: [], limites: null,
      archivos: ficheros.filter((f) => f.tipo === "drawing_svg" || f.tipo === "drawing_dxf"), avisos: [], svg: esquema.contenido,
    }];
  }
  for (const p of piezas) pendientes.push(...pendientesDePieza(p));

  if (e.validation) {
    for (const i of e.validation.issues) avisos.push({ nivel: i.severity === "error" ? "error" : "aviso", codigo: i.code, mensaje: i.message, piezas: [], fuente: "validacion" });
    if (e.validation.status !== "valid") avisos.push({ nivel: "aviso", codigo: `validacion_${e.validation.status}`, mensaje: `La validación constructiva del servidor da «${e.validation.status}».`, piezas: [], fuente: "validacion" });
  }
  for (const f of ficheros.filter((x) => x.estado === "incompleto" && !x.laminaId)) {
    avisos.push({ nivel: "info", codigo: `${f.tipo}_incompleto`, mensaje: `${f.nombre} está incompleto: ${f.motivosIncompleto.join(", ")}.`, piezas: [], fuente: "artefacto" });
  }

  const montaje = escenaMontajeGeneral(e.assembly ?? null, e.packageScene ?? null, piezas);
  const porTipos = escenaSeparada(piezas, [...(e.packageScene?.warnings ?? [])]);
  if (e.packageScene) porTipos.estadoOrigen = e.packageScene.status;
  const escena: Escena3D = montaje ? { ...montaje, alternativa: porTipos.cajas.length ? porTipos : null } : porTipos;
  escena.glbUrl = e.glbUrl ?? null;
  // Informe del validador de montaje: un aviso por código, con sus piezas, aunque no haya colocaciones.
  if (e.assembly) {
    const report = e.assembly.current.report;
    for (const g of incidencias(e.assembly)) {
      avisos.push({ nivel: "error", codigo: g.codigo, mensaje: `${g.etiqueta}${g.veces > 1 ? ` (${g.veces})` : ""}`, piezas: g.piezas, fuente: "escena" });
    }
    if (report.placements.length && report.status !== "accepted") {
      const estado = report.status === "rejected" ? "rechazado" : report.status;
      avisos.push({ nivel: "aviso", codigo: `montaje_${report.status}`, mensaje: `Montaje ${estado} por el validador; penetración máxima ${Number(report.max_penetration_mm.toFixed(1))} mm.`, piezas: [], fuente: "escena" });
    }
  }

  const hayPiezas = piezas.length > 0;
  // "listo" solo sin nada pendiente: una estimación por confirmar o un BOM incompleto ya es "incompleto".
  const incompleto = pendientes.length > 0 || (e.validation != null && e.validation.status !== "valid")
    || e.packageStatus === "incomplete" || ficheros.some((f) => f.estado === "incompleto");
  const estado: EstadoMesa = !hayPiezas ? (avisos.some((a) => a.nivel === "error") ? "error" : "sin_propuesta")
    : e.record && !e.construction && !e.bomRows?.length ? "en_revision"
    : incompleto ? "incompleto" : "listo";

  return {
    id: e.id, titulo: e.titulo, via: "general", origen: e.origen, sintetico: e.sintetico, estado,
    plano, piezas, laminas, escena, avisos, pendientes,
    artefactos: ficheros.filter((f) => !f.laminaId), evaluacion: e.evaluacion ?? null, notas: e.notas ?? [],
    coste: null, ...extras(e),
  };
}

// ---------- Vía legacy (vistas montadas, demo procesada) ----------

export interface EntradaLegacy extends Extras {
  id: string;
  titulo: string;
  origen: OrigenVista;
  sintetico: boolean;
  drawing: DrawingExtraction | null;
  result: Result;
  scene: ReconstructionScene | null;
  explanations?: ExplanationBundle | null;
  notas?: string[];
  avisos?: Aviso[];
}

const CAMPOS_LEGACY = [["largo", "length_mm"], ["ancho", "width_mm"], ["grueso", "thickness_mm"]] as const;

/** Escena de GET /runs/{id}/scene (legacy y mesa): objetos colocados, y = altura. */
function escenaReconstruccion(scene: ReconstructionScene | null, piezas: PiezaVista[]): Escena3D {
  if (scene && scene.objects.length) {
    const cajas = scene.objects.map((o) => ({
      id: o.id, piezaId: o.piece_id, ocurrencia: o.occurrence_index,
      posicion_mm: { ...o.bbox_mm.min }, tamano_mm: { ...o.dimensions_mm },
      estimada: o.placement_status === "hypothesis", base: o.placement_basis, conflicto: false,
    }));
    return { ...escenaVacia(scene.coordinate_system), disposicion: "montaje", estadoOrigen: scene.state, cajas, limites: limites3d(cajas), avisos: [...scene.warnings, ...scene.assumptions] };
  }
  const escena = escenaSeparada(piezas, scene ? [...scene.warnings, ...scene.assumptions] : []);
  if (scene) escena.estadoOrigen = scene.state;
  return escena;
}
const avisosEscena = (scene: ReconstructionScene | null): Aviso[] => (scene?.warnings ?? []).map((w) => ({
  nivel: "aviso", codigo: w, mensaje: w === "human_review_required" ? "La escena 3D espera a la revisión humana." : w, piezas: [], fuente: "escena",
}));

export function desdeLegacy(e: EntradaLegacy): MesaTrabajo {
  const plano = e.drawing ? planoDesde(e.drawing) : null;
  const explicaciones = new Map((e.explanations?.pieces ?? []).map((x) => [x.piece_id, x]));
  const avisos: Aviso[] = [...(e.avisos ?? [])];
  const pendientes: Pendiente[] = [];
  const piezas = e.result.pieces.map((p) => {
    const ex = explicaciones.get(p.id);
    const formula = (campo: string) => ex?.formulas.find((f) => f.field === campo)?.expression ?? null;
    const [l, w, t] = CAMPOS_LEGACY.map(([, campo]) => medida(p[campo], p.field_states[campo] ?? (p[campo] == null ? "unknown" : "observed"), { formula: formula(campo) }));
    const pieza = piezaVacia(p.id, p.label, p.role, cantidad(p.quantity, p.field_states.quantity ?? "unknown"), l, w, t);
    pieza.referencias = [...p.evidence_ids];
    pieza.material = p.material;
    pieza.acabado = p.finish;
    if (p.human_confirmation) pieza.notas.push(p.human_confirmation);
    enlazar(pieza, p.source_contour_ids, ex?.source_contour_ids ?? [], plano);
    return pieza;
  });
  for (const p of piezas) pendientes.push(...pendientesDePieza(p));
  if (e.result.state === "needs_review") {
    const escenarios = e.result.scenarios.map((s) => s.title);
    pendientes.push({
      id: "resultado:revision", tipo: "revisar", piezaId: null, campos: [],
      texto: piezas.length ? "El resultado sigue pendiente de revisión humana."
        : `Sin piezas resueltas: hay que elegir entre ${escenarios.length} escenarios (${escenarios.join("; ")}) y confirmar lo que falta.`,
    });
  }
  const escena = escenaReconstruccion(e.scene, piezas);
  avisos.push(...avisosEscena(e.scene));

  const estado: EstadoMesa = !piezas.length ? "sin_propuesta" : e.result.state === "needs_review" ? "en_revision"
    : pendientes.length ? "incompleto" : "listo";
  return {
    id: e.id, titulo: e.titulo, via: "legacy", origen: e.origen, sintetico: e.sintetico, estado,
    plano, piezas, laminas: [], escena, avisos, pendientes, artefactos: [], evaluacion: null, notas: e.notas ?? [],
    coste: null, ...extras(e),
  };
}

// ---------- Vía tabla (vistas montadas de mesa: programa de catálogo, láminas y coste) ----------

interface ValorTabla { value_mm: number | null; state: string }
/** EvaluatedTableComponent (modelos.py), solo los campos que se usan. */
export interface ComponenteTabla { id: string; role: string; length: ValorTabla; width: ValorTabla; thickness: ValorTabla; quantity: number | null; accepted: boolean; evidence_ids: string[] }
/** GET /runs/{id}/table */
export interface TablaRespuesta { result_revision: number; state: string; selected_table_program_id: string | null; evaluated_table_program: { state: string; components: ComponenteTabla[]; issues: unknown[] } | null }
/** GET /runs/{id}/table-drawings. `content` y `filename` solo en casos congelados. */
export interface TablaLaminas {
  result_revision: number; program_hash: string;
  sheets: { sheet_id: string; kind: string; title: string; component_id: string | null; status: string; warnings: string[]; formats: { format: string; media_type: string; url: string; content?: string; filename?: string }[] }[];
}
/** GET /runs/{id}/table-costs */
export interface TablaCoste {
  currency: string; grand_total_eur: number | null; total_state: string; total_hours: number | null;
  provisional_sale_price_eur: number | null; provisional_margin_percent: number | null; synthetic: boolean; warnings: string[];
  concepts: { id: string; label: string; amount_eur: number | null; state: string }[];
}

export interface EntradaTabla extends Extras {
  id: string;
  titulo: string;
  origen: OrigenVista;
  sintetico: boolean;
  drawing: DrawingExtraction | null;
  resultState: string;
  table: TablaRespuesta | null;
  scene: ReconstructionScene | null;
  drawings: TablaLaminas | null;
  costs: TablaCoste | null;
  /** Rutas del manifiesto de láminas (/api/v1/…) a URL absoluta, en vivo. */
  url?: ((path: string) => string) | null;
  notas?: string[];
  avisos?: Aviso[];
}

/** Nombre corto para los roles del catálogo de mesas. */
const ROL_TABLA: Record<string, string> = {
  tabletop: "Tablero", side_support: "Soporte lateral", leg: "Pata", corner_support: "Soporte de esquina", apron: "Faldón", stretcher: "Travesaño",
};

export function desdeTabla(e: EntradaTabla): MesaTrabajo {
  const plano = e.drawing ? planoDesde(e.drawing) : null;
  const avisos: Aviso[] = [...(e.avisos ?? [])];
  const pendientes: Pendiente[] = [];
  const contornosEscena = new Map<string, string[]>();
  for (const o of e.scene?.objects ?? []) contornosEscena.set(o.piece_id, [...(contornosEscena.get(o.piece_id) ?? []), ...o.source_contour_ids]);
  const componentes = e.table?.evaluated_table_program?.components ?? [];
  const piezas = componentes.map((c) => {
    // La cantidad sale de la regla del programa de catálogo, no de una cota: estado "derived".
    const pieza = piezaVacia(c.id, ROL_TABLA[c.role] ?? c.role, c.role, cantidad(c.quantity, "derived"),
      medida(c.length.value_mm, c.length.state), medida(c.width.value_mm, c.width.state), medida(c.thickness.value_mm, c.thickness.state));
    pieza.referencias = [...c.evidence_ids];
    if (!c.accepted) pieza.notas.push("Componente no aceptado por el programa evaluado.");
    // Origen: los contornos de sus objetos en la escena; antes de la revisión no hay escena y valen los de su evidencia.
    const evidencia = idsContorno(c.evidence_ids.map((id) => id.replace(/^evidence-/, "")));
    enlazar(pieza, contornosEscena.get(c.id) ?? evidencia, evidencia, plano);
    return pieza;
  });
  for (const p of piezas) pendientes.push(...pendientesDePieza(p));
  if (e.resultState === "needs_review") pendientes.push({ id: "resultado:revision", tipo: "revisar", piezaId: null, campos: [], texto: "El resultado sigue pendiente de revisión humana." });

  const archivosLamina = (s: TablaLaminas["sheets"][number]): ArchivoVista[] => s.formats.map((f) => ({
    id: `${s.sheet_id}.${f.format}`, tipo: `table_sheet_${f.format}`, formato: f.format === "svg" ? "svg" : f.format === "dxf" ? "dxf" : "otro",
    nombre: f.filename ?? `${s.sheet_id}.${f.format}`, estado: s.status === "ready" ? "listo" : "incompleto", motivosIncompleto: [...s.warnings],
    laminaId: s.sheet_id, piezaId: s.component_id, url: e.url ? e.url(f.url) : null, contenido: f.content ?? null, mediaType: f.media_type,
  }));
  const laminas: LaminaVista[] = (e.drawings?.sheets ?? []).map((s) => {
    const ficheros = archivosLamina(s);
    return {
      id: s.sheet_id, tipo: s.kind === "component" ? "pieza" : "conjunto", titulo: s.title, piezaId: s.component_id,
      primitivas: [], limites: null, archivos: ficheros,
      avisos: s.warnings.map((w) => ({ nivel: "aviso" as const, codigo: "lamina", mensaje: w, piezas: s.component_id ? [s.component_id] : [], fuente: "construccion" as const })),
      svg: ficheros.find((f) => f.formato === "svg")?.contenido ?? null,
    };
  });
  for (const p of piezas) p.laminas = laminas.filter((l) => l.piezaId === p.id).map((l) => l.id);

  const escena = escenaReconstruccion(e.scene, piezas);
  avisos.push(...avisosEscena(e.scene));
  const c = e.costs;
  const coste: CosteVista | null = c ? {
    moneda: c.currency, total: c.grand_total_eur, estadoTotal: c.total_state, horas: c.total_hours,
    precioProvisional: c.provisional_sale_price_eur, margenPorcentaje: c.provisional_margin_percent, sintetico: c.synthetic,
    conceptos: c.concepts.map((x) => ({ id: x.id, etiqueta: x.label, importe: x.amount_eur, estado: x.state })), avisos: [...c.warnings],
  } : null;

  const estado: EstadoMesa = !piezas.length ? "sin_propuesta" : e.resultState === "needs_review" ? "en_revision" : pendientes.length ? "incompleto" : "listo";
  return {
    id: e.id, titulo: e.titulo, via: "tabla", origen: e.origen, sintetico: e.sintetico, estado,
    plano, piezas, laminas, escena, avisos, pendientes, artefactos: [], evaluacion: null, notas: e.notas ?? [],
    coste, ...extras(e),
  };
}

/** Comprueba que cada pieza y cada caja apuntan a ids existentes. Devuelve la lista de fallos. */
export function comprobarEnlaces(mesa: MesaTrabajo): string[] {
  const fallos: string[] = [];
  const contornos = new Set(mesa.plano?.contornos.map((c) => c.id) ?? []);
  const piezas = new Set(mesa.piezas.map((p) => p.id));
  const laminas = new Set(mesa.laminas.map((l) => l.id));
  for (const p of mesa.piezas) {
    for (const id of [...p.contornos, ...p.contornosEvidencia]) if (!contornos.has(id)) fallos.push(`${mesa.id}/${p.id}: contorno ${id} no está en el plano`);
    for (const id of p.contornosAusentes) fallos.push(`${mesa.id}/${p.id}: cita el contorno ${id}, que no existe en el plano`);
    for (const id of p.laminas) if (!laminas.has(id)) fallos.push(`${mesa.id}/${p.id}: lámina ${id} inexistente`);
    if (p.inferida !== (p.contornos.length === 0)) fallos.push(`${mesa.id}/${p.id}: marca inferida incoherente`);
  }
  for (const escena of [mesa.escena, mesa.escena.alternativa].filter((x): x is Escena3D => !!x)) {
    for (const c of escena.cajas) if (!piezas.has(c.piezaId)) fallos.push(`${mesa.id}: caja ${c.id} apunta a la pieza ${c.piezaId}, que no existe`);
  }
  for (const l of mesa.laminas) if (l.piezaId && !piezas.has(l.piezaId)) fallos.push(`${mesa.id}: lámina ${l.id} apunta a la pieza ${l.piezaId}, que no existe`);
  for (const a of mesa.avisos) for (const id of a.piezas) if (!piezas.has(id)) fallos.push(`${mesa.id}: aviso ${a.codigo} apunta a la pieza ${id}, que no existe`);
  return fallos;
}

// ---------- Vía de Construcción 3D (reconstruction3d: propuesta de montaje y GLB) ----------

/** Componente de AssemblyProposal (reconstruction3d/models.py): caja con origen en la esquina, x ancho, y fondo, z alto. */
export interface ComponenteReconstruccion { id: string; label: string; size_mm: number[]; origin_mm: number[]; source_refs: string[]; assumptions: string[] }
/** Un trabajo de GET /reconstruction/{job}, con los campos que usa el portal. */
export interface TrabajoReconstruccion {
  job_id: string;
  status: string;
  revision: number;
  parent_job_id: string | null;
  unit: string | null;
  intended_use_from_user?: string | null;
  geometry_provenance?: string;
  proposal: { status: string; intended_use: string; unit: string; components: ComponenteReconstruccion[]; assumptions: string[]; missing_information: string[]; functional_notes: string[] } | null;
  checks: { contacts?: unknown[]; overlaps?: unknown[]; floating_ids?: string[]; below_ground_ids?: string[]; grounded_ids?: string[] } | null;
  has_glb: boolean;
  /** Solo en los casos congelados: SHA-256 de source.png, archivos del pipeline y filas de bom.csv. */
  source_sha256?: string | null;
  files?: { views: string[]; masks: string[]; exploded: string | null; bom: string | null; parts: string[] };
  bom_rows?: Record<string, string>[];
  /** Solo en los casos congelados: cada archivo del pipeline como data URL, por nombre. */
  media?: Record<string, string>;
  models?: string[];
}

export interface EntradaReconstruccion {
  id: string;
  titulo: string;
  origen: OrigenVista;
  sintetico: boolean;
  /** Trabajos de la primera a la última versión. */
  trabajos: TrabajoReconstruccion[];
  /** URL de un archivo del trabajo: "assembly.glb", "source.png" o un artefacto («view-00.png», «parts/x.svg»…). */
  url: (jobId: string, archivo: string) => string;
  notas?: string[];
}

/**
 * Confianza de una pieza de Construcción 3D a partir de sus supuestos (proposal.json):
 *   baja   si la medida es hipótesis, decisión de diseño, elegida, propuesta sin medir, añadida o por simetría;
 *   media  si se infiere de proporciones, correspondencia entre vistas o se deriva de otra medida;
 *   alta   si sale de una cota del plano sin supuestos sobre la medida.
 * Si checks.json la marca (sin apoyo o solape), baja un nivel.
 */
const BAJA = /hipot|decisi[oó]n ([a-záéíóúñ]+ )?de dise|decisi[oó]n constructiva|elegid|no medid|propuest[oa],? no|a[nñ]adid|incorpor|por simetr|no confirma|no se identifica|no demuestra/iu;
const MEDIA = /inferid|infier|proporci|correspondencia|derivad|aproximad/i;
export function confianzaDe(supuestos: string[], fuentes: string[], marcada: boolean): { nivel: "alta" | "media" | "baja"; motivo: string } {
  const baja = supuestos.find((x) => BAJA.test(x));
  const media = supuestos.find((x) => MEDIA.test(x));
  const cota = supuestos.find((x) => /cotas?/i.test(x));
  let nivel: "alta" | "media" | "baja" = baja ? "baja" : media ? "media" : cota && fuentes.includes("input") ? "alta" : "media";
  const motivo = baja ?? media ?? cota ?? supuestos[0] ?? "Sin supuestos sobre la medida";
  if (marcada) nivel = nivel === "alta" ? "media" : "baja";
  return { nivel, motivo: marcada ? `${motivo} Además, checks.json la marca.` : motivo };
}

const SISTEMA_RECONSTRUCCION = "x ancho, y fondo, z alto en mm; origen en la esquina inferior delantera izquierda";

function mesaDeTrabajo(e: EntradaReconstruccion, t: TrabajoReconstruccion): MesaTrabajo {
  const propuesta = t.proposal;
  const componentes = propuesta?.components ?? [];
  // Las medidas salen de una hipótesis de diseño generada: todas estimadas.
  const piezas = componentes.map((c) => {
    const [largo, ancho, grueso] = [...c.size_mm].sort((a, b) => b - a);
    const pieza = piezaVacia(c.id, c.label, c.id, cantidad(1, "hypothesis"), medida(largo, "hypothesis"), medida(ancho, "hypothesis"), medida(grueso, "hypothesis"));
    pieza.notas.push(...c.assumptions);
    pieza.referencias = [...c.source_refs];
    const marcada = (t.checks?.floating_ids ?? []).includes(c.id) || (t.checks?.overlaps ?? []).some((par) => Array.isArray(par) && par.includes(c.id));
    pieza.confianza = confianzaDe(c.assumptions, c.source_refs, marcada);
    return pieza;
  });
  const cajas: Caja[] = componentes.map((c) => ({
    id: c.id, piezaId: c.id, ocurrencia: 1,
    posicion_mm: { x: c.origin_mm[0], y: c.origin_mm[1], z: c.origin_mm[2] },
    tamano_mm: { x: c.size_mm[0], y: c.size_mm[1], z: c.size_mm[2] },
    estimada: true, base: "proposal.components", conflicto: false,
  }));
  const avisos: Aviso[] = [];
  const checks = t.checks ?? {};
  if (checks.overlaps?.length) avisos.push({ nivel: "aviso", codigo: "overlaps", mensaje: `${checks.overlaps.length} solapes entre piezas`, piezas: [], fuente: "escena" });
  if (checks.floating_ids?.length) avisos.push({ nivel: "aviso", codigo: "floating", mensaje: "Piezas sin apoyo", piezas: checks.floating_ids.filter((id) => componentes.some((c) => c.id === id)), fuente: "escena" });
  const pendientes: Pendiente[] = (propuesta?.missing_information ?? []).map((texto, i) => ({ id: `${t.job_id}:falta:${i}`, tipo: "revisar", piezaId: null, campos: [], texto }));
  const escena: Escena3D = cajas.length
    ? { ...escenaVacia(SISTEMA_RECONSTRUCCION), disposicion: "montaje", estadoOrigen: t.status, ejeVertical: "z", cajas, limites: limites3d(cajas), glbUrl: t.has_glb ? e.url(t.job_id, "assembly.glb") : null }
    : escenaVacia(SISTEMA_RECONSTRUCCION);
  const notas = [
    ...(propuesta?.intended_use ? [propuesta.intended_use] : []),
    ...(propuesta?.assumptions ?? []),
    ...(propuesta?.functional_notes ?? []),
    ...(t.geometry_provenance ? [`geometry_provenance: ${t.geometry_provenance}`] : []),
    ...(e.notas ?? []),
  ];
  return {
    id: `${e.id}:${t.job_id}`, titulo: e.titulo, via: "reconstruccion", origen: e.origen, sintetico: e.sintetico,
    estado: !piezas.length ? "sin_propuesta" : pendientes.length ? "incompleto" : "listo",
    plano: null, piezas, laminas: [], escena, avisos, pendientes, artefactos: [], evaluacion: null, notas,
    coste: null, original: null, traza: [], atribucion: null, versiones: [], imagenOriginal: e.url(t.job_id, "source.png"),
    reconstruccion: t.files ? {
      jobId: t.job_id, revision: t.revision,
      vistas: t.files.views.map((f) => e.url(t.job_id, f)),
      mascaras: t.files.masks.map((f) => e.url(t.job_id, f)),
      despiece: t.files.exploded ? e.url(t.job_id, t.files.exploded) : null,
      bomUrl: t.files.bom ? e.url(t.job_id, t.files.bom) : null,
      bom: (t.bom_rows ?? []).map((r) => ({ id: r.component_id, nombre: r.label, x: Number(r.x), y: Number(r.y), z: Number(r.z), cantidad: Number(r.quantity) })),
      laminas: t.files.parts.map((f) => e.url(t.job_id, f)),
      comprobaciones: {
        contactos: checks.contacts?.length ?? 0, solapes: checks.overlaps?.length ?? 0,
        sinApoyo: checks.floating_ids?.length ?? 0, apoyadas: checks.grounded_ids?.length ?? 0,
      },
      unidad: t.unit, modelos: t.models ?? [], estado: propuesta?.status ?? t.status,
      uso: propuesta?.intended_use ?? "",
      supuestos: (propuesta?.assumptions ?? []).filter((x) => !/^revisi[oó]n contra el plano/i.test(x)),
      conclusionRevision: [...(propuesta?.assumptions ?? []), ...componentes.flatMap((c) => c.assumptions)].filter((x) => /^revisi[oó]n contra el plano/i.test(x)),
      preguntas: propuesta?.missing_information ?? [],
      render: t.files.views[0] ? e.url(t.job_id, t.files.views[0]) : null,
    } : null,
  };
}

/** La última versión es la que se abre; las demás quedan en `versiones` para el selector «Versión 1 / Versión 2». */
export function desdeReconstruccion(e: EntradaReconstruccion): MesaTrabajo {
  const versiones = e.trabajos.map((t) => ({ id: t.job_id, etiqueta: `Versión ${t.revision}`, mesa: mesaDeTrabajo(e, t) }));
  const ultima = versiones[versiones.length - 1].mesa;
  return { ...ultima, id: e.id, versiones: versiones.length > 1 ? versiones : [] };
}
