import { useEffect, useState } from "react";
import { api } from "../api";
import { COPY } from "../copy";
import { ValueCell } from "../components/DataClass";
import { ErrorNote, LoadingBar, Spinner } from "../components/ui";
import { fmtEur } from "../lib/domain";
import { useApi } from "../lib/useApi";
import { toAppError, useStore, type AppError } from "../state";
import { saveFile } from "../workspace/store";

/**
 * Presupuesto: el total provisional de la estimación vigente (GET /runs/{id}) y sus salidas, CSV, JSON y láminas.
 * El cálculo y sus términos están en Coste; aquí no se recalcula nada.
 */
export function Budget({ request, onPrint }: { request: { format: "json" | "csv"; tick: number } | null; onPrint: () => void }) {
  const { current, run, go } = useStore();
  const detail = useApi(run && current ? () => api.getRun(run.id) : null, [run?.id, current?.result_revision]);
  const [exported, setExported] = useState<{ format: "json" | "csv"; filename: string; body: string; mediaType: string } | null>(null);
  const [busy, setBusy] = useState<"json" | "csv" | null>(null);
  const [error, setError] = useState<AppError | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const estimate = detail.data?.estimate ?? null;

  async function doExport(format: "json" | "csv") {
    if (!run) return;
    setBusy(format);
    setError(null);
    setNote(null);
    try { setExported({ format, ...(await api.getExport(run.id, format)) }); }
    catch (err) { setError(toAppError(err)); }
    finally { setBusy(null); }
  }
  useEffect(() => { if (request) doExport(request.format); }, [request?.tick]); // eslint-disable-line react-hooks/exhaustive-deps

  async function download() {
    if (!exported) return;
    const outcome = await saveFile(new Blob([exported.body], { type: exported.mediaType }), exported.filename);
    setNote(outcome === "saved" ? COPY.cad.downloaded(exported.filename) : outcome === "declined" ? null : COPY.cad.viewerUnavailable);
  }
  async function copy() {
    if (!exported) return;
    try { await navigator.clipboard.writeText(exported.body); setNote(COPY.purchase.copied); } catch { setNote(null); }
  }

  return (
    <div className="flex flex-col gap-s5 p-s4 lg:p-s5">
      <section aria-labelledby="budget-total" className="flex flex-col gap-s3">
        <h3 id="budget-total" className="text-sm text-muted">{COPY.purchase.total}</h3>
        {detail.loading && <LoadingBar />}
        {estimate ? (
          <div className="flex flex-wrap items-end justify-between gap-s4 border border-line bg-surface px-s4 py-s4">
            <span className="flex flex-col gap-s1">
              <span className="num font-mono text-xl font-medium text-ink">{fmtEur(estimate.total)}</span>
              <span className="text-sm text-muted">{COPY.portal.budget.revision(estimate.result_revision)}</span>
            </span>
            <span className="flex items-center gap-s2 text-sm text-muted">
              {COPY.purchase.hours}
              <ValueCell cell={estimate.hours == null ? { value: null, cls: "unknown" } : { value: estimate.hours, cls: "calculated" }} unit="h" />
            </span>
          </div>
        ) : !detail.loading && (
          <div className="flex flex-col items-start gap-s3 border border-dashed border-line-strong px-s4 py-s4">
            <p className="text-base text-ink">{COPY.portal.budget.none}</p>
            <button className="btn btn-sm" onClick={() => go("compras")}>{COPY.portal.budget.toCost}</button>
          </div>
        )}
        <p className="flex items-center gap-s2 text-sm text-muted">
          <span className="inline-flex h-6 items-center bg-ink px-s2 text-xs font-bold text-surface">Sintético</span>
          {COPY.purchase.synthetic}
        </p>
      </section>

      <section aria-labelledby="budget-out" className="flex flex-col gap-s3">
        <h3 id="budget-out" className="text-sm text-muted">{COPY.portal.blocks.outputs}</h3>
        <div className="flex flex-wrap gap-s2">
          <button className="btn btn-sm" onClick={() => doExport("csv")} disabled={busy !== null}>{busy === "csv" ? <Spinner size={12} /> : null}{COPY.portal.out.csv}</button>
          <button className="btn btn-sm" onClick={() => doExport("json")} disabled={busy !== null}>{busy === "json" ? <Spinner size={12} /> : null}{COPY.portal.out.json}</button>
          <button className="btn btn-sm" onClick={onPrint}>{COPY.portal.out.sheets}</button>
        </div>
        {error && <ErrorNote error={error} />}
        {exported && (
          <div className="border border-line bg-surface">
            <div className="flex h-11 items-center justify-between gap-s3 border-b border-line pl-s4 pr-s2">
              <span className="num truncate font-mono text-2xs text-ink">{exported.filename}</span>
              <span className="flex items-center gap-s1">
                <button className="btn btn-ghost btn-sm" onClick={download}>{COPY.purchase.download}</button>
                <button className="btn btn-ghost btn-sm" onClick={copy}>{COPY.purchase.copy}</button>
              </span>
            </div>
            <pre className="scroll-thin num max-h-72 overflow-auto bg-bg px-s4 py-s3 font-mono text-2xs text-ink">{exported.body.length > 6000 ? `${exported.body.slice(0, 6000)}\n…` : exported.body}</pre>
          </div>
        )}
        {note && <p role="status" className="text-sm text-muted">{note}</p>}
      </section>
    </div>
  );
}
