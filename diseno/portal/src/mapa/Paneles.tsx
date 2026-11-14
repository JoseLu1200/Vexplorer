import { useEffect, useMemo, useState } from "react";
import { type DatosEmb, type DatosGeo, type DatosMapa, type EntradaEspacio, GEOMETRIA, type Proyeccion, SPLITS, categoriaEs, medidas, vecinosDe } from "./datos";
import { composicion, etiquetas } from "./etiquetas";
import { Miniatura } from "./Silueta";

export const fmt = (v: number) => v.toLocaleString("es-ES");
const medidasTxt = (d: DatosGeo, i: number) => medidas(d, i).map(fmt).join(" × ") + " mm";
const dec = (v: number, n = 2) => v.toLocaleString("es-ES", { minimumFractionDigits: n, maximumFractionDigits: n });

/** Canal mínimo para el hover: la escena publica sin pasar por el estado del componente principal. */
export interface Hover {
  i: number;
  x: number;
  y: number;
}
export class CanalHover {
  private oyentes = new Set<(h: Hover | null) => void>();
  actual: Hover | null = null;
  set(h: Hover | null) {
    if (h?.i === this.actual?.i && h?.x === this.actual?.x && h?.y === this.actual?.y) return;
    this.actual = h;
    this.oyentes.forEach((f) => f(h));
  }
  on(f: (h: Hover | null) => void) {
    this.oyentes.add(f);
    return () => void this.oyentes.delete(f);
  }
}

const grupoDe = (d: DatosMapa, i: number) => (d.tipo === "embedding" ? d.categorias[d.puntos[i].cat] : d.familias[d.familia[i]].nombre);

function Lineas({ d, i }: { d: DatosMapa; i: number }) {
  if (d.tipo === "geometria")
    return (
      <>
        <div className="mt-s1 leading-4">{grupoDe(d, i)}</div>
        <div className="mt-s1 whitespace-nowrap font-mono text-muted">{medidasTxt(d, i)}</div>
        <div className="font-mono text-muted">{d.piezas[i]} piezas</div>
      </>
    );
  const p = d.puntos[i];
  return (
    <>
      {p.etiqueta && <div className="mt-s1 leading-4">{p.etiqueta}</div>}
      <div className="mt-s1 leading-4">{grupoDe(d, i)}</div>
      {p.split && <div className="font-mono text-muted">{p.split}</div>}
    </>
  );
}

export function TarjetaHover({ d, canal, ancho, alto }: { d: DatosMapa; canal: CanalHover; ancho: number; alto: number }) {
  const [h, setH] = useState<Hover | null>(canal.actual);
  useEffect(() => canal.on(setH), [canal]);
  if (!h || h.i >= d.n) return null;
  const W = 240;
  const left = Math.max(8, Math.min(ancho - W - 8, h.x + 16 + W > ancho ? h.x - 16 - W : h.x + 16));
  const top = Math.min(Math.max(8, h.y - 40), alto - 120);
  return (
    <div className="pointer-events-none absolute z-20 flex gap-s3 border border-line bg-surface p-s2 shadow-sm" style={{ left, top, width: W }} data-testid="mapa-hover">
      <Miniatura d={d} i={h.i} caja={72} className="shrink-0" />
      <div className="min-w-0 text-2xs text-ink">
        <div className="truncate font-mono">{d.ids[h.i]}</div>
        <Lineas d={d} i={h.i} />
      </div>
    </div>
  );
}

function FichaEmb({ d, i }: { d: DatosEmb; i: number }) {
  const p = d.puntos[i];
  return (
    <>
      {p.etiqueta && <div className="mt-s1 text-sm leading-5">{p.etiqueta}</div>}
      <div className="mt-s1 text-sm leading-5">{d.categorias[p.cat]}</div>
      <div className="mt-s1 font-mono text-2xs text-muted">
        {d.categoriasId[p.cat]}
        {p.split ? ` · ${p.split}` : ""}
      </div>
      {p.clas && (
        <div className="mt-s1 text-2xs leading-4 text-ink" data-testid="mapa-clasificacion">
          {p.clas.metodo}: {categoriaEs(p.clas.etiqueta)} {dec(p.clas.score)} · {p.clas.calibrada ? "calibrada" : "sin calibrar"}
        </div>
      )}
    </>
  );
}

