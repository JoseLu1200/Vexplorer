import { useEffect, useRef } from "react";
import { COPY } from "../copy";
import { Swatch } from "../components/DataClass";
import { More } from "../components/ui";
import type { Cantidad, Medida, MesaTrabajo, PiezaVista } from "../general";
import { CLASE, ESTADO_MESA, ESTADO_TEXTO } from "./mesa";
import { COLOR_CONFIANZA } from "./confianza";

const VISTA: Record<string, string> = { FRONT: "Alzado", TOP: "Planta", SIDE: "Perfil" };
const ORDER = ["observed", "calculated", "hypothesis", "confirmed", "unknown"] as const;

export interface FichaGeneralProps {
  mesa: MesaTrabajo;
  selected: PiezaVista | null;
  hoverId: string | null;
  /** Sección del resumen a la que llevar la vista (los indicadores de la barra de pasos). */
  section: { id: "pendientes" | "avisos"; tick: number } | null;
  onHover(id: string | null): void;
  onSelect(id: string | null): void;
  onHoverContours(ids: string[] | null): void;
  onFocus(ids: string[]): void;
  onLamina(id: string): void;
}

/** Ficha de la vía general: sin selección, el resumen del mueble; con una pieza, sus medidas, su origen y sus pendientes. */
export function FichaGeneral(props: FichaGeneralProps) {
  return props.selected ? <Pieza {...props} pieza={props.selected} /> : <Resumen {...props} />;
}

