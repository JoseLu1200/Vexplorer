// Carga del mapa: geometría de scripts/mapa_generar.py y espacios de embeddings de scripts/mapa_embeddings.py
// (public/local/mapa/, no versionado). Las dos fuentes traen PCA a 3 componentes y vecinos del espacio original.

export const ROLES = ["laterales", "divisores", "tapas", "bases", "baldas", "traseras", "puertas", "cajones", "patas", "otras"] as const;
export type Rol = (typeof ROLES)[number];
export const SPLITS = ["train", "valid", "test"] as const;

/** Lo que necesita la escena, común a la geometría y a los embeddings. */
interface Base {
  clave: string;
  nombre: string;
  n: number;
  k: number;
  ids: string[];
  indice: Map<string, number>;
  /** PC1, PC2, PC3 intercalados, centrados en la mediana y con radio robusto 1 (misma escala en los tres ejes). */
  pos: Float32Array;
  /** fracción de varianza explicada por PC1, PC2 y PC3. */
  varianza: [number, number, number];
  /** vecinos en el espacio original, k por punto, ordenados. */
  vecinos: Uint16Array;
  /** grupo de color: familia en geometría; categoría en embeddings (las 7 mayores y «otras»). */
  familia: Uint8Array;
  familias: { nombre: string; n: number }[];
  /** índice del grupo «otras», que va en gris; -1 si no hay. */
  otras: number;
  raros: Set<number>;
  base: string;
  pie: string;
}

export interface DatosGeo extends Base {
  tipo: "geometria";
  /** ancho, fondo, alto en mm, intercalados. */
  medidas: Uint16Array;
  piezas: Uint8Array;
  split: Uint8Array;
  /** 10 cuentas por mueble, en el orden de ROLES. */
  roles: Uint8Array;
  tipos: Uint8Array;
  grosor: Uint8Array;
  /** asimetría izquierda/derecha × 1000. */
  asim: Uint16Array;
  lote: number;
}

export interface PuntoEmb {
  id: string;
  etiqueta: string | null;
  cat: number;
  split: string | null;
  x: number;
  y: number;
  z: number;
  render: string | null;
  clas: { etiqueta: string; score: number; metodo: string; calibrada: boolean } | null;
}

export interface DatosEmb extends Base {
  tipo: "embedding";
  modelo: string;
  modo: string;
  dims: number;
  /** nombres en español para la interfaz. */
  categorias: string[];
  /** ids originales de categoría del paquete de demo, para la ficha del punto. */
  categoriasId: string[];
  puntos: PuntoEmb[];
  /** coseno de cada vecino, alineado con `vecinos`. */
  cos: Float32Array;
}

export type DatosMapa = DatosGeo | DatosEmb;

export interface EntradaEspacio {
  clave: string;
  nombre: string;
  n: number;
  principal: boolean;
  archivo: string;
}

export const GEOMETRIA: EntradaEspacio = { clave: "geometria", nombre: "Geometría · PlankAssembly (26.707)", n: 26707, principal: true, archivo: "mapa.json" };
const PIE_GEO = "PlankAssembly, manycore-research, CC BY-NC-ND 4.0 · vector geométrico, sin modelo";

export const rutaPorDefecto = () => `${import.meta.env.BASE_URL}local/mapa/`;

/** Centra en la mediana y escala para que el percentil 98 de la distancia al centro sea 1: los atípicos no encogen la nube. */
function normalizar(pos: Float32Array, n: number) {
  const med = [0, 1, 2].map((e) => {
    const v = new Float32Array(n);
    for (let i = 0; i < n; i++) v[i] = pos[3 * i + e];
    v.sort();
    return v[Math.floor(n / 2)];
  });
  const r = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    for (let e = 0; e < 3; e++) pos[3 * i + e] -= med[e];
    r[i] = Math.hypot(pos[3 * i], pos[3 * i + 1], pos[3 * i + 2]);
  }
  r.sort();
  const radio = r[Math.min(n - 1, Math.floor(n * 0.98))] || 1;
  for (let i = 0; i < pos.length; i++) pos[i] /= radio;
}

async function json<T>(url: string): Promise<T> {
  const r = await fetch(url);
  // Vite devuelve index.html con 200 para rutas que no existen: se exige JSON.
  if (!r.ok || !(r.headers.get("content-type") ?? "").includes("json")) throw new Error("sin-datos");
  return (await r.json()) as T;
}

