import type { ReactNode } from "react";
import { COPY } from "../copy";
import type { AppError } from "../state";

export function Spinner({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" className="animate-spin text-ink motion-reduce:animate-none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function LoadingBar() {
  return (
    <div className="relative h-0.5 w-full overflow-hidden bg-line" role="progressbar" aria-busy="true">
      <div className="anim-bar absolute inset-y-0 left-0 w-2/5 bg-ink" />
    </div>
  );
}

export function ErrorNote({ error, onRetry, action }: { error: AppError; onRetry?: () => void; action?: ReactNode }) {
  return (
    <div role="alert" className="flex flex-wrap items-start gap-s3 border border-danger/50 bg-danger-soft px-s4 py-s3 text-base">
      <svg width="16" height="16" viewBox="0 0 16 16" className="mt-0.5 shrink-0 text-danger" aria-hidden="true">
        <path d="M8 1.5 15 14H1Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
        <path d="M8 6v3.6M8 11.4v.1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      <div className="min-w-0 flex-1 basis-[240px]">
        <p className="text-ink">{error.message}</p>
        <TechDetails>
          <span className="num font-mono">{error.status ? `HTTP ${error.status} · ` : ""}{error.code}</span>
        </TechDetails>
      </div>
      {action}
      {onRetry && error.retryable && <button className="btn btn-sm" onClick={onRetry}>{COPY.errors.retry}</button>}
    </div>
  );
}

export function EmptyState({ title, body, action, children }: { title: string; body?: string; action?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-s3 py-s4">
      {children}
      <h2 className="text-lg font-semibold tracking-[-0.01em] text-ink">{title}</h2>
      {body && <p className="max-w-[48ch] text-base text-muted">{body}</p>}
      {action}
    </div>
  );
}

export function SectionTitle({ children, aside, id }: { children: ReactNode; aside?: ReactNode; id?: string }) {
  return (
    <div className="flex min-h-[32px] items-center justify-between gap-s3">
      <h2 id={id} className="text-md font-semibold text-ink">{children}</h2>
      {aside}
    </div>
  );
}

export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "strong" | "hip" }) {
  const tones = {
    neutral: "border-line-strong text-muted",
    strong: "border-ink bg-ink text-surface",
    hip: "border-hip border-dashed text-hip",
  };
  return <span className={`inline-flex h-6 items-center gap-s1 whitespace-nowrap border px-s2 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
}

export function Kv({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_1fr] items-baseline gap-s3 py-s2">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="min-w-0 text-base text-ink">{children}</dd>
    </div>
  );
}

export function IdList({ ids, max = 4 }: { ids: string[]; max?: number }) {
  if (!ids.length) return <span className="text-sm text-muted">Ninguna</span>;
  const shown = ids.slice(0, max);
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((id) => <code key={id} className="num bg-sunken px-1 font-mono text-2xs text-muted">{id}</code>)}
      {ids.length > max && <span className="text-2xs text-muted">y {ids.length - max} más</span>}
    </span>
  );
}

/** Contenido secundario a un clic: códigos, identificadores, premisas y explicaciones largas. */
export function More({ children, label = "Detalles técnicos", className = "" }: { children: ReactNode; label?: string; className?: string }) {
  return (
    <details className={`group text-sm ${className}`}>
      <summary className="inline-flex min-h-[32px] cursor-pointer select-none items-center gap-s2 text-muted marker:content-none hover:text-ink">
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className="transition-transform group-open:rotate-90"><path d="M3.5 2 7 5 3.5 8" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg>
        {label}
      </summary>
      <div className="mt-s1 flex flex-col gap-s1 text-muted">{children}</div>
    </details>
  );
}
export const TechDetails = More;
