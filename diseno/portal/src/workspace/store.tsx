/**
 * Espacio de trabajo: carpetas, planos, cola de subida y apertura de análisis.
 *
 * Usa solo la interfaz VexplorerApi, así que funciona igual con el mock que con el backend real.
 * Cada plano tiene su propio id; el documento y el análisis del servidor se guardan como referencia.
 * Abrir un plano pasa siempre por `ensureRun`: si el servidor conserva el análisis lo lee, y si no
 * (404, o el mock ha reutilizado su id para otro plano) vuelve a subir el DXF guardado, lo analiza y
 * repite las revisiones que se enviaron, en el mismo orden.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "../api";
import { MOCK_SAMPLES } from "../api/mock";
import libraryDrawingsRaw from "../api/fixtures/library_drawings.json";
import type { DrawingExtraction, LibraryItem, Result, ReviewRequest, RunEvent, RunMode, RunSnapshot } from "../api/types";
import { COPY } from "../copy";
import { useRouter } from "../router";
import { openWorkspaceDb, type WorkspaceDb } from "./db";
import { abrirRun, analizarPlano, CASOS, cargarCaso, runDeCaso, RUNS_DEMO, type CasoMeta, type MesaTrabajo } from "../general";
import { analizarMesa, sha256Hex } from "../general/vivo";
import { GENERALES_GUARDADOS, RECONSTRUCCIONES_PNG } from "../casos";
import { cargarRaro, indiceRaros, PREFIJO_RARO } from "../casos/raros";
import { miniaturaMontaje } from "../general/miniatura";
import { generalApi } from "../api";
import { recordarMesa } from "../portal/mesa";
import { PROCESSED_FOLDER, sampleFile, SEED_FOLDERS, SEED_PLANS } from "./samples";
import type { Folder, LiveAnalysis, PlanRecord, PlanStatus, RunSnapshotBundle, ThumbContour, WorkspaceData } from "./types";

export interface Toast { id: number; message: string; tone: "info" | "error"; action?: { label: string; run: () => void } }

export type Opened =
  | { kind: "run"; bundle: RunSnapshotBundle }
  | { kind: "library"; item: LibraryItem; drawing: DrawingExtraction };

interface Workspace {
  ready: boolean;
  persistent: boolean;
  folders: Folder[];
  plans: PlanRecord[];
  live: Record<string, LiveAnalysis>;
  /** Planos subidos por el usuario en esta sesión, en el orden del panel de subidas. */
  uploads: string[];
  toasts: Toast[];
  mode: RunMode;
  setMode(mode: RunMode): void;
  /** Qué vía usan las subidas: piezas separadas (por defecto) o mueble general (solo con el backend real). */
  uploadKind: "parts" | "general" | "mesa";
  setUploadKind(kind: "parts" | "general" | "mesa"): void;
  /** Cambia cuando un análisis del servidor pasa a pertenecer a otro plano (ids compartidos del mock). */
  ownersTick: number;
  ownerOf(runId: string): string | undefined;
  createFolder(name: string, parentId: string | null): string;
  renameFolder(id: string, name: string): void;
  moveFolder(id: string, parentId: string | null): boolean;
  deleteFolder(id: string): void;
  renamePlan(id: string, name: string): void;
  movePlan(id: string, folderId: string | null): void;
  deletePlan(id: string): void;
  addFiles(files: File[], folderId: string | null, mode?: RunMode): string[];
  retry(planId: string): void;
  ensureRun(planId: string): Promise<Opened>;
  recordRevision(planId: string, result: Result, request?: ReviewRequest): void;
  downloadDxf(planId: string): Promise<boolean>;
  toast(message: string, options?: { tone?: Toast["tone"]; action?: Toast["action"] }): void;
  dismissToast(id: number): void;
  clearUploads(): void;
  folderPath(folderId: string | null): Folder[];
  descendants(folderId: string): Set<string>;
}

const Ctx = createContext<Workspace | null>(null);
const CONCURRENCY = 2;
const EMPTY: WorkspaceData = { version: 1, folders: [], plans: [], seeded: false };
const libraryDrawings = libraryDrawingsRaw as unknown as Record<string, { filename: string }>;

