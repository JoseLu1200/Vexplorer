/** Piezas de interfaz del espacio de trabajo: menú, diálogo, esqueleto, estado de plano, avisos y panel de subidas. */
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { COPY } from "../copy";
import { useRouter } from "../router";
import type { PlanStatus } from "../workspace/types";
import { useWorkspace } from "../workspace/store";
import { Spinner } from "./ui";

// ---- Menú contextual ----
export interface MenuItem { label: string; onSelect?: () => void; disabled?: boolean; hint?: string; danger?: boolean; group?: string }

export function Menu({ label, items, align = "right", className = "", trigger, triggerClassName = "h-8 w-8" }: { label: string; items: MenuItem[]; align?: "left" | "right"; className?: string; trigger?: ReactNode; triggerClassName?: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const onDown = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.stopPropagation(); setOpen(false); (root.current?.querySelector("[aria-haspopup]") as HTMLElement | null)?.focus(); }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const list = [...(root.current?.querySelectorAll<HTMLElement>("[role=menuitem]:not([aria-disabled=true])") ?? [])];
        const index = list.indexOf(document.activeElement as HTMLElement);
        list[(index + (event.key === "ArrowDown" ? 1 : -1) + list.length) % list.length]?.focus();
      }
    };
    addEventListener("pointerdown", onDown);
    addEventListener("keydown", onKey, true);
    setTimeout(() => (root.current?.querySelector("[role=menuitem]:not([aria-disabled=true])") as HTMLElement | null)?.focus(), 0);
    return () => { removeEventListener("pointerdown", onDown); removeEventListener("keydown", onKey, true); };
  }, [open]);
  return (
    <div ref={root} className={`relative ${className}`} onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        className={`inline-flex items-center justify-center text-ink hover:bg-sunken ${triggerClassName}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-label={label}
        title={label}
        onClick={() => setOpen((value) => !value)}
      >
        {trigger ?? <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="3.5" cy="8" r="1.3" fill="currentColor" /><circle cx="8" cy="8" r="1.3" fill="currentColor" /><circle cx="12.5" cy="8" r="1.3" fill="currentColor" /></svg>}
      </button>
      {open && (
        <div id={id} role="menu" aria-label={label} className={`absolute top-[calc(100%+4px)] z-40 flex min-w-[220px] flex-col border border-line-strong bg-surface py-s1 shadow-[0_8px_24px_rgb(0_0_0/0.12)] ${align === "right" ? "right-0" : "left-0"}`}>
          {items.map((item, index) => (
            <div key={item.label} className="contents">
            {item.group && item.group !== items[index - 1]?.group && (
              <span role="presentation" className={`px-s3 pb-s1 pt-s2 text-2xs font-semibold text-muted ${index ? "mt-s1 border-t border-line" : ""}`}>{item.group}</span>
            )}
            <button
              type="button"
              role="menuitem"
              aria-disabled={item.disabled || undefined}
              className={`flex min-h-[36px] flex-col items-start justify-center px-s3 py-s1 text-left text-sm ${item.disabled ? "cursor-not-allowed text-muted" : item.danger ? "text-danger hover:bg-sunken focus:bg-sunken" : "text-ink hover:bg-sunken focus:bg-sunken"} outline-none`}
              onClick={() => { if (item.disabled) return; setOpen(false); item.onSelect?.(); }}
            >
              <span>{item.label}</span>
              {item.hint && <span className="text-2xs text-muted">{item.hint}</span>}
            </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---- Diálogo modal ----
export function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.stopPropagation(); onClose(); }
      if (event.key === "Tab" && box.current) {
        const focusables = [...box.current.querySelectorAll<HTMLElement>("button:not(:disabled), input, select, textarea, [tabindex='0']")];
        if (!focusables.length) return;
        const first = focusables[0], last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    addEventListener("keydown", onKey, true);
    setTimeout(() => (box.current?.querySelector<HTMLElement>("input, select, button.btn-primary, button") ?? box.current)?.focus(), 0);
    return () => { removeEventListener("keydown", onKey, true); previous?.focus?.(); };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-[rgb(var(--ink)/0.28)] sm:items-center" onPointerDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div ref={box} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} className="anim-in flex max-h-[85vh] w-full flex-col border border-line-strong bg-surface sm:w-[440px]">
        <h2 id={titleId} className="border-b border-line px-s4 py-s3 text-md font-semibold text-ink">{title}</h2>
        <div className="scroll-thin flex flex-col gap-s3 overflow-y-auto px-s4 py-s4">{children}</div>
        <div className="flex justify-end gap-s2 border-t border-line px-s4 py-s3 pb-[max(12px,env(safe-area-inset-bottom,0px))]">{footer}</div>
      </div>
    </div>
  );
}

// ---- Esqueleto ----
export function Skel({ className = "" }: { className?: string }) {
  return <span className={`skel block ${className}`} aria-hidden="true" />;
}

// ---- Estado de un plano ----
const STATUS_DOT: Record<PlanStatus, string> = {
  analyzing: "",
  needs_review: "bg-hip",
  reviewed: "bg-conf",
  error: "bg-danger",
};
export function StatusBadge({ status, className = "" }: { status: PlanStatus; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-s2 whitespace-nowrap text-sm ${status === "error" ? "text-danger" : "text-ink"} ${className}`}>
      {status === "analyzing" ? <Spinner size={11} /> : <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[status]}`} aria-hidden="true" />}
      {COPY.status[status]}
    </span>
  );
}

// ---- Avisos breves ----
export function Toasts() {
  const { toasts, dismissToast } = useWorkspace();
  return (
    <div className="pointer-events-none fixed inset-x-0 top-[68px] z-50 flex flex-col items-center gap-s2 px-s4" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast-in pointer-events-auto flex w-full max-w-[420px] items-center gap-s3 border px-s4 py-s3 text-sm shadow-[0_8px_24px_rgb(0_0_0/0.14)] ${toast.tone === "error" ? "border-danger/60 bg-danger-soft text-ink" : "border-ink bg-ink text-surface"}`}>
          <span className="min-w-0 flex-1 break-words">{toast.message}</span>
          {toast.action && (
            <button className={`shrink-0 font-semibold underline underline-offset-2 ${toast.tone === "error" ? "text-ink" : "text-surface"}`} onClick={() => { toast.action!.run(); dismissToast(toast.id); }}>{toast.action.label}</button>
          )}
          <button className={`shrink-0 ${toast.tone === "error" ? "text-ink" : "text-surface"}`} onClick={() => dismissToast(toast.id)} aria-label={COPY.toasts.dismiss}>
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
          </button>
        </div>
      ))}
    </div>
  );
}

