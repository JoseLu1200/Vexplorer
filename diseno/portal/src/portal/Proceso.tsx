import { useEffect } from "react";
import { COPY } from "../copy";
import type { EstadoPaso, PasoProceso } from "../general/proceso";
import { COLOR_CONFIANZA } from "./confianza";

const DOT: Record<EstadoPaso, string> = {
  hecho: "bg-conf", en_curso: "bg-wood animate-pulse", pendiente: "border border-line-strong", requiere_modelo: "border border-line-strong",
  requiere_revision: "bg-hip", fallo: "bg-danger", sin_datos: "border border-line-strong",
};

export interface ProcesoProps {
  pasos: PasoProceso[];
  /** Paso activo; null en la subida en curso, donde solo se ve el avance. */
  actual: number | null;
  onPaso?: (index: number) => void;
  auto?: boolean;
  onAuto?: (value: boolean) => void;
  onClose?: () => void;
  /** Etiqueta corta del origen del resultado (p. ej. «Guardado 14 nov»). */
  etiqueta?: string | null;
  /** Acción humana del paso activo, si la hay (aceptar la plantilla de mesa). */
  accion?: { label: string; busy: boolean; run: () => void } | null;
  className?: string;
}

/** Pasos del proceso en una columna: el activo con su línea, hora y modelo; Anterior, Siguiente y avance automático. */
export function Proceso({ pasos, actual, onPaso, auto = false, onAuto, onClose, etiqueta, accion, className = "" }: ProcesoProps) {
  const guiado = actual != null && !!onPaso;
  useEffect(() => {
    if (!guiado || !auto) return;
    if (actual! >= pasos.length - 1) { onAuto?.(false); return; }
    const timer = setTimeout(() => onPaso!(actual! + 1), 3500);
    return () => clearTimeout(timer);
  }, [guiado, auto, actual, pasos.length, onPaso, onAuto]);

  return (
    <section className={`flex flex-col border border-line-strong bg-surface ${className}`} aria-label={COPY.portal.proceso.title} data-testid="proceso">
      <header className="flex h-10 items-center justify-between gap-s2 border-b border-line pl-s3 pr-s1">
        <span className="flex min-w-0 items-baseline gap-s2">
          <h2 className="text-sm font-semibold text-ink">{COPY.portal.proceso.title}</h2>
          {etiqueta && <span className="truncate border border-line-strong px-s1 text-2xs text-ink" data-testid="etiqueta-origen">{etiqueta}</span>}
        </span>
        {onClose && (
          <button className="inline-flex h-8 w-8 items-center justify-center text-ink hover:bg-sunken" onClick={onClose} aria-label={COPY.portal.closeSheet} title={COPY.portal.closeSheet}>
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
          </button>
        )}
      </header>
      <ol className="flex flex-col py-s1">
        {pasos.map((p, i) => {
          const activo = actual === i;
          return (
            <li key={p.id}>
              <button
                className={`flex w-full flex-col gap-0.5 px-s3 py-s1 text-left ${activo ? "bg-sunken" : guiado ? "hover:bg-sunken" : "cursor-default"}`}
                onClick={() => guiado && onPaso!(i)} aria-current={activo ? "step" : undefined} disabled={!guiado} data-paso={p.id} data-estado={p.estado}
              >
                <span className="flex items-center gap-s2">
                  <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${DOT[p.estado]}`} aria-hidden="true" />
                  <span className={`min-w-0 flex-1 truncate text-sm ${activo ? "font-semibold" : ""} text-ink`}>{p.titulo}</span>
                  {p.hora && <span className="num shrink-0 font-mono text-2xs text-muted">{p.hora}</span>}
                </span>
                {(activo || !guiado) && (
                  <span className="flex flex-col gap-0.5 pl-s4 text-2xs text-ink">
                    <span>{p.linea}</span>
                    {p.modelo && <span className="num font-mono text-muted">{p.modelo}</span>}
                  </span>
                )}
                {activo && p.detalles && p.detalles.length > 0 && (
                  <ul className="mt-0.5 flex max-h-[220px] flex-col gap-0.5 overflow-y-auto pl-s4 text-2xs text-ink" data-testid="detalles-paso">
                    {p.detalles.map((d, k) => (
                      <li key={k} className="flex items-start gap-s1">
                        {d.nivel && <span className="mt-[3px] inline-block h-2 w-2 shrink-0" style={{ background: COLOR_CONFIANZA[d.nivel] }} aria-hidden="true" />}
                        <span>{d.texto}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </button>
              {activo && accion && (
                <div className="px-s3 pb-s2 pl-[calc(theme(spacing.s3)+theme(spacing.s4))]">
                  <button className="btn btn-sm" onClick={accion.run} disabled={accion.busy} data-testid="accion-proceso">{accion.busy ? COPY.portal.proceso.working : accion.label}</button>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {guiado && (
        <footer className="flex items-center justify-between gap-s2 border-t border-line px-s2 py-s1">
          <span className="flex items-center">
            <button className="inline-flex h-8 items-center px-s2 text-sm text-ink hover:bg-sunken disabled:opacity-40" onClick={() => onPaso!(Math.max(0, actual! - 1))} disabled={actual === 0}>{COPY.portal.proceso.prev}</button>
            <button className="inline-flex h-8 items-center px-s2 text-sm font-semibold text-ink hover:bg-sunken disabled:opacity-40" onClick={() => onPaso!(Math.min(pasos.length - 1, actual! + 1))} disabled={actual === pasos.length - 1} data-testid="proceso-siguiente">{COPY.portal.proceso.next}</button>
          </span>
          {onAuto && (
            <label className="inline-flex h-8 cursor-pointer items-center gap-s2 px-s2 text-sm text-ink">
              <input type="checkbox" checked={auto} onChange={(event) => onAuto(event.target.checked)} />
              {COPY.portal.proceso.auto}
            </label>
          )}
        </footer>
      )}
    </section>
  );
}