function Resumen({ mesa, hoverId, section, onHover, onSelect }: FichaGeneralProps) {
  const pendientes = useRef<HTMLDetailsElement>(null);
  const avisos = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!section) return;
    const el = section.id === "pendientes" ? pendientes.current : avisos.current;
    if (el) { el.open = true; el.scrollIntoView({ block: "nearest" }); }
  }, [section]);
  const ev = mesa.evaluacion;
  const v = mesa.escena.validacion;
  return (
    <div className="flex flex-col gap-s4 p-s4">
      <h2 className="sr-only">{COPY.portal.summary}</h2>
      {mesa.coste && (
        <p className="flex items-baseline justify-between gap-s2" data-testid="coste">
          <span className="text-sm text-muted">{COPY.portal.general.cost}</span>
          <span className="num font-mono text-md font-semibold text-conf">{mesa.coste.total == null ? "?" : EUR(mesa.coste.moneda).format(mesa.coste.total)}</span>
        </p>
      )}
      {v && v.estado !== "accepted" && <Validacion v={v} />}

      {mesa.piezas.length > 0 && (
        <ul className="-mx-s2 flex flex-col" aria-label={COPY.portal.pieces}>
          {mesa.piezas.map((p) => (
            <li key={p.id}>
              <button
                className={`grid w-full grid-cols-[minmax(0,1fr)_auto_auto] items-baseline gap-x-s2 px-s2 py-s1 text-left ${hoverId === p.id ? "bg-sunken" : "hover:bg-sunken"}`}
                onClick={() => onSelect(p.id)} onPointerEnter={() => onHover(p.id)} onPointerLeave={() => onHover(null)} data-row={p.id} title={p.nombre}
              >
                <span className="truncate text-sm text-ink">{p.nombreCorto}</span>
                <span className="num font-mono text-2xs text-ink">{p.cantidad.valor == null ? "×?" : `×${p.cantidad.valor}`}</span>
                <span className="num whitespace-nowrap font-mono text-2xs text-ink">{medidas(p)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col">
        {mesa.pendientes.length > 0 && (
          <details ref={pendientes} className="group text-sm" data-testid="pendientes">
            <Summary label={COPY.portal.general.pending} n={mesa.pendientes.length} />
            <ul className="mt-s1 flex flex-col gap-s1 text-muted">{mesa.pendientes.map((p) => <li key={p.id}>{p.texto}</li>)}</ul>
          </details>
        )}
        {mesa.avisos.length > 0 && (
          <details ref={avisos} className="group text-sm">
            <Summary label={COPY.portal.general.warnings} n={mesa.avisos.length} />
            <ul className="mt-s1 flex flex-col gap-s1 text-muted">{mesa.avisos.map((a, i) => <li key={`${a.codigo}-${i}`}>{a.mensaje}</li>)}</ul>
          </details>
        )}
        {ev && (
          <More label={`${COPY.portal.general.evaluation} ${ev.cotasCorrectas}/${ev.cotasRequeridas}`}>
            <span>{ev.aprobado ? COPY.portal.general.passes : COPY.portal.general.fails}</span>
            <span>{COPY.portal.general.evalLine(ev)}</span>
            {ev.construccionPendiente.length > 0 && <span>{COPY.portal.general.missing}: {ev.construccionPendiente.join(", ")}</span>}
            {ev.limitaciones.map((item) => <span key={item}>{item}</span>)}
          </More>
        )}
        <More label={COPY.portal.details}>
          <span>{ESTADO_MESA[mesa.estado]}{mesa.sintetico ? ` · ${COPY.portal.general.synthetic}` : ""}</span>
          <span className="flex flex-wrap gap-x-s3 gap-y-s1 text-2xs" aria-label={COPY.workspace.legend}>
            {ORDER.map((cls) => <span key={cls} className="inline-flex items-center gap-s1" title={COPY.classDefs[cls]}><Swatch cls={cls} />{COPY.classes[cls]}</span>)}
            <span className="inline-flex items-center gap-s1">≈ {COPY.portal.general.estimated}</span>
          </span>
          {mesa.atribucion && <span data-testid="atribucion">{COPY.portal.general.source}: {mesa.atribucion}</span>}
          {mesa.original && <span className="num font-mono text-2xs">{mesa.original.nombre}</span>}
          {mesa.notas.map((n) => <span key={n}>{n}</span>)}
          {v?.incidencias.map((i) => <span key={i.codigo} className="num font-mono text-2xs">{i.codigo} ×{i.veces}</span>)}
          {mesa.coste?.conceptos.map((c) => <span key={c.id}>{c.etiqueta}: <span className="num font-mono text-2xs">{c.importe == null ? "?" : EUR(mesa.coste!.moneda).format(c.importe)}</span></span>)}
          {mesa.coste?.avisos.map((a) => <span key={a}>{a}</span>)}
        </More>
      </div>
    </div>
  );
}

const EUR = (currency: string) => new Intl.NumberFormat("es-ES", { style: "currency", currency, maximumFractionDigits: 2 });
const mmText = (value: number) => `${Number(value.toFixed(1)).toLocaleString("es-ES")} mm`;
const cifra = (m: Medida) => (m.valor_mm == null ? "?" : `${Number.isInteger(m.valor_mm) ? m.valor_mm : Number(m.valor_mm.toFixed(1))}`);
/** Medidas de la lista: una sola «≈» delante si alguna es estimada; sin color. */
const medidas = (p: PiezaVista) => `${[p.largo, p.ancho, p.grueso].some((m) => m.estimada) ? "≈ " : ""}${cifra(p.largo)} × ${cifra(p.ancho)} × ${cifra(p.grueso)}`;

/** Resultado del validador de montaje en una línea; el desglose y la penetración máxima, plegados. */
function Validacion({ v }: { v: NonNullable<MesaTrabajo["escena"]["validacion"]> }) {
  const cruces = v.incidencias.find((i) => i.codigo === "aabb_penetration")?.veces ?? 0;
  const total = v.incidencias.reduce((sum, i) => sum + i.veces, 0);
  return (
    <details className="group text-sm" data-testid="validacion">
      <summary className="flex cursor-pointer select-none items-center gap-s2 text-ink marker:content-none">
        <span className="inline-block h-2 w-2 shrink-0 bg-danger" aria-hidden="true" />
        <span className="font-semibold">{v.estado === "rejected" ? COPY.portal.general.rejected : v.estado}</span>
        <span>· {cruces ? COPY.portal.general.crossings(cruces) : COPY.portal.general.issues(total)}</span>
      </summary>
      <ul className="mt-s1 flex flex-col gap-0.5 pl-s4 text-muted">
        {v.incidencias.map((i) => (
          <li key={i.codigo} className="flex items-baseline justify-between gap-s2">
            <span className="min-w-0">{i.etiqueta}</span>
            <span className="num shrink-0 font-mono text-2xs">×{i.veces}</span>
          </li>
        ))}
        {v.penetracionMax_mm > 0 && <li className="flex items-baseline justify-between gap-s2"><span>{COPY.portal.general.maxPenetration}</span><span className="num font-mono text-2xs">{mmText(v.penetracionMax_mm)}</span></li>}
      </ul>
    </details>
  );
}

function Summary({ label, n }: { label: string; n: number }) {
  return (
    <summary className="inline-flex min-h-[32px] cursor-pointer select-none items-center gap-s2 text-muted marker:content-none hover:text-ink">
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className="transition-transform group-open:rotate-90"><path d="M3.5 2 7 5 3.5 8" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg>
      {label} <span className="num font-mono text-2xs text-ink">{n}</span>
    </summary>
  );
}

function Pieza({ mesa, pieza, onSelect, onHoverContours, onFocus, onLamina }: FichaGeneralProps & { pieza: PiezaVista }) {
  const index = mesa.piezas.findIndex((p) => p.id === pieza.id);
  const step = (delta: number) => onSelect(mesa.piezas[(index + delta + mesa.piezas.length) % mesa.piezas.length].id);
  const vistas = new Map<string, string[]>();
  const contorno = new Map((mesa.plano?.contornos ?? []).map((c) => [c.id, c]));
  pieza.contornos.forEach((id) => { const v = contorno.get(id)?.vista ?? ""; vistas.set(v, [...(vistas.get(v) ?? []), id]); });
  const etiqueta = (viewId: string) => VISTA[mesa.plano?.vistas.find((v) => v.id === viewId)?.etiqueta ?? ""] ?? COPY.portal.general.drawing;
  const pendientes = mesa.pendientes.filter((p) => p.piezaId === pieza.id);
  const validacion = mesa.escena.validacion;
  const incidencias = validacion?.incidencias.filter((i) => i.piezas.includes(pieza.id)) ?? [];
  // Las incidencias del montaje ya tienen su bloque: en Detalles solo van los demás avisos de la pieza.
  const avisos = mesa.avisos.filter((a) => a.piezas.includes(pieza.id) && !incidencias.some((i) => i.codigo === a.codigo));
  const sinCaja = mesa.escena.sinCaja.find((item) => item.piezaId === pieza.id);
  const lamina = pieza.laminas[0] ?? mesa.laminas.find((l) => l.piezaId === pieza.id)?.id ?? null;
  const medidas: [string, Medida | Cantidad][] = [[COPY.cols.quantity, pieza.cantidad], [COPY.cols.length, pieza.largo], [COPY.cols.width, pieza.ancho], [COPY.cols.thickness, pieza.grueso]];
  return (
    <div className="anim-in flex flex-col gap-s4 p-s4" data-testid="ficha">
      <div className="flex items-center justify-between gap-s2">
        <button className="inline-flex h-8 items-center gap-s1 text-sm text-muted hover:text-ink" onClick={() => onSelect(null)}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
          {COPY.portal.back}
        </button>
        <span className="flex items-center">
          <Icon label={COPY.portal.prev} onClick={() => step(-1)} d="M3 7.5 6 4.5l3 3" />
          <Icon label={COPY.portal.next} onClick={() => step(1)} d="M3 4.5 6 7.5l3-3" />
          <Icon label={COPY.portal.clear} onClick={() => onSelect(null)} d="M3 3l6 6M9 3 3 9" />
        </span>
      </div>
      <div className="flex flex-col gap-s1">
        <h2 className="text-lg font-semibold leading-6 text-ink">{pieza.nombre}</h2>
        {pieza.confianza ? (
          <p className="flex items-start gap-s2 text-sm text-ink" data-testid="confianza">
            <span className="mt-1 inline-block h-2.5 w-2.5 shrink-0" style={{ background: COLOR_CONFIANZA[pieza.confianza.nivel] }} aria-hidden="true" />
            <span>{COPY.portal.general.confianzaLinea(pieza.confianza.nivel)} {pieza.confianza.motivo}</span>
          </p>
        ) : pieza.inferida && <p className="text-sm text-muted" data-testid="inferida">{COPY.portal.general.inferred}</p>}
      </div>

      <dl className="divide-y divide-line border-y border-line">
        {medidas.map(([label, m]) => {
          const cls = CLASE[m.estado];
          const known = "valor_mm" in m ? m.valor_mm != null : m.valor != null;
          return (
            <div key={label} className="flex items-baseline justify-between gap-s2 py-s2">
              <dt className="text-sm text-muted">{label}</dt>
              <dd className="flex items-center gap-s2 text-right" title={known ? ESTADO_TEXTO[m.estado] : undefined}>
                {known && <Swatch cls={cls} />}
                <span className="num whitespace-nowrap font-mono text-[13px] text-ink">{m.texto}</span>
              </dd>
            </div>
          );
        })}
      </dl>

      {!pieza.inferida && (
        <section className="flex flex-col gap-s2" aria-labelledby="g-contour">
          <div className="flex items-center justify-between">
            <h3 id="g-contour" className="text-sm text-muted">{COPY.portal.contour}</h3>
            <button className="text-sm font-semibold text-ink underline underline-offset-2" onClick={() => onFocus(pieza.contornos)}>{COPY.portal.focus}</button>
          </div>
          <ul className="flex flex-wrap gap-s2">
            {[...vistas].map(([viewId, ids]) => (
              <li key={viewId}>
                <button className="inline-flex h-8 items-center gap-s2 border border-line-strong px-s2 text-sm text-ink hover:border-ink hover:bg-sunken"
                  onPointerEnter={() => onHoverContours(ids)} onPointerLeave={() => onHoverContours(null)} onFocus={() => onHoverContours(ids)} onBlur={() => onHoverContours(null)} onClick={() => onFocus(ids)}>
                  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="1.5" y="3" width="9" height="6" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
                  {etiqueta(viewId)}{ids.length > 1 && <span className="num font-mono text-2xs text-muted">×{ids.length}</span>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {lamina && <button className="btn btn-sm self-start" onClick={() => onLamina(lamina)}>{COPY.portal.general.seeSheet}</button>}

      {incidencias.length > 0 && (
        <ul className="flex flex-col gap-s1 border-l-2 border-danger pl-s3 text-sm text-ink" data-testid="incidencias-pieza">
          {incidencias.map((i) => (
            <li key={i.codigo}>
              {i.etiqueta}
              {i.codigo === "aabb_penetration" && validacion && validacion.penetracionMax_mm > 0 && (
                <span className="block text-2xs text-muted">{COPY.portal.general.maxPenetration} <span className="num font-mono">{mmText(validacion.penetracionMax_mm)}</span></span>
              )}
            </li>
          ))}
        </ul>
      )}

      {(pendientes.length > 0 || sinCaja) && (
        <ul className="flex flex-col gap-s1 border-l-2 border-hip pl-s3 text-sm text-ink">
          {pendientes.map((p) => <li key={p.id}>{p.texto}</li>)}
          {sinCaja && <li>{COPY.portal.general.no3d}: {sinCaja.motivo}</li>}
        </ul>
      )}

      <More label={COPY.portal.details}>
        <span>{pieza.rol}</span>
        {pieza.material && <span>{COPY.cols.material}: {pieza.material}</span>}
        {pieza.acabado && <span>{COPY.cols.finish}: {pieza.acabado}</span>}
        {[pieza.largo, pieza.ancho, pieza.grueso].map((m, i) => (m.formula || m.explicacion) && <span key={i}>{[COPY.cols.length, COPY.cols.width, COPY.cols.thickness][i]}: {[m.formula, m.explicacion].filter(Boolean).join(" · ")}</span>)}
        {avisos.map((a, i) => <span key={i}>{a.mensaje}</span>)}
        {incidencias.map((i) => <span key={i.codigo} className="num font-mono text-2xs">{i.codigo}</span>)}
        {pieza.notas.map((n) => <span key={n}>{n}</span>)}
        {pieza.contornosEvidencia.length > 0 && <span className="num font-mono text-2xs">{COPY.portal.evidence}: {pieza.contornosEvidencia.join(", ")}</span>}
        {pieza.referencias.length > 0 && <span className="num font-mono text-2xs">{pieza.referencias.join(", ")}</span>}
      </More>
    </div>
  );
}

function Icon({ label, onClick, d }: { label: string; onClick: () => void; d: string }) {
  return (
    <button className="inline-flex h-8 w-8 items-center justify-center text-ink hover:bg-sunken" onClick={onClick} aria-label={label} title={label}>
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d={d} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
  );
}
