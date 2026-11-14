import { useEffect, useState } from "react";
import { api } from "../api";
import type { AssemblyCandidate, DrawingExtraction, LibraryItem, Result, RunSnapshot } from "../api/types";
import { COPY } from "../copy";
import { Swatch, ValueCell } from "../components/DataClass";
import { More } from "../components/ui";
import {
  AXIS_LABELS, classOfDerived, fmt, RESULT_STATE_LABELS, ROLE_LABELS, translateEvidence, translatePremise, translateWarning, VIEW_LABELS,
  type Cell, type DataClass, type PartRow,
} from "../lib/domain";
import { useApi } from "../lib/useApi";
import { completable, EDIT_FIELDS, InlineComplete, layoutShort } from "../screens/Workspace";

const TONE: Record<DataClass, string> = { observed: "text-ink", calculated: "text-calc", hypothesis: "text-hip", confirmed: "text-conf", unknown: "text-muted" };
const ORDER: DataClass[] = ["observed", "calculated", "hypothesis", "confirmed", "unknown"];

export interface FichaProps {
  rows: PartRow[];
  selected: PartRow | null;
  current: Result | null;
  run: RunSnapshot | null;
  candidate: AssemblyCandidate | null;
  drawing: DrawingExtraction | null;
  library: LibraryItem | null;
  hoverId: string | null;
  completeTick: number;
  /** Título del escenario en los análisis de vistas montadas, que no traen candidatos de montaje. */
  scenarioTitle?: string | null;
  onHover(id: string | null): void;
  onSelect(id: string | null): void;
  onHoverContours(ids: string[] | null): void;
  onFocus(ids: string[]): void;
  onReview(): void;
}

/** Panel lateral: sin selección, el resumen del plano y la lista de piezas; con una pieza, su ficha. */
export function Ficha(props: FichaProps) {
  return props.selected ? <PieceCard {...props} row={props.selected} /> : <Summary {...props} />;
}

