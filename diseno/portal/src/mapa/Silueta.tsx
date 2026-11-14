import { useEffect, useState } from "react";
import { type DatosGeo, type DatosMapa, type Rects, medidas, renderDe, silueta, siluetaEnCache } from "./datos";

// Vista frontal (x/z) del mueble: trasera al fondo, estructura en tinta y frentes (puertas, cajones) delante.
const TRASERA = 5;
const PUERTA = 6;
const CAJON = 7;

export function useSilueta(d: DatosGeo | null, i: number | null): Rects | null {
  const [r, setR] = useState<Rects | null>(() => (d && i !== null ? siluetaEnCache(d, i) ?? null : null));
  useEffect(() => {
    if (!d || i === null) {
      setR(null);
      return;
    }
    const hit = siluetaEnCache(d, i);
    setR(hit ?? null);
    if (hit) return;
    let vivo = true;
    silueta(d, i).then((x) => vivo && setR(x), () => {});
    return () => {
      vivo = false;
    };
  }, [d, i]);
  return r;
}

export function Silueta({ d, i, caja = 72, className = "" }: { d: DatosGeo; i: number; caja?: number; className?: string }) {
  const rects = useSilueta(d, i);
  const [W, , H] = medidas(d, i);
  // Encaje: se usa la extensión real de los rectángulos (no solo la envolvente declarada) y un margen, para que la silueta nunca salga cortada.
  let x0 = 0, x1 = 255, y0 = 0, y1 = 255;
  if (rects && rects.length) {
    x0 = 255; x1 = 0; y0 = 255; y1 = 0;
    for (let o = 0; o < rects.length; o += 5) { x0 = Math.min(x0, rects[o]); y0 = Math.min(y0, rects[o + 1]); x1 = Math.max(x1, rects[o + 2]); y1 = Math.max(y1, rects[o + 3]); }
    if (x1 <= x0) { x0 = 0; x1 = 255; }
    if (y1 <= y0) { y0 = 0; y1 = 255; }
  }
  const pad = Math.max(3, caja * 0.06);
  const util = caja - 2 * pad;
  const Wr = W * (x1 - x0) / 255, Hr = H * (y1 - y0) / 255;
  const esc = util / Math.max(Wr, Hr, 1e-6);
  const w = Math.max(6, W * esc);
  const h = Math.max(6, H * esc);
  const offX = (caja - Wr * esc) / 2 - (x0 / 255) * w;
  const offY = (caja - Hr * esc) / 2 - ((255 - y1) / 255) * h;
  return (
    <svg width={caja} height={caja} viewBox={`0 0 ${caja} ${caja}`} className={className} aria-hidden="true" style={{ overflow: "visible", flexShrink: 0 }}>
      <g transform={`translate(${offX} ${offY})`}>
        {rects
          ? Array.from({ length: rects.length / 5 }, (_, k) => {
              const o = k * 5;
              const rol = rects[o + 4];
              const x = (rects[o] / 255) * w;
              const y = h - (rects[o + 3] / 255) * h;
              const rw = Math.max(0.8, ((rects[o + 2] - rects[o]) / 255) * w);
              const rh = Math.max(0.8, ((rects[o + 3] - rects[o + 1]) / 255) * h);
              if (rol === TRASERA) return <rect key={k} x={x} y={y} width={rw} height={rh} className="fill-sunken" />;
              if (rol === PUERTA || rol === CAJON)
                return <rect key={k} x={x + 0.5} y={y + 0.5} width={Math.max(0.5, rw - 1)} height={Math.max(0.5, rh - 1)} className="fill-surface stroke-ink" strokeWidth={1} fillOpacity={0.88} />;
              return <rect key={k} x={x} y={y} width={rw} height={rh} className="fill-ink" />;
            })
          : <rect x={0.5} y={0.5} width={w - 1} height={h - 1} className="fill-none stroke-line" strokeDasharray="2 2" />}
      </g>
    </svg>
  );
}

/** Silueta frontal en geometría; render del plano en embeddings, o un hueco si no hay render. */
export function Miniatura({ d, i, caja = 72, className = "" }: { d: DatosMapa; i: number; caja?: number; className?: string }) {
  if (d.tipo === "geometria") return <Silueta d={d} i={i} caja={caja} className={className} />;
  const src = renderDe(d, i);
  return src ? (
    <img src={src} alt="" width={caja} height={caja} className={`border border-line bg-white object-contain ${className}`} style={{ width: caja, height: caja }} />
  ) : (
    <span className={`block border border-dashed border-line ${className}`} style={{ width: caja, height: caja }} />
  );
}
