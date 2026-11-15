/**
 * Proceso de un mueble en seis pasos (plano, limpieza y cotas, propuesta, revisión, montaje y salidas), sacado de lo
 * que hay de verdad: la mesa de trabajo y su traza de eventos. Sirve para «Ver el proceso» sobre un caso guardado y
 * para la subida en vivo. Nada se completa por inferencia: un paso sin datos queda pendiente con su motivo.
 *
 *   pasosDeMesa(mesa, origen)        pasos de un mueble ya cargado.
 *   pasosEnCurso(fase, flujo)        pasos mientras la subida avanza, antes de tener la mesa.
 */
import type { MesaTrabajo, PasoTraza } from "./modelo";

export type PasoId = "plano" | "limpieza" | "propuesta" | "revision" | "montaje" | "salidas"
  | "lectura" | "piezas" | "comprobaciones" | "despiece" | "bom" | "pendientes";
export type EstadoPaso = "hecho" | "en_curso" | "pendiente" | "requiere_modelo" | "requiere_revision" | "fallo" | "sin_datos";
/** vivo: lo hizo el backend en esta sesión; guardado: resultado de una ejecución anterior; grabado: respuesta de modelo reproducida. */
export type OrigenPaso = "vivo" | "guardado" | "grabado";
export type VistaPaso = "original" | "plano" | "piezas" | "esquema" | "salidas" | "revision" | "bom";

export interface PasoProceso {
  id: PasoId;
  titulo: string;
  estado: EstadoPaso;
  /** Una línea con lo que hizo el sistema, con datos del run. */
  linea: string;
  hora: string | null;
  modelo: string | null;
  origen: OrigenPaso | null;
  vista: VistaPaso;
  /** Versión del mueble que enseña el paso (Construcción 3D con versiones); null si no hay versiones. */
  version?: number | null;
  /** Líneas debajo del paso activo: una por pieza, por supuesto o por pregunta. `nivel` es la confianza de la pieza. */
  detalles?: { texto: string; nivel?: "alta" | "media" | "baja" | null }[];
}

export const TITULOS: Record<PasoId, string> = {
  plano: "Plano original",
  limpieza: "Limpieza y cotas",
  propuesta: "Propuesta de piezas",
  revision: "Revisión",
  montaje: "Montaje 3D",
  salidas: "Salidas",
  lectura: "Lectura",
  piezas: "Piezas",
  comprobaciones: "Comprobación",
  despiece: "Despiece",
  bom: "BOM",
  pendientes: "Pendientes",
};
const VISTA: Record<PasoId, VistaPaso> = {
  plano: "original", limpieza: "plano", propuesta: "piezas", revision: "piezas", montaje: "esquema", salidas: "salidas",
  lectura: "original", piezas: "esquema", comprobaciones: "esquema", despiece: "esquema", bom: "bom", pendientes: "esquema",
};

const paso = (id: PasoId, estado: EstadoPaso, linea: string, extra: Partial<PasoProceso> = {}): PasoProceso => ({
  id, titulo: TITULOS[id], estado, linea, hora: null, modelo: null, origen: null, vista: VISTA[id], ...extra,
});
const buscar = (traza: PasoTraza[], ...etiquetas: string[]) => traza.find((t) => etiquetas.some((e) => t.etiqueta.startsWith(e) || t.herramienta === e));
const ultimo = (traza: PasoTraza[], ...etiquetas: string[]) => [...traza].reverse().find((t) => etiquetas.some((e) => t.etiqueta.startsWith(e) || t.herramienta === e));
const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;
const EUR = (value: number, currency: string) => new Intl.NumberFormat("es-ES", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);

export interface OrigenMesa {
  /** Quién leyó el plano: el backend en esta sesión o la ejecución guardada. */
  geometria: OrigenPaso;
  /** De dónde salen propuesta, revisión, montaje y salidas. */
  resto: OrigenPaso;
  /** Hora de la lectura en vivo cuando el resto es guardado (la traza guardada no es de esta lectura). */
  horaGeometria?: string | null;
}