const newId = (prefix: string) => {
  try { return `${prefix}-${crypto.randomUUID()}`; } catch { return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`; }
};

export function thumbOf(drawing: DrawingExtraction): ThumbContour[] {
  const mm = drawing.coordinate_unit === "mm";
  return drawing.contours.map((c) => ({ id: c.id, points: (mm ? c.points_mm : null) ?? c.points_source, closed: c.closed }));
}

/** Estado del plano a partir de la respuesta del servidor: Completo solo llega tras una revisión de persona. */
export function statusOf(run: RunSnapshot | null, result: Result | null): PlanStatus {
  if (run && (run.state === "failed" || run.state === "cancelled" || run.state === "timed_out")) return "error";
  return result?.state === "completed" ? "reviewed" : "needs_review";
}

function libraryStatus(item: LibraryItem): PlanStatus {
  return item.descriptor.classification_status === "confirmed" && item.descriptor.unknown_fields.length === 0 ? "reviewed" : "needs_review";
}

type SaveOutcome = "saved" | "declined" | "rejected" | "unavailable";
interface DownloadsHost { use(name: "downloads"): Promise<{ save(request: { filename: string; data: Blob }): Promise<unknown> } | null> }

/**
 * Entrega un archivo al usuario. Dentro del visor de Artifacts el marco no puede descargar por su cuenta y pasa por la
 * capacidad `downloads`, que pide confirmación y solo admite ciertas extensiones; fuera, un enlace con el blob.
 */
export async function saveFile(file: Blob, filename: string): Promise<SaveOutcome> {
  const host = (window as unknown as { claude?: DownloadsHost }).claude;
  if (host && typeof host.use === "function") {
    try {
      const downloads = await host.use("downloads");
      if (!downloads) return "unavailable";
      await downloads.save({ filename, data: file });
      return "saved";
    } catch (error) {
      const code = (error as { code?: string } | null)?.code;
      if (code === "declined") return "declined";
      if (code === "rejected_extension" || code === "extension_not_enabled") return "rejected";
      return "unavailable";
    }
  }
  const url = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  return "saved";
}

const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404;
const errorOf = (error: unknown) =>
  error instanceof ApiError
    ? { message: error.message, code: error.code, status: error.status, retryable: error.retryable }
    : { message: error instanceof Error ? error.message : String(error), code: "unexpected", status: 0, retryable: true };

function readMode(): RunMode {
  try {
    const value = localStorage.getItem("vx-mode");
    if (value === "live" || value === "geometry_only") return value;
  } catch { /* sin almacenamiento */ }
  return "geometry_only";
}

interface Job { planId: string; file: File; mode: RunMode; origin: LiveAnalysis["origin"]; stream: boolean }

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<WorkspaceData>(EMPTY);
  const [ready, setReady] = useState(false);
  const [persistent, setPersistent] = useState(true);
  const [live, setLive] = useState<Record<string, LiveAnalysis>>({});
  const [uploads, setUploads] = useState<string[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [mode, setModeState] = useState<RunMode>(readMode);
  const [uploadKind, setUploadKindState] = useState<"parts" | "general" | "mesa">(() => {
    try {
      const saved = localStorage.getItem("vx-upload-kind");
      return !api.isMock && (saved === "general" || saved === "mesa") ? saved : "parts";
    } catch { return "parts"; }
  });
  const [ownersTick, setOwnersTick] = useState(0);
  const db = useRef<WorkspaceDb | null>(null);
  const dataRef = useRef(data);
  dataRef.current = data;
  const owners = useRef(new Map<string, string>());
  const queue = useRef<Job[]>([]);
  const active = useRef(0);
  const ensuring = useRef(new Map<string, Promise<Opened>>());
  const toastId = useRef(0);
  const started = useRef(false);
  const { navigate } = useRouter();

  const setOwner = useCallback((runId: string, planId: string) => {
    if (owners.current.get(runId) === planId) return;
    owners.current.set(runId, planId);
    setOwnersTick((value) => value + 1);
  }, []);

  const update = useCallback((fn: (prev: WorkspaceData) => WorkspaceData) => {
    setData((prev) => {
      const next = fn(prev);
      dataRef.current = next;
      return next;
    });
  }, []);
  const patchPlan = useCallback((id: string, patch: Partial<PlanRecord> | ((plan: PlanRecord) => Partial<PlanRecord>)) => {
    update((prev) => ({ ...prev, plans: prev.plans.map((plan) => (plan.id === id ? { ...plan, ...(typeof patch === "function" ? patch(plan) : patch) } : plan)) }));
  }, [update]);
  const patchLive = useCallback((planId: string, patch: Partial<LiveAnalysis>) => {
    setLive((prev) => (prev[planId] ? { ...prev, [planId]: { ...prev[planId], ...patch } } : prev));
  }, []);

  const dismissToast = useCallback((id: number) => setToasts((list) => list.filter((item) => item.id !== id)), []);
  const toast = useCallback<Workspace["toast"]>((message, options) => {
    const id = ++toastId.current;
    setToasts((list) => [...list.slice(-2), { id, message, tone: options?.tone ?? "info", action: options?.action }]);
    setTimeout(() => dismissToast(id), options?.action ? 7000 : 4500);
  }, [dismissToast]);

  const fileFor = useCallback(async (plan: PlanRecord): Promise<File | null> => {
    if (plan.source === "upload" || plan.source === "general") {
      const blob = await db.current?.getFile(plan.id).catch(() => null);
      return blob ? new File([blob], plan.filename, { type: blob.type || "application/dxf" }) : null;
    }
    return plan.asset ? sampleFile(plan.asset) : null;
  }, []);

  /** Sube, lee el plano, analiza y (si se pide) lee la traza. Actualiza el estado en vivo en cada paso. */
  const runAnalysis = useCallback(async (job: Job) => {
    const { planId, file, mode: runMode, origin, stream } = job;
    setLive((prev) => ({ ...prev, [planId]: { planId, stage: "uploading", origin, document: null, run: null, result: null, drawing: null, events: [], error: null, startedAt: Date.now() } }));
    patchPlan(planId, { status: "analyzing", error: null });
    try {
      const document = await api.uploadDocument(file);
      patchLive(planId, { document, stage: "reading" });
      patchPlan(planId, { documentId: document.document_id, sizeBytes: document.size_bytes });
      // La geometría del documento llega antes que el análisis: la pantalla de análisis la va dibujando.
      try {
        const preview = await api.getDocumentDrawing(document.document_id, "separated_part_views");
        patchLive(planId, { drawing: preview });
        patchPlan(planId, { thumb: thumbOf(preview) });
      } catch { /* sin vista previa: el plano llega con el análisis */ }
      patchLive(planId, { stage: "running" });
      const created = await api.createRun({ document_id: document.document_id, mode: runMode, input_kind: "separated_part_views" });
      setOwner(created.run.id, planId);
      patchLive(planId, { run: created.run, result: created.result, stage: "tracing" });
      patchPlan(planId, origin === "sync"
        ? { runId: created.run.id, revision: created.result.result_revision }
        : { runId: created.run.id, revision: created.result.result_revision, mode: runMode, reviews: [] });
      const seen = new Set<number>();
      const append = (event: RunEvent) => {
        if (seen.has(event.sequence)) return;
        seen.add(event.sequence);
        setLive((prev) => (prev[planId] ? { ...prev, [planId]: { ...prev[planId], events: [...prev[planId].events, event] } } : prev));
      };
      const [drawing] = await Promise.all([api.getDrawing(created.run.id), stream ? api.streamEvents(created.run.id, append) : Promise.resolve()]);
      patchLive(planId, { drawing, stage: "done" });
      const status = statusOf(created.run, created.result);
      patchPlan(planId, { status, thumb: thumbOf(drawing), updatedAt: new Date().toISOString() });
      return { document, run: created.run, result: created.result, drawing };
    } catch (error) {
      const info = errorOf(error);
      patchLive(planId, { stage: "error", error: info });
      patchPlan(planId, { status: "error", error: { message: info.message, code: info.code }, updatedAt: new Date().toISOString() });
      throw error;
    }
  }, [patchLive, patchPlan, setOwner]);

  const pump = useCallback(() => {
    while (active.current < CONCURRENCY && queue.current.length) {
      const job = queue.current.shift()!;
      active.current += 1;
      runAnalysis(job)
        .then((outcome) => {
          if (job.origin !== "user") return;
          const plan = dataRef.current.plans.find((item) => item.id === job.planId);
          if (!plan) return;
          toast(COPY.toasts.analyzed(plan.name, COPY.status[statusOf(outcome.run, outcome.result)]), {
            action: { label: COPY.toasts.open, run: () => navigate({ kind: "plan", planId: plan.id, screen: "plano" }) },
          });
        })
        .catch(() => {
          if (job.origin !== "user") return;
          const plan = dataRef.current.plans.find((item) => item.id === job.planId);
          if (plan) toast(COPY.toasts.failed(plan.name), { tone: "error" });
        })
        .finally(() => { active.current -= 1; pump(); });
    }
  }, [runAnalysis, toast, navigate]);

  const enqueue = useCallback((job: Job) => {
    queue.current.push(job);
    setLive((prev) => ({ ...prev, [job.planId]: { planId: job.planId, stage: "queued", origin: job.origin, document: null, run: null, result: null, drawing: null, events: [], error: null, startedAt: Date.now() } }));
    pump();
  }, [pump]);

  // ---- Arranque: abrir almacenamiento, cargar o sembrar ----
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      const store = await openWorkspaceDb();
      db.current = store;
      let loaded = await store.load();
      setPersistent(store.persistent);
      const pending: Job[] = [];
      const resumeGeneral: { plan: PlanRecord; file: File }[] = [];
      if (!loaded || loaded.version !== 1) {
        loaded = api.isMock ? await seed() : { ...EMPTY, seeded: true };
        for (const plan of loaded.plans) {
          if (plan.source !== "sample" || !plan.asset) continue;
          const file = await sampleFile(plan.asset);
          if (file) pending.push({ planId: plan.id, file, mode: "geometry_only", origin: "seed", stream: false });
        }
      } else {
        // Análisis interrumpidos por una recarga: se repiten con el archivo guardado.
        for (const plan of loaded.plans.filter((item) => item.status === "analyzing")) {
          const file = await (plan.source === "upload" || plan.source === "general" ? store.getFile(plan.id).then((blob) => (blob ? new File([blob], plan.filename) : null)).catch(() => null) : plan.asset ? sampleFile(plan.asset) : Promise.resolve(null));
          if (file && plan.source === "general") resumeGeneral.push({ plan, file });
          else if (file) pending.push({ planId: plan.id, file, mode: plan.mode, origin: "sync", stream: false });
          else {
            plan.status = "error";
            plan.error = { message: COPY.workspace2.fileMissing, code: "file_missing" };
          }
        }
      }
      dataRef.current = loaded;
      setData(loaded);
      setReady(true);
      setPersistent(store.persistent);
      pending.forEach(enqueue);
      resumeGeneral.forEach(({ plan, file }) => runGeneral(plan, file));
      seedCasos();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Guardado ----
  useEffect(() => {
    if (!ready || !db.current) return;
    const id = setTimeout(() => {
      db.current?.save(dataRef.current).then(() => setPersistent(Boolean(db.current?.persistent)));
    }, 120);
    return () => clearTimeout(id);
  }, [data, ready]);

  const descendants = useCallback((folderId: string) => {
    const out = new Set<string>([folderId]);
    let grew = true;
    while (grew) {
      grew = false;
      for (const folder of dataRef.current.folders) if (folder.parentId && out.has(folder.parentId) && !out.has(folder.id)) { out.add(folder.id); grew = true; }
    }
    return out;
  }, []);

  const folderPath = useCallback((folderId: string | null) => {
    const path: Folder[] = [];
    let cursor = folderId;
    const guard = new Set<string>();
    while (cursor && !guard.has(cursor)) {
      guard.add(cursor);
      const folder = dataRef.current.folders.find((item) => item.id === cursor);
      if (!folder) break;
      path.unshift(folder);
      cursor = folder.parentId;
    }
    return path;
  }, []);

  const ensureRun = useCallback((planId: string): Promise<Opened> => {
    const pendingOpen = ensuring.current.get(planId);
    if (pendingOpen) return pendingOpen;
    const task = (async (): Promise<Opened> => {
      const plan = dataRef.current.plans.find((item) => item.id === planId);
      if (!plan) throw new ApiError(COPY.workspace2.planMissing, 404, "plan_not_found");
      const owner = plan.runId ? owners.current.get(plan.runId) : undefined;
      if (plan.runId && (owner === planId || owner === undefined)) {
        try {
          const [detail, revisions, drawing] = await Promise.all([api.getRun(plan.runId), api.getRevisions(plan.runId), api.getDrawing(plan.runId)]);
          setOwner(plan.runId, planId);
          const current = revisions[revisions.length - 1] ?? detail.result;
          patchPlan(planId, { status: statusOf(detail.run, current), revision: current.result_revision, thumb: plan.thumb ?? thumbOf(drawing) });
          return { kind: "run", bundle: { planId, document: null, run: detail.run, revisions: revisions.length ? revisions : [detail.result], drawing } };
        } catch (error) {
          if (!isNotFound(error)) throw error;
        }
      }
      if (plan.source === "library" && plan.runId) {
        // El análisis existe solo en la biblioteca del servidor: se abre su ficha y su plano.
        const [library, drawing] = await Promise.all([api.getLibrary(), api.getDrawing(plan.runId)]);
        const item = library.find((entry) => entry.id === plan.libraryItemId || entry.run_id === plan.runId);
        if (!item) throw new ApiError(COPY.workspace2.libraryMissing, 404, "library_item_not_found");
        return { kind: "library", item, drawing };
      }
      const file = await fileFor(plan);
      if (!file) throw new ApiError(COPY.workspace2.fileMissing, 404, "file_missing");
      const outcome = await runAnalysis({ planId, file, mode: plan.mode, origin: "sync", stream: false });
      const revisions: Result[] = [outcome.result];
      const replayed: ReviewRequest[] = [];
      for (const request of plan.reviews) {
        try {
          const next = await api.createReview(outcome.run.id, { ...request, base_result_revision: revisions[revisions.length - 1].result_revision });
          revisions.push(next);
          replayed.push(request);
        } catch {
          break;
        }
      }
      const current = revisions[revisions.length - 1];
      patchPlan(planId, { reviews: replayed, revision: current.result_revision, status: statusOf(outcome.run, current) });
      return { kind: "run", bundle: { planId, document: outcome.document, run: { ...outcome.run, result_revision: current.result_revision }, revisions, drawing: outcome.drawing } };
    })();
    ensuring.current.set(planId, task);
    task.finally(() => ensuring.current.delete(planId)).catch(() => undefined);
    return task;
  }, [fileFor, patchPlan, runAnalysis, setOwner]);

  /**
   * Carpeta «Muebles procesados» con los casos de src/casos: arriba los que tienen montaje 3D, con la miniatura del
   * montaje, y en la subcarpeta «Sin montaje» el resto, con la del plano. En mock y en real.
   * Cada versión de la siembra añade los casos que falten y recoloca los ya sembrados; sustituye a «Demo procesada».
   * La fecha de cada caso respeta el orden de CASOS para que la ordenación por fecha lo conserve.
   */
  async function seedCasos() {
    const key = "vx-muebles-procesados-5";
    try { if (localStorage.getItem(key) === "1") return; } catch { /* sin almacenamiento: se intenta igual */ }
    const loaded = (await Promise.all(CASOS.map(async (meta) => {
      try { return { meta, mesa: await cargarCaso(meta.id) }; } catch { return null; }
    }))).filter((item): item is NonNullable<typeof item> => item !== null);
    if (!loaded.length) return;
    // Raros de PlankAssembly sin procesar: solo si existen en public/local (uso local).
    const raros = (await Promise.all((await indiceRaros()).map(async (meta) => {
      try { return { meta, mesa: await cargarRaro(meta.id, meta.titulo) }; } catch { return null; }
    }))).filter((item): item is NonNullable<typeof item> => item !== null);
    const demoRuns = new Set(RUNS_DEMO.map((item) => item.runId));
    const base = Date.now();
    const thumbOfMesa = (meta: CasoMeta, mesa: MesaTrabajo): ThumbContour[] | null => {
      const montaje = meta.montaje ? miniaturaMontaje(mesa.escena, mesa.via === "general" || mesa.via === "reconstruccion" ? 1 : -1) : [];
      if (montaje.length) return montaje;
      return mesa.plano ? mesa.plano.contornos.map((c) => ({ id: c.id, points: c.puntos.map(([x, y]) => ({ x, y })), closed: c.cerrado })) : null;
    };
    update((prev) => {
      const plans = prev.plans.filter((plan) => !(plan.source === "server" && plan.runId && demoRuns.has(plan.runId)));
      const old = prev.folders.find((folder) => folder.name === PROCESSED_FOLDER && folder.parentId === null);
      const keepOld = old && plans.some((plan) => plan.folderId === old.id);
      const existing = prev.folders.find((folder) => folder.name === COPY.portal.general.folder && folder.parentId === null);
      const mainId = existing?.id ?? newId("folder");
      const existingSub = prev.folders.find((folder) => folder.name === COPY.portal.general.subfolderNoAssembly && folder.parentId === mainId);
      const subId = existingSub?.id ?? newId("folder");
      const existingRaw = prev.folders.find((folder) => folder.name === COPY.portal.general.subfolderRaw && folder.parentId === mainId);
      const rawId = existingRaw?.id ?? newId("folder");
      const folders = [
        ...prev.folders.filter((folder) => folder !== old || keepOld),
        ...(existing ? [] : [{ id: mainId, name: COPY.portal.general.folder, parentId: null, createdAt: new Date(base).toISOString() }]),
        ...(existingSub ? [] : [{ id: subId, name: COPY.portal.general.subfolderNoAssembly, parentId: mainId, createdAt: new Date(base).toISOString() }]),
        // «Sin procesar» va la última: fecha más antigua que «Sin montaje».
        ...(existingRaw || !raros.length ? [] : [{ id: rawId, name: COPY.portal.general.subfolderRaw, parentId: mainId, createdAt: new Date(base - 1000).toISOString() }]),
      ];
      const byCase = new Map(loaded.map((item) => [item.meta.id as string, item]));
      // Los casos ya sembrados se recolocan y estrenan miniatura; el resto de planos no se toca.
      const kept = plans.map((plan) => {
        const item = plan.source === "caso" && plan.asset ? byCase.get(plan.asset) : undefined;
        if (!item) return plan;
        const when = new Date(base - CASOS.indexOf(item.meta) * 60_000).toISOString();
        return { ...plan, name: item.meta.titulo, folderId: item.meta.montaje || item.meta.principal ? mainId : subId, thumb: thumbOfMesa(item.meta, item.mesa), createdAt: when, updatedAt: when };
      });
      const added = loaded.filter(({ meta }) => !kept.some((plan) => plan.source === "caso" && plan.asset === meta.id)).map(({ meta, mesa }): PlanRecord => {
        const when = new Date(base - CASOS.indexOf(meta) * 60_000).toISOString();
        return {
          id: newId("plan"), name: meta.titulo, filename: meta.titulo, folderId: meta.montaje || meta.principal ? mainId : subId, createdAt: when, updatedAt: when,
          status: mesa.estado === "listo" ? "reviewed" : "needs_review", revision: null, mode: meta.conModelo ? "live" : "geometry_only",
          inputKind: meta.via === "general" ? "general_furniture" : "mounted_views_legacy", documentId: null,
          runId: runDeCaso(meta.id)?.runId ?? null, source: "caso", asset: meta.id, sizeBytes: 0,
          thumb: thumbOfMesa(meta, mesa), error: null, reviews: [],
        };
      });
      const rawAdded = raros.filter(({ meta }) => !kept.some((plan) => plan.asset === `${PREFIJO_RARO}${meta.id}`)).map(({ meta, mesa }, i): PlanRecord => {
        const when = new Date(base - (CASOS.length + i) * 60_000).toISOString();
        return {
          id: newId("plan"), name: meta.titulo, filename: `${meta.id}.dxf`, folderId: rawId, createdAt: when, updatedAt: when,
          status: "needs_review", revision: null, mode: "geometry_only", inputKind: "general_furniture", documentId: null, runId: null,
          source: "caso", asset: `${PREFIJO_RARO}${meta.id}`, sizeBytes: 0,
          thumb: mesa.plano ? mesa.plano.contornos.map((c) => ({ id: c.id, points: c.puntos.map(([x, y]) => ({ x, y })), closed: c.cerrado })) : null,
          error: null, reviews: [],
        };
      });
      return { ...prev, folders, plans: [...kept, ...added, ...rawAdded] };
    });
    try { localStorage.setItem(key, "1"); } catch { /* sin almacenamiento */ }
  }


  /**
   * Subidas por la mesa de trabajo (solo modo real), con su proceso en vivo:
   * - mesa: plantilla de catálogo sin modelo, láminas de la revisión 1; la aceptación es una acción de la persona.
   * - general: lectura del plano en geometry_only; si el DXF coincide por SHA-256 con un mueble general guardado,
   *   la propuesta, la revisión, el montaje y las salidas salen de esa ejecución guardada (flujo "guardado").
   * El plano se abre en cuanto empieza la subida y enseña cada paso según llega (live[plan].stage).
   */
  function runGeneral(plan: PlanRecord, file: File) {
    setLive((prev) => ({ ...prev, [plan.id]: { planId: plan.id, stage: "uploading", origin: "user", document: null, run: null, result: null, drawing: null, events: [], error: null, startedAt: Date.now() } }));
    patchPlan(plan.id, { status: "analyzing", error: null });
    const fail = (message: string, code: string) => {
      patchLive(plan.id, { stage: "error", error: { message, code, status: 0, retryable: true } });
      patchPlan(plan.id, { status: "error", error: { message, code }, updatedAt: new Date().toISOString() });
      toast(COPY.toasts.failed(plan.name), { tone: "error" });
    };
    const stage = (fase: "subiendo" | "analizando" | "salidas" | "hecho") =>
      patchLive(plan.id, { stage: fase === "subiendo" ? "uploading" : fase === "analizando" ? "running" : fase === "salidas" ? "tracing" : "done" });
    const finish = (runId: string, mesa: MesaTrabajo) => {
      recordarMesa(plan.id, mesa);
      const status: PlanStatus = mesa.estado === "listo" ? "reviewed" : "needs_review";
      patchLive(plan.id, { stage: "done" });
      const montaje = miniaturaMontaje(mesa.escena, mesa.via === "general" ? 1 : -1);
      patchPlan(plan.id, {
        runId, status, updatedAt: new Date().toISOString(),
        thumb: montaje.length ? montaje : mesa.plano ? mesa.plano.contornos.map((c) => ({ id: c.id, points: c.puntos.map(([x, y]) => ({ x, y })), closed: c.cerrado })) : null,
      });
      try { sessionStorage.setItem(`vx-proceso-${plan.id}`, "1"); } catch { /* sin almacenamiento: el proceso se abre a mano */ }
      toast(COPY.toasts.analyzed(plan.name, COPY.status[status]), { action: { label: COPY.toasts.open, run: () => navigate({ kind: "plan", planId: plan.id, screen: "plano" }) } });
    };
    const onError = (error: unknown) => { const info = errorOf(error); fail(info.message, info.code); };
    (async () => {
      // La huella manda sobre el tipo de subida: un DXF ya procesado con modelo abre su resultado guardado.
      const caso = GENERALES_GUARDADOS[await sha256Hex(file).catch(() => "")];
      if (caso) {
        const meta = CASOS.find((item) => item.id === caso);
        patchPlan(plan.id, { source: "general", flujo: "guardado", casoGuardado: caso, inputKind: "general_furniture", name: meta?.titulo ?? plan.name });
        stage("analizando");
        if (api.isMock) { finish(`caso:${caso}`, await cargarCaso(caso)); return; }
        const outcome = await analizarPlano(generalApi, file, file.name, "geometry_only");
        const runId = outcome.job?.run_id ?? null;
        if (!runId) return fail(outcome.mensaje, outcome.job?.error?.code ?? "general_sin_analisis");
        finish(runId, await cargarCaso(caso));
        return;
      }
      if (plan.flujo === "mesa") {
        const { job, runId } = await analizarMesa(generalApi, file, file.name, stage);
        if (!runId) return fail(job.error?.message ?? COPY.errors.generic, job.error?.code ?? "mesa_sin_analisis");
        finish(runId, await abrirRun(generalApi, runId, { titulo: plan.name }));
        return;
      }
      stage("analizando");
      const outcome = await analizarPlano(generalApi, file, file.name, "geometry_only");
      const runId = outcome.job?.run_id ?? null;
      if (!outcome.mesa || !runId) return fail(outcome.mensaje, outcome.job?.error?.code ?? "general_sin_analisis");
      finish(runId, outcome.mesa);
    })().catch(onError);
  }

  function addGeneral(files: File[], folderId: string | null, flujo: "general" | "mesa"): string[] {
    const now = new Date().toISOString();
    const created: PlanRecord[] = files.map((file) => ({
      id: newId("plan"), name: file.name, filename: file.name, folderId, createdAt: now, updatedAt: now, status: "analyzing", revision: null,
      mode: "geometry_only", inputKind: flujo === "mesa" ? "mounted_orthographic_views" : "general_furniture", documentId: null, runId: null,
      source: "general", flujo, sizeBytes: file.size, thumb: null, error: null, reviews: [],
    }));
    update((prev) => ({ ...prev, plans: [...prev.plans, ...created] }));
    setUploads((list) => [...list, ...created.map((plan) => plan.id)]);
    created.forEach((plan, index) => { db.current?.putFile(plan.id, files[index]); runGeneral(plan, files[index]); });
    // Una sola subida: se abre su proceso según llega.
    if (created.length === 1) navigate({ kind: "plan", planId: created[0].id, screen: "plano" });
    return created.map((plan) => plan.id);
  }

  async function seed(): Promise<WorkspaceData> {
    const now = new Date().toISOString();
    const folders: Folder[] = SEED_FOLDERS.map((folder) => ({ id: newId("folder"), name: folder.name, parentId: null, createdAt: now }));
    const folderOf = (key: string) => folders[SEED_FOLDERS.findIndex((folder) => folder.key === key)].id;
    let library: LibraryItem[] = [];
    try { library = await api.getLibrary(); } catch { /* sin biblioteca no se siembran sus planos */ }
    const plans: PlanRecord[] = [];
    for (const entry of SEED_PLANS) {
      const base = {
        id: newId("plan"), name: entry.file, filename: entry.file, folderId: folderOf(entry.folder), createdAt: now, updatedAt: now,
        mode: "geometry_only" as RunMode, inputKind: "separated_part_views" as const, documentId: null, asset: entry.file, sizeBytes: 0,
        thumb: null, error: null, reviews: [],
      };
      if (MOCK_SAMPLES.some((sample) => sample.filename === entry.file)) {
        plans.push({ ...base, status: "analyzing", revision: null, runId: null, source: "sample" });
        continue;
      }
      const runId = Object.entries(libraryDrawings).find(([, value]) => value.filename === entry.file)?.[0];
      const item = library.find((value) => value.run_id === runId);
      if (!item) continue;
      let thumb: ThumbContour[] | null = null;
      try { thumb = thumbOf(await api.getDrawing(item.run_id)); } catch { /* miniatura vacía */ }
      plans.push({ ...base, status: libraryStatus(item), revision: item.result_revision, runId: item.run_id, source: "library", libraryItemId: item.id, createdAt: item.created_at, updatedAt: item.created_at, thumb });
    }
    return { version: 1, folders, plans, seeded: true };
  }

  const value = useMemo<Workspace>(() => ({
    ready, persistent, folders: data.folders, plans: data.plans, live, uploads, toasts, mode, ownersTick, uploadKind,
    setUploadKind: (next) => {
      setUploadKindState(next);
      try { localStorage.setItem("vx-upload-kind", next); } catch { /* sin almacenamiento */ }
    },
    ownerOf: (runId) => owners.current.get(runId),
    setMode: (next) => {
      setModeState(next);
      try { localStorage.setItem("vx-mode", next); } catch { /* sin almacenamiento */ }
    },
    createFolder: (name, parentId) => {
      const id = newId("folder");
      update((prev) => ({ ...prev, folders: [...prev.folders, { id, name: name.trim() || COPY.folders.untitled, parentId, createdAt: new Date().toISOString() }] }));
      return id;
    },
    renameFolder: (id, name) => {
      if (!name.trim()) return;
      update((prev) => ({ ...prev, folders: prev.folders.map((folder) => (folder.id === id ? { ...folder, name: name.trim() } : folder)) }));
    },
    moveFolder: (id, parentId) => {
      if (parentId && descendants(id).has(parentId)) return false;
      update((prev) => ({ ...prev, folders: prev.folders.map((folder) => (folder.id === id ? { ...folder, parentId } : folder)) }));
      return true;
    },
    deleteFolder: (id) => {
      const gone = descendants(id);
      const removed = dataRef.current.plans.filter((plan) => plan.folderId && gone.has(plan.folderId));
      removed.forEach((plan) => db.current?.deleteFile(plan.id));
      update((prev) => ({ ...prev, folders: prev.folders.filter((folder) => !gone.has(folder.id)), plans: prev.plans.filter((plan) => !(plan.folderId && gone.has(plan.folderId))) }));
    },
    renamePlan: (id, name) => { if (name.trim()) patchPlan(id, { name: name.trim() }); },
    movePlan: (id, folderId) => patchPlan(id, { folderId }),
    deletePlan: (id) => {
      db.current?.deleteFile(id);
      queue.current = queue.current.filter((job) => job.planId !== id);
      update((prev) => ({ ...prev, plans: prev.plans.filter((plan) => plan.id !== id) }));
      setUploads((list) => list.filter((item) => item !== id));
    },
    addFiles: (files, folderId, modeOverride) => {
      const esPng = (file: File) => /\.png$/i.test(file.name);
      if ((uploadKind === "general" || uploadKind === "mesa") && !api.isMock && !modeOverride && !files.some(esPng)) return addGeneral(files, folderId, uploadKind);
      const runMode = modeOverride ?? mode;
      const now = new Date().toISOString();
      const created: PlanRecord[] = files.map((file) => ({
        id: newId("plan"), name: file.name, filename: file.name, folderId, createdAt: now, updatedAt: now, status: "analyzing", revision: null,
        mode: runMode, inputKind: "separated_part_views", documentId: null, runId: null, source: "upload", sizeBytes: file.size, thumb: null, error: null, reviews: [],
      }));
      update((prev) => ({ ...prev, plans: [...prev.plans, ...created] }));
      setUploads((list) => [...list, ...created.map((plan) => plan.id)]);
      created.forEach((plan, index) => {
        const file = files[index];
        db.current?.putFile(plan.id, file);
        // Un DXF que coincide por SHA-256 con un mueble general guardado va a su resultado guardado, sea cual sea el tipo elegido.
        sha256Hex(file).catch(() => "").then((sha) => {
          const reconstruccion = RECONSTRUCCIONES_PNG[sha];
          if (reconstruccion) {
            // El PNG de un trabajo de Construcción 3D: se abre su caso con «Ver el proceso», sin duplicarlo.
            const existente = dataRef.current.plans.find((item) => item.source === "caso" && item.asset === reconstruccion);
            const meta = CASOS.find((item) => item.id === reconstruccion);
            if (existente) {
              db.current?.deleteFile(plan.id);
              update((prev) => ({ ...prev, plans: prev.plans.filter((item) => item.id !== plan.id) }));
              setUploads((list) => list.filter((item) => item !== plan.id));
            } else {
              patchPlan(plan.id, { source: "caso", asset: reconstruccion, name: meta?.titulo ?? plan.name, status: "needs_review", inputKind: "general_furniture" });
            }
            const destino = existente?.id ?? plan.id;
            try { sessionStorage.setItem(`vx-proceso-${destino}`, "1"); } catch { /* sin almacenamiento */ }
            navigate({ kind: "plan", planId: destino, screen: "esquema" });
            return;
          }
          if (GENERALES_GUARDADOS[sha]) runGeneral({ ...plan, source: "general", flujo: "guardado" }, file);
          else enqueue({ planId: plan.id, file, mode: runMode, origin: "user", stream: true });
        });
      });
      return created.map((plan) => plan.id);
    },
    retry: (planId) => {
      const plan = dataRef.current.plans.find((item) => item.id === planId);
      if (!plan) return;
      fileFor(plan).then((file) => {
        if (!file) { toast(COPY.workspace2.fileMissing, { tone: "error" }); return; }
        setUploads((list) => (list.includes(planId) ? list : [...list, planId]));
        if (plan.source === "general") runGeneral(plan, file);
        else enqueue({ planId, file, mode: plan.mode, origin: "user", stream: true });
      });
    },
    ensureRun,
    recordRevision: (planId, result, request) => {
      const plan = dataRef.current.plans.find((item) => item.id === planId);
      if (!plan) return;
      const isNew = result.result_revision !== plan.revision;
      patchPlan(planId, (prev) => ({
        revision: result.result_revision,
        status: result.state === "completed" ? "reviewed" : "needs_review",
        updatedAt: result.created_at,
        reviews: request ? [...prev.reviews, request] : prev.reviews,
      }));
      if (isNew && request) toast(COPY.toasts.reviewed(result.result_revision, plan.name));
    },
    downloadDxf: async (planId) => {
      const plan = dataRef.current.plans.find((item) => item.id === planId);
      if (!plan) return false;
      const file = await fileFor(plan);
      if (!file) { toast(COPY.cad.missing, { tone: "error" }); return false; }
      try {
        const outcome = await saveFile(file, plan.filename);
        if (outcome === "saved") toast(COPY.cad.downloaded(plan.filename));
        else if (outcome === "rejected") toast(COPY.cad.viewerRejects, { tone: "error" });
        else if (outcome === "unavailable") toast(COPY.cad.viewerUnavailable, { tone: "error" });
        return outcome === "saved";
      } catch {
        toast(COPY.cad.failed, { tone: "error" });
        return false;
      }
    },
    toast, dismissToast,
    clearUploads: () => setUploads((list) => list.filter((id) => {
      const stage = live[id]?.stage;
      return stage !== undefined && stage !== "done" && stage !== "error";
    })),
    folderPath, descendants,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [ready, persistent, data, live, uploads, toasts, mode, uploadKind, ownersTick, update, patchPlan, descendants, enqueue, fileFor, ensureRun, toast, dismissToast, folderPath]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspace() {
  const value = useContext(Ctx);
  if (!value) throw new Error("WorkspaceProvider ausente");
  return value;
}