// ---- Panel de subidas ----
const STEPS = ["uploading", "reading", "running", "tracing", "done"];

export function QueuePanel() {
  const { uploads, live, plans, retry, clearUploads } = useWorkspace();
  const { navigate, route } = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  // En la mesa de trabajo queda por encima de la barra de pasos.
  const lift = route.kind === "plan" ? "bottom-[44px] lg:bottom-[56px]" : "bottom-0 lg:bottom-s4";
  const items = uploads.map((id) => ({ plan: plans.find((plan) => plan.id === id), live: live[id] })).filter((item) => item.plan);
  if (!items.length) return null;
  const busy = items.filter((item) => item.live && item.live.stage !== "done" && item.live.stage !== "error").length;
  return (
    <section aria-label={COPY.queue.title} className={`fixed inset-x-0 ${lift} z-40 flex max-h-[50vh] flex-col border-t-2 border-ink bg-surface shadow-[0_-8px_24px_rgb(0_0_0/0.12)] lg:left-auto lg:right-s4 lg:w-[400px] lg:border-2`} data-testid="queue">
      <div className="flex h-11 shrink-0 items-center justify-between gap-s2 border-b border-line pl-s4 pr-s1">
        <h2 className="flex items-center gap-s2 text-base font-semibold text-ink">{busy > 0 && <Spinner size={12} />}{COPY.queue.title}</h2>
        <div className="flex items-center">
          <button className="btn btn-ghost btn-icon" onClick={() => setCollapsed((value) => !value)} aria-expanded={!collapsed} aria-label={collapsed ? COPY.queue.expand : COPY.queue.collapse} title={collapsed ? COPY.queue.expand : COPY.queue.collapse}>
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className={collapsed ? "rotate-180" : ""}><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
          {busy === 0 && (
            <button className="btn btn-ghost btn-icon" onClick={clearUploads} aria-label={COPY.queue.close} title={COPY.queue.close}>
              <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
            </button>
          )}
        </div>
      </div>
      {!collapsed && (
        <ul className="scroll-thin divide-y divide-line overflow-y-auto">
          {items.map(({ plan, live: entry }) => {
            const stage = entry?.stage ?? (plan!.status === "error" ? "error" : plan!.status === "analyzing" ? "queued" : "done");
            const step = STEPS.indexOf(stage);
            const errorText = entry?.error ? shortError(entry.error.code, entry.error.message) : plan!.error ? shortError(plan!.error.code, plan!.error.message) : "";
            return (
              <li key={plan!.id} className="flex flex-col gap-s2 px-s4 py-s3" data-testid="queue-item" data-stage={stage}>
                <div className="flex items-center justify-between gap-s3">
                  <span className="num min-w-0 truncate font-mono text-2xs text-ink" title={plan!.filename}>{plan!.filename}</span>
                  {stage === "error" ? (
                    errorRetryable(entry?.error?.code ?? plan!.error?.code) ? <button className="shrink-0 text-sm font-semibold text-ink underline underline-offset-2" onClick={() => retry(plan!.id)}>{COPY.queue.retry}</button> : null
                  ) : (
                    <button className="shrink-0 text-sm font-semibold text-ink underline underline-offset-2" onClick={() => navigate({ kind: "plan", planId: plan!.id, screen: stage === "done" ? "plano" : "analisis" })}>{COPY.queue.view}</button>
                  )}
                </div>
                <div className="flex items-center gap-s3">
                  <span className="grid flex-1 grid-cols-5 gap-0.5" aria-hidden="true">
                    {STEPS.map((name, index) => (
                      <span key={name} className={`h-1 ${stage === "error" ? (index === 0 ? "bg-danger" : "bg-line") : index <= step ? "bg-ink" : index === step + 1 && stage !== "done" && stage !== "queued" ? "anim-pulse bg-line-strong" : "bg-line"}`} />
                    ))}
                  </span>
                  <span className={`w-[132px] shrink-0 text-right text-xs ${stage === "error" ? "text-danger" : "text-muted"}`}>{stage === "error" ? COPY.queue.stages.error : COPY.queue.stages[stage]}</span>
                </div>
                {errorText && <p className="text-sm text-danger" data-testid="queue-error">{errorText}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const SHORT_ERRORS: Record<string, string> = {
  unsupported_format: "Formato no admitido: Vexplorer solo lee DXF.",
  upload_too_large: "El archivo supera 20 MiB.",
  invalid_dxf: "El DXF no se puede leer.",
  unsupported_geometry: "Las vistas no forman piezas rectangulares.",
  live_provider_unavailable: "El asistente IA no está activado.",
  live_provider_failed: "El asistente IA falló durante el análisis.",
  network_error: "Sin conexión con el servidor.",
  file_missing: "El DXF ya no está guardado en este navegador.",
};
export const shortError = (code: string, message: string) => SHORT_ERRORS[code] ?? message;
const errorRetryable = (code: string | undefined) => code !== "unsupported_format" && code !== "upload_too_large" && code !== "file_missing";
