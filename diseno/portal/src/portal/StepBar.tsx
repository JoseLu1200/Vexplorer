import type { ReactNode } from "react";
import { api } from "../api";
import type { Result } from "../api/types";
import { COPY } from "../copy";
import { RESULT_STATE_LABELS } from "../lib/domain";
import type { Screen } from "../router";

export type StepId = "original" | "plano" | "piezas" | "compras" | "presupuesto";
export type StepState = "done" | "review" | "pending" | "off";
const STEPS: StepId[] = ["original", "plano", "piezas", "compras", "presupuesto"];

/** Marca de estado de un paso: hecho relleno, por revisar en el tono de Hipótesis, pendiente vacío y sin datos en discontinuo. */
function Marker({ state }: { state: StepState }) {
  const cls = state === "done" ? "border-ink bg-ink" : state === "review" ? "border-hip border-2" : state === "pending" ? "border-line-strong" : "border-dashed border-line-strong";
  return <span className={`inline-block h-2.5 w-2.5 shrink-0 border ${cls}`} aria-hidden="true" />;
}

/** Barra fina con los cinco pasos. Cada uno cambia la vista del lienzo o abre su panel; no ocupa más sitio que esta fila. */
export function StepBar({ active, states, onStep, current, wide, extra = null, offTitle }: {
  active: StepId | null; states: Record<StepId, StepState>; onStep: (screen: Screen) => void; current: Result | null; wide: boolean;
  /** Indicadores compactos a la derecha (pendientes, avisos, evaluación). */
  extra?: ReactNode;
  offTitle?: string;
}) {
  return (
    <nav data-noprint aria-label={COPY.portal.stepsLabel} className="flex h-11 shrink-0 items-stretch border-t border-line bg-surface" data-testid="steps">
      <ol className="flex min-w-0 flex-1">
        {STEPS.map((step) => {
          const on = step === active;
          const disabled = states[step] === "off" && step !== "original" && step !== "plano";
          return (
            <li key={step} className="flex min-w-0 flex-auto lg:flex-none">
              <button
                className={`relative flex h-full w-full items-center justify-center gap-s1 px-0.5 text-2xs lg:justify-start lg:gap-s2 lg:px-s4 lg:text-sm ${on ? "font-bold text-ink" : disabled ? "cursor-not-allowed text-faint" : "font-medium text-muted hover:text-ink"}`}
                aria-current={on ? "step" : undefined}
                disabled={disabled}
                title={disabled ? offTitle ?? COPY.portal.off : `${COPY.portal.steps[step]}: ${COPY.portal.stepState[states[step]]}`}
                onClick={() => onStep(step)}
              >
                {on && <span className="absolute inset-x-s2 top-0 h-[3px] bg-ink lg:inset-x-s3" aria-hidden="true" />}
                <Marker state={states[step]} />
                <span className="truncate">{wide ? COPY.portal.steps[step] : COPY.portal.stepsShort[step]}</span>
                <span className="sr-only">, {COPY.portal.stepState[states[step]]}</span>
              </button>
            </li>
          );
        })}
      </ol>
      {extra && <div className="flex shrink-0 items-center gap-s2 border-l border-line px-s2 lg:px-s3">{extra}</div>}
      {wide && (
        <div className="flex shrink-0 items-center gap-s3 pr-s4">
          {current && (
            <span className="inline-flex items-center gap-s2 text-sm text-ink">
              <span className={`inline-block h-2 w-2 rounded-full ${current.state === "completed" ? "bg-conf" : "bg-hip"}`} aria-hidden="true" />
              <span className="num font-mono text-2xs">r{current.result_revision}</span>
              {RESULT_STATE_LABELS[current.state]}
            </span>
          )}
          {api.isMock && (
            <span className="inline-flex h-7 items-center whitespace-nowrap border border-line-strong px-s2 text-xs font-semibold text-ink" title="Respuestas grabadas del backend sobre planos públicos de ejemplo">{COPY.mockBadge}</span>
          )}
        </div>
      )}
    </nav>
  );
}
