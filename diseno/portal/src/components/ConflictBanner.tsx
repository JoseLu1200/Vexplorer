import { useState } from "react";
import { api } from "../api";
import type { AssemblyCandidate, Result, RunSnapshot } from "../api/types";
import { COPY } from "../copy";
import { buildRows, fmt, pickCandidate, type PartRow } from "../lib/domain";
import { toAppError, useStore, type AppError } from "../state";
import { ErrorNote, Spinner } from "./ui";

type Field = "length" | "width" | "thickness";
const FIELDS: Record<string, Field | undefined> = { length: "length", width: "width", thickness: "thickness" };

interface Conflict {
  id: string;
  field: Field;
  label: string;
  observed: { value: number; keys: string[] }[];
  confirmed: { value: number; rows: PartRow[] }[];
}

/** Conflictos del candidato elegido, con los valores tal como llegan del backend. */
export function conflictsOf(result: Result, run: RunSnapshot | null): { candidate: AssemblyCandidate | null; items: Conflict[] } {
  const candidate = pickCandidate(result, run);
  if (!candidate || result.selected_assembly_candidate_id !== candidate.id) return { candidate, items: [] };
  const rows = buildRows(result, candidate);
  const items = candidate.constraints.flatMap((constraint) => {
    const field = FIELDS[constraint.dimension];
    if (constraint.status !== "conflict" || !field) return [];
    const observed = new Map<number, string[]>();
    const confirmed = new Map<number, PartRow[]>();
    rows.forEach((row) => {
      const cell = row[field];
      if (typeof cell.value !== "number") return;
      if (cell.cls === "observed") observed.set(cell.value, [...new Set([...(observed.get(cell.value) ?? []), row.key])]);
      if (cell.cls === "confirmed") confirmed.set(cell.value, [...(confirmed.get(cell.value) ?? []), row]);
    });
    return [{
      id: constraint.id, field, label: (COPY.constraints[constraint.dimension] ?? constraint.dimension).toLowerCase(),
      observed: [...observed].map(([value, keys]) => ({ value, keys })),
      confirmed: [...confirmed].map(([value, list]) => ({ value, rows: list })),
    }];
  });
  return { candidate, items };
}

/** Una línea en Plano y Compras que lleva al único aviso de Revisión. */
export function ConflictLine({ result, run }: { result: Result; run: RunSnapshot | null }) {
  const { reviewField } = useStore();
  const { items } = conflictsOf(result, run);
  if (!items.length) return null;
  return (
    <p role="alert" className="flex flex-wrap items-center gap-x-s3 gap-y-s1 border border-danger/50 bg-danger-soft px-s3 py-s2 text-base text-ink">
      <span className="font-semibold text-danger">Conflicto de {items[0].label} pendiente.</span>
      <button className="font-semibold underline underline-offset-2" onClick={() => reviewField(items[0].field)}>Resolver en Revisión</button>
    </p>
  );
}

/**
 * Aviso único en Revisión con las dos salidas posibles.
 * El backend no deja sustituir una medida observada, así que mantener el valor confirmado solo es posible corrigiendo el DXF.
 */
export function ConflictResolver({ result, run, reviewer }: { result: Result; run: RunSnapshot; reviewer: string }) {
  const { addRevision } = useStore();
  const { candidate, items } = conflictsOf(result, run);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AppError | null>(null);
  if (!candidate || !items.length) return null;
  const conflict = items[0];
  const observed = conflict.observed.length === 1 ? conflict.observed[0] : null;
  const confirmed = conflict.confirmed[0] ?? null;
  const field = `${conflict.field}_mm` as const;

  async function useObserved() {
    if (!observed || !confirmed || !candidate) return;
    setBusy(true);
    setError(null);
    const note = `Conflicto de ${conflict.label} resuelto: se usa ${fmt(observed.value)} mm, observado en el plano`;
    try {
      const request = {
        base_result_revision: result.result_revision,
        reviewer_name: reviewer.trim(),
        assembly_candidate_id: candidate.id,
        notes: note,
        decisions: confirmed.rows.filter((row) => row.use).map((row) => ({ proposal_id: row.id, action: "confirm" as const, role: row.use!.role, [field]: observed.value, notes: note })),
      };
      const next = await api.createReview(run.id, request);
      addRevision(next, request);
    } catch (err) {
      setError(toAppError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="conflict-title" className="flex flex-col gap-s3 border border-danger/50 bg-danger-soft p-s4">
      <h2 id="conflict-title" className="text-base font-semibold text-ink">
        Conflicto de {conflict.label}:{" "}
        <span className="font-[400]">
          {conflict.observed.map((item) => `${item.keys.join(", ")} a ${fmt(item.value)} mm observado`).join(", ")}
          {confirmed ? ` frente a ${[...new Set(confirmed.rows.map((row) => row.key))].join(", ")} a ${fmt(confirmed.value)} mm confirmado` : ""}
        </span>
      </h2>
      <div className="flex flex-col gap-s3">
        {observed && (
          <div className="flex flex-wrap items-center gap-s3">
            <button className="btn" disabled={busy || !reviewer.trim()} onClick={useObserved}>
              {busy ? <><Spinner size={12} /> Guardando</> : `Usar ${fmt(observed.value)} mm (observado en el plano)`}
            </button>
            {!reviewer.trim() && (
              <button className="text-sm text-ink underline underline-offset-2" onClick={() => document.getElementById("reviewer")?.focus()}>
                Indica el revisor en el formulario para usar esta opción
              </button>
            )}
          </div>
        )}
        {confirmed && observed && (
          <div className="flex flex-col gap-s1 border-l-2 border-line-strong pl-s3">
            <p id="keep-reason" className="text-sm text-muted">
              {observed.keys.join(", ")} tiene {fmt(observed.value)} mm medidos en el plano y no se puede sustituir. Para mantener {fmt(confirmed.value)} mm, corrige el DXF y vuelve a analizarlo.
            </p>
            <span className="text-base text-muted" aria-disabled="true" aria-describedby="keep-reason">
              Mantener {fmt(confirmed.value)} mm (confirmado): no disponible
            </span>
          </div>
        )}
      </div>
      {error && <ErrorNote error={error} />}
    </section>
  );
}
