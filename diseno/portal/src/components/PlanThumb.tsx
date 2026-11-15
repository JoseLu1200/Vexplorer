import type { DrawingContour } from "../api/types";

/** Tonos de madera clara por cara, con la luz desde arriba: la tapa más clara y el lado más oscuro. */
const CARA: Record<string, string> = { arriba: "#ead8b6", frente: "#d7bd92", lado: "#c3a57a" };

/** Miniatura del plano dibujada con los contornos del ledger (GET /runs/{id}/drawing), en trazo cobalto sobre fondo liso. */
export function PlanThumb({ contours, mm = true, className = "", label }: { contours: Pick<DrawingContour, "id" | "points_mm" | "points_source" | "closed">[]; mm?: boolean; className?: string; label: string }) {
  const points = contours.flatMap((c) => (mm ? c.points_mm ?? c.points_source : c.points_source));
  const a11y = label ? { role: "img", "aria-label": label } : { "aria-hidden": true };
  if (!points.length) return <div className={className} {...a11y} />;
  const xs = points.map((p) => p.x), ys = points.map((p) => -p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const w = maxX - minX || 1, h = maxY - minY || 1, pad = Math.max(w, h) * 0.08;
  return (
    <svg viewBox={`${minX - pad} ${minY - pad} ${w + pad * 2} ${h + pad * 2}`} preserveAspectRatio="xMidYMid meet" className={className} {...a11y}>
      {contours.map((c) => {
        const pts = mm ? c.points_mm ?? c.points_source : c.points_source;
        // Caras del montaje (miniaturaMontaje): sólido en madera clara con una sombra por cara y aristas finas en tinta.
        const cara = CARA[c.id.slice(c.id.lastIndexOf(":") + 1)];
        return (
          <path key={c.id} d={pts.map((p, i) => `${i ? "L" : "M"}${p.x} ${-p.y}`).join(" ") + (c.closed ? " Z" : "")} pathLength={1}
            fill={cara ?? "rgb(var(--cobalt) / 0.06)"} stroke="#4a2f1c" strokeWidth={cara ? 0.7 : 1.4} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        );
      })}
    </svg>
  );
}
