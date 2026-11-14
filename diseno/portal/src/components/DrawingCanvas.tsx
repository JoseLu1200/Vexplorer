import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent, type ReactNode } from "react";
import type { DrawingExtraction, Point2D } from "../api/types";
import { COPY } from "../copy";
import { fmt, VIEW_LABELS } from "../lib/domain";

/** Qué se ve de cada vista en la pantalla de análisis, según los eventos que han llegado. */
export interface Reveal {
  contour(viewId: string): "hidden" | "faint" | "solid";
  dims(viewId: string): boolean;
  texts(viewId: string): boolean;
}

interface Props {
  drawing: DrawingExtraction;
  primary: Set<string>;
  secondary: Set<string>;
  /** Contornos de la pieza bajo el puntero en la tabla. */
  hover?: Set<string>;
  onSelectContour?: (contourId: string | null) => void;
  onHoverContour?: (contourId: string | null) => void;
  /** view_id → rótulo corto (p. ej. «K1»). */
  viewKeys: Map<string, string>;
  className?: string;
  reveal?: Reveal | null;
  /** Medir y capas. */
  tools?: boolean;
  /** Atajos M, F, + y − mientras no se escribe en un campo. */
  keyboard?: boolean;
  /** «original»: el DXF tal como llega, en línea neutra y por capas del archivo. «clean»: contornos agrupados por pieza y vista. */
  variant?: "clean" | "original";
  /** Píxeles que ocupan arriba y abajo los controles flotantes: el encuadre y los rótulos los respetan. */
  insetTop?: number;
  insetBottom?: number;
  /** Píxeles extra abajo que el encuadre deja libres (la barra de herramientas), sin mover los controles. */
  reserveBottom?: number;
  /** Encuadra estos contornos cada vez que cambia `tick`. */
  focus?: { ids: string[]; tick: number } | null;
}

interface Box { x: number; y: number; w: number; h: number }
type Layers = { contours: boolean; dims: boolean; texts: boolean };
interface Snap { point: Point2D; kind: "vertex" | "edge" | "free" }

/** Martian Mono a la anchura de la landing (wdth 87,5). Avance medido por carácter, en em, para decidir si un rótulo cabe. */
const MONO = "Martian Mono, ui-monospace, monospace";
const MONO_STYLE = { fontVariationSettings: '"wdth" 87.5' } as const;
const MONO_EM = 0.65;
const SNAP_VERTEX_PX = 10;
const SNAP_EDGE_PX = 7;

const typing = (target: EventTarget | null) => {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
};

