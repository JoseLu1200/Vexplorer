import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "./api";
import type { AppConfig, DrawingExtraction, Result, ReviewRequest, RunSnapshot, UploadedDocument } from "./api/types";
import { useRouter, type Screen } from "./router";
import type { RunSnapshotBundle } from "./workspace/types";
import { useWorkspace } from "./workspace/store";

export type { Screen } from "./router";
export { SCREENS } from "./router";

export interface AppError { message: string; code: string; status: number; retryable: boolean }
export const toAppError = (error: unknown): AppError =>
  error instanceof ApiError
    ? { message: error.message, code: error.code, status: error.status, retryable: error.retryable }
    : { message: error instanceof Error ? error.message : String(error), code: "unexpected", status: 0, retryable: true };

type ReviewField = "quantity" | "length" | "width" | "thickness" | "material" | "finish";

/** Estado del plano abierto. Las pantallas de un plano leen de aquí; el espacio de trabajo decide qué análisis se carga. */
interface Store {
  config: AppConfig | null;
  configError: AppError | null;
  /** Plano cuyo análisis está cargado. */
  planId: string | null;
  document: UploadedDocument | null;
  run: RunSnapshot | null;
  revisions: Result[];
  current: Result | null;
  previous: Result | null;
  drawing: DrawingExtraction | null;
  selectedRowId: string | null;
  candidateId: string | null;
  screen: Screen;
  theme: "light" | "dark";
  /** Campo que Revisión debe resaltar al llegar desde un aviso de conflicto. */
  focusField: ReviewField | null;
  reviewField(field: ReviewField): void;
  /** Carga un análisis. Con keepSelection conserva la pieza y el candidato elegidos (recarga del mismo plano). */
  load(bundle: RunSnapshotBundle | null, options?: { keepSelection?: boolean }): void;
  reloadRun(): Promise<void>;
  /** Añade una revisión nueva. Con la petición enviada, el espacio de trabajo la guarda para poder repetirla. */
  addRevision(result: Result, request?: ReviewRequest): void;
  select(id: string | null): void;
  setCandidate(id: string | null): void;
  go(screen: Screen): void;
  toggleTheme(): void;
}

const Ctx = createContext<Store | null>(null);

function initialTheme(): "light" | "dark" {
  const param = new URLSearchParams(location.search).get("theme");
  if (param === "dark" || param === "light") return param;
  const host = document.documentElement.getAttribute("data-theme");
  if (host === "dark" || host === "light") return host;
  try {
    const stored = localStorage.getItem("vx-theme");
    if (stored === "dark" || stored === "light") return stored;
  } catch { /* almacenamiento no disponible */ }
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const { route, navigate } = useRouter();
  const workspace = useWorkspace();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [configError, setConfigError] = useState<AppError | null>(null);
  const [planId, setPlanId] = useState<string | null>(null);
  const [document, setDocument] = useState<UploadedDocument | null>(null);
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [revisions, setRevisions] = useState<Result[]>([]);
  const [drawing, setDrawing] = useState<DrawingExtraction | null>(null);
  const [selectedRowId, setSelected] = useState<string | null>(null);
  const [candidateId, setCandidateId] = useState<string | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">(initialTheme);
  const [focusField, setFocusField] = useState<Store["focusField"]>(null);
  const screen: Screen = route.kind === "plan" ? route.screen : "plano";

  useEffect(() => {
    api.getConfig().then(setConfig).catch((err) => setConfigError(toAppError(err)));
  }, []);

  useEffect(() => {
    window.document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("vx-theme", theme); } catch { /* sin almacenamiento */ }
  }, [theme]);

  const go = useCallback((next: Screen) => {
    if (route.kind === "plan") navigate({ kind: "plan", planId: route.planId, screen: next });
  }, [route, navigate]);

  const load = useCallback((bundle: RunSnapshotBundle | null, options?: { keepSelection?: boolean }) => {
    setPlanId(bundle?.planId ?? null);
    setDocument(bundle?.document ?? null);
    setRun(bundle?.run ?? null);
    setRevisions(bundle?.revisions ?? []);
    setDrawing(bundle?.drawing ?? null);
    if (options?.keepSelection) return;
    setSelected(null);
    setCandidateId(null);
    setFocusField(null);
  }, []);

  const reloadRun = useCallback(async () => {
    if (!run) return;
    const [detail, list] = await Promise.all([api.getRun(run.id), api.getRevisions(run.id)]);
    setRun(detail.run);
    setRevisions(list);
  }, [run]);

  const { recordRevision } = workspace;
  const addRevision = useCallback((result: Result, request?: ReviewRequest) => {
    setRevisions((list) => [...list.filter((item) => item.result_revision !== result.result_revision), result].sort((a, b) => a.result_revision - b.result_revision));
    setRun((value) => (value ? { ...value, result_revision: result.result_revision } : value));
    setCandidateId(result.selected_assembly_candidate_id);
    setFocusField(null);
    if (planId) recordRevision(planId, result, request);
  }, [planId, recordRevision]);

  const current = revisions[revisions.length - 1] ?? null;
  const previous = revisions.length > 1 ? revisions[revisions.length - 2] : null;

  const value = useMemo<Store>(() => ({
    config, configError, planId, document, run, revisions, current, previous, drawing, selectedRowId, candidateId, screen, theme, focusField,
    reviewField: (field) => {
      setFocusField(field);
      go("revision");
      if (field === "material" || field === "finish") setTimeout(() => window.document.getElementById(field)?.focus(), 80);
    },
    load, reloadRun, addRevision, select: setSelected, setCandidate: setCandidateId, go,
    toggleTheme: () => setTheme((value) => (value === "dark" ? "light" : "dark")),
  }), [config, configError, planId, document, run, revisions, current, previous, drawing, selectedRowId, candidateId, screen, theme, focusField, load, reloadRun, addRevision, go]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore() {
  const value = useContext(Ctx);
  if (!value) throw new Error("StoreProvider ausente");
  return value;
}
