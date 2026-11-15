import { useEffect, useState } from "react";
import { api } from "../api";
import type { AssemblyCandidate, Result, ReviewDecision, ReviewRequest, RunSnapshot } from "../api/types";
import { COPY } from "../copy";
import { EmptyState, ErrorNote, Spinner } from "../components/ui";
import { ROLE_LABELS, type PartRow } from "../lib/domain";
import { toAppError, useStore, type AppError } from "../state";

export function NoRun() {
  const { go } = useStore();
  return (
    <div className="page py-s5 lg:py-s6">
      <EmptyState title={COPY.workspace.noRun} action={<button className="btn btn-primary" onClick={() => go("analisis")}>{COPY.workspace.noRunAction}</button>} />
    </div>
  );
}

export type EditField = "quantity" | "length" | "width" | "thickness";
export const EDIT_FIELDS: EditField[] = ["quantity", "length", "width", "thickness"];
const API_FIELD: Record<EditField, "quantity" | "length_mm" | "width_mm" | "thickness_mm"> = { quantity: "quantity", length: "length_mm", width: "width_mm", thickness: "thickness_mm" };

/** Mismo criterio que Revisión: se completa lo que el plano no observa y sigue desconocido. */
export function completable(row: PartRow, field: EditField) {
  if (row[field].cls !== "unknown") return false;
  return field === "quantity" ? (row.use ? row.use.quantity_source === "unknown" : row.observation.quantity.state !== "observed") : row.observation.dimensions[field].state !== "observed";
}

/** Montaje en dos palabras: dónde van tapa y base respecto a los laterales. */
export function layoutShort(candidate: AssemblyCandidate) {
  return candidate.layout === "between_sides" ? "Entre laterales" : candidate.layout === "cap_sides" ? "Sobre laterales" : "Montaje desconocido";
}

/** Reparto de funciones por pieza: «K1 lateral · K2 tapa y base · K3 balda». */
export function assignmentOf(candidate: AssemblyCandidate, keyOf: (observationId: string) => string) {
  const parts = new Map<string, string[]>();
  candidate.uses.forEach((use) => parts.set(keyOf(use.part_observation_id), [...(parts.get(keyOf(use.part_observation_id)) ?? []), (ROLE_LABELS[use.role] ?? use.role).toLowerCase()]));
  return [...parts].map(([key, list]) => `${key} ${list.join(" y ")}`).join(" · ");
}

function readReviewer(fallback: string) {
  try { return localStorage.getItem("vx-reviewer") || fallback; } catch { return fallback; }
}

/**
 * Completar desde el despiece los campos desconocidos de la pieza seleccionada.
 * Es la misma petición POST /reviews que Revisión, con el revisor, el motivo y el montaje elegido.
 */
