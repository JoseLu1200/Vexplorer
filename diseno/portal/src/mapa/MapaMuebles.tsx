import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { type DatosMapa, type EntradaEspacio, GEOMETRIA, PUBLICO, type Proyeccion, cargarEmbedding, cargarEspacios, cargarMapa, cargarProyecciones, precargar, rutaPorDefecto, vecinosDe } from "./datos";
import { Escena } from "./escena";
import { type Tema, colorGrupo, leerTema } from "./paleta";
import { Buscador, CanalHover, Leyenda, PanelFijado, SelectorEspacio, SelectorProyeccion, TarjetaHover } from "./Paneles";

export interface MapaMueblesProps {
  /** Abre el mapa centrado en este punto y lo deja fijado. */
  focoId?: string | null;
  /** Espacio inicial: «geometria» o la clave de un espacio de embeddings. */
  espacio?: string;
  /** Proyección inicial: tsne2 (por defecto), umap2 o pca3. */
  proyeccion?: Proyeccion["clave"];
  /** Carpeta con los datos. Por defecto `${BASE_URL}local/mapa/`. */
  rutaDatos?: string;
  alFijar?: (id: string | null) => void;
  className?: string;
  /** Expone window.__mapa para capturas y medidas de rendimiento. */
  depuracion?: boolean;
}

const ANCHO_PANEL = 330 + 12 * 2;
const cache = new Map<string, Promise<DatosMapa>>();

function cargar(ruta: string, e: EntradaEspacio): Promise<DatosMapa> {
  const k = `${ruta}|${e.clave}`;
  let p = cache.get(k);
  if (!p) {
    p = e.clave === GEOMETRIA.clave ? cargarMapa(ruta) : cargarEmbedding(ruta, e);
    p.catch(() => cache.delete(k));
    cache.set(k, p);
  }
  return p;
}

const pct = (v: number) => `${Math.round(v * 100)} %`;

