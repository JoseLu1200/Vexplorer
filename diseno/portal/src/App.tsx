import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { MOCK_SAMPLES } from "./api/mock";
import type { DrawingExtraction, LibraryItem } from "./api/types";
import { COPY } from "./copy";
import { Modal, QueuePanel, Skel, Toasts } from "./components/system";
import { PortalBar } from "./components/TopBar";
import { ErrorNote, Spinner } from "./components/ui";
import { LOGO_A, LOGO_B } from "./components/Logo";
import { buildRows, pickCandidate } from "./lib/domain";
import { enabledScreens } from "./portal/nav";
import { Workbench } from "./portal/Workbench";
import { MesaGeneral } from "./portal/MesaGeneral";
import { cargarMesa, olvidarMesa } from "./portal/mesa";
import { Proceso } from "./portal/Proceso";
import { pasosEnCurso } from "./general/proceso";
import type { MesaTrabajo } from "./general";
import type { PlanRecord } from "./workspace/types";
import { useRouter, VIEWS, type Screen } from "./router";
import { AnalysisScreen } from "./screens/Analysis";
import { DRAG_FOLDER, DRAG_PLAN, ProjectsScreen } from "./screens/Projects";
import { toAppError, useStore, type AppError } from "./state";
import { sampleFile } from "./workspace/samples";
import { useWorkspace } from "./workspace/store";
import { PaginaMapa } from "./mapa/PaginaMapa";

const AUTOPILOT = api.isMock && new URLSearchParams(location.search).has("auto");

export function App() {
  const { route } = useRouter();
  const ws = useWorkspace();
  const [library, setLibrary] = useState<{ planId: string; item: LibraryItem; drawing: DrawingExtraction } | null>(null);
  const libraryOnly = route.kind === "plan" && library?.planId === route.planId;
  useCaptureAutopilot();
  useShortcuts();
  if (location.hash.startsWith("#mapa")) return <PaginaMapa />;
  return (
    <div className="flex min-h-full flex-col">
      <Boot ready={ws.ready} />
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-sm focus:bg-surface focus:px-3 focus:py-2">Saltar al contenido</a>
      {route.kind === "home" && <PortalBar />}
      <main id="main" className="flex min-h-0 flex-1 flex-col">
        {route.kind === "home"
          ? <ProjectsScreen key={route.folderId ?? "root"} folderId={route.folderId} />
          : <PlanHost planId={route.planId} screen={route.screen} library={libraryOnly ? library : null} onLibrary={setLibrary} />}
      </main>
      <DropLayer />
      <QueuePanel />
      <Toasts />
      <ShortcutsDialog />
    </div>
  );
}

/** Arranque breve con el logo mientras se abre el almacenamiento y se siembra el espacio de trabajo. */
function Boot({ ready }: { ready: boolean }) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [minDone, setMinDone] = useState(AUTOPILOT);
  const [gone, setGone] = useState(AUTOPILOT);
  useEffect(() => { const id = setTimeout(() => setMinDone(true), reduced ? 150 : 1700); return () => clearTimeout(id); }, [reduced]);
  const leaving = ready && minDone;
  useEffect(() => { if (leaving) { const id = setTimeout(() => setGone(true), reduced ? 0 : 220); return () => clearTimeout(id); } }, [leaving, reduced]);
  if (gone) return null;
  return (
    <div className={`fixed inset-0 z-[70] flex items-center justify-center bg-bg ${leaving ? "boot-out" : ""}`} role="status" aria-label="Abriendo Vexplorer" data-testid="boot">
      <div className="flex items-center gap-s3">
        <svg width="180" height="180" viewBox="0 0 100 100" className="boot-mark text-ink" aria-hidden="true" style={{ overflow: "visible", width: "clamp(78px,13.5vw,180px)", height: "auto" }}>
          <defs>
            <mask id="boot-mask" maskUnits="userSpaceOnUse" x="-10" y="-10" width="120" height="120">
              <rect x="-10" y="-10" width="120" height="120" fill="white" />
              <polygon points={LOGO_A} fill="black" />
              <polygon points={LOGO_B} fill="black" />
            </mask>
          </defs>
          <g mask="url(#boot-mask)" stroke="currentColor" strokeWidth="5" fill="none">
            <path className="b b3" pathLength={1} d="M34 80 L74 24" />
            <path className="b b3" pathLength={1} d="M60 24 L74 24 L74 38" strokeLinecap="square" strokeLinejoin="miter" />
          </g>
          <polygon className="b" pathLength={1} points={LOGO_A} fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinejoin="miter" />
          <polygon className="b b2" pathLength={1} points={LOGO_B} fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinejoin="miter" />
        </svg>
        <span className="boot-word translate-y-px text-[clamp(52px,9vw,120px)] font-bold leading-none tracking-[0.005em] text-ink">Vexplorer</span>
      </div>
    </div>
  );
}