export function pasosDeMesa(mesa: MesaTrabajo, origen: OrigenMesa): PasoProceso[] {
  const t = mesa.traza;
  const inicio = origen.geometria === "vivo" && origen.resto === "guardado" ? origen.horaGeometria ?? null : t[0]?.hora ?? null;
  const plano = mesa.plano;
  const pasos: PasoProceso[] = [];

  pasos.push(plano
    ? paso("plano", "hecho", `${plural(plano.contornos.length, "contorno", "contornos")} en ${plural(plano.vistas.length, "vista", "vistas")}`, { hora: inicio, origen: origen.geometria })
    : mesa.imagenOriginal ? paso("plano", "hecho", "Imagen del plano", { origen: origen.geometria })
    : paso("plano", "sin_datos", "Sin geometría leída"));
  pasos.push(!plano && mesa.imagenOriginal ? paso("limpieza", "sin_datos", "Sin DXF") : plano
    ? paso("limpieza", "hecho", plano.cotas.length ? `${plural(plano.cotas.length, "cota", "cotas")} y ${plural(plano.textos.length, "texto", "textos")}` : "El DXF no trae cotas", { hora: inicio, origen: origen.geometria })
    : paso("limpieza", "sin_datos", "Sin geometría leída"));

  // Propuesta
  const ocurrencias = mesa.piezas.reduce((sum, p) => sum + (p.cantidad.valor ?? 0), 0);
  const tipos = `${plural(mesa.piezas.length, "tipo", "tipos")}, ${plural(ocurrencias, "pieza", "piezas")}`;
  const propone = buscar(t, "proponer_mueble_general", "proponer_descomposicion", "Propone");
  if (!mesa.piezas.length) {
    pasos.push(paso("propuesta", "requiere_modelo", "Pendiente: requiere modelo"));
  } else if (mesa.via === "tabla") {
    pasos.push(paso("propuesta", "hecho", `Plantilla de catálogo · ${tipos}`, { hora: buscar(t, "Resultado guardado")?.hora ?? inicio, origen: origen.resto }));
  } else if (propone) {
    pasos.push(paso("propuesta", "hecho", `${propone.etiqueta} · ${tipos}`, { hora: propone.hora, modelo: propone.modelo, origen: origen.resto }));
  } else {
    pasos.push(paso("propuesta", "hecho", tipos, { hora: inicio, origen: origen.resto }));
  }

  // Revisión
  const auto = ultimo(t, "Autorrevisión terminada");
  const humana = ultimo(t, "Revisión humana");
  const pendienteRevision = mesa.pendientes.some((p) => p.id === "resultado:revision");
  if (!mesa.piezas.length) pasos.push(paso("revision", "requiere_modelo", "Pendiente: requiere modelo"));
  else if (auto) pasos.push(paso("revision", "hecho", `Autorrevisión ${auto.estado ?? ""}`.trim(), { hora: auto.hora, modelo: auto.modelo, origen: origen.resto }));
  else if (humana) pasos.push(paso("revision", "hecho", humana.etiqueta, { hora: humana.hora, origen: origen.resto }));
  else if (pendienteRevision && mesa.via === "tabla") pasos.push(paso("revision", "requiere_revision", "Pendiente: aceptar la plantilla"));
  else if (pendienteRevision) pasos.push(paso("revision", "requiere_revision", "Pendiente de revisión humana"));
  else pasos.push(paso("revision", "sin_datos", "Sin revisión guardada"));

  // Montaje
  const escena = mesa.escena;
  const fallos = ultimo(t, "Montaje fallido");
  if (escena.disposicion === "montaje") {
    const v = escena.validacion;
    const linea = v && v.estado !== "accepted"
      ? `${plural(escena.cajas.length, "pieza colocada", "piezas colocadas")} · ${v.estado === "rejected" ? "rechazado" : v.estado}, ${plural(v.incidencias.reduce((s, i) => s + i.veces, 0), "incidencia", "incidencias")}`
      : `${plural(escena.cajas.length, "pieza colocada", "piezas colocadas")}${escena.glbUrl ? " · GLB" : ""}`;
    pasos.push(paso("montaje", v && v.estado !== "accepted" ? "fallo" : "hecho", linea, { hora: fallos?.horaFin ?? fallos?.hora ?? null, origen: origen.resto }));
  } else if (!mesa.piezas.length) {
    pasos.push(paso("montaje", "requiere_modelo", "Pendiente: requiere modelo"));
  } else if (fallos) {
    const codigos = fallos.resultados.map((r) => `${r.resultado}${r.veces > 1 ? ` ×${r.veces}` : ""}`).join(", ");
    pasos.push(paso("montaje", "fallo", `Sin colocaciones · ${codigos}`, { hora: fallos.horaFin ?? fallos.hora, origen: origen.resto }));
  } else if (pendienteRevision) {
    pasos.push(paso("montaje", "pendiente", "Pendiente de la revisión"));
  } else {
    pasos.push(paso("montaje", "sin_datos", "Sin montaje guardado"));
  }

  // Salidas
  const piezasSalida: string[] = [];
  const formatos = new Set(mesa.artefactos.filter((a) => a.contenido != null || a.url).map((a) => a.formato.toUpperCase()));
  if (formatos.size) piezasSalida.push(`archivos ${[...formatos].join(", ")}`);
  if (mesa.laminas.length) piezasSalida.push(plural(mesa.laminas.length, "lámina", "láminas"));
  if (mesa.coste?.total != null) piezasSalida.push(EUR(mesa.coste.total, mesa.coste.moneda));
  const horaSalidas = ultimo(t, "Coste guardado", "Láminas guardadas")?.hora ?? null;
  pasos.push(piezasSalida.length
    ? paso("salidas", "hecho", piezasSalida.join(" · "), { hora: horaSalidas, origen: origen.resto })
    : paso("salidas", mesa.piezas.length ? "sin_datos" : "requiere_modelo", mesa.piezas.length ? "Sin salidas guardadas" : "Pendiente: requiere modelo"));
  return pasos;
}

