import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { CostConcept, Estimate } from "../api/types";
import { COPY } from "../copy";
import { Legend, ValueCell } from "../components/DataClass";
import { ErrorNote, LoadingBar, More, Spinner, Tag } from "../components/ui";
import { buildRows, classOfFieldState, fmt, fmtEur, fmtFactor, localizeAmounts, pickCandidate } from "../lib/domain";
import { useApi } from "../lib/useApi";
import { toAppError, useStore, type AppError } from "../state";
import { NoRun } from "./Workspace";
import { ConflictLine } from "../components/ConflictBanner";

/**
 * Fórmula del backend (backend/app/estimacion/service.py) con sus términos reales:
 * fijo = coste fijo del comparable; tablero = coste de tablero del comparable × (área de las piezas ÷ área del comparable).
 * La interfaz solo muestra los términos que llegan; no recalcula nada.
 */
function Formula({ concept, referenceAreaMm2 }: { concept: CostConcept; referenceAreaMm2: number | null }) {
  if (concept.cost_type === "fixed") {
    return <span className="text-sm text-muted">Coste fijo del comparable</span>;
  }
  const area = referenceAreaMm2 === null ? null : `${fmt(referenceAreaMm2 / 1_000_000)} m²`;
  return (
    <span className="flex flex-col gap-s1 text-sm text-muted">
      <span className="num font-mono text-2xs text-ink">{fmtEur(concept.base_amount)} × {fmtFactor(concept.factor)} = {fmtEur(concept.amount)}</span>
      <More label="Cálculo">
        <span><span className="num font-mono text-2xs text-ink">{fmtEur(concept.base_amount)}</span>: coste de tablero del comparable{area ? <>, para <span className="num font-mono text-2xs text-ink">{area}</span></> : null}.</span>
        <span><span className="num font-mono text-2xs text-ink">{fmtFactor(concept.factor)}</span>: área total de las piezas confirmadas ÷ {area ? <span className="num font-mono text-2xs text-ink">{area}</span> : "área del comparable"}.</span>
        <span>{localizeAmounts(concept.explanation.split(";")[0])}.</span>
      </More>
    </span>
  );
}

/** Total en cifra grande; su condición de provisional va en la etiqueta de la fila y en el aviso sintético. */
function Total({ value }: { value: number }) {
  return <span className="num font-mono text-md font-medium text-ink">{fmtEur(value)}</span>;
}

// Premisas que ya dicen el aviso sintético o la fila de horas: no se repiten.
const REPEATED = [/sintétic/i, /horas desconocidas/i];