type OpenState = { status: "loading"; reanalyzing: boolean } | { status: "ready" } | { status: "error"; error: AppError };

/** Abre un plano: espera a su análisis, lo carga en el estado y enseña la pantalla pedida, con esqueleto mientras tanto. */
function PlanHost({ planId, screen, library, onLibrary }: { planId: string; screen: Screen; library: { item: LibraryItem; drawing: DrawingExtraction } | null; onLibrary: (value: { planId: string; item: LibraryItem; drawing: DrawingExtraction } | null) => void }) {
  const ws = useWorkspace();
  const store = useStore();
  const { navigate } = useRouter();
  const plan = ws.plans.find((item) => item.id === planId);
  const live = ws.live[planId];
  const userAnalysis = plan?.status === "analyzing" && live?.origin !== "sync";
  const [open, setOpen] = useState<OpenState>({ status: "loading", reanalyzing: false });
  const { load, planId: loadedId, run } = store;
  const routePlan = useRef(planId);
  routePlan.current = planId;

  const viaMesa = plan?.source === "caso" || plan?.source === "general";
  useEffect(() => {
    if (!ws.ready || !plan || viaMesa || userAnalysis || plan.status === "error") return;
    if (loadedId === planId && run && ws.ownerOf(run.id) === planId) { setOpen({ status: "ready" }); return; }
    if (library) { setOpen({ status: "ready" }); return; }
    let alive = true;
    if (loadedId === planId && run) {
      // El mock ha dado este run_id a otro plano: se rehace en segundo plano y la pantalla sigue a la vista.
      // Sin depender de este efecto, que se repite en cuanto el plano recupera su run_id.
      ws.ensureRun(planId)
        .then((opened) => { if (routePlan.current === planId && opened.kind === "run") load(opened.bundle, { keepSelection: true }); })
        .catch((error) => { if (routePlan.current === planId) setOpen({ status: "error", error: toAppError(error) }); });
      return;
    }
    setOpen({ status: "loading", reanalyzing: false });
    ws.ensureRun(planId)
      .then((opened) => {
        if (!alive) return;
        if (opened.kind === "run") { onLibrary(null); load(opened.bundle); }
        else onLibrary({ planId, item: opened.item, drawing: opened.drawing });
        setOpen({ status: "ready" });
      })
      .catch((error) => { if (alive) setOpen({ status: "error", error: toAppError(error) }); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId, plan?.status, ws.ready, ws.ownersTick]);

  useEffect(() => {
    if (open.status === "loading" && live?.origin === "sync" && live.stage !== "done") setOpen({ status: "loading", reanalyzing: true });
  }, [open.status, live?.origin, live?.stage]);

  const framed = (node: React.ReactNode) => <><PortalBar />{node}</>;
  if (!ws.ready) return framed(<PlanSkeleton />);
  if (!plan) {
    return framed(
      <div className="page flex flex-col items-start gap-s3 py-s6">
        <h1 className="text-lg font-semibold text-ink">{COPY.workspace2.planMissing}</h1>
        <button className="btn btn-sm" onClick={() => navigate({ kind: "home", folderId: null })}>{COPY.workspace2.backHome}</button>
      </div>,
    );
  }
  if (viaMesa && enabledScreens(plan, false).has(screen)) return <MesaHost plan={plan} screen={screen} framed={framed} />;
  const allowed = enabledScreens(plan, !library && loadedId === planId, live?.origin);
  if (!allowed.has(screen)) {
    const fallback: Screen = allowed.has("plano") ? "plano" : allowed.has("analisis") ? "analisis" : "original";
    return <Redirect to={() => navigate({ kind: "plan", planId, screen: fallback }, { replace: true })} />;
  }
  if (userAnalysis || plan.status === "error" || (screen === "analisis" && live && live.origin === "user")) return framed(<AnalysisScreen plan={plan} />);
  if (open.status === "error") {
    return framed(
      <div className="page flex flex-col gap-s3 py-s6">
        <ErrorNote error={open.error} action={<button className="btn btn-sm" onClick={() => navigate({ kind: "home", folderId: plan.folderId })}>{COPY.workspace2.backHome}</button>} />
      </div>,
    );
  }
  if (open.status === "loading" || (!library && loadedId !== planId)) return framed(<PlanSkeleton note={open.status === "loading" && open.reanalyzing ? COPY.workspace2.reanalyzing : undefined} />);
  if (screen === "analisis") return framed(<AnalysisScreen plan={plan} />);
  return <Workbench plan={plan} screen={screen} library={library} />;
}

/**
 * Mueble de la carpeta «Muebles procesados» o subido por la vía general: se carga su MesaTrabajo (src/general) una vez
 * y se abre en la mesa de trabajo. Mientras la subida se analiza o si falla, la franja superior y el estado.
 */
function MesaHost({ plan, screen, framed }: { plan: PlanRecord; screen: Screen; framed: (node: React.ReactNode) => JSX.Element }) {
  const [state, setState] = useState<{ mesa: MesaTrabajo } | { error: AppError } | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const { navigate } = useRouter();
  const ws = useWorkspace();
  const pending = plan.status === "analyzing" || (plan.source === "general" && !plan.runId);
  useEffect(() => {
    if (pending || plan.status === "error") return;
    let alive = true;
    if (!reloadTick) setState(null);
    cargarMesa(plan).then((mesa) => { if (alive) setState({ mesa }); }).catch((error) => { if (alive) setState({ error: toAppError(error) }); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan.id, plan.runId, pending, plan.status, reloadTick]);
  const reload = () => { olvidarMesa(plan.id); setReloadTick((value) => value + 1); };
  const back = <button className="btn btn-sm" onClick={() => navigate({ kind: "home", folderId: plan.folderId })}>{COPY.workspace2.backHome}</button>;
  if (plan.status === "error") return framed(<div className="page flex flex-col gap-s3 py-s6"><ErrorNote error={{ message: plan.error?.message ?? COPY.errors.generic, code: plan.error?.code ?? "error", status: 0, retryable: false }} action={back} /></div>);
  if (pending) {
    // Subida en curso: los pasos del proceso según llegan, con el estado real de cada uno.
    const stage = ws.live[plan.id]?.stage;
    const fase = stage === "uploading" || stage === "queued" ? "subiendo" : stage === "tracing" ? "salidas" : stage === "done" ? "hecho" : "analizando";
    return framed(
      <div className="page flex flex-col items-start gap-s4 py-s6">
        <h1 className="text-lg font-semibold text-ink">{plan.name}</h1>
        <Proceso pasos={pasosEnCurso(fase, plan.flujo ?? "general")} actual={null} etiqueta={plan.flujo === "guardado" ? COPY.portal.general.saved : null} className="w-full max-w-[420px]" />
      </div>,
    );
  }
  if (!state) return framed(<PlanSkeleton />);
  if ("error" in state) return framed(<div className="page flex flex-col gap-s3 py-s6"><ErrorNote error={state.error} action={back} /></div>);
  return <MesaGeneral key={plan.id} plan={plan} mesa={state.mesa} screen={screen} onReload={reload} />;
}

function Redirect({ to }: { to: () => void }) {
  useEffect(() => { to(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

/** Esqueleto con la forma de la mesa: lienzo grande y ficha estrecha. */
function PlanSkeleton({ note }: { note?: string }) {
  return (
    <div className="flex h-[calc(100dvh-var(--bar-h))] flex-col" aria-busy="true" data-testid="plan-skeleton">
      <span className="sr-only" role="status">{note ?? "Abriendo el plano"}</span>
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1 border-t border-line bg-canvas">
          {note && <p className="absolute left-s4 top-s4 inline-flex items-center gap-s2 border border-line-strong bg-surface px-s3 py-s2 text-sm text-ink"><Spinner size={12} /> {note}</p>}
          <div className="absolute inset-s6 flex flex-col justify-center gap-s5" aria-hidden="true">
            <Skel className="h-12 w-2/5" /><Skel className="h-12 w-3/5" /><Skel className="h-12 w-1/2" />
          </div>
        </div>
        <div className="hidden w-[320px] flex-col gap-s3 border-l border-t border-line bg-surface p-s4 lg:flex">
          <Skel className="h-6 w-1/3" />
          <div className="flex flex-col gap-s2 pt-s3">{[0, 1, 2, 3].map((i) => <Skel key={i} className="h-8" />)}</div>
        </div>
      </div>
    </div>
  );
}

/**
 * Arrastrar archivos sobre la ventana o sobre una carpeta. También mueve planos y carpetas arrastrados dentro de la app.
 * El destino es el elemento con data-drop-folder bajo el puntero o, si no hay, la carpeta abierta.
 */
function DropLayer() {
  const ws = useWorkspace();
  const { route } = useRouter();
  const [over, setOver] = useState<string | null | undefined>(undefined);
  const marked = useRef<Element | null>(null);
  const routeRef = useRef(route);
  routeRef.current = route;
  const plansRef = useRef(ws.plans);
  plansRef.current = ws.plans;
  const wsRef = useRef(ws);
  wsRef.current = ws;

  useEffect(() => {
    const currentFolder = () => {
      const r = routeRef.current;
      return r.kind === "home" ? r.folderId : plansRef.current.find((plan) => plan.id === r.planId)?.folderId ?? null;
    };
    const mark = (el: Element | null) => {
      if (marked.current === el) return;
      marked.current?.classList.remove("is-drop-target");
      el?.classList.add("is-drop-target");
      marked.current = el;
    };
    const targetOf = (event: DragEvent) => (event.target instanceof Element ? event.target.closest("[data-drop-folder]") : null);
    const folderOf = (el: Element | null) => {
      const value = el?.getAttribute("data-drop-folder");
      return value === undefined || value === null ? undefined : value === "root" ? null : value;
    };
    const hasFiles = (event: DragEvent) => [...(event.dataTransfer?.types ?? [])].includes("Files");
    const isInternal = (event: DragEvent) => { const types = [...(event.dataTransfer?.types ?? [])]; return types.includes(DRAG_PLAN) || types.includes(DRAG_FOLDER); };
    const reset = () => { mark(null); setOver(undefined); };

    const onOver = (event: DragEvent) => {
      if (!hasFiles(event) && !isInternal(event)) return;
      const el = targetOf(event);
      if (isInternal(event)) {
        if (!el) { mark(null); return; }
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
        mark(el);
        return;
      }
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      mark(el);
      const folder = folderOf(el);
      setOver(folder === undefined ? currentFolder() : folder);
    };
    const onLeave = (event: DragEvent) => {
      if (event.relatedTarget === null || event.clientX <= 0 || event.clientY <= 0 || event.clientX >= innerWidth || event.clientY >= innerHeight) reset();
    };
    const onDrop = (event: DragEvent) => {
      const el = targetOf(event);
      const folder = folderOf(el);
      if (isInternal(event)) {
        event.preventDefault();
        const planId = event.dataTransfer?.getData(DRAG_PLAN);
        const folderId = event.dataTransfer?.getData(DRAG_FOLDER);
        const destination = folder === undefined ? undefined : folder;
        if (destination !== undefined) {
          const w = wsRef.current;
          const name = destination ? w.folders.find((item) => item.id === destination)?.name ?? "" : COPY.folders.root;
          if (planId) { w.movePlan(planId, destination); w.toast(COPY.folders.moved(w.plans.find((item) => item.id === planId)?.name ?? "", name)); }
          else if (folderId && folderId !== destination) {
            if (w.moveFolder(folderId, destination)) w.toast(COPY.folders.moved(w.folders.find((item) => item.id === folderId)?.name ?? "", name));
            else w.toast(COPY.folders.cycle, { tone: "error" });
          }
        }
        reset();
        return;
      }
      if (!hasFiles(event)) return;
      event.preventDefault();
      const files = [...(event.dataTransfer?.files ?? [])];
      if (files.length) wsRef.current.addFiles(files, folder === undefined ? currentFolder() : folder);
      reset();
    };
    addEventListener("dragover", onOver);
    addEventListener("dragleave", onLeave);
    addEventListener("drop", onDrop);
    addEventListener("dragend", reset);
    return () => {
      removeEventListener("dragover", onOver);
      removeEventListener("dragleave", onLeave);
      removeEventListener("drop", onDrop);
      removeEventListener("dragend", reset);
    };
  }, []);

  if (over === undefined) return null;
  const name = over ? ws.folders.find((item) => item.id === over)?.name ?? COPY.folders.root : COPY.folders.root;
  return (
    <div className="pointer-events-none fixed inset-0 z-[55] border-[3px] border-dashed border-ink" aria-hidden="true" data-testid="drop-overlay">
      <div className="absolute bottom-s5 left-1/2 flex w-max max-w-[calc(100vw-40px)] -translate-x-1/2 flex-col items-center gap-s1 border border-ink bg-ink px-s5 py-s3 text-center text-surface">
        <span className="text-md font-semibold">{COPY.home.dropTitle(name)}</span>
        <span className="text-sm text-surface/80">{COPY.home.dropHint}</span>
      </div>
    </div>
  );
}

const typing = (target: EventTarget | null) => {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
};

/** Atajos globales: / buscar, ? atajos, 1 a 6 pantallas del plano. Los del lienzo viven en DrawingCanvas. */
function useShortcuts() {
  const { route, navigate } = useRouter();
  const ws = useWorkspace();
  const { planId: loadedId } = useStore();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) return;
      if (document.querySelector("[aria-modal=true]")) return;
      if (event.key === "?") { event.preventDefault(); dispatchEvent(new CustomEvent("vx-shortcuts")); return; }
      if (event.key === "/") {
        event.preventDefault();
        if (route.kind !== "home") navigate({ kind: "home", folderId: null });
        setTimeout(() => dispatchEvent(new CustomEvent("vx-focus-search")), 30);
        return;
      }
      if (route.kind === "plan" && /^[1-4]$/.test(event.key)) {
        const plan = ws.plans.find((item) => item.id === route.planId);
        const target = VIEWS[Number(event.key) - 1];
        if (enabledScreens(plan, loadedId === route.planId, ws.live[route.planId]?.origin).has(target)) { event.preventDefault(); navigate({ kind: "plan", planId: route.planId, screen: target }); }
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [route, navigate, ws.plans, ws.live, loadedId]);
}

function ShortcutsDialog() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const toggle = () => setOpen((value) => !value);
    addEventListener("vx-shortcuts", toggle);
    return () => removeEventListener("vx-shortcuts", toggle);
  }, []);
  if (!open) return null;
  const S = COPY.shortcuts.items;
  const groups: { title: string; rows: [string[], string][] }[] = [
    { title: COPY.shortcuts.groups.general, rows: [[["/"], S.search], [["?"], S.help], [["Esc"], S.escape], [["1", "4"], S.screens]] },
    { title: COPY.shortcuts.groups.plan, rows: [[["M"], S.measure], [["F"], S.fit], [["+", "−"], S.zoom], [["↑", "↓"], S.rows]] },
  ];
  return (
    <Modal title={COPY.shortcuts.title} onClose={() => setOpen(false)} footer={<button className="btn btn-sm" onClick={() => setOpen(false)}>{COPY.queue.close}</button>}>
      {groups.map((group) => (
        <section key={group.title} className="flex flex-col gap-s1">
          <h3 className="eyebrow">{group.title}</h3>
          <dl className="divide-y divide-line border-y border-line">
            {group.rows.map(([keys, label]) => (
              <div key={label} className="flex items-center justify-between gap-s3 py-s2">
                <dt className="text-base text-ink">{label}</dt>
                <dd className="flex items-center gap-s1">
                  {keys.map((key, index) => (
                    <span key={key} className="flex items-center gap-s1">
                      {index > 0 && <span className="text-sm text-muted">{keys.length === 2 && key === "4" ? "a" : "·"}</span>}
                      <kbd className="inline-flex h-7 min-w-[28px] items-center justify-center border border-line-strong bg-bg px-s2 font-mono text-2xs text-ink">{key}</kbd>
                    </span>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </Modal>
  );
}

/**
 * Solo para capturas locales en modo mock: ?auto=principal&mode=live&review=18&sel=K3&go=plano.
 * Abre el plano sembrado de ese ejemplo y recorre el flujo con los mismos actos que una persona.
 * En el Artifact publicado no hay query string y no se activa.
 */
function useCaptureAutopilot() {
  const ws = useWorkspace();
  const store = useStore();
  const { navigate } = useRouter();
  const params = useRef(new URLSearchParams(location.search));
  const stage = useRef(0);
  const target = useRef<string | null>(null);
  useEffect(() => {
    const p = params.current;
    if (!AUTOPILOT || !ws.ready || !store.config) return;
    const sample = MOCK_SAMPLES.find((item) => item.fixture === p.get("auto")) ?? MOCK_SAMPLES[0];
    const go = (p.get("go") === "carga" ? "analisis" : p.get("go")) as Screen | null;
    if (stage.current === 0) {
      const seeded = ws.plans.find((plan) => plan.asset === sample.filename && plan.source === "sample");
      if (!seeded) return;
      stage.current = 1;
      if (p.get("mode") === "live") {
        sampleFile(sample.filename).then((file) => {
          if (!file) return;
          const [id] = ws.addFiles([file], seeded.folderId, "live");
          target.current = id;
          navigate({ kind: "plan", planId: id, screen: go === "analisis" ? "analisis" : "analisis" });
          if (go === "analisis") stage.current = 9;
        });
        return;
      }
      target.current = seeded.id;
      if (seeded.status !== "analyzing") navigate({ kind: "plan", planId: seeded.id, screen: "plano" });
      return;
    }
    const plan = ws.plans.find((item) => item.id === target.current);
    if (stage.current === 1 && plan && plan.status !== "analyzing" && store.planId !== plan.id) {
      navigate({ kind: "plan", planId: plan.id, screen: "plano" });
      return;
    }
    if (stage.current === 1 && plan && store.planId === plan.id && store.current && store.run) {
      stage.current = 2;
      const finish = () => {
        stage.current = 3;
        const key = p.get("sel");
        if (key && store.current) {
          const row = buildRows(store.current, pickCandidate(store.current, store.run)).find((item) => item.key === key && (!p.get("role") || item.use?.role === p.get("role")));
          if (row) store.select(row.id);
        }
        if (go) navigate({ kind: "plan", planId: plan.id, screen: go });
      };
      const reviewWanted = p.get("review");
      if (reviewWanted) {
        const result = store.current;
        const candidate = result.assembly_candidates[0];
        const observations = new Map((result.part_analysis?.observations ?? []).map((item) => [item.id, item]));
        const decisions = candidate.uses
          .filter((use) => observations.get(use.part_observation_id)?.dimensions.thickness.state !== "observed")
          .map((use) => ({ proposal_id: use.id, action: "confirm" as const, role: use.role, thickness_mm: Number(reviewWanted === "19" ? 19 : 18), notes: "Grosor confirmado con compras" }));
        const request = { base_result_revision: result.result_revision, reviewer_name: "L. Ferrer", assembly_candidate_id: candidate.id, decisions, notes: "Montaje entre laterales revisado", material: "tablero sintético", finish: "melamina sintética" };
        const runId = store.run.id;
        api.createReview(runId, request)
          .then((next) => { store.addRevision(next, request); })
          .then(() => (p.get("estimate") ? api.createEstimate(runId, { result_revision: result.result_revision + 1 }) : null))
          .then(() => (p.get("save") ? api.saveToLibrary(runId, { result_revision: result.result_revision + 1, label: "Estantería E-900 cuatro baldas", embedding_mode: "offline" }) : null))
          .then(() => setTimeout(finish, 50));
      } else finish();
    }
    if (stage.current === 3 && p.get("sel") && store.current && !store.selectedRowId) {
      const row = buildRows(store.current, pickCandidate(store.current, store.run)).find((item) => item.key === p.get("sel"));
      if (row) store.select(row.id);
    }
  });
}