// ---- Resumen ----
function Summary({ rows, current, candidate, library, hoverId, scenarioTitle, onHover, onSelect, onReview }: FichaProps) {
  if (library) return <LibrarySummary item={library} />;
  const locked = Boolean(current?.selected_assembly_candidate_id);
  const warnings = [...new Set((current?.part_analysis?.warnings ?? []).map(translateWarning))];
  return (
    <div className="flex flex-col gap-s4 p-s4">
      <h2 className="sr-only">{COPY.portal.summary}</h2>
      {!candidate && scenarioTitle && (
        <dl className="flex flex-col gap-s1">
          <dt className="text-sm text-muted">{COPY.portal.assembly}</dt>
          <dd className="inline-flex items-center gap-s2 text-base font-semibold text-ink">
            <Swatch cls={current?.review ? "confirmed" : "hypothesis"} />
            {scenarioTitle}
          </dd>
        </dl>
      )}
      {candidate && (
        <dl className="flex flex-col gap-s3">
          <div className="flex flex-col gap-s1">
            <dt className="text-sm text-muted">{COPY.portal.assembly}</dt>
            <dd className="flex items-center justify-between gap-s2">
              <span className="inline-flex items-center gap-s2 text-base font-semibold text-ink">
                <Swatch cls={locked ? "confirmed" : "hypothesis"} />
                {layoutShort(candidate)}
                <span className="sr-only">, {COPY.classes[locked ? "confirmed" : "hypothesis"]}</span>
              </span>
              {!locked && <button className="text-sm font-semibold text-ink underline underline-offset-2" onClick={onReview}>{COPY.portal.changeAssembly}</button>}
            </dd>
          </div>
          <div className="flex flex-col gap-s1">
            <dt className="text-sm text-muted">{COPY.portal.exterior}</dt>
            <dd className="grid grid-cols-3 gap-s2">
              {(["width", "height", "depth"] as const).map((axis) => {
                const derived = candidate.derived_dimensions.find((item) => item.axis === axis);
                return (
                  <span key={axis} className="flex flex-col">
                    <span className="text-2xs text-muted">{AXIS_LABELS[axis]}</span>
                    <ValueCell cell={derived ? classOfDerived(derived.state, derived.value_mm) : { value: null, cls: "unknown" }} align="left" />
                  </span>
                );
              })}
            </dd>
          </div>
        </dl>
      )}
      <section aria-labelledby="ficha-pieces" className="flex flex-col">
        <h3 id="ficha-pieces" className="flex items-baseline justify-between pb-s1 text-sm text-muted">
          <span>{COPY.portal.pieces}</span>
          <span className="text-2xs">{COPY.cols.qty} · {COPY.cols.length} × {COPY.cols.width} × {COPY.cols.thickness}</span>
        </h3>
        {rows.length === 0 ? <p className="text-sm text-muted">{COPY.portal.noPieces}</p> : (
          <ul className="-mx-s2 flex flex-col" aria-label={COPY.portal.pieces}>
            {rows.map((row) => (
              <li key={row.id}>
                <button
                  className={`grid w-full grid-cols-[minmax(38px,auto)_minmax(0,1fr)_auto] items-center gap-x-s2 px-s2 py-s1 text-left ${hoverId === row.id ? "bg-sunken" : "hover:bg-sunken"} ${row.changed.size ? "shadow-[inset_3px_0_0_rgb(var(--cobalt))]" : ""}`}
                  onClick={() => onSelect(row.id)}
                  onPointerEnter={() => onHover(row.id)}
                  onPointerLeave={() => onHover(null)}
                  data-row={row.id}
                >
                  <span className="num font-mono text-[13px] font-medium text-ink">{row.key}</span>
                  <span className="flex min-w-0 items-baseline gap-s2">
                    <span className={`truncate text-sm ${TONE[row.role.cls]}`}>{row.role.value ?? COPY.classes.unknown}</span>
                    <Qty cell={row.quantity} />
                  </span>
                  <Dims row={row} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <CompactLegend />
      {warnings.length > 0 && (
        <More label={`${warnings.length === 1 ? "Aviso" : "Avisos"} del análisis`}>
          {warnings.map((warning) => <span key={warning}>{warning}</span>)}
        </More>
      )}
      {current && <p className="sr-only">r{current.result_revision} · {RESULT_STATE_LABELS[current.state]}</p>}
    </div>
  );
}

function Qty({ cell }: { cell: Cell }) {
  if (cell.value === null) return <span className="text-2xs text-muted">×?</span>;
  return <span className={`num font-mono text-2xs ${TONE[cell.cls]}`}>×{fmt(Number(cell.value))}</span>;
}

/** Largo × ancho × grosor en la mono, cada cifra con el color de su clase y «?» para lo desconocido. */
export function Dims({ row }: { row: PartRow }) {
  const one = (cell: Cell) => cell.value === null
    ? <span className="text-muted" title={COPY.classes.unknown}>?<span className="sr-only"> {COPY.classes.unknown}</span></span>
    : <span className={TONE[cell.cls]}>{fmt(Number(cell.value))}</span>;
  return (
    <span className="num whitespace-nowrap font-mono text-2xs">
      {one(row.length)}<span className="text-muted"> × </span>{one(row.width)}<span className="text-muted"> × </span>{one(row.thickness)}
    </span>
  );
}

/** Las cinco clases en una línea; la definición de cada una va en el título. */
function CompactLegend() {
  return (
    <ul className="flex flex-wrap gap-x-s3 gap-y-s1 border-t border-line pt-s3 text-2xs text-muted" aria-label={COPY.workspace.legend}>
      {ORDER.map((cls) => (
        <li key={cls} className="inline-flex items-center gap-s1" title={COPY.classDefs[cls]}><Swatch cls={cls} />{COPY.classes[cls]}</li>
      ))}
    </ul>
  );
}

// ---- Ficha de pieza ----
function PieceCard({ row, rows, current, run, candidate, drawing, completeTick, onSelect, onHoverContours, onFocus }: FichaProps & { row: PartRow }) {
  const [completing, setCompleting] = useState(false);
  useEffect(() => { setCompleting(false); }, [row.id]);
  useEffect(() => { if (completeTick) setCompleting(true); }, [completeTick]);
  const explanations = useApi(current && run ? () => api.getExplanations(run.id, current.result_revision) : null, [run?.id, current?.result_revision]);
  const explanation = explanations.data?.pieces.find((item) => item.proposal_id === row.id || item.piece_id === row.id) ?? null;
  const index = rows.findIndex((item) => item.id === row.id);
  const siblings = rows.filter((item) => item.observationId === row.observationId && item.id !== row.id);
  const canComplete = Boolean(candidate) && EDIT_FIELDS.some((field) => completable(row, field));
  const evidenceById = new Map((drawing?.evidence ?? []).map((item) => [item.id, item.description]));
  const premises = [...new Set((explanation?.premises ?? []).map(translatePremise).filter(Boolean))];
  const step = (delta: number) => onSelect(rows[(index + delta + rows.length) % rows.length].id);

  return (
    <div className="anim-in flex flex-col gap-s4 p-s4" data-testid="ficha">
      <div className="flex items-center justify-between gap-s2">
        <button className="inline-flex h-8 items-center gap-s1 text-sm text-muted hover:text-ink" onClick={() => onSelect(null)}>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
          {COPY.portal.back}
        </button>
        <span className="flex items-center">
          <IconButton label={COPY.portal.prev} onClick={() => step(-1)} d="M3 7.5 6 4.5l3 3" />
          <IconButton label={COPY.portal.next} onClick={() => step(1)} d="M3 4.5 6 7.5l3-3" />
          <IconButton label={COPY.portal.clear} onClick={() => onSelect(null)} d="M3 3l6 6M9 3 3 9" />
        </span>
      </div>
      <h2 className="flex items-baseline gap-s2">
        <span className="num font-mono text-lg font-medium text-ink">{row.key}</span>
        {row.role.value !== row.key && <span className={`text-lg font-semibold ${TONE[row.role.cls]}`}>{row.role.value ?? COPY.classes.unknown}</span>}
        {row.role.cls === "hypothesis" && <span className="text-2xs text-hip">{COPY.classes.hypothesis.toLowerCase()}</span>}
      </h2>

      <section aria-labelledby="ficha-measures">
        <h3 id="ficha-measures" className="sr-only">{COPY.portal.measures}</h3>
        <dl className="divide-y divide-line border-y border-line">
          {(["quantity", "length", "width", "thickness"] as const).map((field) => (
            <div key={field} className="flex items-center justify-between gap-s2 py-s2">
              <dt className="text-sm text-muted">{COPY.cols[field]}</dt>
              <dd className="flex items-baseline gap-s2">
                <ValueCell cell={row[field]} unit={field === "quantity" ? undefined : "mm"} />
                {row[field].value !== null && !row[field].conflict && <span className={`w-[68px] text-right text-2xs ${TONE[row[field].cls]}`}>{COPY.classes[row[field].cls].toLowerCase()}</span>}
                {row[field].value === null && <span className="w-[68px]" aria-hidden="true" />}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="ficha-contour" className="flex flex-col gap-s2">
        <div className="flex items-center justify-between">
          <h3 id="ficha-contour" className="text-sm text-muted">{COPY.portal.contour}</h3>
          <button className="text-sm font-semibold text-ink underline underline-offset-2" onClick={() => onFocus(row.contourIds)}>{COPY.portal.focus}</button>
        </div>
        <ul className="flex flex-wrap gap-s2">
          {row.observation.views.map((view) => (
            <li key={view.view_id}>
              <button
                className="inline-flex h-8 items-center gap-s2 border border-line-strong px-s2 text-sm text-ink hover:border-ink hover:bg-sunken"
                onPointerEnter={() => onHoverContours(view.contour_ids)}
                onPointerLeave={() => onHoverContours(null)}
                onFocus={() => onHoverContours(view.contour_ids)}
                onBlur={() => onHoverContours(null)}
                onClick={() => onFocus(view.contour_ids)}
              >
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect x="1.5" y="3" width="9" height="6" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
                {VIEW_LABELS[view.role]}
              </button>
            </li>
          ))}
        </ul>
        {siblings.length > 0 && (
          <p className="flex flex-wrap items-center gap-x-s2 text-sm text-muted">
            {COPY.portal.sharesContour}
            {siblings.map((item) => (
              <button key={item.id} className="font-semibold text-ink underline underline-offset-2" onClick={() => onSelect(item.id)}>
                {item.key} {String(item.role.value ?? "").toLowerCase()}
              </button>
            ))}
          </p>
        )}
      </section>

      {canComplete && candidate && current && run && (
        completing
          ? <InlineComplete key={`${row.id}-${current.result_revision}`} row={row} candidate={candidate} result={current} run={run} focus={{ field: EDIT_FIELDS.find((field) => completable(row, field))!, tick: completeTick + 1 }} idSuffix="" />
          : <button className="btn btn-sm self-start" onClick={() => setCompleting(true)}>{COPY.portal.complete} {EDIT_FIELDS.filter((field) => completable(row, field)).map((field) => COPY.cols[field].toLowerCase()).join(" y ")}</button>
      )}

      <More label={COPY.portal.details}>
        <span className="flex items-baseline justify-between gap-s2"><span>{COPY.cols.material}</span><ValueCell cell={row.material} /></span>
        {row.note && <span>{COPY.workspace.reviewNote}: <span className="text-ink">{row.note}</span></span>}
        <span>{COPY.portal.evidence}: {[...new Set(row.evidenceIds.map((id) => translateEvidence(evidenceById.get(id) ?? "")).filter(Boolean))].join(", ")}</span>
        {premises.map((premise) => <span key={premise}>{premise}</span>)}
        <span className="num font-mono text-2xs">{row.contourIds.join(", ")}</span>
        <span className="num font-mono text-2xs">{row.evidenceIds.join(", ")}</span>
        {row.use && <span className="num font-mono text-2xs">{ROLE_LABELS[row.use.role] ?? row.use.role} · {row.use.id}</span>}
      </More>
    </div>
  );
}

function IconButton({ label, onClick, d }: { label: string; onClick: () => void; d: string }) {
  return (
    <button className="inline-flex h-8 w-8 items-center justify-center text-ink hover:bg-sunken" onClick={onClick} aria-label={label} title={label}>
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d={d} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </button>
  );
}

// ---- Plano solo de biblioteca ----
function LibrarySummary({ item }: { item: LibraryItem }) {
  const d = item.descriptor;
  return (
    <div className="flex flex-col gap-s4 p-s4">
      <div className="flex flex-col gap-s1">
        <h2 className="text-md font-semibold text-ink">{item.label}</h2>
        <p className="text-sm text-muted">{COPY.portal.library} · <span className="num font-mono text-2xs">r{item.result_revision}</span></p>
      </div>
      <dl className="grid grid-cols-3 gap-s2">
        {(["width", "height", "depth"] as const).map((axis) => {
          const value = d.dimensions[`${axis}_mm` as const];
          return (
            <span key={axis} className="flex flex-col">
              <dt className="text-2xs text-muted">{AXIS_LABELS[axis]}</dt>
              <dd><ValueCell cell={value === null ? { value: null, cls: "unknown" } : { value, cls: "calculated" }} align="left" /></dd>
            </span>
          );
        })}
      </dl>
      <ul className="flex flex-col divide-y divide-line border-y border-line">
        {d.roles.map((role) => (
          <li key={role.role} className="flex items-baseline justify-between py-s1 text-sm text-ink">
            <span>{ROLE_LABELS[role.role] ?? role.role}</span>
            <span className="num font-mono text-2xs">{role.quantity === null ? "?" : `×${role.quantity}`}</span>
          </li>
        ))}
      </ul>
      <p className="text-sm text-muted">{COPY.libraryPlan.note}</p>
      <CompactLegend />
    </div>
  );
}