/** Plano 2D dibujado solo con primitivas seguras del ledger (contornos, cotas y textos). Eje Y del CAD invertido. */
export function DrawingCanvas({ drawing, primary, secondary, hover, onSelectContour, onHoverContour, viewKeys, className = "", reveal = null, tools = false, keyboard = false, variant = "clean", insetTop = 0, insetBottom = 0, reserveBottom = 0, focus = null }: Props) {
  const raw = variant === "original";
  const mm = drawing.coordinate_unit === "mm";
  const unit = mm ? "mm" : "u";
  const P = useCallback((point: Point2D) => ({ x: point.x, y: -point.y }), []);
  const host = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 520 });
  const [layers, setLayers] = useState<Layers>({ contours: true, dims: true, texts: true });
  const [layersOpen, setLayersOpen] = useState(false);
  const [measuring, setMeasuring] = useState(false);
  const [measure, setMeasure] = useState<Point2D[]>([]);
  const [cursor, setCursor] = useState<Snap | null>(null);

  const contourPoints = useCallback((c: DrawingExtraction["contours"][number]) => (mm ? c.points_mm ?? c.points_source : c.points_source), [mm]);
  // Entidades que no forman contorno, cota ni texto (líneas sueltas, ejes, círculos): solo salen en la vista original.
  const loose = useMemo(() => {
    const used = new Set([...drawing.contours.flatMap((c) => c.source_entity_ids), ...drawing.dimension_graphics.map((g) => g.source_entity_id), ...drawing.texts.map((t) => t.source_entity_id)]);
    return drawing.entities.filter((e) => !used.has(e.id) && e.source_points.length > 1).map((e) => ({ id: e.id, layer: e.layer, points: mm ? e.points_mm ?? e.source_points : e.source_points }));
  }, [drawing, mm]);

  const world = useMemo<Box>(() => {
    const xs: number[] = [];
    const ys: number[] = [];
    const add = (point: Point2D | null) => { if (point) { xs.push(point.x); ys.push(-point.y); } };
    drawing.contours.forEach((c) => (mm ? c.points_mm ?? [] : c.points_source).forEach(add));
    loose.forEach((e) => e.points.forEach(add));
    drawing.dimension_graphics.forEach((g) => { add(mm ? g.dimension_start_mm : g.dimension_start_source); add(mm ? g.dimension_end_mm : g.dimension_end_source); add(mm ? g.text_position_mm : g.text_position_source); });
    drawing.texts.forEach((t) => add(mm ? t.position_mm : t.position_source));
    if (!xs.length) return { x: 0, y: 0, w: 100, h: 100 };
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    return { x: minX, y: minY, w: Math.max(maxX - minX, 1), h: Math.max(maxY - minY, 1) };
  }, [drawing, mm, loose]);

  /** Encaja una caja del dibujo en el hueco libre entre los controles de arriba y de abajo. */
  const fitBox = useCallback((box: Box, m: { l: number; r: number; t: number; b: number }): Box => {
    const bottom = insetBottom + reserveBottom;
    const free = Math.max(size.h - insetTop - bottom, 50);
    const aspect = size.w / free;
    let w = box.w + m.l + m.r;
    let h = box.h + m.t + m.b;
    const cx = box.x - m.l + w / 2, cy = box.y - m.t + h / 2;
    if (w / h > aspect) h = w / aspect; else w = h * aspect;
    const perPx = w / size.w;
    return { x: cx - w / 2, y: cy - h / 2 - insetTop * perPx, w, h: h + (insetTop + bottom) * perPx };
  }, [size, insetTop, insetBottom, reserveBottom]);
  // Margen extra a la derecha: los rótulos del DXF empiezan en su punto de inserción y crecen hacia la derecha.
  // En la vista original los textos del DXF van completos y piden más margen a la derecha.
  const fit = useCallback((): Box => fitBox(world, { l: world.w * 0.06, r: world.w * (raw ? 0.16 : 0.08), t: world.h * 0.16, b: world.h * 0.08 }), [world, fitBox, raw]);

  const [view, setView] = useState<Box>(() => fit());
  useLayoutEffect(() => {
    const el = host.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setSize({ w: Math.max(entry.contentRect.width, 50), h: Math.max(entry.contentRect.height, 50) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // Caja encuadrada con Centrar: los cambios de tamaño o de controles reencuadran sobre ella y no sobre todo el plano.
  const focused = useRef<{ box: Box; m: { l: number; r: number; t: number; b: number } } | null>(null);
  const refit = useCallback(() => (focused.current ? fitBox(focused.current.box, focused.current.m) : fit()), [fit, fitBox]);
  const fitAll = useCallback(() => { focused.current = null; setView(fit()); }, [fit]);
  useEffect(() => { setView(refit()); }, [refit]);
  useEffect(() => { focused.current = null; }, [drawing]);
  useEffect(() => {
    if (!focus || !focus.ids.length) return;
    const ids = new Set(focus.ids);
    const pts = drawing.contours.filter((c) => ids.has(c.id)).flatMap((c) => contourPoints(c)).map((p) => ({ x: p.x, y: -p.y }));
    if (!pts.length) return;
    const minX = Math.min(...pts.map((p) => p.x)), maxX = Math.max(...pts.map((p) => p.x));
    const minY = Math.min(...pts.map((p) => p.y)), maxY = Math.max(...pts.map((p) => p.y));
    const box = { x: minX, y: minY, w: Math.max(maxX - minX, 1), h: Math.max(maxY - minY, 1) };
    const m = Math.max(box.w, box.h) * 0.12;
    focused.current = { box, m: { l: m, r: m * 1.5, t: m * 1.6, b: m } };
    setView(fitBox(box, focused.current.m));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.tick]);

  // Capas del archivo para la vista original: la de la entidad de origen de cada contorno, la de cada cota y la de cada texto.
  const entityLayer = useMemo(() => new Map(drawing.entities.map((e) => [e.id, e.layer])), [drawing]);
  const layerOfContour = useCallback((c: DrawingExtraction["contours"][number]) => entityLayer.get(c.source_entity_ids[0]) ?? "0", [entityLayer]);
  const dxfLayers = useMemo(() => {
    const counts = new Map<string, number>();
    const add = (layer: string) => counts.set(layer, (counts.get(layer) ?? 0) + 1);
    drawing.contours.forEach((c) => add(layerOfContour(c)));
    drawing.dimension_graphics.forEach((g) => add(g.layer));
    drawing.texts.forEach((t) => add(t.layer));
    loose.forEach((e) => add(e.layer));
    return [...counts.keys()];
  }, [drawing, layerOfContour, loose]);
  const [hiddenLayers, setHiddenLayers] = useState<Set<string>>(new Set());

  const px = size.w / view.w; // píxeles por unidad
  const u = (pixels: number) => pixels / px;

  const zoomAt = useCallback((factor: number, cx = size.w / 2, cy = size.h / 2) => {
    setView((v) => {
      const wx = v.x + (cx / size.w) * v.w;
      const wy = v.y + (cy / size.h) * v.h;
      const w = Math.min(Math.max(v.w / factor, world.w / 40), world.w * 8);
      const h = (w * v.h) / v.w;
      return { x: wx - (cx / size.w) * w, y: wy - (cy / size.h) * h, w, h };
    });
  }, [size, world]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - rect.left, event.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const stopMeasure = useCallback(() => { setMeasuring(false); setMeasure([]); setCursor(null); }, []);
  useEffect(() => {
    if (!keyboard) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === "m" && tools) { event.preventDefault(); if (measuring) stopMeasure(); else setMeasuring(true); }
      else if (key === "f") { event.preventDefault(); fitAll(); }
      else if (key === "+" || key === "=") { event.preventDefault(); zoomAt(1.3); }
      else if (key === "-" || key === "_") { event.preventDefault(); zoomAt(1 / 1.3); }
      else if (key === "escape" && (measuring || layersOpen)) { setLayersOpen(false); if (measure.length) setMeasure([]); else stopMeasure(); }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [keyboard, tools, measuring, layersOpen, measure.length, fitAll, zoomAt, stopMeasure]);

  // ---- Imán de la medición: vértices de los contornos y extremos de cotas; si no, la arista más cercana ----
  const vertices = useMemo(() => {
    const out: Point2D[] = [];
    drawing.contours.forEach((c) => contourPoints(c).forEach((p) => out.push(p)));
    drawing.dimension_graphics.forEach((g) => {
      for (const p of [mm ? g.extension_start_a_mm : g.extension_start_a_source, mm ? g.extension_start_b_mm : g.extension_start_b_source]) if (p) out.push(p);
    });
    return out;
  }, [drawing, mm, contourPoints]);
  const snapAt = useCallback((x: number, y: number): Snap => {
    let best: Point2D | null = null;
    let bestD = SNAP_VERTEX_PX / px;
    for (const p of vertices) {
      const d = Math.hypot(p.x - x, p.y - y);
      if (d <= bestD) { best = p; bestD = d; }
    }
    if (best) return { point: best, kind: "vertex" };
    let edge: Point2D | null = null;
    let edgeD = SNAP_EDGE_PX / px;
    for (const c of drawing.contours) {
      const pts = contourPoints(c);
      const n = c.closed ? pts.length : pts.length - 1;
      for (let i = 0; i < n; i++) {
        const a = pts[i], b = pts[(i + 1) % pts.length];
        const dx = b.x - a.x, dy = b.y - a.y;
        const len2 = dx * dx + dy * dy || 1;
        const t = Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / len2));
        const q = { x: a.x + t * dx, y: a.y + t * dy };
        const d = Math.hypot(q.x - x, q.y - y);
        if (d <= edgeD) { edge = q; edgeD = d; }
      }
    }
    if (edge) return { point: edge, kind: "edge" };
    return { point: { x, y }, kind: "free" };
  }, [vertices, px, drawing.contours, contourPoints]);

  const toDrawing = (clientX: number, clientY: number) => {
    const rect = host.current!.getBoundingClientRect();
    const wx = view.x + ((clientX - rect.left) / size.w) * view.w;
    const wy = view.y + ((clientY - rect.top) / size.h) * view.h;
    return { x: wx, y: -wy };
  };

  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const onPointerDown = (event: RPointerEvent) => {
    if (event.button !== 0) return;
    drag.current = { x: event.clientX, y: event.clientY, moved: false };
  };
  const onPointerMove = (event: RPointerEvent) => {
    if (measuring) {
      const p = toDrawing(event.clientX, event.clientY);
      setCursor(snapAt(p.x, p.y));
    }
    const d = drag.current;
    // Solo se desplaza con el botón principal pulsado: un movimiento justo después de soltar no es un arrastre.
    if (!d || (event.pointerType === "mouse" && (event.buttons & 1) === 0)) return;
    const dx = event.clientX - d.x;
    const dy = event.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 3) return;
    if (!d.moved) (event.currentTarget as Element).setPointerCapture(event.pointerId);
    d.moved = true;
    d.x = event.clientX;
    d.y = event.clientY;
    setView((v) => ({ ...v, x: v.x - dx / px, y: v.y - dy / px }));
  };
  const onPointerUp = () => { setTimeout(() => { drag.current = null; }, 0); };
  const clickable = () => !drag.current?.moved;
  const onCanvasClick = (event: React.MouseEvent) => {
    if (!clickable()) return;
    if (measuring) {
      const p = toDrawing(event.clientX, event.clientY);
      const snap = snapAt(p.x, p.y);
      setMeasure((list) => (list.length >= 2 ? [snap.point] : [...list, snap.point]));
      return;
    }
    onSelectContour?.(null);
  };

  const path = (points: Point2D[], closed: boolean) =>
    points.map((p, i) => `${i ? "L" : "M"}${P(p).x} ${P(p).y}`).join(" ") + (closed ? " Z" : "");

  const hasSelection = primary.size > 0;
  const narrow = size.w < 600;
  const showTexts = !narrow && px >= 0.9;
  const selectedViews = new Set(drawing.contours.filter((c) => primary.has(c.id)).map((c) => c.view_id));
  const untagged = new Set(drawing.views.filter((v) => v.label === "UNKNOWN" && !viewKeys.has(v.id)).map((v) => v.id));
  const contourState = (viewId: string) => (reveal ? reveal.contour(viewId) : "solid");
  const dimsOn = (viewId: string, layer: string) => (raw ? !hiddenLayers.has(layer) : layers.dims) && (!reveal || reveal.dims(viewId));
  const textsOn = (viewId: string, layer: string) => (raw ? !hiddenLayers.has(layer) : layers.texts) && (!reveal || reveal.texts(viewId));
  const contoursOn = (c: DrawingExtraction["contours"][number]) => (raw ? !hiddenLayers.has(layerOfContour(c)) : layers.contours);

  // Barra de escala: múltiplo «redondo» cercano a 120 px
  const scale = useMemo(() => {
    const target = 120 / px;
    const pow = 10 ** Math.floor(Math.log10(target));
    const step = [1, 2, 5, 10].map((m) => m * pow).find((value) => value >= target * 0.6) ?? pow * 10;
    return { value: step, pixels: step * px };
  }, [px]);

  const [a, b] = measure;
  const end = b ?? (measuring && a ? cursor?.point ?? null : null);
  const distance = a && end ? Math.hypot(end.x - a.x, end.y - a.y) : null;

  return (
    <div className={`overflow-hidden ${className || "relative"}`}>
      <div
        ref={host}
        className={`plan-grid absolute inset-0 touch-none select-none ${measuring ? "cursor-crosshair" : "cursor-grab active:cursor-grabbing"}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onPointerLeave={() => setCursor(null)}
        onClick={onCanvasClick}
        data-measuring={measuring || undefined}
      >
        <svg width={size.w} height={size.h} viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} role="img" aria-labelledby="plan-title" className="block">
          <title id="plan-title">Plano DXF con {drawing.contours.length} contornos y sus cotas</title>
          {/* Recuadro de vista seleccionada */}
          {!raw && layers.contours && drawing.views.filter((v) => selectedViews.has(v.id) && (v.label !== "UNKNOWN" || viewKeys.has(v.id))).map((v) => {
            const box = mm ? v.bounds_mm ?? v.bounds_source : v.bounds_source;
            const m = u(10);
            return (
              <g key={v.id}>
                <rect x={box.min_x - m} y={-box.max_y - m} width={box.max_x - box.min_x + 2 * m} height={box.max_y - box.min_y + 2 * m} fill="none" stroke="rgb(var(--select))" strokeOpacity={0.55} strokeDasharray={`${u(4)} ${u(3)}`} strokeWidth={u(1)} />
                {!narrow && layers.texts && <ViewTag b={{ ...box, max_y: box.max_y + m }} label={viewKeys.get(v.id) ? `${viewKeys.get(v.id)} · ${VIEW_LABELS[v.label]}` : VIEW_LABELS[v.label]} u={u} rightEdge={world.x + world.w} color="rgb(var(--select))" strong />}
              </g>
            );
          })}
          {/* Cotas */}
          {drawing.dimension_graphics.map((g) => {
            if (!dimsOn(g.view_id, g.layer)) return null;
            const ea = mm ? g.extension_start_a_mm : g.extension_start_a_source;
            const eb = mm ? g.extension_start_b_mm : g.extension_start_b_source;
            const s = mm ? g.dimension_start_mm : g.dimension_start_source;
            const e = mm ? g.dimension_end_mm : g.dimension_end_source;
            const t = mm ? g.text_position_mm : g.text_position_source;
            if (!ea || !eb || !s || !e || !t) return null;
            const S = P(s), E = P(e), A = P(ea), B = P(eb);
            const k = u(4);
            const active = selectedViews.has(g.view_id);
            const color = active ? "rgb(var(--select))" : raw ? "rgb(var(--muted))" : "rgb(var(--dim))";
            const horizontal = Math.abs(E.y - S.y) < Math.abs(E.x - S.x);
            const label = g.display_text.replace(" mm", "");
            // La cota se rotula solo si su texto (12 px) cabe en la línea a este zoom.
            const fits = Math.hypot(E.x - S.x, E.y - S.y) * px >= label.length * 12 * MONO_EM + 12;
            // Las cotas en cadena medidas sobre la geometría se ocultan enteras cuando su rótulo no cabe.
            if (g.id.startsWith("cadena:") && (!fits || px < 0.2)) return null;
            // El texto va por el lado de la línea de cota opuesto al contorno (las líneas de extensión parten del contorno).
            const awayDown = horizontal ? A.y < S.y : false;
            const awayLeft = !horizontal ? A.x > S.x : false;
            const mid = { x: (S.x + E.x) / 2, y: (S.y + E.y) / 2 };
            const tx = horizontal ? mid.x : awayLeft ? mid.x - u(4) : mid.x + u(13);
            const ty = horizontal ? (awayDown ? mid.y + u(14) : mid.y - u(4)) : mid.y;
            return (
              <g key={g.id} stroke={color} strokeWidth={u(0.9)} fill="none" className={reveal ? "anim-in" : undefined}>
                <path d={`M${A.x} ${A.y} L${S.x} ${S.y} M${B.x} ${B.y} L${E.x} ${E.y} M${S.x} ${S.y} L${E.x} ${E.y}`} opacity={hasSelection && !active ? 0.5 : 1} />
                <path d={`M${S.x - k} ${S.y + k} L${S.x + k} ${S.y - k} M${E.x - k} ${E.y + k} L${E.x + k} ${E.y - k}`} strokeWidth={u(1.2)} opacity={hasSelection && !active ? 0.5 : 1} />
                {fits && (
                <text
                  x={tx} y={ty} fontSize={u(12)} fill={color} textAnchor="middle" dominantBaseline="auto"
                  stroke="rgb(var(--canvas))" strokeWidth={u(3.5)} strokeLinejoin="round"
                  fontFamily={MONO} style={{ ...MONO_STYLE, paintOrder: "stroke" }} transform={horizontal ? undefined : `rotate(-90 ${tx} ${ty})`}
                >
                  {label}
                </text>)}
              </g>
            );
          })}
          {/* Con poco zoom los textos del DXF se pisan: se sustituyen por una etiqueta por vista */}
          {!raw && !showTexts && !narrow && drawing.views.filter((v) => !selectedViews.has(v.id) && (v.label !== "UNKNOWN" || viewKeys.has(v.id)) && layers.texts && (!reveal || reveal.texts(v.id))).map((v) => {
            const box = mm ? v.bounds_mm ?? v.bounds_source : v.bounds_source;
            return (
              <ViewTag key={`tag-${v.id}`} b={box} label={viewKeys.get(v.id) ? `${viewKeys.get(v.id)} · ${VIEW_LABELS[v.label]}` : VIEW_LABELS[v.label]} u={u} rightEdge={world.x + world.w} color="rgb(var(--ink))" />
            );
          })}
          {/* Textos del DXF */}
          {drawing.texts.map((t) => {
            // Con poco zoom los textos ceden su sitio a la etiqueta de vista; las vistas sin rótulo ni clave no la tienen y conservan sus textos.
            if (!showTexts && !raw && !untagged.has(t.view_id)) return null;
            if (!textsOn(t.view_id, t.layer)) return null;
            const p = mm ? t.position_mm : t.position_source;
            if (!p) return null;
            const T = P(p);
            const active = selectedViews.has(t.view_id);
            return (
              <text key={t.id} x={T.x} y={T.y} fontSize={u(11)} fill={active ? "rgb(var(--select))" : "rgb(var(--ink))"} fontFamily={MONO} style={MONO_STYLE} opacity={hasSelection && !active ? 0.5 : 1}>
                {t.text}
              </text>
            );
          })}
          {raw && loose.map((e) => (hiddenLayers.has(e.layer) ? null : (
            <path key={e.id} d={path(e.points, false)} fill="none" stroke="rgb(var(--muted))" strokeWidth={u(0.9)} opacity={hasSelection ? 0.5 : 1} pointerEvents="none" />
          )))}
          {/* Contornos */}
          {drawing.contours.map((c) => {
            if (!contoursOn(c)) return null;
            const state = contourState(c.view_id);
            if (state === "hidden") return null;
            const points = contourPoints(c);
            const isPrimary = primary.has(c.id);
            const isHover = !isPrimary && !!hover?.has(c.id);
            const isSecondary = !isPrimary && !isHover && secondary.has(c.id);
            if (state === "faint") {
              return <path key={c.id} d={path(points, c.closed)} fill="none" stroke="rgb(var(--canvas-ink))" strokeOpacity={0.5} strokeWidth={u(1)} strokeDasharray={`${u(5)} ${u(4)}`} />;
            }
            const interactive = !reveal && !!onSelectContour;
            return (
              <path
                key={c.id}
                d={path(points, c.closed)}
                pathLength={reveal ? 1 : undefined}
                fill={isPrimary ? "rgb(var(--wood) / 0.32)" : isHover ? "rgb(var(--wood) / 0.2)" : isSecondary ? "rgb(var(--wood) / 0.12)" : "rgb(var(--canvas) / 0.001)"}
                stroke={isPrimary || isHover ? "rgb(var(--select))" : raw ? "rgb(var(--ink))" : "rgb(var(--canvas-ink))"}
                strokeWidth={u(isPrimary ? 2.25 : isHover ? 2 : raw ? 1 : 1.4)}
                strokeLinejoin="round"
                opacity={hasSelection && !isPrimary && !isSecondary && !isHover ? 0.55 : 1}
                className={reveal ? "draw-in" : interactive ? (measuring ? "" : "cursor-pointer") : undefined}
                onClick={interactive ? (event) => { if (measuring) return; event.stopPropagation(); if (clickable()) onSelectContour!(c.id); } : undefined}
                onPointerEnter={interactive && onHoverContour ? () => onHoverContour(c.id) : undefined}
                onPointerLeave={interactive && onHoverContour ? () => onHoverContour(null) : undefined}
                role={interactive ? "button" : undefined}
                aria-label={interactive ? `Contorno ${c.id}` : undefined}
                aria-pressed={interactive ? isPrimary : undefined}
                data-contour={c.id}
              />
            );
          })}
          {/* Medición */}
          {measuring && cursor && cursor.kind !== "free" && (
            cursor.kind === "vertex"
              ? <rect x={P(cursor.point).x - u(5)} y={P(cursor.point).y - u(5)} width={u(10)} height={u(10)} fill="none" stroke="rgb(var(--select))" strokeWidth={u(1.5)} />
              : <path d={`M${P(cursor.point).x - u(5)} ${P(cursor.point).y - u(5)} L${P(cursor.point).x + u(5)} ${P(cursor.point).y + u(5)} M${P(cursor.point).x + u(5)} ${P(cursor.point).y - u(5)} L${P(cursor.point).x - u(5)} ${P(cursor.point).y + u(5)}`} stroke="rgb(var(--select))" strokeWidth={u(1.5)} />
          )}
          {a && (
            <g pointerEvents="none">
              {end && <line x1={P(a).x} y1={P(a).y} x2={P(end).x} y2={P(end).y} stroke="rgb(var(--select))" strokeWidth={u(1.5)} strokeDasharray={b ? undefined : `${u(6)} ${u(4)}`} />}
              {[a, b].filter(Boolean).map((p, i) => <circle key={i} cx={P(p!).x} cy={P(p!).y} r={u(3.5)} fill="rgb(var(--canvas))" stroke="rgb(var(--select))" strokeWidth={u(1.5)} />)}
              {end && distance !== null && distance > 0 && (
                <text
                  x={(P(a).x + P(end).x) / 2} y={(P(a).y + P(end).y) / 2 - u(8)} fontSize={u(12.5)} textAnchor="middle" fill="rgb(var(--select))"
                  stroke="rgb(var(--canvas))" strokeWidth={u(4)} strokeLinejoin="round" fontFamily={MONO} style={{ ...MONO_STYLE, paintOrder: "stroke", fontWeight: 560 }}
                >
                  {fmt(Math.round(distance * 10) / 10)}
                </text>
              )}
            </g>
          )}
        </svg>
      </div>

      {!mm && (
        <div className="pointer-events-none absolute left-s3" style={{ top: insetTop + 12 }}>
          <span className="inline-flex h-7 items-center border border-line-strong bg-surface px-s2 text-sm text-ink">{COPY.workspace.unitUnknown}</span>
        </div>
      )}
      {measuring && (
        <div style={{ top: insetTop + (mm ? 12 : 48) }} className={`absolute left-s3 flex min-w-[200px] flex-col gap-s1 border border-line-strong bg-surface px-s3 py-s2`} role="status" aria-live="polite" data-testid="measure-readout">
          {distance !== null && distance > 0 ? (
            <>
              <span className="flex items-baseline justify-between gap-s3">
                <span className="text-sm text-muted">{COPY.tools.distance}</span>
                <span className="num font-mono text-[15px] font-medium text-ink" data-testid="measure-value">{fmt(Math.round(distance * 10) / 10)} <span className="text-2xs text-muted">{unit}</span></span>
              </span>
              <span className="num font-mono text-2xs text-muted">Δx {fmt(Math.round(Math.abs(end!.x - a!.x) * 10) / 10)} · Δy {fmt(Math.round(Math.abs(end!.y - a!.y) * 10) / 10)}</span>
            </>
          ) : (
            <span className="text-sm text-muted">{COPY.tools.measureHint}</span>
          )}
          {cursor && <span className="num font-mono text-2xs text-muted">x {fmt(Math.round(cursor.point.x * 10) / 10)} · y {fmt(Math.round(cursor.point.y * 10) / 10)}{cursor.kind !== "free" ? ` · ${cursor.kind === "vertex" ? COPY.tools.snapVertex : COPY.tools.snapEdge}` : ""}</span>}
        </div>
      )}
      <div className="pointer-events-none absolute left-s3 flex flex-col items-start gap-s1" style={{ bottom: insetBottom + 12 }}>
        <span className="num bg-canvas pr-s1 font-mono text-2xs text-muted">{fmt(scale.value)} {unit}</span>
        <span className="block h-1.5 border-x border-b border-muted" style={{ width: scale.pixels }} aria-hidden="true" />
      </div>
      {/* Herramientas de visor en un solo bloque: medir, capas, zoom y encajar. */}
      <div className="absolute right-s3 flex items-stretch border border-line-strong bg-surface" style={{ bottom: insetBottom + 12 }} role="toolbar" aria-label={COPY.tools.block}>
        {tools && (
          <>
            <ToolButton pressed={measuring} onClick={() => (measuring ? stopMeasure() : setMeasuring(true))} label={COPY.tools.measure} shortcut="M">
              <path d="M1.5 9.5 9.5 1.5l3 3-8 8Z M4 7l1.2 1.2 M5.8 5.2 7 6.4 M7.6 3.4l1.2 1.2" />
            </ToolButton>
            <div className="relative flex border-l border-l-line">
              <ToolButton pressed={layersOpen} onClick={() => setLayersOpen((v) => !v)} label={COPY.tools.layers} expanded={layersOpen}>
                <path d="M7 1.8 12.5 4.6 7 7.4 1.5 4.6Z M1.5 7.2 7 10l5.5-2.8 M1.5 9.8 7 12.6l5.5-2.8" />
              </ToolButton>
              {layersOpen && (
                <fieldset className="absolute bottom-[calc(100%+8px)] right-0 z-10 flex w-[200px] flex-col border border-line-strong bg-surface py-s1">
                  <legend className="sr-only">{COPY.tools.layers}</legend>
                  {raw ? dxfLayers.map((layer) => (
                    <label key={layer} className="flex h-9 cursor-pointer items-center gap-s2 px-s3 text-ink hover:bg-sunken">
                      <input type="checkbox" className="accent-[rgb(var(--ink))]" checked={!hiddenLayers.has(layer)} onChange={(event) => setHiddenLayers((value) => { const next = new Set(value); if (event.target.checked) next.delete(layer); else next.add(layer); return next; })} />
                      <span className="num truncate font-mono text-2xs">{layer}</span>
                    </label>
                  )) : (["contours", "dims", "texts"] as const).map((key) => (
                    <label key={key} className="flex h-9 cursor-pointer items-center gap-s2 px-s3 text-sm text-ink hover:bg-sunken">
                      <input type="checkbox" className="accent-[rgb(var(--ink))]" checked={layers[key]} onChange={(event) => setLayers((value) => ({ ...value, [key]: event.target.checked }))} />
                      {COPY.tools[key]}
                    </label>
                  ))}
                </fieldset>
              )}
            </div>
          </>
        )}
        <button className={`btn btn-ghost btn-icon rounded-none ${tools ? "border-l border-l-line" : ""}`} onClick={() => zoomAt(1 / 1.3)} aria-label={COPY.workspace.zoomOut} title={`${COPY.workspace.zoomOut} (−)`}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M2.5 7h9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
        </button>
        <button className="btn btn-ghost btn-icon rounded-none border-l border-l-line" onClick={() => zoomAt(1.3)} aria-label={COPY.workspace.zoomIn} title={`${COPY.workspace.zoomIn} (+)`}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 2.5v9M2.5 7h9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
        </button>
        <ToolButton pressed={false} onClick={fitAll} label={COPY.workspace.fit} shortcut="F" className="border-l border-l-line">
          <path d="M1.5 4.5v-3h3M9.5 1.5h3v3M12.5 9.5v3h-3M4.5 12.5h-3v-3" />
        </ToolButton>
      </div>
    </div>
  );
}

export function ToolButton({ pressed, onClick, label, shortcut, expanded, disabled = false, className = "", children }: { pressed: boolean; onClick: () => void; label: string; shortcut?: string; expanded?: boolean; disabled?: boolean; className?: string; children: ReactNode }) {
  return (
    <button
      className={`inline-flex h-9 items-center gap-s2 px-s3 text-sm font-semibold disabled:cursor-not-allowed disabled:text-faint ${pressed ? "bg-ink text-surface" : "text-ink enabled:hover:bg-sunken"} ${className}`}
      onClick={onClick}
      disabled={disabled}
      aria-pressed={expanded === undefined && !disabled ? pressed : undefined}
      aria-expanded={expanded}
      title={shortcut ? `${label} (${shortcut})` : label}
    >
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">{children}</svg>
      <span className="hidden sm:inline">{label}</span>
      <span className="sr-only sm:hidden">{label}</span>
    </button>
  );
}

/**
 * Etiqueta de vista fuera del contorno, encima, con una línea guía corta hasta su esquina.
 * En las vistas pegadas al borde derecho se alinea por la derecha para no salirse del lienzo.
 */
function ViewTag({ b, label, u, rightEdge, color, strong = false }: { b: { min_x: number; max_x: number; max_y: number }; label: string; u: (px: number) => number; rightEdge: number; color: string; strong?: boolean }) {
  const width = u(label.length * 11.5 * MONO_EM);
  const alignRight = b.min_x + width > rightEdge + u(8);
  const anchorX = alignRight ? b.max_x : b.min_x;
  const top = -b.max_y;
  return (
    <g>
      <path d={`M${anchorX} ${top} L${anchorX} ${top - u(10)}`} stroke={color} strokeWidth={u(1)} />
      <text x={alignRight ? anchorX - u(3) : anchorX + u(3)} y={top - u(12)} textAnchor={alignRight ? "end" : "start"} fontSize={u(11.5)} fontWeight={strong ? 560 : 400} fill={color} fontFamily={MONO} style={MONO_STYLE}>
        {label}
      </text>
    </g>
  );
}
