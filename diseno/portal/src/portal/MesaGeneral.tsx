import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { COPY } from "../copy";
import { DrawingCanvas, ToolButton } from "../components/DrawingCanvas";
import type { MenuItem } from "../components/system";
import { Menu } from "../components/system";
import type { MesaTrabajo } from "../general";
import { isView, useRouter, type Screen, type View } from "../router";
import { useStore } from "../state";
import { useWorkspace } from "../workspace/store";
import type { PlanRecord } from "../workspace/types";
import { BoxViewer, type BoxItem } from "./BoxViewer";
import { FichaGeneral } from "./FichaGeneral";
import { Laminas } from "./Laminas";
import { corta, descargarArchivo, planoComoDrawing } from "./mesa";
import { Traza } from "./Traza";
import { COLOR_CONFIANZA } from "./confianza";
import { Proceso } from "./Proceso";
import { pasosDeMesa, pasosReconstruccion } from "../general/proceso";
import { EscenarioReconstruccion, type Escenario } from "./EscenarioReconstruccion";
import { cotasCalculadas, cotasDeContornos } from "../general/cotas";
import { aceptarPlantillaMesa } from "../general/vivo";
import { generalApi } from "../api";
import { PiezasGeneral } from "./PiezasGeneral";
import { StepBar, type StepId, type StepState } from "./StepBar";
import { useMedia } from "./useMedia";
import { Block, Brand, ViewSwitch } from "./Workbench";

/**
 * Mesa de trabajo de un mueble de la vía general o de un caso congelado (formato MesaTrabajo de src/general).
 * Misma disposición que la mesa de piezas separadas: lienzo, ficha plegable, pasos abajo y acciones por bloques.
 * La selección vive aquí y se conserva al cambiar de vista; las piezas inferidas no tienen contorno y no iluminan el plano.
 */
