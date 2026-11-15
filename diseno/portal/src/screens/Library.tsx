import { useState } from "react";
import { api } from "../api";
import type { LibraryItem, SimilarityMatch } from "../api/types";
import { COPY } from "../copy";
import { ClassChip, ValueCell } from "../components/DataClass";
import { PlanThumb } from "../components/PlanThumb";
import { ErrorNote, LoadingBar, Spinner, TechDetails } from "../components/ui";
import { AXIS_LABELS, classOfDerived, fmt, fmtDate, FAMILY_LABELS, pickCandidate } from "../lib/domain";
import { useApi } from "../lib/useApi";
import { toAppError, useStore, type AppError } from "../state";
import { NoRun } from "./Workspace";

const DIFF_LABELS: Record<string, string> = {
  "dimensions.width_mm": "Ancho", "dimensions.depth_mm": "Fondo", "dimensions.height_mm": "Alto", thicknesses_mm: "Grosores",
  family: "Familia", structure: "Montaje", material: "Material", finish: "Acabado", roles: "Funciones",
};
const COMPONENT_LABELS: Record<string, string> = { dimensions: "Dimensiones", roles: "Funciones", thickness: "Grosor" };

/** Los valores llegan como texto del backend («900.0», «(18.0,)»): solo se les quita la notación Python. */
function showValue(raw: string) {
  const cleaned = raw.replace(/^\(|,?\)$/g, "");
  return cleaned.split(",").map((part) => {
    const n = Number(part.trim());
    return part.trim() !== "" && Number.isFinite(n) ? fmt(n) : part.trim();
  }).join(", ");
}

