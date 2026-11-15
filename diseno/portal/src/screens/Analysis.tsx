import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { DrawingExtraction, Result, RunEvent, RunSnapshot, UploadedDocument } from "../api/types";
import { COPY } from "../copy";
import { DrawingCanvas, type Reveal } from "../components/DrawingCanvas";
import { ErrorNote, LoadingBar, Spinner, TechDetails } from "../components/ui";
import { fmt, fmtEur, RESULT_STATE_LABELS } from "../lib/domain";
import { useStore } from "../state";
import { useWorkspace } from "../workspace/store";
import type { LiveStage, PlanRecord } from "../workspace/types";

interface View {
  stage: LiveStage;
  document: UploadedDocument | null;
  run: RunSnapshot | null;
  result: Result | null;
  drawing: DrawingExtraction | null;
  events: RunEvent[];
  error: { message: string; code: string; status: number; retryable: boolean } | null;
}

/**
 * Pantalla de análisis de un plano. Mientras se analiza lee el estado en vivo del espacio de trabajo;
 * con el análisis terminado vuelve a pedir la traza (GET /runs/{id}/events) y el plano se dibuja otra vez con ella.
 */
export function AnalysisScreen({ plan }: { plan: PlanRecord }) {
  const ws = useWorkspace();
  const store = useStore();
  const live = ws.live[plan.id];
  const fromLive = Boolean(live && (live.stage !== "done" || live.events.length > 0 || live.origin === "user"));
  const replayRun = !fromLive && store.planId === plan.id ? store.run : null;
  const [replay, setReplay] = useState<{ runId: string; events: RunEvent[]; done: boolean } | null>(null);

  useEffect(() => {
    if (!replayRun) return;
    const controller = new AbortController();
    const seen = new Set<number>();
    setReplay({ runId: replayRun.id, events: [], done: false });
    api.streamEvents(replayRun.id, (event) => {
      if (seen.has(event.sequence)) return;
      seen.add(event.sequence);
      setReplay((value) => (value && value.runId === replayRun.id ? { ...value, events: [...value.events, event] } : value));
    }, controller.signal)
      .then(() => setReplay((value) => (value ? { ...value, done: true } : value)))
      .catch(() => setReplay((value) => (value ? { ...value, done: true } : value)));
    return () => controller.abort();
  }, [replayRun?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const view: View | null = fromLive && live
    ? { stage: live.stage, document: live.document, run: live.run, result: live.result, drawing: live.drawing, events: live.events, error: live.error }
    : replayRun && store.current
      ? { stage: replay?.done ? "done" : "tracing", document: store.document, run: replayRun, result: store.revisions[0] ?? store.current, drawing: store.drawing, events: replay?.events ?? [], error: null }
      : plan.status === "error" && plan.error
        ? { stage: "error", document: null, run: null, result: null, drawing: null, events: [], error: { ...plan.error, status: 0, retryable: true } }
        : null;

  if (!view) {
    return (
      <div className="flex items-center gap-s2 p-s5 text-sm text-muted"><Spinner /> {COPY.queue.stages.queued}</div>
    );
  }
  return <AnalysisView plan={plan} view={view} />;
}

function AnalysisView({ plan, view }: { plan: PlanRecord; view: View }) {
  const { go } = useStore();
  const ws = useWorkspace();
  const { stage, document, run, result, drawing, events, error } = view;
  const observations = result?.part_analysis?.observations ?? [];
  const evidenceKey = new Map(observations.flatMap((o, i) => o.evidence_ids.map((id) => [id, o.part_key ?? `Sin etiqueta ${i + 1}`] as const)));
  const keyOfEvidence = (id: string) => evidenceKey.get(id) ?? null;
  const viewKeys = useMemo(() => {
    const map = new Map<string, string>();
    observations.forEach((o, i) => o.views.forEach((v) => map.set(v.view_id, o.part_key ?? `Sin etiqueta ${i + 1}`)));
    return map;
  }, [observations]);
  const reveal = useMemo(() => revealFor(stage, events, result, run), [stage, events, result, run]);
  const timing = traceTiming(events);
  const failedAt = stage === "error" ? (!document ? 1 : !run ? 2 : 3) : 0;
  const uploadState: StageState = document || run ? "done" : failedAt === 1 ? "error" : stage === "queued" ? "waiting" : "active";
  const runState: StageState = failedAt === 2 ? "error" : run ? "done" : stage === "running" || stage === "reading" ? "active" : "waiting";
  const traceState: StageState = stage === "done" ? "done" : stage === "tracing" ? "active" : failedAt === 3 ? "error" : "waiting";
  const empty = new Set<string>();
  // Si el archivo no llegó a leerse no hay plano que enseñar: la pantalla queda en una columna.
  const showCanvas = Boolean(drawing) || stage !== "error";

  return (
    <div className={showCanvas ? "grid grid-cols-1 lg:h-[calc(100vh-var(--bar-h))] lg:grid-cols-[minmax(0,1fr)_minmax(400px,38%)]" : "page max-w-[720px]"}>
      <h1 className="sr-only">{COPY.nav.analysis}</h1>
      {showCanvas && <section aria-label={COPY.workspace.plan} className="relative h-[44vh] min-h-[300px] border-b border-line lg:h-auto lg:border-b-0 lg:border-r">
        {drawing ? (
          <DrawingCanvas drawing={drawing} primary={empty} secondary={empty} viewKeys={viewKeys} reveal={reveal} className="absolute inset-0" />
        ) : (
          <div className="plan-grid absolute inset-0" />
        )}
        {(stage === "uploading" || stage === "reading" || stage === "running" || stage === "queued") && <div className="absolute inset-x-0 top-0"><LoadingBar /></div>}
      </section>}

      <div className={`scroll-thin flex min-w-0 flex-col gap-s5 py-s5 ${showCanvas ? "px-s4 lg:overflow-y-auto lg:px-s5" : "lg:py-s6"}`}>
        <ol className="relative flex flex-col">
          <Stage state={uploadState} title={COPY.upload.stages.upload}>
            {document ? (
              <span className="flex flex-col gap-s1 text-sm text-muted">
                <span className="num break-all font-mono text-2xs text-ink">{document.original_filename} · {fmt(Math.round(document.size_bytes / 1024))} KiB</span>
                <TechDetails><span className="num break-all font-mono text-2xs">sha256 {document.sha256}</span></TechDetails>
              </span>
            ) : run && (
              <span className="num break-all font-mono text-2xs text-ink">{plan.filename}{plan.sizeBytes ? ` · ${fmt(Math.round(plan.sizeBytes / 1024))} KiB` : ""}</span>
            )}
          </Stage>
          <Stage state={runState} title={COPY.upload.stages.run}>
            {run && <span className="text-sm text-muted">{COPY.upload.modes[run.mode].label}</span>}
          </Stage>
          <Stage state={traceState} title={COPY.upload.stages.trace}>
            {timing.label && <span className="text-sm text-muted">{timing.label}</span>}
          </Stage>
          <Stage state={stage === "done" ? "done" : "waiting"} title={COPY.upload.stages.done} last>
            {stage === "done" && result && (
              <div className="flex flex-col items-start gap-s3" aria-live="polite">
                <span className="text-base text-ink">
                  Revisión <span className="num font-mono text-[13px]">{result.result_revision}</span> · {RESULT_STATE_LABELS[result.state]}
                </span>
                <button className="btn btn-primary" onClick={() => go("plano")}>{COPY.upload.open}</button>
              </div>
            )}
          </Stage>
        </ol>
        {error && (
          <ErrorNote
            error={{ ...error, message: UPLOAD_ERRORS[error.code] ?? error.message }}
            action={error.code !== "unsupported_format" && error.code !== "upload_too_large" ? <button className="btn btn-sm" onClick={() => ws.retry(plan.id)}>{COPY.queue.retry}</button> : undefined}
          />
        )}

        <section aria-labelledby="trace-title" className="flex min-w-0 flex-col border-t border-line pt-s4">
          <h2 id="trace-title" className="mb-s2 text-base font-semibold text-ink">{COPY.upload.stages.trace}</h2>
          {events.length === 0 ? (
            <p className="py-s3 text-base text-muted">{failedAt && failedAt < 3 ? COPY.upload.notStarted : COPY.upload.traceEmpty}</p>
          ) : (
            <ol className="flex flex-col">
              {events.map((event) => <TraceRow key={event.sequence} event={event} keyOfEvidence={keyOfEvidence} showTime={timing.perRow} />)}
              {stage === "tracing" && (
                <li className="py-s3 text-base text-muted">
                  <span className="inline-flex items-center gap-s2"><span className="anim-pulse inline-block h-1.5 w-1.5 rounded-full bg-ink" aria-hidden="true" />Pendiente</span>
                </li>
              )}
            </ol>
          )}
        </section>
      </div>
    </div>
  );
}

/**
 * El plano se dibuja con la traza y sin eventos inventados:
 * al leer el DXF se ven los contornos en discontinuo; con «Análisis iniciado» pasan a trazo firme;
 * cada «Inspeccionar pieza» del asistente dibuja las vistas de esa pieza con sus cotas;
 * con el resultado guardado aparecen todas las cotas y con «Análisis terminado», los rótulos.
 */
function revealFor(stage: LiveStage, events: RunEvent[], result: Result | null, run: RunSnapshot | null): Reveal {
  const types = new Set(events.map((event) => event.event_type));
  const committed = types.has("result_committed") || types.has("run_finished") || (stage === "done" && events.length === 0);
  const finished = types.has("run_finished") || (stage === "done" && events.length === 0);
  const started = types.has("run_state_changed") || committed;
  const live = run?.mode === "live" || events.some((event) => event.event_type === "tool_completed");
  const touched = new Set<string>();
  const observations = result?.part_analysis?.observations ?? [];
  for (const event of events) {
    if (event.event_type !== "tool_completed") continue;
    const evidence = new Set((event.data.evidence_ids as string[] | undefined) ?? []);
    for (const observation of observations) if (observation.evidence_ids.some((id) => evidence.has(id))) observation.views.forEach((view) => touched.add(view.view_id));
  }
  return {
    contour: (viewId) => (committed || touched.has(viewId) || (started && !live) ? "solid" : "faint"),
    dims: (viewId) => committed || touched.has(viewId),
    texts: (viewId) => finished || touched.has(viewId),
  };
}

type StageState = "done" | "active" | "waiting" | "error";

/** Etapa sin número: el estado se lee en el punto (hecho, en curso, en espera o error). */
function Stage({ state, title, children, last = false }: { state: StageState; title: string; children?: React.ReactNode; last?: boolean }) {
  const dot = {
    done: "border-ink bg-ink text-surface",
    active: "border-ink bg-surface text-ink",
    waiting: "border-line-strong bg-bg",
    error: "border-danger bg-danger-soft text-danger",
  }[state];
  return (
    <li className={`relative grid grid-cols-[20px_1fr] gap-x-s3 ${last ? "" : "pb-s4"}`} data-stage-state={state}>
      {!last && <span className={`absolute left-[9.5px] top-5 h-[calc(100%-20px)] w-px ${state === "done" ? "bg-ink" : "bg-line-strong"}`} aria-hidden="true" />}
      <span className={`relative z-[1] mt-px flex h-5 w-5 items-center justify-center rounded-full border ${dot}`}>
        {state === "done" ? (
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M1.6 5.3 4 7.6 8.6 2.6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        ) : state === "active" ? <Spinner size={12} /> : state === "error" ? <span className="h-1.5 w-1.5 rounded-full bg-danger" aria-hidden="true" /> : null}
      </span>
      <div className="flex min-w-0 flex-col gap-s1">
        <span className={`text-base ${state === "waiting" ? "text-muted" : "text-ink"} ${state === "active" ? "font-semibold" : ""}`}>{title}</span>
        {children}
      </div>
    </li>
  );
}

const STATE_LABELS: Record<string, string> = { needs_review: "Requiere revisión", completed: "Completo", failed: "Fallido", cancelled: "Cancelado", timed_out: "Tiempo agotado" };
const MODE_LABELS: Record<string, string> = { geometry_only: COPY.upload.modes.geometry_only.label, live: COPY.upload.modes.live.label };

const TOOL_SUMMARY: Record<string, string> = {
  inspeccionar_pieza: "Ha leído sus vistas, cotas y cantidad.",
  entregar_candidato_montaje: "Queda pendiente de que una persona lo confirme.",
  inspeccionar_evidencia: "Ha consultado contornos y cotas del plano.",
  explicar_pieza: "Ha consultado de dónde sale cada medida.",
};
function toolTitle(tool: string, evidence: string[], keyOf: (id: string) => string | null) {
  if (tool === "inspeccionar_pieza") return `Inspeccionar pieza ${evidence.map(keyOf).find(Boolean) ?? ""}`.trim();
  if (tool === "entregar_candidato_montaje") return "Proponer montaje";
  if (tool === "inspeccionar_evidencia") return "Consultar el plano";
  if (tool === "explicar_pieza") return "Explicar pieza";
  return "Paso del asistente";
}

/** Hora real de cada evento; si todos caen en el mismo segundo, solo la duración total. */
function traceTiming(events: RunEvent[]): { perRow: boolean; label: string } {
  const times = events.map((event) => Date.parse(String(event.data.timestamp ?? ""))).filter((value) => !Number.isNaN(value));
  if (times.length < 2) return { perRow: false, label: "" };
  const span = Math.max(...times) - Math.min(...times);
  if (span < 1000) return { perRow: false, label: "Menos de 1 s" };
  return { perRow: true, label: `${fmt(Math.round(span / 1000))} s` };
}

function TraceRow({ event, keyOfEvidence, showTime }: { event: RunEvent; keyOfEvidence: (id: string) => string | null; showTime: boolean }) {
  const d = event.data as Record<string, unknown>;
  let title = event.event_type;
  let detail: React.ReactNode = null;
  let tone = "text-ink";
  switch (event.event_type) {
    case "run_state_changed":
      title = "Análisis iniciado";
      detail = <span>{MODE_LABELS[String(d.mode)] ?? String(d.mode)} · {STATE_LABELS[String(d.state)] ?? String(d.state)}</span>;
      break;
    case "tool_completed":
      title = toolTitle(String(d.tool_name), (d.evidence_ids as string[]) ?? [], keyOfEvidence);
      tone = d.ok ? "text-ink" : "text-danger";
      detail = (
        <span className="flex flex-col gap-s1">
          <span>{d.ok ? TOOL_SUMMARY[String(d.tool_name)] ?? String(d.summary) : String(d.summary)}</span>
          <TechDetails>
            <span className="num font-mono text-2xs">{String(d.tool_name)}</span>
            {Array.isArray(d.evidence_ids) && (d.evidence_ids as string[]).map((id) => <span key={id} className="num font-mono text-2xs">{id}</span>)}
            {typeof d.selected_assembly_candidate_id === "string" && <span className="num break-all font-mono text-2xs">{d.selected_assembly_candidate_id}</span>}
          </TechDetails>
        </span>
      );
      break;
    case "result_committed":
      title = "Resultado guardado";
      detail = <span>Revisión <span className="num font-mono text-2xs">{String(d.result_revision)}</span> · {STATE_LABELS[String(d.state)] ?? String(d.state)}</span>;
      break;
    case "run_finished":
      title = "Análisis terminado";
      detail = <span>{STATE_LABELS[String(d.state)] ?? String(d.state)}</span>;
      break;
    case "human_review_committed":
      title = "Revisión de persona";
      detail = <span>Revisión <span className="num font-mono text-2xs">{String(d.result_revision)}</span> · {String(d.reviewer_name)}</span>;
      break;
    case "estimate_committed":
      title = "Estimación guardada";
      detail = <span>Revisión <span className="num font-mono text-2xs">{String(d.result_revision)}</span> · <span className="num font-mono text-2xs">{fmtEur(Number(d.total))}</span></span>;
      break;
    case "library_item_saved":
      title = "Guardado en biblioteca";
      detail = <span>Revisión <span className="num font-mono text-2xs">{String(d.result_revision)}</span></span>;
      break;
  }
  return (
    <li className="anim-in grid grid-cols-[minmax(0,1fr)_auto] gap-x-s3 border-b border-line py-s3 last:border-b-0">
      <div className="flex min-w-0 flex-col gap-s1">
        <span className={`text-base font-semibold ${tone}`}>{title}</span>
        <span className="text-sm text-muted">{detail}</span>
      </div>
      <span className="num pt-px font-mono text-2xs text-muted">{showTime && d.timestamp ? new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Europe/Madrid" }).format(new Date(String(d.timestamp))) : ""}</span>
    </li>
  );
}

export const UPLOAD_ERRORS: Record<string, string> = {
  unsupported_format: "Vexplorer solo lee DXF. Exporta el plano a DXF desde el programa de CAD y vuelve a cargarlo.",
  upload_too_large: "El archivo supera 20 MiB. Limpia capas y bloques que no se usen y vuelve a exportarlo.",
  invalid_dxf: "El DXF no se puede leer. Comprueba que se abre en el programa de CAD y vuelve a exportarlo.",
  unsupported_geometry: "Las vistas no forman piezas rectangulares que Vexplorer pueda medir.",
  live_provider_unavailable: "El asistente IA no está activado. Analiza en modo Solo medidas del plano.",
  live_provider_failed: "El asistente IA falló durante el análisis. Vuelve a intentarlo o analiza en modo Solo medidas del plano.",
  recorded_replay_unavailable: "Todavía no hay análisis guardados.",
  file_missing: "El DXF ya no está guardado en este navegador. Vuelve a subirlo.",
};