export function MapaMuebles({ focoId = null, espacio = PUBLICO ? "eg2-mixed-768" : GEOMETRIA.clave, proyeccion = "tsne2", rutaDatos, alFijar, className = "", depuracion = false }: MapaMueblesProps) {
  const ruta = rutaDatos ?? rutaPorDefecto();
  const [espacios, setEspacios] = useState<EntradaEspacio[]>([]);
  const [clave, setClave] = useState(espacio);
  const [d, setD] = useState<DatosMapa | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fijado, setFijado] = useState<number | null>(null);
  const [familia, setFamilia] = useState<number | null>(null);
  const [tam, setTam] = useState({ w: 0, h: 0 });
  const [tema, setTema] = useState<Tema | null>(null);
  const [proys, setProys] = useState<Proyeccion[]>([]);
  const [proy, setProy] = useState<Proyeccion["clave"]>(proyeccion);

  const caja = useRef<HTMLDivElement>(null);
  const lienzo = useRef<HTMLCanvasElement>(null);
  const rotulos = useRef<(HTMLDivElement | null)[]>([null, null, null]);
  const escena = useRef<Escena | null>(null);
  const canal = useRef(new CanalHover()).current;
  const vivo = useRef({ d, fijado, movil: false });
  const movil = tam.w > 0 && tam.w < 640;
  vivo.current = { d, fijado, movil };

  useEffect(() => {
    cargarEspacios(ruta).then(setEspacios);
  }, [ruta]);

  useEffect(() => setClave(espacio), [espacio]);

  useEffect(() => {
    let ok = true;
    const entrada = clave === GEOMETRIA.clave ? GEOMETRIA : espacios.find((e) => e.clave === clave);
    if (!entrada) return;
    setError(null);
    cargar(ruta, entrada).then(
      (x) => {
        if (!ok) return;
        setFijado(null);
        setFamilia(null);
        canal.set(null);
        setD(x);
      },
      (e: Error) => ok && setError(e.message),
    );
    return () => {
      ok = false;
    };
  }, [ruta, clave, espacios, canal]);

  // Tema: se relee si cambia data-theme o la preferencia del sistema.
  useEffect(() => {
    const leer = () => setTema(leerTema(caja.current ?? undefined));
    leer();
    const mo = new MutationObserver(leer);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", leer);
    return () => {
      mo.disconnect();
      mq.removeEventListener("change", leer);
    };
  }, []);

  useLayoutEffect(() => {
    const cv = lienzo.current;
    const el = caja.current;
    if (!cv || !el) return;
    const es = new Escena(cv, rotulos.current.filter((x): x is HTMLDivElement => !!x));
    escena.current = es;
    const ro = new ResizeObserver(([e]) => {
      const w = Math.round(e.contentRect.width);
      const h = Math.round(e.contentRect.height);
      if (!w || !h) return;
      es.tam(w, h);
      setTam({ w, h });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      es.dispose();
      escena.current = null;
    };
  }, []);

  useEffect(() => {
    if (!d) return;
    escena.current?.datos(d);
    setProys([]);
    let ok = true;
    cargarProyecciones(d).then((l) => ok && setProys(l));
    return () => {
      ok = false;
    };
  }, [d]);
  // Proyección activa: al cargar un espacio se coloca sin animar; al cambiar de proyección, los puntos viajan.
  const puesta = useRef<{ d: DatosMapa | null; clave: string | null }>({ d: null, clave: null });
  useEffect(() => {
    const es = escena.current;
    const p = proys.find((x) => x.clave === proy) ?? proys[0];
    // proys[0] es la PCA 3D del propio espacio: si no coincide, la lista aún es la del espacio anterior.
    if (!es || !p || !d || proys[0].pos !== d.pos) return;
    const nuevo = puesta.current.d !== d;
    if (!nuevo && puesta.current.clave === p.clave) return;
    es.setProyeccion(p, !nuevo);
    puesta.current = { d, clave: p.clave };
  }, [proys, proy, d]);
  useEffect(() => {
    if (tema) escena.current?.setTema(tema);
  }, [tema]);
  useEffect(() => {
    escena.current?.setEstado({ familia, fijado, hover: null });
  }, [familia, fijado, d]);
  // El panel tapa parte del lienzo: el centro de la vista se desplaza a la zona libre.
  useEffect(() => {
    const es = escena.current;
    if (!es) return;
    if (fijado === null) es.setDesplazamiento(0, 0);
    else if (movil) es.setDesplazamiento(0, Math.round(tam.h * 0.26));
    else es.setDesplazamiento(Math.round(ANCHO_PANEL / 2), 0);
  }, [fijado, movil, tam]);

  const fijar = useCallback(
    (i: number | null, centrar = false) => {
      setFijado(i);
      const { d: dd } = vivo.current;
      if (!dd) return;
      alFijar?.(i === null ? null : dd.ids[i]);
      if (i !== null) {
        precargar(dd, vecinosDe(dd, i).slice(0, 6));
        if (centrar) escena.current?.enfocar(i);
      }
    },
    [alFijar],
  );

  // Foco externo.
  useEffect(() => {
    if (!d || !tam.w || !focoId) return;
    const i = d.indice.get(focoId);
    if (i === undefined) return;
    fijar(i, true);
    // Solo al cambiar el foco o al tener datos y tamaño por primera vez.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, focoId, tam.w > 0]);

  // Hover y clic. OrbitControls se queda con el arrastre; un clic sin movimiento fija el punto.
  useEffect(() => {
    const cv = lienzo.current;
    if (!cv) return;
    let ini: { x: number; y: number } | null = null;
    let pend = 0;
    let ultimo: PointerEvent | null = null;
    const local = (e: PointerEvent) => {
      const b = cv.getBoundingClientRect();
      return { x: e.clientX - b.left, y: e.clientY - b.top };
    };
    const hover = () => {
      pend = 0;
      const es = escena.current;
      if (!ultimo || !es) return;
      const p = local(ultimo);
      const i = es.pick(p.x, p.y);
      es.setHover(i);
      cv.style.cursor = i === null ? "grab" : "pointer";
      canal.set(i === null ? null : { i, x: p.x, y: p.y });
    };
    const down = (e: PointerEvent) => {
      ini = local(e);
      canal.set(null);
      escena.current?.setHover(null);
    };
    const move = (e: PointerEvent) => {
      if (e.pointerType !== "mouse" || e.buttons) return;
      ultimo = e;
      if (!pend) pend = requestAnimationFrame(hover);
    };
    const up = (e: PointerEvent) => {
      const p = local(e);
      if (ini && Math.hypot(p.x - ini.x, p.y - ini.y) < 5) {
        const i = escena.current?.pick(p.x, p.y) ?? null;
        fijar(i);
      }
      ini = null;
    };
    const leave = () => {
      canal.set(null);
      escena.current?.setHover(null);
    };
    cv.addEventListener("pointerdown", down, true); // en captura: antes que OrbitControls
    cv.addEventListener("pointermove", move);
    cv.addEventListener("pointerup", up, true);
    cv.addEventListener("pointerleave", leave);
    // Sin esto, el clic de compatibilidad tras un toque cae en el panel recién abierto (en móvil, sobre el «×»).
    const sinClicFantasma = (e: TouchEvent) => e.cancelable && e.preventDefault();
    cv.addEventListener("touchend", sinClicFantasma, { passive: false });
    return () => {
      cv.removeEventListener("touchend", sinClicFantasma);
      cancelAnimationFrame(pend);
      cv.removeEventListener("pointerdown", down, true);
      cv.removeEventListener("pointermove", move);
      cv.removeEventListener("pointerup", up, true);
      cv.removeEventListener("pointerleave", leave);
    };
  }, [canal, fijar]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape" && vivo.current.fijado !== null) fijar(null);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [fijar]);

  // Gancho de capturas y medidas.
  useEffect(() => {
    const es = escena.current;
    if (!depuracion || !d || !es) return;
    es.medir = true;
    (window as unknown as { __mapa?: unknown }).__mapa = {
      listo: true,
      espacio: d.clave,
      n: d.n,
      pantalla: (id: string) => {
        const i = d.indice.get(id);
        if (i === undefined) return null;
        const p = es.pantalla(i);
        const b = lienzo.current!.getBoundingClientRect();
        return p && { x: b.left + p.x, y: b.top + p.y };
      },
      fijar: (id: string) => {
        const i = d.indice.get(id);
        if (i !== undefined) fijar(i, true);
      },
      raros: [...d.raros].map((i) => d.ids[i]),
      ids: (k: number) => d.ids.slice(0, k),
      tiempos: () => es.tiempos.slice(),
      limpiarTiempos: () => void (es.tiempos = []),
      cambiarEspacio: (c: string) => setClave(c),
      proyeccion: (c: Proyeccion["clave"]) => setProy(c),
      pick: (x: number, y: number) => {
        const b = lienzo.current!.getBoundingClientRect();
        const i = es.pick(x - b.left, y - b.top);
        return i === null ? null : d.ids[i];
      },
    };
  }, [depuracion, d, fijar]);

  const colores = d && tema ? d.familias.map((_, g) => colorGrupo(tema, g, d.otras)) : [];

  return (
    <div ref={caja} className={`relative h-full w-full select-none overflow-hidden bg-bg font-sans text-ink ${className}`} data-testid="mapa-muebles">
      <canvas ref={lienzo} className="absolute inset-0 h-full w-full" style={{ touchAction: "none", cursor: "grab" }} role="img" aria-label={d ? `${d.nombre}: ${d.n.toLocaleString("es-ES")} puntos en las tres primeras componentes principales` : "Mapa"} />
      <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden" aria-hidden="true">
        {[0, 1, 2].map((k) => (
          <div key={k} ref={(el) => (rotulos.current[k] = el)} className="absolute left-0 top-0 whitespace-nowrap font-mono text-2xs text-muted" style={{ display: "none" }}>
            PC{k + 1}
            {d ? ` (${pct(d.varianza[k])})` : ""}
          </div>
        ))}
      </div>
      {!d && (
        <div className="absolute inset-0 grid place-items-center text-xs text-muted" data-testid="mapa-estado">
          {error === "sin-datos" ? "Faltan los datos del mapa: genera public/local/mapa con scripts/mapa_generar.py" : error ? `No se pudo cargar el mapa (${error})` : "Cargando mapa…"}
        </div>
      )}
      {d && tema && (
        <>
          <div className={`pointer-events-none absolute left-s3 top-s3 z-20 flex flex-col gap-s2 ${movil ? "right-[60px]" : "w-[300px]"}`}>
            {espacios.length > 0 && <SelectorEspacio espacios={espacios} actual={clave} onCambio={setClave} />}
            {proys.length > 1 && <SelectorProyeccion proys={proys} actual={proys.some((p) => p.clave === proy) ? proy : proys[0].clave} onCambio={setProy} />}
            <Buscador d={d} onElegir={(i) => fijar(i, true)} />
            <Leyenda d={d} colores={colores} familia={familia} onFamilia={setFamilia} raro={tema.raro} movil={movil} />
          </div>
          <div className={`absolute top-s3 z-20 flex flex-col border border-line bg-surface ${!movil && fijado !== null ? "right-[354px]" : "right-s3"}`}>
            {(
              [
                ["+", "Acercar", () => escena.current?.zoom(1.6)],
                ["−", "Alejar", () => escena.current?.zoom(1 / 1.6)],
                ["⤢", "Encuadrar todo", () => escena.current?.encuadrar()],
              ] as const
            ).map(([t, a, f]) => (
              <button key={a} type="button" aria-label={a} title={a} onClick={f} className="h-9 w-9 border-b border-line font-mono text-sm text-ink last:border-b-0 hover:bg-sunken">
                {t}
              </button>
            ))}
          </div>
          <TarjetaHover d={d} canal={canal} ancho={tam.w} alto={tam.h} />
          {fijado !== null && fijado < d.n && <PanelFijado d={d} i={fijado} onFijar={(j) => fijar(j, true)} onCerrar={() => fijar(null)} movil={movil} />}
          {!(movil && fijado !== null) && (
            <p className={`pointer-events-none absolute bottom-s1 z-10 whitespace-nowrap font-sans text-muted ${movil ? "left-s2 right-s2 text-[10px]" : `${fijado !== null ? "right-[354px]" : "right-s3"} text-[10px]`}`}>{d.pie}</p>
          )}
        </>
      )}
    </div>
  );
}

export default MapaMuebles;
