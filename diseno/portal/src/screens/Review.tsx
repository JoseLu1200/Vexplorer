import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { AssemblyCandidate, AssemblyConstraint, ReviewDecision, Result } from "../api/types";
import { COPY } from "../copy";
import { ClassMarker, Legend, ValueCell } from "../components/DataClass";
import { ErrorNote, Spinner, Tag } from "../components/ui";
import {
  buildRows, fmt, fmtDate, LAYOUT_LABELS, pickCandidate, RESULT_STATE_LABELS, ROLE_LABELS, type Cell, type PartRow,
} from "../lib/domain";
import { toAppError, useStore, type AppError } from "../state";
import { NoRun } from "./Workspace";
import { useApi } from "../lib/useApi";
import { ConflictResolver } from "../components/ConflictBanner";

type Field = "quantity" | "length" | "width" | "thickness";
const FIELDS: Field[] = ["quantity", "length", "width", "thickness"];
const API_FIELD: Record<Field, "quantity" | "length_mm" | "width_mm" | "thickness_mm"> = { quantity: "quantity", length: "length_mm", width: "width_mm", thickness: "thickness_mm" };

export function ReviewScreen() {
  const { current, run, revisions, addRevision, reloadRun, go, focusField } = useStore();
  const [candidateId, setCandidateId] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, Partial<Record<Field, string>>>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [reviewer, setReviewer] = useState("");
  const [material, setMaterial] = useState("");
  const [finish, setFinish] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AppError | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [done, setDone] = useState<number | null>(null);
  const doneRef = useRef<HTMLDivElement>(null);
  const comparables = useApi(run ? () => api.getComparables(run.id, 3) : null, [run?.id]);
  // Valores aceptados por la estimación: material y acabado de los comparables que expone GET /comparables.
  const catalog = useMemo(() => ({
    materials: [...new Set((comparables.data ?? []).map((item) => item.material))],
    finishes: [...new Set((comparables.data ?? []).map((item) => item.finish))],
  }), [comparables.data]);

  // Valores de la revisión vigente: la nueva parte de ellos y solo cuenta como cambio lo que se modifica.
  const baseline = useMemo(() => {
    const pieces = current?.pieces ?? [];
    const only = (values: (string | null)[]) => { const set = new Set(values); return set.size === 1 ? [...set][0] ?? "" : ""; };
    return { reviewer: current?.review?.reviewer_name ?? "", material: only(pieces.map((piece) => piece.material)), finish: only(pieces.map((piece) => piece.finish)) };
  }, [current]);
  useEffect(() => {
    setEdits({}); setReasons({}); setError(null); setProblems([]);
    setReviewer((value) => value || baseline.reviewer);
    setMaterial(baseline.material);
    setFinish(baseline.finish);
  }, [current?.result_revision, baseline]);

  if (!current || !run) return <NoRun />;
  const candidate = pickCandidate(current, run, candidateId ?? current.selected_assembly_candidate_id);
  const rows = candidate ? buildRows(current, candidate) : [];
  const nextRevision = current.result_revision + 1;

  // Editable si el plano no lo observa: el backend rechaza sustituir medidas observadas, pero acepta reconfirmar lo que una persona confirmó.
  const editable = (row: PartRow, field: Field) =>
    field === "quantity" ? (row.use ? row.use.quantity_source === "unknown" : row.observation.quantity.state !== "observed") : row.observation.dimensions[field].state !== "observed";
  const touched = (row: PartRow) => Object.values(edits[row.id] ?? {}).some((value) => value !== undefined && value !== "");
  // Hay algo que guardar si se elige otro montaje, se corrige un campo o se indica material o acabado.
  const hasChanges = Boolean(candidate && candidate.id !== current.selected_assembly_candidate_id) || rows.some(touched) || material !== baseline.material || finish !== baseline.finish;
  const rowEditable = (row: PartRow) => FIELDS.some((field) => editable(row, field));
  const canSubmit = hasChanges && reviewer.trim() !== "" && !busy;
  const fieldNode = (row: PartRow, field: Field, suffix: string) =>
    editable(row, field) ? (
      <EditCell
        id={`edit-${row.id}-${field}${suffix}`}
        label={`${COPY.cols[field]} de ${row.key}`}
        value={edits[row.id]?.[field] ?? ""}
        unit={field === "quantity" ? "" : "mm"}
        cell={row[field]}
        highlight={focusField === field}
        onChange={(value) => setEdits((all) => ({ ...all, [row.id]: { ...all[row.id], [field]: value } }))}
      />
    ) : (
      <span className="inline-flex items-center gap-s2" title={COPY.review.locked}>
        <ValueCell cell={row[field]} />
        <LockIcon />
      </span>
    );
  // Solo las filas con algo que confirmar llevan campo de motivo.
  const reasonNode = (row: PartRow, suffix: string) => rowEditable(row) ? (
    <input
      id={`reason-${row.id}${suffix}`}
      aria-label={`${COPY.review.reason} para ${row.key}`}
      className={`input h-9 min-w-[200px] ${touched(row) && !(reasons[row.id] ?? "").trim() ? "border-danger" : ""}`}
      placeholder={touched(row) ? COPY.review.reasonPlaceholder : COPY.review.reason}
      value={reasons[row.id] ?? ""}
      onChange={(event) => setReasons((all) => ({ ...all, [row.id]: event.target.value }))}
    />
  ) : null;

  async function submit() {
    if (!candidate || !current || !run) return;
    const issues: string[] = [];
    if (!reviewer.trim()) issues.push(COPY.review.reviewerRequired);
    if (!note.trim()) issues.push(COPY.review.noteRequired);
    const decisions: ReviewDecision[] = [];
    for (const row of rows) {
      if (!touched(row)) continue;
      const reason = (reasons[row.id] ?? "").trim();
      if (!reason) { issues.push(`${row.key} ${String(row.role.value ?? "").toLowerCase()}: ${COPY.review.reasonRequired.toLowerCase()}`); continue; }
      const decision: ReviewDecision = { proposal_id: row.id, action: "confirm", role: row.use?.role ?? "unknown", notes: reason };
      for (const field of FIELDS) {
        const raw = edits[row.id]?.[field];
        if (raw === undefined || raw === "") continue;
        const value = Number(raw.replace(",", "."));
        if (!Number.isFinite(value) || value <= 0) { issues.push(`${row.key}: valor no válido en ${COPY.cols[field].toLowerCase()}`); continue; }
        if (field === "quantity") decision.quantity = Math.round(value); else decision[API_FIELD[field] as "length_mm"] = value;
      }
      decisions.push(decision);
    }
    setProblems(issues);
    if (issues.length) return;
    setBusy(true);
    setError(null);
    try {
      const request = {
        base_result_revision: current.result_revision, reviewer_name: reviewer.trim(), assembly_candidate_id: candidate.id,
        decisions, notes: note.trim(), material: material.trim() || null, finish: finish.trim() || null,
      };
      const result = await api.createReview(run.id, request);
      addRevision(result, request);
      setDone(result.result_revision);
      setReasons({});
      setNote("");
      setTimeout(() => doneRef.current?.focus(), 0);
    } catch (err) {
      setError(toAppError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid-cols-1 page grid gap-s5 py-s5 2xl:grid-cols-[minmax(0,1fr)_340px] lg:gap-s6 lg:py-s6">
      <h1 className="sr-only">{COPY.review.title}</h1>
      <div className="flex min-w-0 flex-col gap-s6">
        <section aria-labelledby="cand-title" className="flex flex-col gap-s3">
          <h2 id="cand-title" className="text-lg font-semibold tracking-[-0.01em]">{COPY.review.candidates}</h2>
          <CandidateList
            result={current}
            selectedId={candidate?.id ?? null}
            agentId={run.agent_selected_assembly_candidate_id}
            onSelect={(id) => { setCandidateId(id); setEdits({}); setReasons({}); }}
          />
        </section>

        <ConflictResolver result={current} run={run} reviewer={reviewer} />
        {candidate && (
          <section aria-labelledby="edit-title" className="flex flex-col gap-s3">
            <h2 id="edit-title" className="text-lg font-semibold tracking-[-0.01em]">{COPY.review.edit}</h2>
            <ul className="flex flex-col gap-s2 md:hidden">
              {rows.map((row) => (
                <li key={row.id} className="panel flex flex-col gap-s3 p-s3">
                  <p><span className="num font-mono text-[13px] font-medium text-ink">{row.key}</span> <span className="text-base text-muted">{String(row.role.value ?? "")}</span></p>
                  <dl className="grid grid-cols-2 gap-x-s4 gap-y-s2">
                    {FIELDS.map((field) => (
                      <div key={field} className={`flex items-center justify-between gap-s2 ${editable(row, field) ? "col-span-2" : ""}`}>
                        <dt className="text-sm text-muted">{COPY.cols[field]}</dt>
                        <dd>{fieldNode(row, field, "-m")}</dd>
                      </div>
                    ))}
                  </dl>
                  {touched(row) && reasonNode(row, "-m")}
                </li>
              ))}
            </ul>
            <div className="panel hidden overflow-x-auto md:block">
              <table className="w-full min-w-[760px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-line-strong text-sm text-muted">
                    <th scope="col" className="h-10 pl-s4 pr-s2 font-semibold">{COPY.cols.part}</th>
                    {FIELDS.map((field) => <th key={field} scope="col" className="px-s2 text-right font-semibold">{COPY.cols[field]}</th>)}
                    <th scope="col" className="pl-s3 pr-s4 font-semibold">{COPY.review.reason}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="h-14 border-b border-line last:border-b-0">
                      <td className="py-s2 pl-s4 pr-s2">
                        <span className="num font-mono text-[13px] font-medium text-ink">{row.key}</span>{" "}
                        <span className="text-base text-muted">{String(row.role.value ?? "")}</span>
                      </td>
                      {FIELDS.map((field) => (
                        <td key={field} className="px-s2 py-s2 text-right">{fieldNode(row, field, "")}</td>
                      ))}
                      <td className="py-s2 pl-s3 pr-s4">{reasonNode(row, "")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Legend />
            <div className="grid-cols-1 mt-s3 grid gap-s4 sm:grid-cols-3">
              <Field id="reviewer" label={COPY.review.reviewer}><input id="reviewer" className="input" value={reviewer} onChange={(event) => setReviewer(event.target.value)} autoComplete="name" /></Field>
              <Field id="material" label={COPY.review.material}>
                <select id="material" className={`input ${focusField === "material" ? "ring-2 ring-danger" : ""}`} value={material} onChange={(event) => setMaterial(event.target.value)}>
                  <option value="">{COPY.review.none}</option>
                  {catalog.materials.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </Field>
              <Field id="finish" label={COPY.review.finish}>
                <select id="finish" className={`input ${focusField === "finish" ? "ring-2 ring-danger" : ""}`} value={finish} onChange={(event) => setFinish(event.target.value)}>
                  <option value="">{COPY.review.none}</option>
                  {catalog.finishes.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </Field>
            </div>
            <Field id="note" label={COPY.review.generalNote}>
              <textarea id="note" rows={2} className="input" value={note} onChange={(event) => setNote(event.target.value)} placeholder={COPY.review.notePlaceholder} />
            </Field>

            {problems.length > 0 && (
              <ul role="alert" className="flex flex-col gap-s1 border border-danger/50 bg-danger-soft px-s4 py-s3 text-base text-ink">
                {problems.map((problem) => <li key={problem}>{problem}</li>)}
              </ul>
            )}
            {error && (
              error.code === "stale_result_revision"
                ? <ErrorNote error={{ ...error, message: COPY.review.stale }} action={<button className="btn btn-sm" onClick={() => { reloadRun(); setError(null); }}>{COPY.review.reload}</button>} />
                : <ErrorNote error={error.code === "observed_dimension_override" ? { ...error, message: COPY.review.override } : error} />
            )}
            {done !== null && done === current.result_revision && (
              <div ref={doneRef} tabIndex={-1} role="status" className="flex flex-wrap items-center gap-s3 bg-ink px-s4 py-s3 text-base text-surface outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-bg">
                <svg width="18" height="18" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1.3" /><path d="M4.2 7.2 6.2 9.1 9.8 5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
                <span className="flex flex-col">
                  <span className="font-semibold">Revisión <span className="num font-mono text-[13px]">{done}</span> guardada</span>
                  <span className="text-sm text-surface/80">{current.review?.reviewer_name} · {fmtDate(current.created_at)} · se conserva la revisión {done - 1}</span>
                </span>
                <button className="ml-auto inline-flex h-9 items-center border border-surface/50 px-s3 text-sm font-semibold text-surface hover:bg-surface/10" onClick={() => go("plano")}>Ver en el plano</button>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-s3">
              <button className="btn btn-primary" onClick={submit} disabled={!canSubmit} aria-describedby="submit-hint">
                {busy ? <><Spinner size={12} /> {COPY.review.submitting}</> : COPY.review.submit(nextRevision)}
              </button>
              <span id="submit-hint" className="text-sm text-muted">
                {!hasChanges ? COPY.review.noChanges : !reviewer.trim() ? COPY.review.reviewerRequired : ""}
              </span>
            </div>
          </section>
        )}
      </div>

      <aside aria-labelledby="hist-title" className="flex min-w-0 flex-col gap-s3">
        <h2 id="hist-title" className="text-lg font-semibold tracking-[-0.01em]">{COPY.review.history}</h2>
        <History revisions={revisions} />
      </aside>
    </div>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-s2">
      <label htmlFor={id} className="text-sm font-semibold text-ink">{label}</label>
      {children}
    </div>
  );
}

function LockIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" className="shrink-0 text-muted" role="img" aria-label={COPY.review.locked}>
      <rect x="2.2" y="5.2" width="7.6" height="5.6" rx="1" fill="none" stroke="currentColor" strokeWidth="1.1" />
      <path d="M4 5.2V3.8a2 2 0 0 1 4 0v1.4" fill="none" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  );
}

function EditCell({ id, label, value, unit, cell, highlight, onChange }: { id: string; label: string; value: string; unit: string; cell: Cell; highlight: boolean; onChange: (value: string) => void }) {
  const filled = value.trim() !== "";
  const confirmedBefore = !filled && cell.cls === "confirmed" && cell.value !== null;
  return (
    <span className={`inline-flex h-9 items-center gap-s1 border px-s2 ${filled || confirmedBefore ? `border-conf bg-surface ${highlight ? "ring-2 ring-danger ring-offset-1 ring-offset-surface" : ""}` : `unknown border-dashed border-line-strong ${highlight ? "ring-2 ring-danger ring-offset-1 ring-offset-surface" : ""}`}`}>
      {(filled || confirmedBefore) && <ClassMarker cls="confirmed" />}
      <input
        id={id}
        aria-label={label}
        inputMode="decimal"
        className="num w-[88px] bg-transparent text-right font-mono text-[13px] text-ink outline-none placeholder:font-sans placeholder:text-sm placeholder:text-muted"
        placeholder={confirmedBefore ? fmt(Number(cell.value)) : cell.note ? "Conflicto" : COPY.classes.unknown}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {unit && <span className="text-2xs text-muted">{unit}</span>}
    </span>
  );
}

function constraintCell(constraint: AssemblyConstraint): Cell {
  if (constraint.status === "pass") return { value: constraint.result_mm, cls: "calculated" };
  if (constraint.status === "conflict") return { value: null, cls: "unknown", note: "Conflicto" };
  return { value: null, cls: "unknown" };
}

function CandidateList({ result, selectedId, agentId, onSelect }: { result: Result; selectedId: string | null; agentId: string | null; onSelect: (id: string) => void }) {
  const keyOf = useMemo(() => {
    const map = new Map((result.part_analysis?.observations ?? []).map((o, i) => [o.id, o.part_key ?? `Sin etiqueta ${i + 1}`]));
    return (id: string) => map.get(id) ?? id;
  }, [result]);
  const [expanded, setExpanded] = useState(false);
  if (!result.assembly_candidates.length) {
    return <p className="border border-line bg-surface px-s4 py-s3 text-base text-muted">{COPY.workspace.noCandidates}</p>;
  }
  const all = result.assembly_candidates;
  const visible = expanded ? all : all.filter((item, index) => index < 3 || item.id === selectedId);
  const hidden = all.length - visible.length;
  return (
    <div className="flex flex-col gap-s2">
      <div role="radiogroup" aria-label={COPY.review.candidates} className="panel divide-y divide-line overflow-hidden">
        {visible.map((candidate) => {
          const index = all.indexOf(candidate);
          return <CandidateRow key={candidate.id} candidate={candidate} index={index} keyOf={keyOf} checked={candidate.id === selectedId} agent={candidate.id === agentId} current={candidate.id === result.selected_assembly_candidate_id} onSelect={() => onSelect(candidate.id)} />;
        })}
      </div>
      {(hidden > 0 || expanded) && (
        <button className="btn btn-ghost btn-sm self-start px-s2 text-muted" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
          {expanded ? COPY.review.showLess : COPY.review.showMore(hidden)}
        </button>
      )}
    </div>
  );
}

function CandidateRow({ candidate, index, keyOf, checked, agent, current, onSelect }: { candidate: AssemblyCandidate; index: number; keyOf: (id: string) => string; checked: boolean; agent: boolean; current: boolean; onSelect: () => void }) {
  const assignment = new Map<string, string[]>();
  candidate.uses.forEach((use) => assignment.set(keyOf(use.part_observation_id), [...(assignment.get(keyOf(use.part_observation_id)) ?? []), (ROLE_LABELS[use.role] ?? use.role).toLowerCase()]));
  return (
    <label className={`grid cursor-pointer grid-cols-[20px_minmax(0,1fr)] gap-x-s3 gap-y-s2 px-s4 py-s3 ${checked ? "is-selected" : "hover:bg-sunken"}`}>
      <input type="radio" name="candidate" id={`cand-${index}`} checked={checked} onChange={onSelect} className="mt-1 accent-[rgb(var(--ink))]" />
      <span className="flex min-w-0 flex-col gap-s2">
        <span className="flex flex-wrap items-center gap-x-s3 gap-y-s1">
          <span className="text-base font-semibold text-ink">{LAYOUT_LABELS[candidate.layout]}</span>
          <span className="text-base text-muted">{[...assignment].map(([key, roles]) => `${key} ${roles.join(" y ")}`).join(" · ")}</span>
          {current && !candidate.constraints.some((item) => item.status === "conflict") && <Tag tone="strong">{COPY.review.current}</Tag>}
          {current && candidate.constraints.some((item) => item.status === "conflict") && <Tag tone="neutral">Elegido, con conflicto</Tag>}
          {agent && <Tag tone="hip">{COPY.review.agentPick}</Tag>}
        </span>
        <span className="flex flex-wrap gap-x-s4 gap-y-s1">
          {candidate.constraints.map((constraint) => (
            <span key={constraint.id} className="inline-flex items-center gap-s2 text-sm text-muted">
              <span>{COPY.constraints[constraint.dimension] ?? constraint.dimension}</span>
              <ValueCell cell={constraintCell(constraint)} unit="mm" align="left" />
            </span>
          ))}
        </span>
      </span>
    </label>
  );
}

function History({ revisions }: { revisions: Result[] }) {
  const list = [...revisions].reverse();
  return (
    <ol className="panel divide-y divide-line">
      {list.map((result) => {
        const previous = revisions.find((item) => item.result_revision === result.result_revision - 1) ?? null;
        const candidate = result.assembly_candidates.find((item) => item.id === result.selected_assembly_candidate_id) ?? null;
        const changes = previous && candidate ? buildRows(result, candidate, previous).flatMap((row) => [...row.changed].filter((field) => field !== "role" && field !== "material").map((field) => ({ row, field: field as Field }))) : [];
        return (
          <li key={result.result_revision} className="flex flex-col gap-s2 px-s4 py-s3">
            <div className="flex items-center justify-between gap-s2">
              <span className="flex items-center gap-s2">
                <span className="num font-mono text-[13px] font-medium text-ink">r{result.result_revision}</span>
                <Tag tone={result.state === "completed" ? "strong" : "neutral"}>{RESULT_STATE_LABELS[result.state]}</Tag>
              </span>
              <span className="num font-mono text-2xs text-muted">{fmtDate(result.created_at)}</span>
            </div>
            {result.review ? (
              <>
                <p className="text-base text-ink">{result.review.reason}</p>
                <p className="text-sm text-muted">{result.review.reviewer_name}</p>
                {changes.length > 0 && (
                  <ul className="flex flex-col gap-s1 border-l-[3px] border-cobalt pl-s3">
                    {changes.map(({ row, field }) => (
                      <li key={`${row.id}-${field}`} className="text-sm text-muted">
                        <span className="num font-mono text-2xs text-ink">{row.key}</span> {String(row.role.value ?? "").toLowerCase()} · {COPY.cols[field].toLowerCase()}{" "}
                        <span className="num font-mono text-2xs text-conf">{row[field].value === null ? "desconocido" : `${fmt(Number(row[field].value))}${field === "quantity" ? "" : " mm"}`}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="text-sm text-muted">{COPY.review.noReviewYet}</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
