import { useEffect, useMemo } from "react";
import type { DrawingExtraction, Point2D } from "../api/types";
import { COPY } from "../copy";
import { ValueCell } from "../components/DataClass";
import { fmt, type Cell, type DataClass, type PartRow } from "../lib/domain";

const TONE: Record<DataClass, string> = { observed: "rgb(var(--ink))", calculated: "rgb(var(--calc))", hypothesis: "rgb(var(--hip))", confirmed: "rgb(var(--conf))", unknown: "rgb(var(--muted))" };
const MONO = "Martian Mono, ui-monospace, monospace";
const SIDE_PX = 250;
const PAD = { l: 30, r: 10, t: 10, b: 30 };

interface Face { row: PartRow; paths: Point2D[][]; minX: number; minY: number; w: number; h: number }

/**
 * Piezas separadas: cada uso del despiece con la cara que dibuja el plano (la vista de más área), todas a la misma escala.
 * La geometría sale de los contornos del ledger y las cifras, de la fila del despiece con su clase de dato.
 */
export function PartsView({ rows, drawing, schematic = false, selectedId, relatedIds, hoverId, onSelect, onHover, insetTop = 0, insetBottom = 0 }: {
  rows: PartRow[]; drawing: DrawingExtraction; schematic?: boolean; selectedId: string | null; relatedIds: Set<string>; hoverId: string | null;
  onSelect: (id: string | null) => void; onHover: (id: string | null) => void; insetTop?: number; insetBottom?: number;
}) {
  const mm = drawing.coordinate_unit === "mm";
  // La tarjeta elegida desde otra vista o desde la lista queda a la vista.
  useEffect(() => {
    if (selectedId) document.querySelector(`[data-piece="${CSS.escape(selectedId)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);
  const faces = useMemo<Face[]>(() => {
    const byId = new Map(drawing.contours.map((c) => [c.id, c]));
    // Vistas montadas: los contornos son del mueble entero, así que la cara se dibuja con el largo y el ancho de la fila.
    if (schematic) {
      return rows.map((row) => {
        const L = typeof row.length.value === "number" ? row.length.value : null;
        const W = typeof row.width.value === "number" ? row.width.value : null;
        if (L === null || W === null) return { row, paths: [], minX: 0, minY: 0, w: 1, h: 1 };
        return { row, paths: [[{ x: 0, y: 0 }, { x: L, y: 0 }, { x: L, y: W }, { x: 0, y: W }]], minX: 0, minY: 0, w: L, h: W };
      });
    }
    return rows.map((row) => {
      let best: Face | null = null;
      for (const view of row.observation.views) {
        const paths = view.contour_ids.map((id) => byId.get(id)).filter(Boolean).map((c) => (mm ? c!.points_mm ?? c!.points_source : c!.points_source));
        const pts = paths.flat();
        if (!pts.length) continue;
        const minX = Math.min(...pts.map((p) => p.x)), maxX = Math.max(...pts.map((p) => p.x));
        const minY = Math.min(...pts.map((p) => p.y)), maxY = Math.max(...pts.map((p) => p.y));
        const face = { row, paths, minX, minY, w: Math.max(maxX - minX, 1), h: Math.max(maxY - minY, 1) };
        if (!best || face.w * face.h > best.w * best.h) best = face;
      }
      return best ?? { row, paths: [], minX: 0, minY: 0, w: 1, h: 1 };
    });
  }, [rows, drawing, mm, schematic]);
  const maxSide = Math.max(1, ...faces.map((f) => Math.max(f.w, f.h)));
  const s = SIDE_PX / maxSide;
  const boxH = Math.max(...faces.map((f) => f.h * s)) + PAD.t + PAD.b;

  return (
    <div
      className="plan-grid scroll-thin absolute inset-0 overflow-y-auto"
      style={{ paddingTop: insetTop + 8, paddingBottom: insetBottom + 64 }}
      onClick={() => onSelect(null)}
      data-print="laminas"
      aria-label={COPY.portal.viewTitles.piezas}
    >
      <ul className="grid gap-s3 px-s4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr))] lg:px-s5">
        {faces.map((face) => {
          const { row } = face;
          const selected = row.id === selectedId;
          const hovered = row.id === hoverId && !selected;
          const related = relatedIds.has(row.id) && !selected;
          // El lado horizontal lleva la cifra que más se parece a su medida dibujada; sin las dos cifras, el largo va en el lado mayor.
          const L = typeof row.length.value === "number" ? row.length.value : null;
          const W = typeof row.width.value === "number" ? row.width.value : null;
          const horizontalIsLength = mm && L !== null && W !== null ? Math.abs(face.w - L) <= Math.abs(face.w - W) : face.w >= face.h;
          const hCell = horizontalIsLength ? row.length : row.width;
          const vCell = horizontalIsLength ? row.width : row.length;
          return (
            <li key={row.id}>
              <button
                type="button"
                className={`flex w-full flex-col border bg-surface text-left transition-colors ${selected ? "is-selected border-ink" : hovered ? "border-ink bg-sunken" : related ? "border-line-strong bg-sunken/60" : "border-line hover:border-ink"}`}
                aria-pressed={selected}
                onClick={(event) => { event.stopPropagation(); onSelect(selected ? null : row.id); }}
                onPointerEnter={() => onHover(row.id)}
                onPointerLeave={() => onHover(null)}
                style={{ scrollMarginTop: insetTop + 8, scrollMarginBottom: insetBottom + 8 }}
                data-piece={row.id}
              >
                <span className="flex items-baseline justify-between gap-s2 px-s3 pt-s2">
                  <span className="flex min-w-0 items-baseline gap-s2">
                    <span className="num font-mono text-[13px] font-medium text-ink">{row.key}</span>
                    {row.role.value !== row.key && <span className="truncate"><ValueCell cell={row.role} align="left" /></span>}
                  </span>
                  <QtyCell cell={row.quantity} />
                </span>
                {face.paths.length === 0 ? (
                  <span className="flex items-center justify-center px-s3 text-sm text-muted" style={{ height: boxH }}>{COPY.portal.noFace}</span>
                ) : <svg width="100%" height={boxH} viewBox={`0 0 ${SIDE_PX + PAD.l + PAD.r} ${boxH}`} aria-hidden="true" className="block">
                  <g transform={`translate(${(SIDE_PX - face.w * s) / 2} ${(boxH - PAD.t - PAD.b - face.h * s) / 2})`}>
                    {face.paths.map((points, index) => (
                      <path
                        key={index}
                        d={points.map((p, i) => `${i ? "L" : "M"}${PAD.l + (p.x - face.minX) * s} ${PAD.t + (face.minY + face.h - p.y) * s}`).join(" ") + " Z"}
                        fill={selected ? "rgb(var(--wood) / 0.32)" : hovered ? "rgb(var(--wood) / 0.2)" : "rgb(var(--canvas))"}
                        stroke={selected || hovered ? "rgb(var(--select))" : "rgb(var(--canvas-ink))"}
                        strokeWidth={selected ? 1.8 : 1.3}
                        strokeLinejoin="round"
                      />
                    ))}
                    <Dim x1={PAD.l} y1={PAD.t + face.h * s + 12} x2={PAD.l + face.w * s} y2={PAD.t + face.h * s + 12} cell={hCell} />
                    <Dim x1={PAD.l - 12} y1={PAD.t + face.h * s} x2={PAD.l - 12} y2={PAD.t} cell={vCell} vertical />
                  </g>
                </svg>}
                <span className="flex items-center justify-between gap-s2 border-t border-line px-s3 py-s1 text-sm text-muted">
                  <span>{COPY.cols.thickness}</span>
                  <ValueCell cell={row.thickness} unit="mm" />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function QtyCell({ cell }: { cell: Cell }) {
  if (cell.value === null) return <span className="text-sm text-muted">{COPY.cols.qty} ?</span>;
  return <span className="num font-mono text-[13px]" style={{ color: TONE[cell.cls] }}>×{fmt(Number(cell.value))}</span>;
}

/** Línea de cota con el valor de la fila; un valor desconocido se rotula con «?». */
function Dim({ x1, y1, x2, y2, cell, vertical = false }: { x1: number; y1: number; x2: number; y2: number; cell: Cell; vertical?: boolean }) {
  const color = TONE[cell.cls];
  const label = cell.value === null ? "?" : fmt(Number(cell.value));
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  const k = 3;
  return (
    <g stroke={color} strokeWidth={0.9} fill="none">
      <path d={`M${x1} ${y1} L${x2} ${y2}`} strokeDasharray={cell.cls === "unknown" ? "3 2" : undefined} />
      <path d={`M${x1 - k} ${y1 + k} L${x1 + k} ${y1 - k} M${x2 - k} ${y2 + k} L${x2 + k} ${y2 - k}`} />
      <text
        x={vertical ? mx - 5 : mx} y={vertical ? my : my + 13} fontSize={11} fill={color} stroke="rgb(var(--surface))" strokeWidth={3} strokeLinejoin="round"
        textAnchor="middle" fontFamily={MONO} style={{ paintOrder: "stroke", fontVariationSettings: '"wdth" 87.5' }}
        transform={vertical ? `rotate(-90 ${mx - 5} ${my})` : undefined}
      >
        {label}
      </text>
    </g>
  );
}
