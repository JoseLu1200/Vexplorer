import { useState } from "react";
import { COPY } from "../copy";
import type { ArchivoVista, LaminaVista, PrimitivaLamina, Punto } from "../general";
import { CLASE } from "./mesa";

const TONE: Record<string, string> = { observed: "rgb(var(--ink))", calculated: "rgb(var(--calc))", hypothesis: "rgb(var(--hip))", confirmed: "rgb(var(--conf))", unknown: "rgb(var(--muted))" };
const MONO = "Martian Mono, ui-monospace, monospace";
const WIDTH_PX = 760;

/** Láminas de construcción del backend dibujadas desde sus primitivas en mm. Una lista a la izquierda y la lámina elegida. */
export function Laminas({ laminas, initial, onDownload }: { laminas: LaminaVista[]; initial: string | null; onDownload?: (file: ArchivoVista) => void }) {
  const [current, setCurrent] = useState<string | null>(initial ?? laminas[0]?.id ?? null);
  const lamina = laminas.find((item) => item.id === current) ?? laminas[0] ?? null;
  if (!lamina) return <p className="p-s4 text-base text-muted">{COPY.portal.general.noSheets}</p>;
  return (
    <div className="grid grid-cols-1 gap-s4 p-s4 lg:grid-cols-[220px_minmax(0,1fr)] lg:p-s5" data-print="laminas">
      <ul className="flex flex-row gap-s2 overflow-x-auto lg:flex-col lg:overflow-visible" aria-label={COPY.portal.out.sheets} data-noprint>
        {laminas.map((item) => (
          <li key={item.id} className="shrink-0">
            <button className={`w-full border px-s3 py-s2 text-left text-sm ${item.id === lamina.id ? "border-ink bg-surface font-semibold text-ink" : "border-line text-ink hover:border-ink"}`} onClick={() => setCurrent(item.id)} aria-pressed={item.id === lamina.id}>
              {item.titulo.replace(/^Pieza · /, "")}
            </button>
          </li>
        ))}
      </ul>
      <figure className="flex min-w-0 flex-col gap-s2 border border-line bg-surface p-s3">
        <figcaption className="text-sm font-semibold text-ink">{lamina.titulo}</figcaption>
        <Lamina lamina={lamina} />
        {lamina.archivos.length > 0 && (
          <p className="flex flex-wrap gap-x-s3 text-2xs text-muted">
            {lamina.archivos.map((file) => onDownload && (file.contenido != null || file.url)
              ? <button key={file.id} className="num font-mono text-ink underline underline-offset-2" data-noprint onClick={() => onDownload(file)}>{file.nombre}{file.estado === "incompleto" ? ` · ${COPY.portal.general.incomplete}` : ""}</button>
              : <span key={file.id} className="num font-mono">{file.nombre}{file.estado === "incompleto" ? ` · ${COPY.portal.general.incomplete}` : ""}</span>)}
          </p>
        )}
      </figure>
    </div>
  );
}

export function Lamina({ lamina }: { lamina: LaminaVista }) {
  // Láminas del backend que llegan como SVG (mesas, esquema general): se pintan como imagen, sin ejecutar nada del archivo.
  if (lamina.svg) {
    return <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(lamina.svg)}`} alt={lamina.titulo} className="block max-h-[640px] w-full bg-white object-contain" />;
  }
  const l = lamina.limites;
  if (!l) return null;
  const w = Math.max(l.maxX - l.minX, 1), h = Math.max(l.maxY - l.minY, 1);
  const m = Math.max(w, h) * 0.12;
  const k = (w + 2 * m) / WIDTH_PX; // mm por píxel
  const vb = `${l.minX - m} ${-(l.maxY + m)} ${w + 2 * m} ${h + 2 * m}`;
  const Y = ([x, y]: Punto): Punto => [x, -y];
  return (
    <svg viewBox={vb} width="100%" style={{ maxHeight: 560 }} role="img" aria-label={lamina.titulo} className="block bg-canvas">
      {lamina.primitivas.map((p, i) => <Primitiva key={i} p={p} k={k} Y={Y} />)}
    </svg>
  );
}

function Primitiva({ p, k, Y }: { p: PrimitivaLamina; k: number; Y: (p: Punto) => Punto }) {
  const color = TONE[CLASE[p.estado]];
  const dash = p.estado === "estimada" || p.estado === "hipotesis" ? `${5 * k} ${3 * k}` : undefined;
  const pts = p.puntos.map(Y);
  const line = (list: Punto[]) => list.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
  const text = (at: Punto, value: string, rotate = false, anchor: "middle" | "start" = "middle") => (
    <text x={at[0]} y={at[1]} fontSize={11 * k} fill={color} stroke="rgb(var(--canvas))" strokeWidth={3 * k} strokeLinejoin="round" textAnchor={anchor}
      fontFamily={MONO} style={{ paintOrder: "stroke", fontVariationSettings: '"wdth" 87.5' }} transform={rotate ? `rotate(-90 ${at[0]} ${at[1]})` : undefined}>
      {value}
    </text>
  );
  switch (p.tipo) {
    case "linea":
    case "polilinea":
    case "arco":
      return <path d={line(pts)} fill="none" stroke={color} strokeWidth={1.3 * k} strokeDasharray={dash} />;
    case "circulo": {
      if (pts.length < 2) return null;
      const r = Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]);
      return <circle cx={pts[0][0]} cy={pts[0][1]} r={r} fill="none" stroke={color} strokeWidth={1.3 * k} strokeDasharray={dash} />;
    }
    case "cota": {
      if (pts.length < 2) return null;
      const [a, b] = pts;
      const anchor = pts[2] ?? a;
      const horizontal = Math.abs(b[1] - a[1]) <= Math.abs(b[0] - a[0]);
      const off: Punto = horizontal ? [0, anchor[1] - a[1]] : [anchor[0] - a[0], 0];
      const s: Punto = [a[0] + off[0], a[1] + off[1]], e: Punto = [b[0] + off[0], b[1] + off[1]];
      const t = 3 * k;
      const mid: Punto = [(s[0] + e[0]) / 2 + (horizontal ? 0 : -4 * k), (s[1] + e[1]) / 2 + (horizontal ? (off[1] > 0 ? 13 * k : -4 * k) : 0)];
      return (
        <g stroke={color} strokeWidth={0.9 * k} fill="none">
          <path d={`${line([a, s])} ${line([b, e])} ${line([s, e])}`} strokeDasharray={dash} />
          <path d={`M${s[0] - t} ${s[1] + t} L${s[0] + t} ${s[1] - t} M${e[0] - t} ${e[1] + t} L${e[0] + t} ${e[1] - t}`} />
          {p.texto && text(mid, p.texto, !horizontal)}
        </g>
      );
    }
    case "texto":
      return pts[0] && p.texto ? text(pts[0], p.texto, false, "start") : null;
    case "llamada":
      return (
        <g>
          <path d={line(pts)} fill="none" stroke={color} strokeWidth={k} />
          {p.texto && pts.length > 0 && text(pts[pts.length - 1], p.texto, false, "start")}
        </g>
      );
    default:
      return null;
  }
}
