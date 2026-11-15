import { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api";
import type { DrawingExtraction, LibraryItem } from "../api/types";
import { COPY } from "../copy";
import { DrawingCanvas } from "../components/DrawingCanvas";
import { LogoMark } from "../components/Logo";
import { Menu, type MenuItem } from "../components/system";
import { buildRows, pickCandidate } from "../lib/domain";
import { useApi } from "../lib/useApi";
import { completable, EDIT_FIELDS } from "../screens/Workspace";
import { Budget } from "./Budget";
import { isLegacy, legacyRows, legacyScenario } from "./legacy";
import { StepBar, type StepId, type StepState } from "./StepBar";
import { isSheet, isView, useRouter, VIEWS, type Screen, type Sheet, type View } from "../router";
import { LibraryScreen } from "../screens/Library";
import { PurchaseScreen } from "../screens/Purchase";
import { ReviewScreen } from "../screens/Review";
import { useStore } from "../state";
import { useWorkspace } from "../workspace/store";
import type { PlanRecord } from "../workspace/types";
import { Dims, Ficha } from "./Ficha";
import { PartsView } from "./PartsView";
import { useMedia } from "./useMedia";

const SceneView = lazy(() => import("../screens/Scene"));

/**
 * Mesa de trabajo: una sola pantalla con el lienzo ocupando casi todo, la ficha plegable a la derecha y los pasos abajo.
 * La vista del lienzo y el panel abierto salen del segmento de la ruta; la selección vive en el estado común.
 */
export function Workbench({ plan, screen, library }: { plan: PlanRecord; screen: Screen; library: { item: LibraryItem; drawing: DrawingExtraction } | null }) {
  const store = useStore();
  const ws = useWorkspace();
  const { current, previous, run, selectedRowId, select, candidateId } = store;
  const { navigate } = useRouter();
  const wide = useMedia("(min-width: 1024px)");
  const drawing = library?.drawing ?? store.drawing;
  const candidate = current && !library ? pickCandidate(current, run, candidateId) : null;
  const legacy = isLegacy(current);
  const rows = useMemo(() => (!current || library ? [] : legacy ? legacyRows(current, drawing) : buildRows(current, candidate, previous)), [current, candidate, previous, library, legacy, drawing]);
  const selected = rows.find((row) => row.id === selectedRowId) ?? null;

  const [view, setView] = useState<View>(isView(screen) ? screen : "plano");
  useEffect(() => { if (isView(screen)) setView(screen); }, [screen]);
  const sheet: Sheet | null = isSheet(screen) ? screen : null;
  const go = (next: Screen) => navigate({ kind: "plan", planId: plan.id, screen: next });
  const viewEnabled = (item: View) => !library || item === "original" || item === "plano";

  const [panelOpen, setPanelOpen] = useState(true);
  const [mobileUp, setMobileUp] = useState(false);
  const [focus, setFocus] = useState<{ ids: string[]; tick: number } | null>(null);
  const [completeTick, setCompleteTick] = useState(0);
  const [exportRequest, setExportRequest] = useState<{ format: "json" | "csv"; tick: number } | null>(null);
  useEffect(() => { if (selectedRowId) { setPanelOpen(true); setMobileUp(true); } }, [selectedRowId]);

  // Estado de los pasos: la estimación vigente se vuelve a leer al cerrar un panel (Coste puede haberla creado).
  const detail = useApi(run && current && !library ? () => api.getRun(run.id) : null, [run?.id, current?.result_revision, sheet === null]);
  const estimate = detail.data?.estimate ?? null;
  const states: Record<StepId, StepState> = {
    original: drawing ? "done" : "off",
    plano: !drawing ? "off" : drawing.status === "ready" ? "done" : "review",
    piezas: library || !current ? "off" : current.state === "completed" ? "done" : "review",
    compras: library ? "off" : estimate ? "done" : "pending",
    presupuesto: library ? "off" : estimate ? "done" : "pending",
  };
  const activeStep: StepId | null = sheet === "compras" || sheet === "presupuesto" ? sheet : sheet ? null : view === "esquema" ? null : view;
  const unknownFields = !candidate ? [] : rows.flatMap((row) => EDIT_FIELDS.filter((field) => completable(row, field)).map((field) => ({ row, field })));

  /** Láminas: la vista de piezas separadas impresa, una tarjeta por pieza. */
  const printSheets = () => {
    go("piezas");
    setTimeout(() => { try { print(); } catch { /* el marco no deja imprimir */ } }, 450);
  };
  const actions: { outputs: MenuItem[]; review: MenuItem[]; more: MenuItem[] } = {
    outputs: [
      { label: COPY.portal.out.cad, hint: COPY.cad.original, onSelect: () => { ws.downloadDxf(plan.id); } },
      { label: COPY.cad.annotated, hint: COPY.cad.annotatedOff, disabled: true },
      { label: COPY.portal.out.csv, disabled: !!library, hint: library ? COPY.portal.off : undefined, onSelect: () => { go("presupuesto"); setExportRequest((value) => ({ format: "csv", tick: (value?.tick ?? 0) + 1 })); } },
      { label: COPY.portal.out.json, disabled: !!library, onSelect: () => { go("presupuesto"); setExportRequest((value) => ({ format: "json", tick: (value?.tick ?? 0) + 1 })); } },
      { label: COPY.portal.out.sheets, hint: COPY.portal.out.sheetsHint, disabled: !!library, onSelect: printSheets },
    ],
    review: [
      {
        label: COPY.portal.review.complete, disabled: !unknownFields.length,
        hint: unknownFields.length ? COPY.portal.review.completeHint(unknownFields.length) : COPY.portal.review.nothing,
        onSelect: () => { select(unknownFields[0].row.id); setCompleteTick((value) => value + 1); },
      },
      { label: COPY.portal.review.full, disabled: !!library, onSelect: () => go("revision") },
    ],
    more: [
      { label: COPY.portal.more.similar, disabled: !!library, onSelect: () => go("similares") },
      { label: COPY.portal.more.trace, disabled: plan.source === "library", onSelect: () => go("analisis") },
      { label: COPY.portal.mapa.link, onSelect: () => { location.hash = `#mapa?foco=${encodeURIComponent(plan.asset ?? plan.id)}`; } },
      { label: store.theme === "dark" ? COPY.theme.light : COPY.theme.dark, onSelect: store.toggleTheme },
      { label: COPY.portal.more.shortcuts, onSelect: () => dispatchEvent(new CustomEvent("vx-shortcuts")) },
    ],
  };

  // Teclado: flechas para cambiar de pieza y Esc para cerrar el panel abierto o quitar la selección.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const el = event.target as HTMLElement | null;
      if (event.ctrlKey || event.metaKey || event.altKey || (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (document.querySelector("[aria-modal=true], [role=menu]")) return;
      if (event.key === "Escape") {
        if (sheet) { go(view); return; }
        if (selectedRowId) select(null);
        return;
      }
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && rows.length && !sheet) {
        event.preventDefault();
        const index = rows.findIndex((row) => row.id === selectedRowId);
        const next = event.key === "ArrowDown" ? (index + 1) % rows.length : index <= 0 ? rows.length - 1 : index - 1;
        select(rows[next].id);
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  // ---- Selección e iluminación cruzadas ----
  // La pieza seleccionada vive en el estado común (sobrevive al cambio de vista); la iluminada por el puntero, aquí.
  // Un contorno puede ser de varias piezas (K2 tapa y K2 base comparten vistas): el clic alterna entre ellas.
  const [hoverRowId, setHoverRowId] = useState<string | null>(null);
  const [hoverContours, setHoverContours] = useState<string[] | null>(null);
  const owners = useMemo(() => {
    const map = new Map<string, string[]>();
    rows.forEach((row) => row.contourIds.forEach((id) => map.set(id, [...(map.get(id) ?? []), row.id])));
    return map;
  }, [rows]);
  useEffect(() => { setHoverRowId(null); setHoverContours(null); }, [view, selectedRowId]);
  const hoverRow = rows.find((row) => row.id === hoverRowId) ?? null;
  // Con el puntero sobre una vista de la ficha, esa vista pasa a primer plano y el resto de la pieza queda en segundo.
  const primary = new Set(hoverContours ?? selected?.contourIds ?? []);
  const secondary = new Set(selected ? rows.filter((row) => row.observationId === selected.observationId).flatMap((row) => row.contourIds) : []);
  const related = new Set(selected ? rows.filter((row) => row.observationId === selected.observationId && row.id !== selected.id).map((row) => row.id) : []);
  const hover = new Set(hoverRow && hoverRow.id !== selectedRowId ? hoverRow.contourIds : []);
  const viewKeys = useMemo(() => {
    const map = new Map<string, string>();
    (current?.part_analysis?.observations ?? []).forEach((o, i) => o.views.forEach((v) => map.set(v.view_id, o.part_key ?? `Sin etiqueta ${i + 1}`)));
    return map;
  }, [current]);
  const onContour = (contourId: string | null) => {
    if (!contourId) return select(null);
    const list = owners.get(contourId) ?? [];
    if (!list.length) return select(null);
    const at = list.indexOf(selectedRowId ?? "");
    select(at === -1 ? list[0] : list[(at + 1) % list.length]);
  };
  const onHoverContour = (contourId: string | null) => {
    const list = contourId ? owners.get(contourId) ?? [] : [];
    setHoverRowId(list.includes(selectedRowId ?? "") ? selectedRowId : list[0] ?? null);
  };

  // En móvil la ficha es una hoja inferior: el encuadre del plano deja libre su altura.
  const mobileSheet = useRef<HTMLDivElement>(null);
  const [mobileH, setMobileH] = useState(52);
  useLayoutEffect(() => {
    const el = mobileSheet.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setMobileH(Math.round(el.getBoundingClientRect().height) + 4));
    ro.observe(el);
    return () => ro.disconnect();
  }, [wide]);
  const insetTop = wide ? 64 : 60;
  const insetBottom = wide ? 0 : mobileH;
  const fichaProps = {
    rows, selected, current, run, candidate, drawing, library: library?.item ?? null, hoverId: hoverRowId, completeTick,
    scenarioTitle: current && legacy ? legacyScenario(current)?.title ?? null : null,
    onHover: setHoverRowId, onSelect: select, onHoverContours: setHoverContours,
    onFocus: (ids: string[]) => { if (view !== "original" && view !== "plano") go("plano"); setFocus((value) => ({ ids, tick: (value?.tick ?? 0) + 1 })); },
    onReview: () => go("revision"),
  };

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-bg" data-testid="workbench">
      <h1 className="sr-only">{plan.name} · {COPY.portal.viewTitles[view]}</h1>
      <div className="relative flex min-h-0 flex-1">
        <section className="relative min-h-0 min-w-0 flex-1 overflow-hidden" aria-label={COPY.portal.viewTitles[view]}>
          {(view === "original" || view === "plano") && (drawing ? (
            <DrawingCanvas
              drawing={drawing} variant={view === "original" ? "original" : "clean"} primary={primary} secondary={secondary} hover={hover} viewKeys={viewKeys}
              onSelectContour={rows.length ? onContour : undefined} onHoverContour={rows.length ? onHoverContour : undefined} className="absolute inset-0" tools keyboard
              insetTop={insetTop} insetBottom={insetBottom} reserveBottom={52} focus={focus}
            />
          ) : <div className="plan-grid absolute inset-0" />)}
          {view === "piezas" && drawing && (
            <PartsView rows={rows} drawing={drawing} schematic={legacy} selectedId={selectedRowId} relatedIds={related} hoverId={hoverRowId} onSelect={select} onHover={setHoverRowId} insetTop={insetTop} insetBottom={insetBottom} />
          )}
          {view === "esquema" && (
            <Suspense fallback={<div className="absolute inset-0 bg-block" />}>
              <SceneView selectedProposal={selectedRowId} hoverProposal={hoverRowId} onPick={select} onHover={setHoverRowId} insetTop={insetTop} insetBottom={insetBottom} />
            </Suspense>
          )}
          {/* Pieza bajo el puntero: rótulo breve abajo, útil con la ficha plegada. */}
          {hoverRow && wide && (
            <div data-noprint className="pointer-events-none absolute bottom-s3 left-1/2 z-10 flex -translate-x-1/2 items-baseline gap-s2 border border-ink bg-surface px-s3 py-s1" role="status" data-testid="hover-chip">
              <span className="num font-mono text-[13px] font-medium text-ink">{hoverRow.key}</span>
              <span className="text-sm text-ink">{hoverRow.role.value}</span>
              <Dims row={hoverRow} />
            </div>
          )}

          <div data-noprint className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start gap-s2 p-s3 lg:grid lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
            <Brand plan={plan} />
            <ViewSwitch view={view} onChange={go} enabled={viewEnabled} />
            <div className="pointer-events-auto ml-auto flex items-center gap-s2 lg:justify-self-end">
              {wide ? (
                <div className="flex h-10 items-stretch border border-line-strong bg-surface" data-testid="action-blocks">
                  <Block label={COPY.portal.blocks.outputs} items={actions.outputs} />
                  <Block label={COPY.portal.blocks.review} items={actions.review} dot={current?.state === "needs_review"} divider />
                  <Block label={COPY.portal.blocks.more} items={actions.more} divider />
                </div>
              ) : (
                <Menu
                  label={COPY.portal.blocks.all}
                  className="border border-line-strong bg-surface"
                  triggerClassName="h-10 w-10"
                  items={[
                    ...actions.outputs.map((item) => ({ ...item, group: COPY.portal.blocks.outputs })),
                    ...actions.review.map((item) => ({ ...item, group: COPY.portal.blocks.review })),
                    ...actions.more.map((item) => ({ ...item, group: COPY.portal.blocks.more })),
                  ]}
                />
              )}
              {wide && (
                <button className="inline-flex h-10 w-10 items-center justify-center border border-line-strong bg-surface text-ink hover:bg-sunken" onClick={() => setPanelOpen((value) => !value)} aria-expanded={panelOpen} aria-label={panelOpen ? COPY.portal.panelClose : COPY.portal.panelOpen} title={panelOpen ? COPY.portal.panelClose : COPY.portal.panelOpen}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true"><rect x="2" y="2.5" width="12" height="11" /><path d="M10 2.5v11" />{panelOpen && <path d="M11.5 5.5h1M11.5 8h1M11.5 10.5h1" />}</svg>
                </button>
              )}
            </div>
          </div>

          {!wide && (
            <div ref={mobileSheet} data-noprint className="absolute inset-x-0 bottom-0 z-20 flex max-h-[56%] flex-col border-t-2 border-ink bg-surface shadow-[0_-8px_24px_rgb(0_0_0/0.12)]">
              <button className="flex h-12 shrink-0 items-center justify-between gap-s3 px-s4 text-left" onClick={() => setMobileUp((value) => !value)} aria-expanded={mobileUp}>
                <span className="flex min-w-0 items-center gap-s3">
                  {selected ? (
                    <span className="flex min-w-0 items-baseline gap-s2">
                      <span className="num font-mono text-[13px] font-medium text-ink">{selected.key}</span>
                      <span className="truncate text-sm text-ink">{selected.role.value}</span>
                      <Dims row={selected} />
                    </span>
                  ) : <span className="truncate text-sm text-ink">{library ? library.item.label : COPY.portal.peek(rows.length)}</span>}
                  {api.isMock && COPY.mockBadge && <span className="inline-flex h-6 shrink-0 items-center border border-line-strong px-s2 text-2xs font-semibold text-ink">{COPY.mockBadge}</span>}
                </span>
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className={`shrink-0 ${mobileUp ? "" : "rotate-180"}`}><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
              {mobileUp && <div className="scroll-thin min-h-0 overflow-y-auto border-t border-line"><Ficha {...fichaProps} /></div>}
            </div>
          )}
        </section>

        {wide && panelOpen && (
          <aside data-noprint className="scroll-thin w-[320px] shrink-0 overflow-y-auto border-l border-line bg-surface" aria-label={selected ? `${selected.key} ${selected.role.value ?? ""}` : COPY.portal.summary}>
            <Ficha {...fichaProps} />
          </aside>
        )}

        {sheet && <SheetHost sheet={sheet} onClose={() => go(view)} budget={<Budget request={exportRequest} onPrint={printSheets} />} />}
      </div>
      <StepBar active={activeStep} states={states} current={library ? null : current} wide={wide} onStep={go} />
    </div>
  );
}

/** Un bloque de acciones del mismo arquetipo: un botón con su nombre que abre la lista. */
export function Block({ label, items, dot = false, divider = false }: { label: string; items: MenuItem[]; dot?: boolean; divider?: boolean }) {
  return (
    <Menu
      label={label}
      items={items}
      className={divider ? "border-l border-l-line" : ""}
      triggerClassName="h-full gap-s2 px-s3 text-sm font-semibold"
      trigger={
        <>
          {dot && <span className="inline-block h-2 w-2 rounded-full bg-hip" aria-hidden="true" />}
          {label}
          <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </>
      }
    />
  );
}

/** Logo de la landing y migas compactas: carpeta y plano. */
export function Brand({ plan }: { plan: PlanRecord }) {
  const ws = useWorkspace();
  const { navigate } = useRouter();
  const path = ws.folderPath(plan.folderId);
  const folder = path[path.length - 1];
  return (
    <nav aria-label="Migas de pan" className="pointer-events-auto flex h-10 min-w-0 items-center gap-s2 justify-self-start border border-line bg-surface pl-s2 pr-s3">
      <a href="#/" onClick={(event) => { event.preventDefault(); navigate({ kind: "home", folderId: null }); }} aria-label="Vexplorer, ir a Planos" className="shrink-0">
        <LogoMark size={26} />
      </a>
      <span className="hidden min-w-0 items-center gap-s2 text-sm lg:flex">
        {folder && (
          <>
            <a href="#" onClick={(event) => { event.preventDefault(); navigate({ kind: "home", folderId: folder.id }); }} className="shrink-0 text-muted hover:text-ink hover:underline">{folder.name}</a>
            <span className="text-muted" aria-hidden="true">›</span>
          </>
        )}
        <span className="num truncate font-mono text-2xs text-ink" aria-current="page" title={plan.name}>{plan.name}</span>
      </span>
    </nav>
  );
}

export function ViewSwitch({ view, onChange, enabled }: { view: View; onChange: (view: View) => void; enabled: (view: View) => boolean }) {
  return (
    <div role="group" aria-label={COPY.portal.viewSwitch} className="pointer-events-auto flex h-10 shrink-0 items-stretch border border-line-strong bg-surface" data-testid="view-switch">
      {VIEWS.map((item, index) => {
        const active = item === view;
        const on = enabled(item);
        return (
          <button
            key={item}
            className={`px-s3 text-sm font-semibold ${index ? "border-l border-l-line" : ""} ${active ? "bg-ink text-surface" : on ? "text-ink hover:bg-sunken" : "cursor-not-allowed text-faint"}`}
            aria-pressed={active}
            disabled={!on}
            title={on ? `${COPY.portal.viewTitles[item]} (${index + 1})` : COPY.portal.viewOff}
            onClick={() => onChange(item)}
          >
            {COPY.portal.views[item]}
          </button>
        );
      })}
    </div>
  );
}

/** Paneles poco frecuentes: se abren encima de la mesa sin perder la vista ni la selección. */
function SheetHost({ sheet, onClose, budget }: { sheet: Sheet; onClose: () => void; budget: ReactNode }) {
  const content: Record<Sheet, ReactNode> = {
    revision: <ReviewScreen />,
    compras: <PurchaseScreen />,
    presupuesto: budget,
    similares: <LibraryScreen />,
  };
  return (
    <div data-noprint className="absolute inset-0 z-30 flex justify-end">
      <div className="absolute inset-0 bg-[rgb(var(--ink)/0.22)]" onClick={onClose} aria-hidden="true" />
      <div role="dialog" aria-labelledby="sheet-title" className="sheet anim-in relative flex h-full w-full max-w-[1000px] flex-col border-l border-line-strong bg-bg shadow-[-12px_0_32px_rgb(0_0_0/0.14)]">
        <header className="flex h-12 shrink-0 items-center justify-between gap-s3 border-b border-line bg-surface pl-s4 pr-s2">
          <h2 id="sheet-title" className="text-md font-semibold text-ink">{COPY.portal.sheets[sheet]}</h2>
          <button className="inline-flex h-9 items-center gap-s2 px-s3 text-sm font-semibold text-ink hover:bg-sunken" onClick={onClose}>
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
            {COPY.portal.closeSheet}
          </button>
        </header>
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">{content[sheet]}</div>
      </div>
    </div>
  );
}