interface Seccion {
  nombre: string;
  tipo: "uint8" | "uint16";
  offset: number;
  largo: number;
}

interface Meta {
  n: number;
  k_vecinos: number;
  lote_siluetas: number;
  secciones: Seccion[];
  familias: { nombre: string; n: number }[];
  raros: number[];
  proyeccion: { metodo: string; varianza: [number, number, number] };
}

export async function cargarMapa(base: string = rutaPorDefecto()): Promise<DatosGeo> {
  const meta = await json<Meta>(`${base}mapa3d.json`);
  if (meta.proyeccion.metodo !== "pca3") throw new Error("sin-datos");
  const [br, ir] = await Promise.all([fetch(`${base}mapa3d.bin`), fetch(`${base}ids.txt`)]);
  if (!br.ok || !ir.ok) throw new Error("sin-datos");
  const buf = await br.arrayBuffer();
  const ids = (await ir.text()).split(/\r?\n/);
  if (ids.length !== meta.n) throw new Error("sin-datos");
  const sec = (nombre: string) => {
    const s = meta.secciones.find((x) => x.nombre === nombre);
    if (!s) throw new Error(`sección ${nombre}`);
    return s.tipo === "uint16" ? new Uint16Array(buf, s.offset, s.largo) : new Uint8Array(buf, s.offset, s.largo);
  };
  const q = sec("pos") as Uint16Array;
  const pos = new Float32Array(q.length);
  for (let i = 0; i < q.length; i++) pos[i] = q[i] / 65535;
  normalizar(pos, meta.n);
  return {
    tipo: "geometria",
    clave: GEOMETRIA.clave,
    nombre: GEOMETRIA.nombre,
    n: meta.n,
    k: meta.k_vecinos,
    ids,
    indice: new Map(ids.map((id, i) => [id, i])),
    pos,
    varianza: meta.proyeccion.varianza,
    vecinos: sec("vecinos") as Uint16Array,
    familia: sec("familia") as Uint8Array,
    familias: meta.familias.map((f) => ({ nombre: f.nombre, n: f.n })),
    otras: -1,
    raros: new Set(meta.raros),
    base,
    pie: PIE_GEO,
    medidas: sec("medidas") as Uint16Array,
    piezas: sec("piezas") as Uint8Array,
    split: sec("split") as Uint8Array,
    roles: sec("roles") as Uint8Array,
    tipos: sec("tipos") as Uint8Array,
    grosor: sec("grosor") as Uint8Array,
    asim: sec("asim") as Uint16Array,
    lote: meta.lote_siluetas,
  };
}

/** Índice de espacios de embeddings. Vacío si no se ha generado. */
export async function cargarEspacios(base: string = rutaPorDefecto()): Promise<EntradaEspacio[]> {
  try {
    return await json<EntradaEspacio[]>(`${base}espacios.json`);
  } catch {
    return [];
  }
}

interface DocEmb {
  clave: string;
  modelo: string;
  modo: string;
  dims: number;
  categorias: string[];
  puntos: PuntoEmb[];
  vecinos: [number, number][][];
  proyeccion: { varianza: [number, number, number] };
}

/** Categorías editoriales del paquete de demo, en español. Las que no están (plank-001…) se muestran tal cual. */
const CATEGORIA_ES: Record<string, string> = {
  sofas: "sofás",
  "simple-tables": "mesas",
  beds: "camas",
  buffets: "aparadores",
  "bathroom-set": "conjuntos de baño",
  bathtubs: "bañeras",
  "dining-sets": "comedores",
  "doors-elevation": "puertas en alzado",
  "doors-plan": "puertas en planta",
  "kitchen-appliances": "electrodomésticos",
  "kitchen-sinks": "fregaderos",
  "living-room": "salones",
  "palm-trees": "palmeras",
  ranges: "cocinas",
  "restaurant-layouts": "distribuciones de restaurante",
  "sanitary-ware": "sanitarios",
  "table-lamps": "lámparas de mesa",
  toilets: "inodoros",
  "trees-3d": "árboles en 3D",
  "trees-elevation": "árboles en alzado",
  "trees-plan": "árboles en planta",
  outside_core_domain: "fuera del dominio",
  rectangular_table: "mesa rectangular",
};
export const categoriaEs = (id: string) => CATEGORIA_ES[id] ?? id;