export function MesaGeneral({ plan, mesa: mesaBase, screen, onReload }: { plan: PlanRecord; mesa: MesaTrabajo; screen: Screen; onReload?: () => void }) {
  // Construcción 3D con revisión padre e hija: «Versión 1 / Versión 2», abre en la última.
  const [version, setVersion] = useState(Math.max(0, mesaBase.versiones.length - 1));
  const mesa = mesaBase.versiones[version]?.mesa ?? mesaBase;
  const { navigate } = useRouter();
  const store = useStore();
  const ws = useWorkspace();
  const wide = useMedia("(min-width: 1024px)");
  const [view, setView] = useState<View>(isView(screen) ? screen : "plano");
  useEffect(() => { if (isView(screen)) setView(screen); }, [screen]);
  const go = (next: Screen) => navigate({ kind: "plan", planId: plan.id, screen: next });

  const drawing = useMemo(() => (mesa.plano ? planoComoDrawing(mesa.plano) : null), [mesa]);
  // «Limpio» añade las cotas medidas sobre la geometría y las dos de la pieza elegida; «Original» queda con las del DXF.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [hoverContours, setHoverContours] = useState<string[] | null>(null);
  const [focus, setFocus] = useState<{ ids: string[]; tick: number } | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [mobileUp, setMobileUp] = useState(false);
  const [section, setSection] = useState<{ id: "pendientes" | "avisos"; tick: number } | null>(null);
  const [sheet, setSheet] = useState<{ lamina: string | null } | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const escena = mesa.escena;
  const download = (file: Parameters<typeof descargarArchivo>[0]) => { void descargarArchivo(file, ws.toast); };

  // ---- Proceso: pasos reales del mueble; cada paso cambia la vista de la mesa ----
  const origenProceso = useMemo(() => (plan.source === "caso"
    ? { geometria: "guardado" as const, resto: "guardado" as const }
    : plan.flujo === "guardado"
      ? { geometria: "vivo" as const, resto: "guardado" as const, horaGeometria: new Date(plan.updatedAt).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) }
      : { geometria: "vivo" as const, resto: "vivo" as const }), [plan.source, plan.flujo, plan.updatedAt]);
  // Construcción 3D: pasos con los archivos del pipeline; con versiones, de la primera a la última.
  const pasos = useMemo(() => pasosReconstruccion(mesaBase) ?? pasosDeMesa(mesa, origenProceso), [mesaBase, mesa, origenProceso]);
  const [escenario, setEscenario] = useState<Escenario | null>(null);
  const [proceso, setProceso] = useState<{ i: number; auto: boolean } | null>(() => {
    try {
      if (sessionStorage.getItem(`vx-proceso-${plan.id}`)) return { i: 0, auto: true };
    } catch { /* sin almacenamiento */ }
    return null;
  });
  // La marca de «recién subido» se borra un poco después: la mesa puede montarse dos veces al terminar la subida.
  useEffect(() => {
    const timer = setTimeout(() => { try { sessionStorage.removeItem(`vx-proceso-${plan.id}`); } catch { /* sin almacenamiento */ } }, 4000);
    return () => clearTimeout(timer);
  }, [plan.id]);
  const [accepting, setAccepting] = useState(false);
  const irAPaso = (i: number) => setProceso((value) => ({ i, auto: value?.auto ?? false }));
  useEffect(() => {
    if (!proceso) { setEscenario(null); return; }
    const paso = pasos[proceso.i];
    const destino = paso?.vista;
    if (paso?.version != null) setVersion(paso.version);
    if (destino === "revision" || destino === "bom") { setSheet(null); setEscenario(destino); return; }
    setEscenario(null);
    if (destino === "salidas") { if (mesa.laminas.length) setSheet({ lamina: null }); else { setSheet(null); go("piezas"); } }
    else if (destino) { setSheet(null); if (destino !== view) go(destino); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proceso?.i, proceso === null]);
  const pasoActual = proceso ? pasos[proceso.i] : null;
  const accion = pasoActual?.id === "revision" && pasoActual.estado === "requiere_revision" && mesa.via === "tabla" && plan.source === "general" && plan.runId
    ? {
        label: COPY.portal.proceso.accept, busy: accepting,
        run: () => {
          setAccepting(true);
          aceptarPlantillaMesa(generalApi, plan.runId!, COPY.portal.proceso.reviewer)
            .then(() => { onReload?.(); })
            .catch((error) => ws.toast(error instanceof Error ? error.message : COPY.errors.generic, { tone: "error" }))
            .finally(() => setAccepting(false));
        },
      }
    : null;
  // «Guardado 14 nov» solo donde la fecha está comprobada (pipeline guardado, F0x y demo); reconstrucción sin fecha; raros sin etiqueta.
  const etiquetaOrigen = plan.asset?.startsWith("raro:") ? null
    : mesa.via === "reconstruccion" ? COPY.portal.general.savedShort
    : plan.source === "caso" || plan.flujo === "guardado" ? COPY.portal.general.saved : null;
  // Construcción 3D: sólido, con cada pieza en el tono de su confianza.
  const solido = mesa.via === "reconstruccion";
  // Paso «Piezas»: las piezas aparecen una a una en el 3D, en el orden de la propuesta.
  const [aparecidas, setAparecidas] = useState<number | null>(null);
  useEffect(() => {
    if (pasoActual?.id !== "piezas" || !solido) { setAparecidas(null); return; }
    setAparecidas(1);
    const timer = setInterval(() => setAparecidas((n) => (n == null || n >= mesa.piezas.length ? n : n + 1)), 450);
    return () => clearInterval(timer);
  }, [pasoActual?.id, solido, mesa.piezas.length]);
  const visibles = useMemo(() => (aparecidas == null ? null : new Set(mesa.piezas.slice(0, aparecidas).map((p) => p.id))), [aparecidas, mesa]);
  const coloresConfianza = useMemo(() => Object.fromEntries(mesa.piezas.filter((p) => p.confianza).map((p) => [p.id, COLOR_CONFIANZA[p.confianza!.nivel]])), [mesa]);
  const [resetTick, setResetTick] = useState(0);
  const selected = mesa.piezas.find((p) => p.id === selectedId) ?? null;
  const calculadas = useMemo(() => {
    if (!mesa.plano) return [];
    const largos = mesa.piezas.map((p) => p.largo.valor_mm ?? 0);
    const maxima = mesa.plano.extensionMaxima_mm ?? (largos.length ? Math.max(...largos) : null);
    return cotasCalculadas(mesa.plano, maxima || null);
  }, [mesa]);
  const drawingLimpio = useMemo(() => {
    if (!mesa.plano) return null;
    const pieza = selected && !selected.inferida ? cotasDeContornos(mesa.plano, selected.contornos) : [];
    if (!calculadas.length && !pieza.length) return drawing;
    return planoComoDrawing({ ...mesa.plano, cotas: [...mesa.plano.cotas, ...calculadas, ...pieza] });
  }, [mesa, calculadas, selected, drawing]);
  const hoverPieza = mesa.piezas.find((p) => p.id === hoverId) ?? null;
  const select = (id: string | null) => setSelectedId(id);
  useEffect(() => { if (selectedId) { setPanelOpen(true); setMobileUp(true); } }, [selectedId]);
  useEffect(() => { setHoverId(null); setHoverContours(null); }, [view, selectedId]);

  // ---- Selección cruzada: contorno ↔ piezas que lo tienen como origen ----
  const owners = useMemo(() => new Map((mesa.plano?.contornos ?? []).map((c) => [c.id, c.piezas])), [mesa]);
  const primary = new Set(hoverContours ?? (selected && !selected.inferida ? selected.contornos : []));
  const secondary = new Set(selected && !selected.inferida ? selected.contornosEvidencia : []);
  const hover = new Set(hoverPieza && hoverPieza.id !== selectedId ? hoverPieza.contornos : []);
  const onContour = (id: string | null) => {
    const list = id ? owners.get(id) ?? [] : [];
    if (!list.length) return select(null);
    const at = list.indexOf(selectedId ?? "");
    select(at === -1 ? list[0] : list[(at + 1) % list.length]);
  };
  const onHoverContour = (id: string | null) => {
    const list = id ? owners.get(id) ?? [] : [];
    setHoverId(list.includes(selectedId ?? "") ? selectedId : list[0] ?? null);
  };

  // ---- 3D: cajas del modelo de vista, con el eje vertical que declara ----
  const boxes = useMemo<BoxItem[]>(() => escena.cajas.map((c) => {
    const p = c.posicion_mm, s = c.tamano_mm;
    return escena.ejeVertical === "z"
      ? { id: c.id, pieza: c.piezaId, min: { x: p.x, y: p.z, z: -(p.y + s.y) }, size: { x: s.x, y: s.z, z: s.y }, dashed: c.estimada, conflict: c.conflicto }
      : { id: c.id, pieza: c.piezaId, min: { ...p }, size: { ...s }, dashed: c.estimada, conflict: c.conflicto };
  }), [escena]);

  // ---- Teclado: flechas para cambiar de pieza, Esc para cerrar ----
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const el = event.target as HTMLElement | null;
      if (event.ctrlKey || event.metaKey || event.altKey || (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (document.querySelector("[aria-modal=true], [role=menu]")) return;
      if (event.key === "Escape") { if (sheet) setSheet(null); else if (traceOpen) setTraceOpen(false); else if (selectedId) select(null); return; }
      if ((event.key === "ArrowDown" || event.key === "ArrowUp") && mesa.piezas.length && !sheet) {
        event.preventDefault();
        const index = mesa.piezas.findIndex((p) => p.id === selectedId);
        const next = event.key === "ArrowDown" ? (index + 1) % mesa.piezas.length : index <= 0 ? mesa.piezas.length - 1 : index - 1;
        select(mesa.piezas[next].id);
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  // ---- Móvil: la ficha es una hoja inferior y el encuadre deja libre su altura ----
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

  const openSection = (id: "pendientes" | "avisos") => { select(null); setPanelOpen(true); setMobileUp(true); setSection((value) => ({ id, tick: (value?.tick ?? 0) + 1 })); };
  const states: Record<StepId, StepState> = {
    original: drawing ? "done" : "off",
    plano: !drawing ? "off" : mesa.plano?.avisos.length ? "review" : "done",
    piezas: !mesa.piezas.length ? "off" : mesa.pendientes.length ? "review" : "done",
    compras: "off",
    presupuesto: "off",
  };
  const activeStep: StepId | null = view === "esquema" ? null : view;
  const viewEnabled = (item: View) => item === "original" ? !!drawing || !!mesa.imagenOriginal : item === "plano" ? !!drawing : mesa.piezas.length > 0 || item === "esquema";

  const actions: { outputs: MenuItem[]; review: MenuItem[]; more: MenuItem[] } = {
    outputs: [
      mesa.original
        ? { label: COPY.portal.out.cad, hint: mesa.original.nombre, onSelect: () => download(mesa.original!) }
        : { label: COPY.portal.out.cad, hint: plan.source === "general" ? COPY.cad.original : COPY.portal.general.noOriginal, disabled: plan.source !== "general", onSelect: () => { ws.downloadDxf(plan.id); } },
      { label: COPY.portal.out.sheets, hint: mesa.laminas.length ? `${mesa.laminas.length}` : COPY.portal.general.noSheets, disabled: !mesa.laminas.length, onSelect: () => setSheet({ lamina: selected?.laminas[0] ?? null }) },
      ...mesa.artefactos.map((file) => ({
        label: file.nombre,
        hint: file.url || file.contenido != null ? (file.estado === "incompleto" ? COPY.portal.general.incomplete : undefined) : COPY.portal.general.noFile,
        disabled: !file.url && file.contenido == null,
        onSelect: () => download(file),
      })),
    ],
    review: [
      { label: COPY.portal.general.seePending(mesa.pendientes.length), disabled: !mesa.pendientes.length, onSelect: () => openSection("pendientes") },
      { label: COPY.portal.review.full, disabled: true, hint: COPY.portal.general.noReview },
    ],
    more: [
      { label: COPY.portal.general.trace, hint: mesa.traza.length ? `${mesa.traza.length}` : COPY.portal.general.traceEmpty, disabled: !mesa.traza.length, onSelect: () => setTraceOpen(true) },
      { label: COPY.portal.mapa.link, onSelect: () => { location.hash = `#mapa?foco=${encodeURIComponent(plan.asset ?? plan.id)}`; } },
      { label: store.theme === "dark" ? COPY.theme.light : COPY.theme.dark, onSelect: store.toggleTheme },
      { label: COPY.portal.more.shortcuts, onSelect: () => dispatchEvent(new CustomEvent("vx-shortcuts")) },
    ],
  };

  // Indicadores compactos de la barra de pasos: pendientes, avisos y evaluador. El detalle está en la ficha.
  const ev = mesa.evaluacion;
  const indicators = (
    <>
      {mesaBase.versiones.length > 1 && (
        <span className="inline-flex border border-line-strong" role="group" aria-label={COPY.portal.general.versions}>
          {mesaBase.versiones.map((item, i) => (
            <button key={item.id} className={`h-8 px-s2 text-2xs font-semibold lg:text-sm ${i === version ? "bg-ink text-bg" : "text-ink hover:bg-sunken"}`} aria-pressed={i === version} onClick={() => { setVersion(i); select(null); }} data-testid={`version-${i + 1}`}>{item.etiqueta}</button>
          ))}
        </span>
      )}
      <button className={`inline-flex h-8 items-center gap-s1 px-s2 text-2xs font-semibold text-ink hover:bg-sunken lg:text-sm ${proceso ? "bg-sunken" : ""}`} onClick={() => setProceso((value) => (value ? null : { i: 0, auto: false }))} aria-pressed={!!proceso} data-testid="ver-proceso">
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 2.5v7l6-3.5z" fill="currentColor" /></svg>
        <span className="hidden lg:inline">{COPY.portal.proceso.open}</span><span className="lg:hidden">{COPY.portal.proceso.title}</span>
      </button>
      {mesa.pendientes.length > 0 && (
        <button className="inline-flex h-8 items-center gap-s1 px-s1 text-2xs text-ink hover:bg-sunken lg:text-sm" onClick={() => openSection("pendientes")} title={COPY.portal.general.pending} data-testid="ind-pendientes">
          <span className="inline-block h-2 w-2 rounded-full bg-hip" aria-hidden="true" />
          <span className="num font-mono">{mesa.pendientes.length}</span><span className="hidden lg:inline">{COPY.portal.general.pendingN(mesa.pendientes.length)}</span>
        </button>
      )}
      {mesa.avisos.length > 0 && (
        <button className="hidden h-8 items-center gap-s1 px-s1 text-sm text-ink hover:bg-sunken lg:inline-flex" onClick={() => openSection("avisos")} title={COPY.portal.general.warnings}>
          <span className="num font-mono">{mesa.avisos.length}</span>{COPY.portal.general.warningsN(mesa.avisos.length)}
        </button>
      )}
      {ev && (
        <span className="hidden items-center gap-s1 text-sm text-ink lg:inline-flex" title={COPY.portal.general.evaluation}>
          <span className={`inline-block h-2 w-2 rounded-full ${ev.aprobado ? "bg-conf" : "bg-hip"}`} aria-hidden="true" />
          <span className="num font-mono text-2xs">{ev.cotasCorrectas}/{ev.cotasRequeridas}</span>{COPY.portal.general.dims}
        </span>
      )}
    </>
  );

  // Subida reconocida por su huella: la procedencia queda en Detalles aunque el panel del proceso esté cerrado.
  const mesaFicha = plan.flujo === "guardado" ? { ...mesa, notas: [COPY.portal.general.savedNote, ...mesa.notas] } : mesa;
  const fichaProps = {
    mesa: mesaFicha, selected, hoverId, section, onHover: setHoverId, onSelect: select, onHoverContours: setHoverContours,
    onFocus: (ids: string[]) => { if (view !== "original" && view !== "plano") go("plano"); setFocus((value) => ({ ids, tick: (value?.tick ?? 0) + 1 })); },
    onLamina: (id: string) => setSheet({ lamina: id }),
  };

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-bg" data-testid="workbench">
      <h1 className="sr-only">{plan.name} · {COPY.portal.viewTitles[view]}</h1>
      <div className="relative flex min-h-0 flex-1">
        <section data-noprint={sheet ? true : undefined} className="relative min-h-0 min-w-0 flex-1 overflow-hidden" aria-label={COPY.portal.viewTitles[view]}>
          {(view === "original" || view === "plano") && (drawing ? (
            <DrawingCanvas
              drawing={view === "original" ? drawing : drawingLimpio ?? drawing} variant={view === "original" ? "original" : "clean"} primary={primary} secondary={secondary} hover={hover} viewKeys={new Map()}
              onSelectContour={mesa.piezas.length ? onContour : undefined} onHoverContour={mesa.piezas.length ? onHoverContour : undefined}
              className="absolute inset-0" tools keyboard insetTop={insetTop} insetBottom={insetBottom} reserveBottom={52} focus={focus}
            />
          ) : mesa.imagenOriginal && view === "original" ? (
            <div className={`plan-grid absolute inset-0 flex items-center justify-center ${proceso ? "lg:pl-[380px]" : ""}`} style={{ paddingTop: insetTop, paddingBottom: insetBottom + 56 }}>
              <img src={mesa.imagenOriginal} alt={plan.name} className="max-h-full max-w-[90%] border border-line bg-white object-contain" />
            </div>
          ) : <div className="plan-grid absolute inset-0" />)}
          {view === "piezas" && (
            <PiezasGeneral piezas={mesa.piezas} selectedId={selectedId} hoverId={hoverId} onSelect={select} onHover={setHoverId} insetTop={insetTop} insetBottom={insetBottom} />
          )}
          {view === "esquema" && (
            <section className="absolute inset-x-0 top-0 bg-block" style={{ bottom: wide ? 0 : insetBottom }} aria-label={COPY.portal.viewTitles.esquema}>
              {boxes.length > 0
                ? <BoxViewer key={mesa.id} glbUrl={escena.glbUrl} solid={solido} colors={coloresConfianza} exploded={pasoActual?.id === "despiece"} visibles={visibles} shiftX={proceso && wide ? 170 : 0} boxes={boxes} selected={selectedId} hover={hoverId} onPick={select} onHover={setHoverId} resetTick={resetTick} front={mesa.via === "general" || mesa.via === "reconstruccion" ? 1 : -1} overhead={escena.disposicion === "piezas_separadas"} />
                : <p className="absolute inset-0 flex items-center justify-center px-s4 text-md font-semibold text-on-block">{COPY.portal.general.noScene}</p>}
              <div className="pointer-events-none absolute bottom-s3 left-s3 flex flex-col items-start gap-s1">
                {solido && boxes.length > 0 && (
                  <span className="flex items-center gap-s3 border border-on-block-2 bg-block px-s2 py-0.5 text-xs text-on-block" data-testid="leyenda-confianza">
                    {(["alta", "media", "baja"] as const).map((nivel) => (
                      <span key={nivel} className="inline-flex items-center gap-s1"><span className="inline-block h-2.5 w-2.5" style={{ background: COLOR_CONFIANZA[nivel] }} aria-hidden="true" />{COPY.portal.general.confianza[nivel]}</span>
                    ))}
                  </span>
                )}
                {escena.disposicion === "montaje" && escena.validacion && escena.validacion.estado !== "accepted" && (
                  <span className="flex items-center gap-s2 border border-on-block-2 bg-block px-s2 py-0.5 text-xs font-semibold text-on-block" data-testid="montaje-rechazado">
                    <span className="inline-block h-2 w-2 bg-danger" aria-hidden="true" />{COPY.portal.general.rejected}
                  </span>
                )}
              </div>
              <div className="absolute bottom-s3 right-s3 flex items-stretch border border-line-strong bg-surface" role="toolbar" aria-label={COPY.tools.block}>
                <ToolButton pressed={false} disabled onClick={() => undefined} label={COPY.tools.measure}><path d="M1.5 9.5 9.5 1.5l3 3-8 8Z M4 7l1.2 1.2 M5.8 5.2 7 6.4 M7.6 3.4l1.2 1.2" /></ToolButton>
                <ToolButton pressed={false} disabled onClick={() => undefined} label={COPY.tools.layers} className="border-l border-l-line"><path d="M7 1.8 12.5 4.6 7 7.4 1.5 4.6Z M1.5 7.2 7 10l5.5-2.8 M1.5 9.8 7 12.6l5.5-2.8" /></ToolButton>
                <ToolButton pressed={false} disabled={!boxes.length} onClick={() => setResetTick((value) => value + 1)} label={COPY.workspace.fit} shortcut="F" className="border-l border-l-line"><path d="M1.5 4.5v-3h3M9.5 1.5h3v3M12.5 9.5v3h-3M4.5 12.5h-3v-3" /></ToolButton>
              </div>
            </section>
          )}
          {escenario && mesa.reconstruccion && (
            <EscenarioReconstruccion r={mesa.reconstruccion} plano={mesa.imagenOriginal} escenario={escenario} insetTop={insetTop} insetBottom={insetBottom} />
          )}
          {proceso && (
            <div data-noprint className="absolute inset-x-s2 top-[60px] z-[35] lg:inset-x-auto lg:left-s3 lg:top-[64px] lg:w-[340px]">
              <Proceso
                pasos={pasos} actual={proceso.i} onPaso={irAPaso} auto={proceso.auto}
                onAuto={(auto) => setProceso((value) => (value ? { ...value, auto } : value))} onClose={() => setProceso(null)}
                etiqueta={etiquetaOrigen} accion={accion} className="shadow-[0_8px_24px_rgb(0_0_0/0.14)]"
              />
            </div>
          )}
          {hoverPieza && wide && (
            <div data-noprint className="pointer-events-none absolute bottom-s3 left-1/2 z-10 flex -translate-x-1/2 items-baseline gap-s2 border border-ink bg-surface px-s3 py-s1" role="status" data-testid="hover-chip">
              <span className="text-sm font-semibold text-ink">{hoverPieza.nombre}</span>
              <span className="num font-mono text-2xs text-ink">{corta(hoverPieza.largo)} × {corta(hoverPieza.ancho)} × {corta(hoverPieza.grueso)}</span>
              {hoverPieza.inferida && <span className="text-2xs text-muted">{COPY.portal.general.inferredShort}</span>}
            </div>
          )}

          <div data-noprint className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start gap-s2 p-s3 lg:grid lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
            <Brand plan={plan} />
            <ViewSwitch view={view} onChange={go} enabled={viewEnabled} />
            <div className="pointer-events-auto ml-auto flex items-center gap-s2 lg:justify-self-end">
              {wide ? (
                <div className="flex h-10 items-stretch border border-line-strong bg-surface" data-testid="action-blocks">
                  <Block label={COPY.portal.blocks.outputs} items={actions.outputs} />
                  <Block label={COPY.portal.blocks.review} items={actions.review} dot={mesa.pendientes.length > 0} divider />
                  <Block label={COPY.portal.blocks.more} items={actions.more} divider />
                </div>
              ) : (
                <Menu label={COPY.portal.blocks.all} className="border border-line-strong bg-surface" triggerClassName="h-10 w-10" items={[
                  ...actions.outputs.map((item) => ({ ...item, group: COPY.portal.blocks.outputs })),
                  ...actions.review.map((item) => ({ ...item, group: COPY.portal.blocks.review })),
                  ...actions.more.map((item) => ({ ...item, group: COPY.portal.blocks.more })),
                ]} />
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
                      <span className="truncate text-sm font-semibold text-ink">{selected.nombre}</span>
                      <span className="num shrink-0 font-mono text-2xs text-ink">{corta(selected.largo)} × {corta(selected.ancho)} × {corta(selected.grueso)}</span>
                    </span>
                  ) : <span className="truncate text-sm text-ink">{COPY.portal.peek(mesa.piezas.length)}</span>}
                  {api.isMock && COPY.mockBadge && <span className="inline-flex h-6 shrink-0 items-center border border-line-strong px-s2 text-2xs font-semibold text-ink">{COPY.mockBadge}</span>}
                </span>
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className={`shrink-0 ${mobileUp ? "" : "rotate-180"}`}><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
              {mobileUp && <div className="scroll-thin min-h-0 overflow-y-auto border-t border-line"><FichaGeneral {...fichaProps} /></div>}
            </div>
          )}
        </section>

        {wide && panelOpen && (
          <aside data-noprint className="scroll-thin w-[320px] shrink-0 overflow-y-auto border-l border-line bg-surface" aria-label={selected ? selected.nombre : COPY.portal.summary}>
            <FichaGeneral {...fichaProps} />
          </aside>
        )}

        {sheet && (
          <div className="absolute inset-0 z-30 flex justify-end">
            <div className="absolute inset-0 bg-[rgb(var(--ink)/0.22)]" onClick={() => setSheet(null)} aria-hidden="true" />
            <div role="dialog" aria-labelledby="sheet-title" className="sheet anim-in relative flex h-full w-full max-w-[1100px] flex-col border-l border-line-strong bg-bg shadow-[-12px_0_32px_rgb(0_0_0/0.14)]">
              <header data-noprint className="flex h-12 shrink-0 items-center justify-between gap-s3 border-b border-line bg-surface pl-s4 pr-s2">
                <h2 id="sheet-title" className="text-md font-semibold text-ink">{COPY.portal.general.sheetsTitle}</h2>
                <span className="flex items-center gap-s1">
                  <button className="inline-flex h-9 items-center px-s3 text-sm font-semibold text-ink hover:bg-sunken" onClick={() => { try { print(); } catch { /* el marco no deja imprimir */ } }}>{COPY.portal.out.sheetsHint}</button>
                  <button className="inline-flex h-9 items-center gap-s2 px-s3 text-sm font-semibold text-ink hover:bg-sunken" onClick={() => setSheet(null)}>
                    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
                    {COPY.portal.closeSheet}
                  </button>
                </span>
              </header>
              <div className="scroll-thin min-h-0 flex-1 overflow-y-auto"><Laminas laminas={mesa.laminas} initial={sheet.lamina} onDownload={download} /></div>
            </div>
          </div>
        )}

        {traceOpen && (
          <div className="absolute inset-0 z-30 flex justify-end">
            <div className="absolute inset-0 bg-[rgb(var(--ink)/0.22)]" onClick={() => setTraceOpen(false)} aria-hidden="true" />
            <div role="dialog" aria-labelledby="trace-title" className="anim-in relative flex h-full w-full max-w-[440px] flex-col border-l border-line-strong bg-surface shadow-[-12px_0_32px_rgb(0_0_0/0.14)]" data-testid="panel-traza">
              <header className="flex h-12 shrink-0 items-center justify-between gap-s3 border-b border-line pl-s4 pr-s2">
                <h2 id="trace-title" className="text-md font-semibold text-ink">{COPY.portal.general.trace}</h2>
                <button className="inline-flex h-9 items-center gap-s2 px-s3 text-sm font-semibold text-ink hover:bg-sunken" onClick={() => setTraceOpen(false)}>
                  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
                  {COPY.portal.closeSheet}
                </button>
              </header>
              <div className="scroll-thin min-h-0 flex-1 overflow-y-auto"><Traza pasos={mesa.traza} /></div>
            </div>
          </div>
        )}
      </div>
      <StepBar active={activeStep} states={states} current={null} wide={wide} onStep={(step) => go(step === "compras" || step === "presupuesto" ? "plano" : step)} extra={indicators} offTitle={COPY.portal.general.noCost} />
    </div>
  );
}