export function InlineComplete({ row, candidate, result, run, focus, idSuffix }: { row: PartRow; candidate: AssemblyCandidate; result: Result; run: RunSnapshot; focus: { field: EditField; tick: number } | null; idSuffix: string }) {
  const { addRevision, reloadRun } = useStore();
  const fields = EDIT_FIELDS.filter((field) => completable(row, field));
  const [values, setValues] = useState<Partial<Record<EditField, string>>>({});
  const [reason, setReason] = useState("");
  const [reviewer, setReviewer] = useState(() => readReviewer(result.review?.reviewer_name ?? ""));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [error, setError] = useState<AppError | null>(null);
  useEffect(() => {
    if (!focus) return;
    const id = setTimeout(() => {
      const el = window.document.getElementById(`inline-${focus.field}${idSuffix}`) as HTMLInputElement | null;
      if (!el || !el.offsetParent) return;
      el.focus({ preventScroll: true });
      el.scrollIntoView({ block: "nearest" });
    }, 60);
    return () => clearTimeout(id);
  }, [focus, idSuffix]);
  if (!fields.length) return null;
  const confirmsLayout = result.selected_assembly_candidate_id !== candidate.id;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const filled = fields.filter((field) => (values[field] ?? "").trim() !== "");
    if (!filled.length || !reason.trim() || !reviewer.trim()) { setProblem(COPY.inline.missing); return; }
    const decision: ReviewDecision = { proposal_id: row.id, action: "confirm", role: row.use?.role ?? "unknown", notes: reason.trim() };
    for (const field of filled) {
      const value = Number(values[field]!.replace(",", "."));
      if (!Number.isFinite(value) || value <= 0) { setProblem(COPY.inline.invalid); return; }
      if (field === "quantity") decision.quantity = Math.round(value); else decision[API_FIELD[field] as "length_mm"] = value;
    }
    setProblem(null);
    setError(null);
    setBusy(true);
    const request: ReviewRequest = {
      base_result_revision: result.result_revision, reviewer_name: reviewer.trim(), assembly_candidate_id: candidate.id,
      decisions: [decision], notes: reason.trim(), material: null, finish: null,
    };
    try {
      const next = await api.createReview(run.id, request);
      try { localStorage.setItem("vx-reviewer", reviewer.trim()); } catch { /* sin almacenamiento */ }
      addRevision(next, request);
    } catch (err) {
      setError(toAppError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-s3 border-t border-line pt-s3" aria-labelledby={`inline-title${idSuffix}`} noValidate>
      <div className="flex flex-wrap items-baseline justify-between gap-s2">
        <h3 id={`inline-title${idSuffix}`} className="text-base font-semibold text-ink">{COPY.inline.title}</h3>
        <span className="text-sm text-muted">{COPY.inline.hint}</span>
      </div>
      <div className="grid grid-cols-1 gap-s3">
        {fields.map((field) => (
          <label key={field} htmlFor={`inline-${field}${idSuffix}`} className="flex flex-col gap-s1">
            <span className="text-sm font-semibold text-ink">{COPY.cols[field]}</span>
            <span className="unknown flex h-10 items-center gap-s2 border border-dashed border-line-strong px-s3 focus-within:border-solid focus-within:border-ink">
              <input
                id={`inline-${field}${idSuffix}`}
                inputMode="decimal"
                className="num w-full bg-transparent font-mono text-[13px] text-ink outline-none placeholder:font-sans placeholder:text-sm placeholder:text-muted"
                placeholder={COPY.classes.unknown}
                value={values[field] ?? ""}
                onChange={(event) => setValues((all) => ({ ...all, [field]: event.target.value }))}
              />
              {field !== "quantity" && <span className="text-2xs text-muted">mm</span>}
            </span>
          </label>
        ))}
        <label htmlFor={`inline-reason${idSuffix}`} className="flex flex-col gap-s1">
          <span className="text-sm font-semibold text-ink">{COPY.inline.reason}</span>
          <input id={`inline-reason${idSuffix}`} className="input" value={reason} onChange={(event) => setReason(event.target.value)} placeholder={COPY.inline.reasonPlaceholder} />
        </label>
        <label htmlFor={`inline-reviewer${idSuffix}`} className="flex flex-col gap-s1">
          <span className="text-sm font-semibold text-ink">{COPY.inline.reviewer}</span>
          <input id={`inline-reviewer${idSuffix}`} className="input" value={reviewer} onChange={(event) => setReviewer(event.target.value)} autoComplete="name" />
        </label>
      </div>
      {confirmsLayout && <p className="text-sm text-muted">{COPY.inline.confirmsCandidate(layoutShort(candidate))}</p>}
      {problem && <p role="alert" className="text-sm text-danger">{problem}</p>}
      {error && (error.code === "stale_result_revision"
        ? <ErrorNote error={{ ...error, message: COPY.review.stale }} action={<button type="button" className="btn btn-sm" onClick={() => { reloadRun(); setError(null); }}>{COPY.review.reload}</button>} />
        : <ErrorNote error={error.code === "observed_dimension_override" ? { ...error, message: COPY.review.override } : error} />)}
      <div className="flex flex-wrap items-center gap-s3">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? <><Spinner size={12} /> {COPY.inline.saving}</> : COPY.inline.submit(result.result_revision + 1)}
        </button>
      </div>
    </form>
  );
}