function FichaGeo({ d, i }: { d: DatosGeo; i: number }) {
  return (
    <>
      <div className="mt-s1 text-sm leading-5">{d.familias[d.familia[i]].nombre}</div>
      <div className="mt-s1 font-mono text-2xs text-muted">{medidasTxt(d, i)}</div>
      <div className="font-mono text-2xs text-muted">
        {d.piezas[i]} piezas · {SPLITS[d.split[i]]}
        {d.raros.has(i) ? " · raro" : ""}
      </div>
      <div className="mt-s1 text-2xs leading-4 text-ink">{composicion(d, i)}</div>
    </>
  );
}

export function PanelFijado({ d, i, onFijar, onCerrar, movil }: { d: DatosMapa; i: number; onFijar: (j: number) => void; onCerrar: () => void; movil: boolean }) {
  const vec = useMemo(() => vecinosDe(d, i).slice(0, 6), [d, i]);
  return (
    <aside
      className={
        movil
          ? "absolute inset-x-0 bottom-0 z-30 max-h-[52%] overflow-y-auto border-t border-line bg-surface"
          : "absolute bottom-s3 right-s3 top-s3 z-30 w-[330px] overflow-y-auto border border-line bg-surface"
      }
      aria-label="Punto fijado"
      data-testid="mapa-panel"
    >
      <header className="flex gap-s3 border-b border-line p-s3">
        <Miniatura d={d} i={i} caja={movil ? 64 : 84} className="shrink-0" />
        <div className="min-w-0 flex-1 text-xs text-ink">
          <div className="break-all font-mono text-2xs">{d.ids[i]}</div>
          {d.tipo === "geometria" ? <FichaGeo d={d} i={i} /> : <FichaEmb d={d} i={i} />}
        </div>
        <button type="button" onClick={onCerrar} className="-mr-s1 -mt-s1 h-8 w-8 shrink-0 text-lg leading-none text-muted hover:text-ink" aria-label="Soltar">
          ×
        </button>
      </header>
      <ul className="divide-y divide-line">
        {vec.map((j) => (
          <li key={j}>
            <button type="button" onClick={() => onFijar(j)} className="flex w-full gap-s3 px-s3 py-s2 text-left hover:bg-sunken focus-visible:bg-sunken focus-visible:outline-none">
              <Miniatura d={d} i={j} caja={52} className="shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-2xs text-muted">{d.ids[j]}</span>
                <span className="mt-s1 flex flex-wrap gap-s1">
                  {etiquetas(d, i, j).map((t) => (
                    <span key={t} className="border border-line px-s1 text-2xs text-ink">
                      {t}
                    </span>
                  ))}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

export function Leyenda({ d, colores, familia, onFamilia, raro, movil }: { d: DatosMapa; colores: string[]; familia: number | null; onFamilia: (f: number | null) => void; raro: string; movil: boolean }) {
  const [abierta, setAbierta] = useState(!movil);
  useEffect(() => setAbierta(!movil), [movil]);
  return (
    <div className="pointer-events-auto border border-line bg-surface/95 text-2xs text-ink" data-testid="mapa-leyenda">
      {movil && (
        <button type="button" className="flex w-full items-center justify-between gap-s2 px-s2 py-s1" onClick={() => setAbierta((v) => !v)} aria-expanded={abierta}>
          <span>{familia === null ? (d.tipo === "geometria" ? "Familias" : "Categorías") : d.familias[familia].nombre}</span>
          <span className="font-mono text-muted">{abierta ? "−" : "+"}</span>
        </button>
      )}
      {abierta && (
        <ul className="py-s1" aria-label={d.tipo === "geometria" ? "Familias" : "Categorías"}>
          {d.familias.map((f, k) => {
            const activa = familia === k;
            const apagada = familia !== null && !activa;
            return (
              <li key={f.nombre}>
                <button
                  type="button"
                  aria-pressed={activa}
                  onClick={() => {
                    onFamilia(activa ? null : k);
                    if (movil) setAbierta(false);
                  }}
                  className={`flex w-full items-center gap-s2 px-s2 py-[3px] text-left hover:bg-sunken ${activa ? "bg-sunken" : ""}`}
                >
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: colores[k], opacity: apagada ? 0.3 : 1 }} />
                  <span className="flex-1">{f.nombre}</span>
                  <span className="font-mono text-muted">{fmt(f.n)}</span>
                </button>
              </li>
            );
          })}
          {d.raros.size > 0 && (
            <li className="flex items-center gap-s2 px-s2 py-[3px]">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full border-[1.5px]" style={{ borderColor: raro }} />
              <span className="flex-1">Raros</span>
              <span className="font-mono text-muted">{d.raros.size}</span>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

export function SelectorEspacio({ espacios, actual, onCambio }: { espacios: EntradaEspacio[]; actual: string; onCambio: (clave: string) => void }) {
  const principales = [GEOMETRIA, ...espacios.filter((e) => e.principal)];
  const otros = espacios.filter((e) => !e.principal);
  return (
    <select
      value={actual}
      onChange={(e) => onCambio(e.target.value)}
      aria-label="Espacio"
      data-testid="mapa-espacio"
      className="pointer-events-auto h-9 w-full border border-line bg-surface px-s2 text-xs text-ink focus:border-ink focus:outline-none"
    >
      {principales.map((e) => (
        <option key={e.clave} value={e.clave}>
          {e.nombre}
        </option>
      ))}
      {otros.length > 0 && (
        <optgroup label="Otros espacios">
          {otros.map((e) => (
            <option key={e.clave} value={e.clave}>
              {e.nombre}
            </option>
          ))}
        </optgroup>
      )}
    </select>
  );
}

export function Buscador({ d, onElegir }: { d: DatosMapa; onElegir: (i: number) => void }) {
  const [q, setQ] = useState("");
  const [abierto, setAbierto] = useState(false);
  useEffect(() => setQ(""), [d]);
  const res = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (t.length < 2) return [];
    const out: number[] = [];
    for (let i = 0; i < d.n && out.length < 6; i++) {
      const et = d.tipo === "embedding" ? d.puntos[i].etiqueta ?? "" : "";
      if (d.ids[i].toLowerCase().includes(t) || et.toLowerCase().includes(t)) out.push(i);
    }
    return out;
  }, [d, q]);
  const elegir = (i: number) => {
    onElegir(i);
    setQ(d.ids[i]);
    setAbierto(false);
  };
  return (
    <div className="pointer-events-auto relative w-full">
      <input
        id="mapa-busqueda"
        type="search"
        value={q}
        placeholder="Buscar id"
        autoComplete="off"
        spellCheck={false}
        aria-label="Buscar por id"
        onChange={(e) => {
          setQ(e.target.value);
          setAbierto(true);
        }}
        onFocus={() => setAbierto(true)}
        onBlur={() => setTimeout(() => setAbierto(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && res[0] !== undefined) elegir(res[0]);
          if (e.key === "Escape") setAbierto(false);
        }}
        className="h-9 w-full border border-line bg-surface px-s2 font-mono text-2xs text-ink placeholder:text-muted focus:border-ink focus:outline-none"
      />
      {abierto && q.trim().length >= 2 && (
        <ul className="absolute inset-x-0 top-full z-40 border border-t-0 border-line bg-surface" role="listbox">
          {res.length === 0 && <li className="px-s2 py-s1 text-2xs text-muted">Sin coincidencias</li>}
          {res.map((i) => (
            <li key={i}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => elegir(i)} className="flex w-full justify-between gap-s2 px-s2 py-s1 text-left font-mono text-2xs text-ink hover:bg-sunken">
                <span className="truncate">{d.ids[i]}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Control segmentado de proyección: un clic, sin desplegable. */
export function SelectorProyeccion({ proys, actual, onCambio }: { proys: Proyeccion[]; actual: string; onCambio: (clave: Proyeccion["clave"]) => void }) {
  return (
    <div className="pointer-events-auto flex border border-line bg-surface" role="radiogroup" aria-label="Proyección" data-testid="mapa-proyeccion">
      {proys.map((p) => {
        const activa = p.clave === actual;
        return (
          <button
            key={p.clave}
            type="button"
            role="radio"
            aria-checked={activa}
            onClick={() => onCambio(p.clave)}
            className={`h-9 flex-1 border-r border-line px-s2 text-xs last:border-r-0 ${activa ? "bg-ink text-bg" : "text-ink hover:bg-sunken"}`}
          >
            {p.nombre}
          </button>
        );
      })}
    </div>
  );
}