/** Fase de una subida en curso, del almacén del espacio de trabajo. */
export type FaseSubida = "subiendo" | "leyendo" | "analizando" | "salidas" | "hecho" | "error";
/** mesa: plantilla de catálogo; general: mueble general nuevo; guardado: mueble general con ejecución guardada. */
export type FlujoSubida = "mesa" | "general" | "guardado";

export function pasosEnCurso(fase: FaseSubida, flujo: FlujoSubida): PasoProceso[] {
  const orden: FaseSubida[] = ["subiendo", "leyendo", "analizando", "salidas", "hecho"];
  const i = orden.indexOf(fase);
  const estado = (desde: number): PasoProceso["estado"] => (fase === "error" ? "pendiente" : i > desde ? "hecho" : i === desde ? "en_curso" : "pendiente");
  const resto = (id: PasoId): PasoProceso => {
    if (flujo === "general") return paso(id, "requiere_modelo", "Pendiente: requiere modelo");
    if (flujo === "guardado") return paso(id, estado(2), "Resultado guardado", { origen: "guardado" });
    if (id === "propuesta") return paso(id, estado(2), "Plantilla de catálogo", { origen: "vivo" });
    if (id === "salidas") return paso(id, estado(3), "Láminas", { origen: "vivo" });
    return paso(id, "pendiente", id === "revision" ? "Pendiente: aceptar la plantilla" : "Pendiente de la revisión");
  };
  // Plano: en curso al subir y al leer; limpieza y cotas: en curso mientras el backend analiza.
  return [
    paso("plano", fase === "error" ? "pendiente" : i >= 2 ? "hecho" : "en_curso", "Lectura del DXF", { origen: "vivo" }),
    paso("limpieza", estado(2), "Contornos y cotas", { origen: "vivo" }),
    resto("propuesta"),
    resto("revision"),
    resto("montaje"),
    resto("salidas"),
  ];
}

/**
 * Proceso de Construcción 3D en el orden de reconstruction3d/service.py: entra el plano, el modelo lo lee y propone
 * las piezas, el sistema comprueba la geometría, renderiza la propuesta y el modelo la revisa contra el plano original;
 * después, montaje, despiece, BOM y lo que queda pendiente. Una abstención se para en la lectura con sus preguntas.
 * Con versiones, los pasos son de la primera y la revisión enseña la versión 1 frente a la última.
 */