export function LibraryScreen() {
  const { current, run, drawing, config } = useStore();
  const [mode] = useState<"geometric" | "semantic">("geometric");
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<AppError | null>(null);
  const [saved, setSaved] = useState<LibraryItem | null>(null);

  const library = useApi(run ? () => api.getLibrary() : null, [run?.id, saved?.id]);
  const matches = useApi(current && run ? () => api.findSimilar(run.id, { result_revision: current.result_revision, mode, limit: 10 }) : null, [run?.id, current?.result_revision, mode, saved?.id]);
  const groups = useApi(run ? () => api.groupLibrary({ mode: "geometric", threshold: 0.8 }) : null, [run?.id, saved?.id]);

  if (!current || !run) return <NoRun />;
  const candidate = pickCandidate(current, run);
  // El backend ya excluye el run actual (main.py, similar()); el filtro se repite aquí para no compararlo nunca consigo mismo.
  const others = matches.data?.filter((match) => match.run_id !== run.id) ?? null;
  const items = new Map((library.data ?? []).map((item) => [item.id, item]));
  const alreadySaved = saved ?? (library.data ?? []).find((item) => item.run_id === run.id && item.result_revision === current.result_revision) ?? null;

  async function save() {
    if (!current || !run || !label.trim()) return;
    setSaving(true);
    setSaveError(null);
    try {
      setSaved(await api.saveToLibrary(run.id, { result_revision: current.result_revision, label: label.trim(), embedding_mode: "offline" }));
    } catch (err) {
      setSaveError(toAppError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid-cols-1 page grid gap-s5 py-s5 lg:grid-cols-[340px_minmax(0,1fr)] lg:gap-s6 lg:py-s6">
      <h1 className="sr-only">{COPY.library.title}</h1>
      <aside className="flex min-w-0 flex-col gap-s4">
        <section aria-labelledby="query-title" className="panel overflow-hidden">
          {drawing && <PlanThumb contours={drawing.contours} mm={drawing.coordinate_unit === "mm"} className="h-44 w-full border-b border-line p-s3" label="Miniatura del plano analizado" />}
          <div className="flex flex-col gap-s3 p-s4">
            <h2 id="query-title" className="text-md font-semibold">{COPY.library.query}</h2>
            {candidate && (
              <>
                <ClassChip cls={current.selected_assembly_candidate_id ? "confirmed" : "hypothesis"} label={FAMILY_LABELS[candidate.family]} />
                <dl className="grid grid-cols-3 gap-s2">
                  {(["width", "height", "depth"] as const).map((axis) => {
                    const d = candidate.derived_dimensions.find((item) => item.axis === axis);
                    return (
                      <div key={axis} className="flex flex-col gap-s1">
                        <dt className="text-sm text-muted">{AXIS_LABELS[axis]}</dt>
                        <dd><ValueCell cell={d ? classOfDerived(d.state, d.value_mm) : { value: null, cls: "unknown" }} align="left" /></dd>
                      </div>
                    );
                  })}
                </dl>
              </>
            )}
            <div className="border-t border-line pt-s3">
              {alreadySaved ? (
                <div className="flex flex-col gap-s1"><span className="text-sm text-muted">{COPY.library.saved}</span><span className="text-base font-semibold text-ink">{alreadySaved.label}</span></div>
              ) : (
                <form className="flex flex-col gap-s2" onSubmit={(event) => { event.preventDefault(); save(); }}>
                  <label htmlFor="lib-label" className="text-sm font-semibold text-ink">{COPY.library.labelField}</label>
                  <div className="flex gap-s2">
                    <input id="lib-label" className="input" value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Ej.: Estantería E-900" />
                    <button className="btn shrink-0" disabled={!label.trim() || saving}>{saving ? <Spinner size={12} /> : COPY.library.save}</button>
                  </div>
                  {saveError && <ErrorNote error={saveError} onRetry={save} />}
                </form>
              )}
            </div>
          </div>
        </section>

        <div className="flex flex-col gap-s2">
          <div className="inline-flex w-full border border-line-strong bg-surface p-0.5" role="radiogroup" aria-label="Método de similitud">
            <button role="radio" aria-checked={mode === "geometric"} className="h-9 flex-1 bg-ink text-sm font-semibold text-surface">{COPY.library.method.geometric}</button>
            <button role="radio" aria-checked={false} disabled={!config?.semantic.available} className="h-9 flex-1 text-sm text-muted/70 disabled:cursor-not-allowed" title={COPY.library.semanticOff}>{COPY.library.method.semantic}</button>
          </div>
          {!config?.semantic.available && <p className="text-sm text-muted">{COPY.library.semanticOff}</p>}
        </div>
      </aside>

      <div className="flex min-w-0 flex-col gap-s6">
        <section aria-labelledby="matches-title" className="flex flex-col gap-s3">
          <h2 id="matches-title" className="text-lg font-semibold tracking-[-0.01em]">{COPY.library.matches}</h2>
          {(matches.loading || library.loading) && <LoadingBar />}
          {matches.error && <ErrorNote error={matches.error} onRetry={matches.retry} />}
          {others && others.length === 0 && <p className="panel px-s4 py-s5 text-base text-muted">{COPY.library.noMatches}</p>}
          {others && others.length > 0 && (
            <ol className="panel divide-y divide-line overflow-hidden">
              {others.map((match) => <MatchRow key={match.library_item_id} match={match} item={items.get(match.library_item_id) ?? null} />)}
            </ol>
          )}
        </section>

        <section aria-labelledby="groups-title" className="flex flex-col gap-s3">
          <h2 id="groups-title" className="text-lg font-semibold tracking-[-0.01em]">{COPY.library.groups}</h2>
          {groups.error && <ErrorNote error={groups.error} onRetry={groups.retry} />}
          {groups.data?.length === 0 && <p className="text-base text-muted">{COPY.library.noGroups}</p>}
          {groups.data?.map((group) => (
            <div key={group.id} className="panel flex flex-col gap-s3 p-s4">
              <span className="text-base text-ink">Parecido {group.method === "geometric" ? "por medidas" : "por descripción"} de <span className="num font-mono text-[13px]">{fmt(group.threshold)}</span> o más</span>
              <ul className="flex flex-wrap gap-s2">
                {group.member_ids.map((id) => (
                  <li key={id} className={`inline-flex h-8 items-center border px-s2 text-sm ${items.get(id)?.run_id === run.id ? "border-2 border-ink font-semibold text-ink" : "border-line-strong text-muted"}`}>
                    {items.get(id)?.label ?? id}{items.get(id)?.run_id === run.id ? " · este plano" : ""}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

function MatchRow({ match, item }: { match: SimilarityMatch; item: LibraryItem | null }) {
  const thumb = useApi(() => api.getDrawing(match.run_id), [match.run_id]);
  const components = Object.entries(match.score_components).filter(([key]) => !key.endsWith("_weight"));
  return (
    <li className="grid-cols-1 grid gap-s4 p-s4 sm:grid-cols-[148px_minmax(0,1fr)_auto]">
      <div className="h-24 overflow-hidden border border-line bg-bg">
        {thumb.data && <PlanThumb contours={thumb.data.contours} mm={thumb.data.coordinate_unit === "mm"} className="h-full w-full p-s2" label={`Plano de ${item?.label ?? match.library_item_id}`} />}
      </div>
      <div className="flex min-w-0 flex-col gap-s2">
        <h3 className="text-md font-semibold text-ink">{item?.label ?? match.library_item_id}</h3>
        {item && (
          <p className="num font-mono text-2xs text-ink">
            {[item.descriptor.dimensions.width_mm, item.descriptor.dimensions.height_mm, item.descriptor.dimensions.depth_mm].map((v) => (v == null ? "desconocido" : fmt(v))).join(" × ")} mm
            {item.descriptor.thicknesses_mm?.length ? ` · tablero ${item.descriptor.thicknesses_mm.map(fmt).join(", ")} mm` : ""}
          </p>
        )}
        {match.differences.length === 0 ? (
          <p className="text-sm text-muted">{COPY.library.noDifferences}</p>
        ) : (
          <ul className="flex flex-wrap gap-x-s4 gap-y-s1">
            {match.differences.map((diff) => (
              <li key={diff.field} className="text-sm text-muted">
                {DIFF_LABELS[diff.field] ?? diff.field}{" "}
                <span className="num font-mono text-2xs text-muted">{showValue(diff.query_value)}</span>
                <span className="px-s1">frente a</span>
                <span className="num font-mono text-2xs font-medium text-ink">{showValue(diff.candidate_value)}</span>
              </li>
            ))}
          </ul>
        )}
        <TechDetails>
          <span className="num font-mono text-2xs">{match.run_id} · r{match.result_revision}{item ? ` · ${fmtDate(item.created_at)}` : ""}</span>
          <span className="num flex flex-wrap gap-x-s3 font-mono text-2xs">
            {components.map(([key, value]) => <span key={key}>{COMPONENT_LABELS[key] ?? key} {fmt(value)}</span>)}
          </span>
        </TechDetails>
      </div>
      <div className="flex items-baseline gap-s2 sm:flex-col sm:items-end sm:gap-0">
        <span className="text-sm text-muted">{COPY.library.score}</span>
        <span className="num font-mono text-lg font-medium text-ink">{fmt(match.score)}</span>
      </div>
    </li>
  );
}
