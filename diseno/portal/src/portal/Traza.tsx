import { COPY } from "../copy";
import type { PasoTraza } from "../general";

/**
 * Traza del pipeline en una línea por paso: hora, etiqueta, modelo y resultado. Los repetidos llegan agrupados
 * desde trazaDesdeEventos con sus veces y cada código de fallo. Sin párrafos ni resúmenes del payload.
 */
export function Traza({ pasos }: { pasos: PasoTraza[] }) {
  if (!pasos.length) return <p className="p-s4 text-sm text-muted">{COPY.portal.general.traceEmpty}</p>;
  return (
    <ol className="flex flex-col" data-testid="traza">
      {pasos.map((p) => (
        <li key={p.id} className="grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-s2 border-b border-line px-s4 py-s2 last:border-b-0">
          <span className="num pt-0.5 font-mono text-2xs text-muted">{p.hora}{p.horaFin && p.horaFin !== p.hora ? <><br />{p.horaFin}</> : null}</span>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="flex items-baseline gap-s2">
              <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${p.ok ? "bg-conf" : "bg-danger"}`} aria-hidden="true" />
              <span className="min-w-0 truncate text-sm text-ink">{p.etiqueta}</span>
              {p.veces > 1 && <span className="num shrink-0 font-mono text-2xs text-ink">×{p.veces}</span>}
            </span>
            <span className="flex flex-wrap items-baseline gap-x-s2 pl-s3 text-2xs text-muted">
              {p.modelo && <span className="num font-mono">{p.modelo}</span>}
              {p.estado && <span>{p.estado}</span>}
              {p.resultados.map((r) => (
                <span key={r.resultado} className={`num font-mono ${r.resultado === "ok" ? "" : "text-danger"}`}>
                  {r.resultado}{r.veces > 1 ? ` ×${r.veces}` : ""}
                </span>
              ))}
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}