const NOMBRE_MODELO: Record<string, string> = {
  "google/embeddinggemma-2": "EmbeddingGemma 2",
  "facebook/dinov3-vits16-pretrain-lvd1689m": "DINOv3",
  "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": "MiniLM",
};

export async function cargarEmbedding(base: string, e: EntradaEspacio): Promise<DatosEmb> {
  const doc = await json<DocEmb>(`${base}${e.archivo}`);
  const n = doc.puntos.length;
  const k = doc.vecinos[0]?.length ?? 0;
  const pos = new Float32Array(3 * n);
  doc.puntos.forEach((p, i) => {
    pos[3 * i] = p.x;
    pos[3 * i + 1] = p.y;
    pos[3 * i + 2] = p.z;
  });
  normalizar(pos, n);
  const vecinos = new Uint16Array(n * k);
  const cos = new Float32Array(n * k);
  doc.vecinos.forEach((l, i) =>
    l.forEach(([j, c], m) => {
      vecinos[i * k + m] = j;
      cos[i * k + m] = c;
    }),
  );
  // Grupos de color: categorías por tamaño; con más de 8, las 7 mayores y el resto en «otras».
  const cuenta = doc.categorias.map((_, c) => doc.puntos.filter((p) => p.cat === c).length);
  const orden = doc.categorias.map((_, c) => c).sort((a, b) => cuenta[b] - cuenta[a] || a - b);
  const otras = orden.length > 8 ? 7 : -1;
  const grupoDeCat = new Uint8Array(doc.categorias.length);
  orden.forEach((c, r) => (grupoDeCat[c] = otras >= 0 && r >= 7 ? 7 : r));
  const familia = Uint8Array.from(doc.puntos, (p) => grupoDeCat[p.cat]);
  const ng = otras >= 0 ? 8 : orden.length;
  const familias = Array.from({ length: ng }, (_, g) => ({ nombre: g === otras ? `otras ${orden.length - 7} categorías` : categoriaEs(doc.categorias[orden[g]]), n: 0 }));
  for (let i = 0; i < n; i++) familias[familia[i]].n++;
  const ids = doc.puntos.map((p) => p.id);
  const modelo = NOMBRE_MODELO[doc.modelo] ?? doc.modelo;
  return {
    tipo: "embedding",
    clave: doc.clave,
    nombre: e.nombre,
    n,
    k,
    ids,
    indice: new Map(ids.map((id, i) => [id, i])),
    pos,
    varianza: doc.proyeccion.varianza,
    vecinos,
    cos,
    familia,
    familias,
    otras,
    raros: new Set(),
    base,
    pie: `${modelo} · ${doc.modo} ${doc.dims} · vecinos por coseno en ${doc.dims} dimensiones`,
    modelo: doc.modelo,
    modo: doc.modo,
    dims: doc.dims,
    categorias: doc.categorias.map(categoriaEs),
    categoriasId: doc.categorias,
    puntos: doc.puntos,
  };
}

export const renderDe = (d: DatosEmb, i: number) => (d.puntos[i].render ? `${d.base}renders/${d.puntos[i].render}` : null);

/** Rectángulos de la vista frontal: x0, z0, x1, z1 en 0..255 sobre ancho y alto, y rol. Ordenados del fondo al frente. */
export type Rects = Uint8Array;

const lotes = new Map<string, Promise<{ bytes: Uint8Array; inicio: Uint32Array }>>();

function lote(d: DatosGeo, l: number) {
  const clave = `${d.base}${l}`;
  let p = lotes.get(clave);
  if (!p) {
    p = fetch(`${d.base}sil/${String(l).padStart(3, "0")}.bin`)
      .then((r) => {
        if (!r.ok) throw new Error("silueta");
        return r.arrayBuffer();
      })
      .then((b) => {
        const a = l * d.lote;
        const m = Math.min(d.n, a + d.lote) - a;
        const inicio = new Uint32Array(m + 1);
        for (let i = 0; i < m; i++) inicio[i + 1] = inicio[i] + d.piezas[a + i] * 5;
        return { bytes: new Uint8Array(b), inicio };
      });
    p.catch(() => lotes.delete(clave));
    lotes.set(clave, p);
  }
  return p;
}

const cache = new Map<string, Rects>();

export function siluetaEnCache(d: DatosGeo, i: number): Rects | undefined {
  return cache.get(`${d.base}${i}`);
}

