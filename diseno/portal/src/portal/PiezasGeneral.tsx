import { useEffect } from "react";
import { COPY } from "../copy";
import type { Medida, PiezaVista } from "../general";
import { CLASE, corta } from "./mesa";

/** Cotas en tinta: lo estimado se distingue por el trazo discontinuo, no por el color. */
const TONE: Record<string, string> = { observed: "rgb(var(--ink))", calculated: "rgb(var(--ink))", hypothesis: "rgb(var(--ink))", confirmed: "rgb(var(--ink))", unknown: "rgb(var(--muted))" };
const MONO = "Martian Mono, ui-monospace, monospace";
const SIDE = 250;
const PAD = { l: 34, r: 10, t: 10, b: 30 };

/**
 * Piezas separadas de un mueble general: cada tipo de pieza con su largo y su ancho a la misma escala.
 * Lo estimado lleva «≈» y la línea discontinua; donde no hay medida se dice «sin medida» y no se dibuja nada.
 */
export function PiezasGeneral({ piezas, selectedId, hoverId, onSelect, onHover, insetTop = 0, insetBottom = 0 }: {
  piezas: PiezaVista[]; selectedId: string | null; hoverId: string | null; onSelect: (id: string | null) => void; onHover: (id: string | null) => void;
  insetTop?: number; insetBottom?: number;
}) {
  // La tarjeta elegida desde otra vista o desde la lista queda a la vista.
  useEffect(() => {
    if (selectedId) document.querySelector(`[data-piece="${CSS.escape(selectedId)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);
  const drawable = (p: PiezaVista) => p.largo.valor_mm != null && p.ancho.valor_mm != null;
  const maxSide = Math.max(1, ...piezas.filter(drawable).map((p) => Math.max(p.largo.valor_mm!, p.ancho.valor_mm!)));
  const s = SIDE / maxSide;
  const boxH = Math.max(60, ...piezas.filter(drawable).map((p) => p.ancho.valor_mm! * s)) + PAD.t + PAD.b;
  return (
    <div className="plan-grid scroll-thin absolute inset-0 overflow-y-auto" style={{ paddingTop: insetTop + 8, paddingBottom: insetBottom + 64 }} onClick={() => onSelect(null)} aria-label={COPY.portal.viewTitles.piezas}>
      <ul className="grid gap-s3 px-s4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr))] lg:px-s5">
        {piezas.map((p) => {
          const selected = p.id === selectedId;
          const hovered = p.id === hoverId && !selected;
          const w = drawable(p) ? p.largo.valor_mm! * s : 0;
          const h = drawable(p) ? p.ancho.valor_mm! * s : 0;
          const dashed = p.largo.estimada || p.ancho.estimada;
          return (
            <li key={p.id}>
              <button
                type="button"
                className={`flex w-full flex-col border bg-surface text-left transition-colors ${selected ? "is-selected border-ink" : hovered ? "border-ink bg-sunken" : "border-line hover:border-ink"}`}
                aria-pressed={selected}
                onClick={(event) => { event.stopPropagation(); onSelect(selected ? null : p.id); }}
                onPointerEnter={() => onHover(p.id)}
                onPointerLeave={() => onHover(null)}
                style={{ scrollMarginTop: insetTop + 8, scrollMarginBottom: insetBottom + 8 }}
                data-piece={p.id}
              >
                <span className="flex items-baseline justify-between gap-s2 px-s3 pt-s2">
                  <span className="min-w-0 truncate text-sm font-semibold text-ink" title={p.nombre}>{p.nombreCorto}</span>
                  <span className="num shrink-0 font-mono text-[13px]" style={{ color: TONE[CLASE[p.cantidad.estado]] }}>{p.cantidad.valor == null ? "×?" : `×${p.cantidad.valor}`}</span>
                </span>
                {p.inferida && <span className="px-s3 text-2xs text-muted">{COPY.portal.general.inferredShort}</span>}
                {drawable(p) ? (
                  <svg width="100%" height={boxH} viewBox={`0 0 ${SIDE + PAD.l + PAD.r} ${boxH}`} aria-hidden="true" className="block">
                    <g transform={`translate(${(SIDE - w) / 2} ${(boxH - PAD.t - PAD.b - h) / 2})`}>
                      <rect x={PAD.l} y={PAD.t} width={w} height={h} fill={selected ? "rgb(var(--wood) / 0.32)" : hovered ? "rgb(var(--wood) / 0.2)" : "rgb(var(--canvas))"}
                        stroke={selected || hovered ? "rgb(var(--select))" : "rgb(var(--canvas-ink))"} strokeWidth={selected ? 1.8 : 1.3} strokeDasharray={dashed ? "5 3" : undefined} />
                      <Dim x1={PAD.l} y1={PAD.t + h + 12} x2={PAD.l + w} y2={PAD.t + h + 12} m={p.largo} />
                      <Dim x1={PAD.l - 12} y1={PAD.t + h} x2={PAD.l - 12} y2={PAD.t} m={p.ancho} vertical />
                    </g>
                  </svg>
                ) : (
                  <span className="flex items-center justify-center px-s3 text-sm text-muted" style={{ height: boxH }}>{COPY.portal.general.noMeasure}</span>
                )}
                <span className="flex items-center justify-between gap-s2 border-t border-line px-s3 py-s1 text-sm text-muted">
                  <span>{COPY.cols.thickness}</span>
                  <span className={`num font-mono text-[13px]`} style={{ color: TONE[CLASE[p.grueso.estado]] }}>{p.grueso.valor_mm == null ? COPY.portal.general.noMeasure : `${corta(p.grueso)} mm`}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Dim({ x1, y1, x2, y2, m, vertical = false }: { x1: number; y1: number; x2: number; y2: number; m: Medida; vertical?: boolean }) {
  const color = TONE[CLASE[m.estado]];
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, k = 3;
  return (
    <g stroke={color} strokeWidth={0.9} fill="none">
      <path d={`M${x1} ${y1} L${x2} ${y2}`} strokeDasharray={m.estimada ? "3 2" : undefined} />
      <path d={`M${x1 - k} ${y1 + k} L${x1 + k} ${y1 - k} M${x2 - k} ${y2 + k} L${x2 + k} ${y2 - k}`} />
      <text x={vertical ? mx - 5 : mx} y={vertical ? my : my + 13} fontSize={11} fill={color} stroke="rgb(var(--surface))" strokeWidth={3} strokeLinejoin="round" textAnchor="middle"
        fontFamily={MONO} style={{ paintOrder: "stroke", fontVariationSettings: '"wdth" 87.5' }} transform={vertical ? `rotate(-90 ${mx - 5} ${my})` : undefined}>
        {m.valor_mm == null ? "?" : Number.isInteger(m.valor_mm) ? m.valor_mm : Number(m.valor_mm.toFixed(1))}
      </text>
    </g>
  );
}