export function PurchaseScreen() {
  const { current, run, go, reviewField } = useStore();
  const detail = useApi(run && current ? () => api.getRun(run.id) : null, [run?.id, current?.result_revision]);
  const comparables = useApi(run && current ? () => api.getComparables(run.id, 3) : null, [run?.id, current?.result_revision]);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AppError | null>(null);

  useEffect(() => { setEstimate(detail.data?.estimate ?? null); }, [detail.data]);
  useEffect(() => { setError(null); }, [current?.result_revision]);

  const candidate = current ? pickCandidate(current, run) : null;
  const rows = useMemo(() => (current ? buildRows(current, candidate) : []), [current, candidate]);
  if (!current || !run) return <NoRun />;

  async function calculate() {
    if (!current || !run) return;
    setBusy(true);
    setError(null);
    try { setEstimate(await api.createEstimate(run.id, { result_revision: current.result_revision })); }
    catch (err) { setError(toAppError(err)); }
    finally { setBusy(false); }
  }

  const usedIds = new Set(estimate?.comparable_ids ?? []);
  const referenceArea = (id: string) => comparables.data?.find((item) => item.id === id)?.reference_area_mm2 ?? null;
  const hasConflict = (pickCandidate(current, run)?.constraints ?? []).some((item) => item.status === "conflict") && current.selected_assembly_candidate_id !== null;
  // Las piezas sin material o acabado confirmado, tal como llegan en la revisión vigente.
  const pieceOf = (rowId: string) => current.pieces.find((piece) => piece.proposal_id === rowId);
  const finishCell = (rowId: string) => { const piece = pieceOf(rowId); return classOfFieldState(piece?.field_states.finish, piece?.finish ?? null); };
  const missing = {
    material: [...new Set(rows.filter((row) => pieceOf(row.id)?.material == null).map((row) => row.key))],
    finish: [...new Set(rows.filter((row) => pieceOf(row.id)?.finish == null).map((row) => row.key))],
  };
  const missingMaterial = [...missing.material, ...missing.finish];

  return (
    <div className="page flex flex-col gap-s5 py-s5 lg:py-s6">
      <h1 className="sr-only">{COPY.purchase.title}</h1>
      <header className="flex flex-wrap items-center justify-between gap-s3">
        <p role="note" className="flex flex-wrap items-center gap-s3 text-base font-semibold text-ink">
          <span className="inline-flex h-6 items-center bg-ink px-s2 text-xs font-bold text-surface">Sintético</span>
          {COPY.purchase.synthetic}
        </p>
        {estimate && <button className="btn btn-sm" onClick={() => go("presupuesto")}>{COPY.portal.steps.presupuesto}</button>}
      </header>

      <div className="grid-cols-1 grid gap-s5 2xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex min-w-0 flex-col gap-s5">
          <section aria-labelledby="est-title" className="panel overflow-hidden">
            <div className="flex h-12 items-center border-b border-line px-s4">
              <h2 id="est-title" className="text-md font-semibold">{COPY.purchase.estimate}</h2>
            </div>
            {detail.loading && <LoadingBar />}
            {!estimate ? (
              <div className="flex flex-col items-start gap-s3 px-s4 py-s5">
                {hasConflict ? (
                  <div className="flex w-full flex-col gap-s2">
                    <p className="text-base font-semibold text-ink">{COPY.purchase.blocked}</p>
                    <ConflictLine result={current} run={run} />
                  </div>
                ) : current.state === "needs_review" ? (
                  <>
                    <p className="max-w-[56ch] text-base text-muted">{COPY.purchase.needsReview}</p>
                    <button className="btn" onClick={() => go("revision")}>{COPY.purchase.goReview}</button>
                  </>
                ) : (
                  <>
                    <button className="btn btn-primary" onClick={calculate} disabled={busy || missingMaterial.length > 0} aria-describedby={missingMaterial.length ? "material-missing" : undefined}>
                      {busy ? <><Spinner size={12} /> {COPY.purchase.calculating}</> : COPY.purchase.calculate}
                    </button>
                    {missingMaterial.length > 0 && (
                      <div id="material-missing" className="flex flex-col gap-s1 text-base">
                        <span className="text-muted">{COPY.purchase.missing}</span>
                        <ul className="flex flex-col gap-s1">
                          {(["material", "finish"] as const).filter((field) => missing[field].length > 0).map((field) => (
                            <li key={field} className="flex flex-wrap items-baseline gap-x-s2">
                              <button className="font-semibold text-ink underline underline-offset-2" onClick={() => reviewField(field)}>
                                {field === "material" ? "Material" : "Acabado"}
                              </button>
                              <span className="text-muted">en {missing[field].join(", ")}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                )}
                {error && (
                  <ErrorNote
                    error={error.code === "result_needs_review" ? { ...error, message: COPY.purchase.needsReview }
                      : error.code === "missing_compatible_material_or_finish" ? { ...error, message: COPY.purchase.missingMaterial }
                      : error}
                    action={error.code === "missing_compatible_material_or_finish" ? <button className="btn btn-sm" onClick={() => go("revision")}>{COPY.purchase.goReview}</button> : undefined}
                  />
                )}
              </div>
            ) : (
              <>
                <ul className="divide-y divide-line md:hidden">
                  {estimate.concepts.map((concept) => (
                    <li key={concept.id} className="flex flex-col gap-s1 px-s4 py-s3">
                      <div className="flex items-baseline justify-between gap-s3">
                        <span className="text-base text-ink">{concept.label}</span>
                        <ValueCell cell={{ value: fmtEur(concept.amount), cls: "calculated" }} />
                      </div>
                      <Formula concept={concept} referenceAreaMm2={referenceArea(concept.comparable_id)} />
                    </li>
                  ))}
                  <li className="flex items-baseline justify-between gap-s3 px-s4 py-s3">
                    <span className="text-base font-semibold text-ink">{COPY.purchase.total}</span>
                    <Total value={estimate.total} />
                  </li>
                  <li className="flex items-center justify-between gap-s3 px-s4 py-s3">
                    <span className="text-base text-ink">{COPY.purchase.hours}</span>
                    <ValueCell cell={estimate.hours == null ? { value: null, cls: "unknown" } : { value: estimate.hours, cls: "calculated" }} unit="h" />
                  </li>
                </ul>
                <div className="hidden overflow-x-auto md:block">
                  <table className="w-full min-w-[560px] border-collapse text-left">
                    <thead>
                      <tr className="border-b border-line-strong text-sm text-muted">
                        <th scope="col" className="h-10 pl-s4 pr-s2 font-semibold">{COPY.purchase.concept}</th>
                        <th scope="col" className="px-s2 font-semibold">Cálculo</th>
                        <th scope="col" className="pl-s2 pr-s4 text-right font-semibold">{COPY.purchase.amount}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {estimate.concepts.map((concept) => (
                        <tr key={concept.id} className="border-b border-line align-top">
                          <td className="py-s3 pl-s4 pr-s2 text-base text-ink">{concept.label}</td>
                          <td className="px-s2 py-s3"><Formula concept={concept} referenceAreaMm2={referenceArea(concept.comparable_id)} /></td>
                          <td className="py-s3 pl-s2 pr-s4 text-right"><ValueCell cell={{ value: fmtEur(concept.amount), cls: "calculated" }} /></td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-b border-line">
                        <th scope="row" colSpan={2} className="py-s3 pl-s4 pr-s2 text-base font-bold text-ink">{COPY.purchase.total}</th>
                        <td className="py-s3 pl-s2 pr-s4 text-right"><Total value={estimate.total} /></td>
                      </tr>
                      <tr>
                        <th scope="row" colSpan={2} className="py-s3 pl-s4 pr-s2 text-base font-semibold text-ink">{COPY.purchase.hours}</th>
                        <td className="py-s3 pl-s2 pr-s4 text-right"><ValueCell cell={estimate.hours == null ? { value: null, cls: "unknown" } : { value: estimate.hours, cls: "calculated" }} unit="h" /></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
                {estimate.assumptions.some((item) => !REPEATED.some((re) => re.test(item))) && (
                  <ul className="flex flex-col gap-s1 border-t border-line px-s4 py-s3">
                    {estimate.assumptions.filter((item) => !REPEATED.some((re) => re.test(item))).map((item) => <li key={item} className="text-sm text-muted">{item}</li>)}
                  </ul>
                )}
              </>
            )}
          </section>

          <section aria-labelledby="bom-title" className="panel overflow-hidden">
            <div className="flex h-12 items-center justify-between gap-s3 border-b border-line px-s4">
              <h2 id="bom-title" className="text-md font-semibold">{COPY.purchase.pieces}</h2>
              <span className="hidden text-sm text-muted sm:inline">{COPY.purchase.area}</span>
            </div>
            <ul className="divide-y divide-line md:hidden">
              {rows.map((row) => (
                <li key={row.id} className="flex flex-col gap-s2 px-s4 py-s3">
                  <p><span className="num font-mono text-[13px] font-medium text-ink">{row.key}</span> <span className="text-base text-muted">{String(row.role.value ?? "")}</span></p>
                  <dl className="grid grid-cols-2 gap-x-s4 gap-y-s2">
                    {(["quantity", "length", "width"] as const).map((field) => (
                      <div key={field} className="flex items-center justify-between gap-s2"><dt className="text-sm text-muted">{COPY.cols[field]}</dt><dd><ValueCell cell={row[field]} /></dd></div>
                    ))}
                    <div className="col-span-2 flex items-center justify-between gap-s2"><dt className="text-sm text-muted">{COPY.cols.material}</dt><dd><ValueCell cell={row.material} /></dd></div>
                    <div className="col-span-2 flex items-center justify-between gap-s2"><dt className="text-sm text-muted">{COPY.cols.finish}</dt><dd><ValueCell cell={finishCell(row.id)} /></dd></div>
                  </dl>
                </li>
              ))}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[640px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-line-strong text-sm text-muted">
                    <th scope="col" className="h-10 pl-s4 pr-s2 font-semibold">{COPY.cols.part}</th>
                    <th scope="col" className="px-s2 text-right font-semibold">{COPY.cols.qty}</th>
                    <th scope="col" className="px-s2 text-right font-semibold">{COPY.cols.length}</th>
                    <th scope="col" className="px-s2 text-right font-semibold">{COPY.cols.width}</th>
                    <th scope="col" className="px-s2 font-semibold">{COPY.cols.material}</th>
                    <th scope="col" className="pl-s2 pr-s4 font-semibold">{COPY.cols.finish}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="h-12 border-b border-line last:border-b-0">
                      <td className="whitespace-nowrap pl-s4 pr-s2"><span className="num font-mono text-[13px] font-medium">{row.key}</span> <span className="text-base text-muted">{String(row.role.value ?? "")}</span></td>
                      <td className="px-s2 text-right"><ValueCell cell={row.quantity} /></td>
                      <td className="px-s2 text-right"><ValueCell cell={row.length} /></td>
                      <td className="px-s2 text-right"><ValueCell cell={row.width} /></td>
                      <td className="px-s2"><ValueCell cell={row.material} align="left" /></td>
                      <td className="pl-s2 pr-s4"><ValueCell cell={finishCell(row.id)} align="left" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="border-t border-line px-s4 pt-s3 text-sm text-muted sm:hidden">{COPY.purchase.area}</p>
            <div className="border-t border-line px-s4 py-s3"><Legend /></div>
          </section>
        </div>

        <aside aria-labelledby="comp-title" className="flex min-w-0 flex-col gap-s3">
          <h2 id="comp-title" className="flex h-12 items-center text-md font-semibold">{COPY.purchase.comparables}</h2>
          {comparables.loading && <LoadingBar />}
          {comparables.error && <ErrorNote error={comparables.error} onRetry={comparables.retry} />}
          <ol className="panel divide-y divide-line">
            {(comparables.data ?? []).map((item) => (
              <li key={item.id} className={`flex flex-col gap-s2 px-s4 py-s3 ${usedIds.has(item.id) ? "shadow-[inset_3px_0_0_rgb(var(--ink))]" : ""}`}>
                <div className="flex items-start justify-between gap-s3">
                  <p className="min-w-0 text-base font-semibold text-ink">{item.name}</p>
                  <span className="shrink-0 text-sm text-muted">{COPY.library.score} <span className="num font-mono text-[13px] text-ink">{fmt(item.score)}</span></span>
                </div>
                {usedIds.has(item.id) && <span className="self-start"><Tag tone="strong">{COPY.purchase.base}</Tag></span>}
                <p className="num font-mono text-2xs text-ink">{fmt(item.width_mm)} × {fmt(item.height_mm)} × {fmt(item.depth_mm)} mm</p>
                <ul className="flex flex-col gap-0.5">
                  {item.differences.map((diff) => <li key={diff} className="text-sm text-muted">{diff.charAt(0).toUpperCase() + diff.slice(1)}</li>)}
                </ul>
                <div className="flex flex-wrap items-center gap-x-s3 gap-y-s1 text-sm text-muted">
                  <span>Fijo <span className="num font-mono text-2xs text-ink">{fmtEur(item.fixed_cost_eur)}</span></span>
                  <span>Tablero <span className="num font-mono text-2xs text-ink">{fmtEur(item.material_cost_eur)}</span></span>
                  <span className="inline-flex items-center gap-s1">Horas {item.hours == null ? <ValueCell cell={{ value: null, cls: "unknown" }} align="left" /> : <span className="num font-mono text-2xs text-ink">{fmt(item.hours)}</span>}</span>
                </div>
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </div>
  );
}