export function pasosReconstruccion(mesa: MesaTrabajo): PasoProceso[] | null {
  const versiones = mesa.versiones.length > 1 ? mesa.versiones : null;
  const base = versiones ? versiones[0].mesa : mesa;
  const r = base.reconstruccion;
  if (!r) return null;
  const v = versiones ? 0 : null;
  const modelo = r.modelos[0] ?? null;
  const comun = { origen: "guardado" as const, version: v };
  const recorta = (texto: string, n = 140) => (texto.length > n ? `${texto.slice(0, n - 1).trimEnd()}…` : texto);
  const pasos: PasoProceso[] = [
    paso("plano", base.imagenOriginal ? "hecho" : "sin_datos", `Entra el plano${r.unidad === "mm" ? ", en mm" : r.unidad === "relative" ? ", sin escala" : ""}`,
      { ...comun, titulo: "Plano", vista: "original" }),
  ];
  // Lectura: qué interpreta el modelo. En una abstención, sus preguntas y nada más.
  const abstiene = r.estado !== "proposed";
  pasos.push(paso("lectura", abstiene ? "requiere_revision" : "hecho", `El modelo interpreta: ${recorta(r.uso, 120)}`, {
    ...comun, titulo: "Lectura", vista: "original", modelo,
    detalles: (abstiene ? r.preguntas : r.supuestos.slice(0, 1)).map((texto) => ({ texto: recorta(texto) })),
  }));
  if (abstiene && !versiones) return pasos;

  const fuente = abstiene && versiones ? versiones[versiones.length - 1].mesa : base;
  const rf = fuente.reconstruccion ?? r;
  const vf = abstiene && versiones ? versiones.length - 1 : v;
  const c = rf.comprobaciones;
  pasos.push(
    paso("piezas", fuente.piezas.length ? "hecho" : "sin_datos", `El modelo propone ${plural(fuente.piezas.length, "pieza", "piezas")}`, {
      origen: "guardado", version: vf, titulo: "Piezas", vista: "esquema", modelo,
      detalles: fuente.piezas.map((p) => ({ texto: `${p.nombreCorto} · ${recorta(p.confianza?.motivo ?? p.notas[0] ?? "", 110)}`, nivel: p.confianza?.nivel ?? null })),
    }),
    paso("comprobaciones", fuente.piezas.length ? (c.solapes || c.sinApoyo ? "fallo" : "hecho") : "sin_datos",
      `${plural(c.contactos, "contacto", "contactos")} · ${c.sinApoyo} sin apoyo · ${plural(c.solapes, "cruce", "cruces")}`,
      { origen: "guardado", version: vf, titulo: "Comprobación", vista: "esquema" }),
  );
  // Revisión: el render de la propuesta frente al plano original; con versiones, la 1 frente a la última.
  if (versiones && !abstiene) {
    const ultima = versiones[versiones.length - 1].mesa;
    const dims = (p: MesaTrabajo["piezas"][number]) => `${p.largo.valor_mm} × ${p.ancho.valor_mm} × ${p.grueso.valor_mm}`;
    const cambios = ultima.piezas.map((p, i) => ({ antes: base.piezas[i], despues: p })).filter(({ antes, despues }) => !antes || dims(antes) !== dims(despues));
    pasos.push(paso("revision", "hecho", `${versiones[0].etiqueta} frente a ${versiones[versiones.length - 1].etiqueta} · ${plural(cambios.length, "pieza cambia", "piezas cambian")}`, {
      origen: "guardado", version: versiones.length - 1, titulo: "Revisión", vista: "revision", modelo,
      detalles: cambios.map(({ antes, despues }) => ({ texto: `${despues.nombreCorto}: ${antes ? dims(antes) : "nueva"} → ${dims(despues)} mm` })),
    }));
  } else {
    pasos.push(paso("revision", rf.render ? "hecho" : "sin_datos", rf.conclusionRevision.length ? "El modelo compara su render con el plano original" : "Render de la propuesta frente al plano original", {
      origen: "guardado", version: vf, titulo: "Revisión", vista: "revision", modelo,
      detalles: rf.conclusionRevision.map((texto) => ({ texto: recorta(texto.replace(/^revisi[oó]n contra el plano original:\s*/i, ""), 160) })),
    }));
  }
  const final = versiones ? versiones[versiones.length - 1].mesa : fuente;
  const vFinal = versiones ? versiones.length - 1 : v;
  const rFinal = final.reconstruccion ?? rf;
  pasos.push(
    paso("montaje", final.escena.disposicion === "montaje" ? "hecho" : "sin_datos",
      final.escena.disposicion === "montaje" ? `${plural(final.escena.cajas.length, "pieza colocada", "piezas colocadas")}${final.escena.glbUrl ? " · GLB" : ""}` : "Sin montaje",
      { origen: "guardado", version: vFinal, titulo: "Montaje", vista: "esquema" }),
    paso("despiece", final.escena.disposicion === "montaje" ? "hecho" : "sin_datos", `Piezas separadas${final.escena.glbUrl ? " del GLB" : ""}`,
      { origen: "guardado", version: vFinal, titulo: "Despiece", vista: "esquema" }),
    paso("bom", rFinal.bom.length ? "hecho" : "sin_datos", plural(rFinal.bom.length, "fila", "filas"), { origen: "guardado", version: vFinal, titulo: "BOM", vista: "bom" }),
    paso("pendientes", rFinal.preguntas.length ? "requiere_revision" : "hecho", plural(rFinal.preguntas.length, "punto abierto", "puntos abiertos"), {
      origen: "guardado", version: vFinal, titulo: "Pendientes", vista: "esquema",
      detalles: rFinal.preguntas.map((texto) => ({ texto: recorta(texto) })),
    }),
  );
  return pasos;
}