export async function silueta(d: DatosGeo, i: number): Promise<Rects> {
  const hit = siluetaEnCache(d, i);
  if (hit) return hit;
  const l = Math.floor(i / d.lote);
  const { bytes, inicio } = await lote(d, l);
  const j = i - l * d.lote;
  const r = bytes.subarray(inicio[j], inicio[j + 1]);
  cache.set(`${d.base}${i}`, r);
  return r;
}

export const medidas = (d: DatosGeo, i: number) => [d.medidas[i * 3], d.medidas[i * 3 + 1], d.medidas[i * 3 + 2]] as const;
export const rolesDe = (d: DatosGeo, i: number) => d.roles.subarray(i * ROLES.length, (i + 1) * ROLES.length);
export const vecinosDe = (d: DatosMapa, i: number) => Array.from(d.vecinos.subarray(i * d.k, (i + 1) * d.k));

/** Precarga lo que pinta la ficha de los vecinos: siluetas en geometría, renders en embeddings. */
export function precargar(d: DatosMapa, ids: number[]) {
  for (const j of ids) {
    if (d.tipo === "geometria") void silueta(d, j).catch(() => {});
    else {
      const u = renderDe(d, j);
      if (u) new Image().src = u;
    }
  }
}

/** Una colocación de los puntos. Los vecinos no cambian: siempre son los del espacio original. */
export interface Proyeccion {
  clave: "pca3" | "umap2" | "tsne2";
  nombre: string;
  dims: 2 | 3;
  /** x, y, z intercalados y normalizados como `pos`; z = 0 en las 2D. */
  pos: Float32Array;
  /** puntos dibujados (t-SNE por muestra); null si son todos. */
  visibles: Uint8Array | null;
}

export const ORDEN_PROYECCIONES = ["pca3", "umap2", "tsne2"] as const;
const NOMBRE_CORTO: Record<Proyeccion["clave"], string> = { pca3: "PCA 3D", umap2: "UMAP 2D", tsne2: "t-SNE 2D" };

interface DocProy {
  n: number;
  proyecciones: { clave: string; nombre: string; dims: 2 | 3; offset?: number; largo?: number; visibles_offset?: number; coords?: number[] }[];
}

/** PCA 3D (de los datos) más las proyecciones precalculadas por scripts/mapa_proyecciones.py, si existen. */
export async function cargarProyecciones(d: DatosMapa): Promise<Proyeccion[]> {
  const out: Proyeccion[] = [{ clave: "pca3", nombre: NOMBRE_CORTO.pca3, dims: 3, pos: d.pos, visibles: null }];
  try {
    const doc = await json<DocProy>(`${d.base}proy/${d.clave}.json`);
    let buf: ArrayBuffer | null = null;
    if (d.tipo === "geometria") {
      const r = await fetch(`${d.base}proy/${d.clave}.bin`);
      if (!r.ok) throw new Error("sin-datos");
      buf = await r.arrayBuffer();
    }
    for (const p of doc.proyecciones) {
      if (p.clave !== "umap2" && p.clave !== "tsne2") continue;
      const pos = new Float32Array(d.n * 3);
      let visibles: Uint8Array | null = null;
      if (buf && p.offset !== undefined && p.largo !== undefined) {
        const q = new Uint16Array(buf, p.offset, p.largo);
        for (let i = 0; i < d.n; i++) for (let e = 0; e < p.dims; e++) pos[3 * i + e] = q[i * p.dims + e] / 65535;
        if (p.visibles_offset !== undefined) visibles = new Uint8Array(buf, p.visibles_offset, d.n);
      } else if (p.coords) {
        for (let i = 0; i < d.n; i++) for (let e = 0; e < p.dims; e++) pos[3 * i + e] = p.coords[i * p.dims + e];
      } else continue;
      normalizar(pos, d.n);
      // t-SNE y UMAP salen con el eje y en cualquier sentido; se deja tal cual, sin reinterpretar.
      out.push({ clave: p.clave, nombre: visibles ? p.nombre : NOMBRE_CORTO[p.clave], dims: 2, pos, visibles });
    }
  } catch {
    /* sin proyecciones precalculadas: solo PCA 3D */
  }
  return out.sort((a, b) => ORDEN_PROYECCIONES.indexOf(a.clave) - ORDEN_PROYECCIONES.indexOf(b.clave));
}
