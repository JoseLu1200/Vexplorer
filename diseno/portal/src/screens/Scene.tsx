import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { api } from "../api";
import type { ReconstructionScene, SceneObject } from "../api/types";
import { COPY } from "../copy";
import { ToolButton } from "../components/DrawingCanvas";
import { ErrorNote, LoadingBar } from "../components/ui";
import { useApi } from "../lib/useApi";
import { useStore } from "../state";

/**
 * Vista 3D de la mesa de trabajo: la escena de GET /runs/{id}/scene de la revisión vigente, sin volúmenes inventados.
 * Si la revisión no tiene escena (antes de confirmar un montaje) se dice y se ofrece ir a Revisión.
 */
export default function SceneView({ selectedProposal, hoverProposal, onPick, onHover, insetTop = 0, insetBottom = 0 }: {
  selectedProposal: string | null; hoverProposal: string | null; onPick: (proposal: string | null) => void; onHover: (proposal: string | null) => void;
  insetTop?: number; insetBottom?: number;
}) {
  const { current, run, go } = useStore();
  const scene = useApi(current && run ? () => api.getScene(run.id, current.result_revision) : null, [run?.id, current?.result_revision]);
  const [resetTick, setResetTick] = useState(0);
  const data = scene.data;
  const empty = data && (data.state === "unavailable" || data.objects.length === 0);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const el = event.target as HTMLElement | null;
      if (event.ctrlKey || event.metaKey || event.altKey || (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (event.key.toLowerCase() === "f") { event.preventDefault(); setResetTick((value) => value + 1); }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);

  return (
    <section className="absolute inset-0 bg-block" aria-label={COPY.portal.viewTitles.esquema}>
      {scene.loading && <div className="absolute inset-x-0" style={{ top: insetTop }}><LoadingBar /></div>}
      {scene.error && <div className="absolute inset-x-s4" style={{ top: insetTop + 12 }}><ErrorNote error={scene.error} onRetry={scene.retry} /></div>}
      {data && !empty && <Viewer scene={data} selectedProposal={selectedProposal} hoverProposal={hoverProposal} onPick={onPick} onHover={onHover} resetTick={resetTick} />}
      {empty && (
        <div className="absolute inset-0 flex items-center justify-center px-s4">
          <div className="flex max-w-[340px] flex-col items-start gap-s3 border border-on-block-2 bg-block px-s4 py-s4 text-on-block">
            <p className="text-md font-semibold">{COPY.portal.sceneOff}</p>
            <p className="text-sm text-on-block-2">{COPY.portal.sceneOffHint}</p>
            <button className="btn btn-sm !border-on-block !bg-on-block !text-block hover:!shadow-none" onClick={() => go("revision")}>{COPY.portal.sceneGo}</button>
          </div>
        </div>
      )}
      {data && !empty && (
        <span className="pointer-events-none absolute left-s3 border border-on-block-2 bg-block px-s2 py-s1 text-sm font-semibold text-on-block" style={{ bottom: insetBottom + 12 }}>{COPY.portal.notForManufacture}</span>
      )}
      <div className="absolute right-s3 flex items-stretch border border-line-strong bg-surface" style={{ bottom: insetBottom + 12 }} role="toolbar" aria-label={COPY.tools.block}>
        <ToolButton pressed={false} disabled onClick={() => undefined} label={COPY.tools.measure}>
          <path d="M1.5 9.5 9.5 1.5l3 3-8 8Z M4 7l1.2 1.2 M5.8 5.2 7 6.4 M7.6 3.4l1.2 1.2" />
        </ToolButton>
        <ToolButton pressed={false} disabled onClick={() => undefined} label={COPY.tools.layers} className="border-l border-l-line">
          <path d="M7 1.8 12.5 4.6 7 7.4 1.5 4.6Z M1.5 7.2 7 10l5.5-2.8 M1.5 9.8 7 12.6l5.5-2.8" />
        </ToolButton>
        <ToolButton pressed={false} disabled={!data || !!empty} onClick={() => setResetTick((value) => value + 1)} label={COPY.workspace.fit} shortcut="F" className="border-l border-l-line">
          <path d="M1.5 4.5v-3h3M9.5 1.5h3v3M12.5 9.5v3h-3M4.5 12.5h-3v-3" />
        </ToolButton>
      </div>
    </section>
  );
}

/**
 * Pieza colocada a una altura que nadie ha medido. El contrato marca estas baldas como human_selected,
 * pero su placement_basis dice «height not observed»; se usan los dos para no perder ningún caso.
 */
export function isHypotheticalHeight(object: SceneObject) {
  return object.placement_status === "hypothesis" || /height not observed/i.test(object.placement_basis);
}

function cssColor(name: string): THREE.Color {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim().split(/\s+/).map(Number);
  return new THREE.Color(raw[0] / 255, raw[1] / 255, raw[2] / 255);
}

export function Viewer({ scene, selectedProposal, hoverProposal, onPick, onHover, resetTick }: {
  scene: ReconstructionScene; selectedProposal: string | null; hoverProposal: string | null;
  onPick: (proposal: string | null) => void; onHover: (proposal: string | null) => void; resetTick: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const meshes = useRef<{ mesh: THREE.Mesh; edges: THREE.LineSegments; object: SceneObject; hypothetical: boolean }[]>([]);
  const overlay = useRef<HTMLDivElement>(null);
  const labels = useRef<{ el: HTMLElement; at: THREE.Vector3; kind: "hyp" | "dim" }[]>([]);
  const dimGroup = useRef<THREE.Group | null>(null);
  const redraw = useRef<() => void>(() => {});
  const reset = useRef<() => void>(() => {});
  const handlers = useRef({ onPick, onHover });
  handlers.current = { onPick, onHover };
  const [failed, setFailed] = useState(false);
  const { theme } = useStore();

  const bounds = useMemo(() => {
    const box = new THREE.Box3();
    scene.objects.forEach((o) => box.expandByPoint(new THREE.Vector3(o.bbox_mm.min.x, o.bbox_mm.min.y, o.bbox_mm.min.z)).expandByPoint(new THREE.Vector3(o.bbox_mm.max.x, o.bbox_mm.max.y, o.bbox_mm.max.z)));
    return box;
  }, [scene]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    } catch {
      setFailed(true);
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const three = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 10, 50000);
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z) || 1000;
    const controls = new OrbitControls(camera, renderer.domElement);
    // Coordenadas del backend: x ancho, y alto, z fondo con origen delante-izquierda-abajo; la cámara mira desde delante (+z invertido).
    reset.current = () => {
      camera.position.set(center.x + radius * 1.25, center.y + radius * 0.75, center.z - radius * 2.1);
      controls.target.copy(center);
      controls.update();
    };
    reset.current();
    controls.enableDamping = true;

    three.add(new THREE.HemisphereLight(0xffffff, 0x888888, 1.6));
    const light = new THREE.DirectionalLight(0xffffff, 1.4);
    light.position.set(center.x + radius, center.y + radius * 2, center.z - radius * 1.5);
    three.add(light);

    // Bloque cobalto de la landing: trazo claro sobre cobalto liso; la rejilla del suelo, apagada.
    const ink = new THREE.Color("#4a2f1c"); // aristas en marrón oscuro, no blancas
    const panel = cssColor("on-block");
    const floor = cssColor("on-block-2").lerp(cssColor("block"), 0.72);
    const grid = new THREE.GridHelper(radius * 2.4, 24, floor, floor);
    grid.position.set(center.x, 0, center.z);
    three.add(grid);

    labels.current.forEach((item) => item.el.remove());
    labels.current = [];
    meshes.current = scene.objects.map((object) => {
      const geometry = new THREE.BoxGeometry(object.dimensions_mm.x, object.dimensions_mm.y, object.dimensions_mm.z);
      const hypothetical = isHypotheticalHeight(object);
      const material = new THREE.MeshStandardMaterial({ color: panel, roughness: 0.9, metalness: 0, transparent: true, opacity: hypothetical ? 0.04 : 0.16, depthWrite: false });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(object.position_mm.x + object.dimensions_mm.x / 2, object.position_mm.y + object.dimensions_mm.y / 2, object.position_mm.z + object.dimensions_mm.z / 2);
      const edgeMaterial = hypothetical
        ? new THREE.LineDashedMaterial({ color: ink, dashSize: 42, gapSize: 30 })
        : new THREE.LineBasicMaterial({ color: ink });
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), edgeMaterial);
      if (hypothetical) edges.computeLineDistances();
      edges.position.copy(mesh.position);
      three.add(mesh, edges);
      if (hypothetical && overlay.current) {
        const label = document.createElement("span");
        label.className = "pointer-events-none absolute left-0 top-0 whitespace-nowrap border border-dashed border-on-block-2 bg-block px-1.5 py-0.5 text-xs text-on-block";
        label.textContent = COPY.portal.hypothetical;
        overlay.current.appendChild(label);
        labels.current.push({ el: label, at: new THREE.Vector3(mesh.position.x, object.bbox_mm.max.y + 45, object.bbox_mm.min.z), kind: "hyp" });
      }
      return { mesh, edges, object, hypothetical };
    });
    dimGroup.current = new THREE.Group();
    three.add(dimGroup.current);

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let frame = 0;
    const place = () => {
      const w = el.clientWidth, h = el.clientHeight;
      labels.current.forEach(({ el: label, at }) => {
        const v = at.clone().project(camera);
        label.style.transform = `translate(${((v.x + 1) / 2) * w}px, ${((1 - v.y) / 2) * h}px) translate(-50%, -50%)`;
        label.style.display = v.z > 1 ? "none" : "";
      });
    };
    const loop = () => { controls.update(); renderer.render(three, camera); place(); frame = requestAnimationFrame(loop); };
    loop();
    redraw.current = () => renderer.render(three, camera);

    const raycaster = new THREE.Raycaster();
    const pick = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      raycaster.setFromCamera(new THREE.Vector2(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1), camera);
      const hit = raycaster.intersectObjects(meshes.current.map((item) => item.mesh))[0];
      return hit ? meshes.current.find((item) => item.mesh === hit.object)?.object.proposal_id ?? null : null;
    };
    let downAt = { x: 0, y: 0 };
    let dragging = false;
    let hovered: string | null = null;
    let pending = 0;
    const onDown = (event: PointerEvent) => { downAt = { x: event.clientX, y: event.clientY }; dragging = true; };
    const onUp = (event: PointerEvent) => {
      dragging = false;
      if (Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y) > 4) return;
      handlers.current.onPick(pick(event));
    };
    // Puntero sobre un volumen: se ilumina su pieza en la lista y en el plano. Un cálculo por fotograma como mucho.
    const onMove = (event: PointerEvent) => {
      if (dragging || pending) return;
      pending = requestAnimationFrame(() => {
        pending = 0;
        const found = pick(event);
        renderer.domElement.style.cursor = found ? "pointer" : "grab";
        if (found !== hovered) { hovered = found; handlers.current.onHover(found); }
      });
    };
    const onLeave = () => { if (hovered) { hovered = null; handlers.current.onHover(null); } };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    return () => {
      cancelAnimationFrame(frame);
      cancelAnimationFrame(pending);
      ro.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      renderer.dispose();
      labels.current.forEach((item) => item.el.remove());
      labels.current = [];
      el.removeChild(renderer.domElement);
    };
  }, [scene, bounds, theme]);

  useEffect(() => { if (resetTick) reset.current(); }, [resetTick]);

  useEffect(() => {
    // Selección en tablero (wood), el acento de la landing, que se distingue del trazo claro sobre cobalto.
    const wood = cssColor("wood");
    const ink = new THREE.Color("#4a2f1c"); // aristas en marrón oscuro, no blancas
    const panel = cssColor("on-block");
    const any = meshes.current.some(({ object }) => object.proposal_id === selectedProposal);
    meshes.current.forEach(({ mesh, edges, object, hypothetical }) => {
      const active = object.proposal_id === selectedProposal;
      const hot = !active && object.proposal_id === hoverProposal;
      const material = mesh.material as THREE.MeshStandardMaterial;
      material.color = active || hot ? wood : panel;
      material.opacity = active ? (hypothetical ? 0.3 : 0.55) : hot ? 0.3 : any ? (hypothetical ? 0.02 : 0.08) : hypothetical ? 0.04 : 0.16;
      const line = edges.material as THREE.LineBasicMaterial;
      line.color = active || hot ? wood : ink;
      line.transparent = true;
      line.opacity = active || hot || !any ? 1 : 0.35;
    });
    // Cotas x, y, z sobre el primer volumen seleccionado: líneas por fuera de sus aristas y el valor que trae la escena.
    labels.current.filter((item) => item.kind === "dim").forEach((item) => item.el.remove());
    labels.current = labels.current.filter((item) => item.kind !== "dim");
    const group = dimGroup.current;
    if (group) {
      group.clear();
      const target = meshes.current.find(({ object }) => object.proposal_id === selectedProposal)?.object;
      if (target && overlay.current) {
        const { min, max } = target.bbox_mm;
        const off = 40;
        const segments: [THREE.Vector3, THREE.Vector3, number, string][] = [
          [new THREE.Vector3(min.x, min.y - off, min.z - off), new THREE.Vector3(max.x, min.y - off, min.z - off), target.dimensions_mm.x, "x"],
          [new THREE.Vector3(min.x - off, min.y, min.z - off), new THREE.Vector3(min.x - off, max.y, min.z - off), target.dimensions_mm.y, "y"],
          [new THREE.Vector3(max.x + off, min.y - off, min.z), new THREE.Vector3(max.x + off, min.y - off, max.z), target.dimensions_mm.z, "z"],
        ];
        const lineMaterial = new THREE.LineBasicMaterial({ color: ink });
        segments.forEach(([a, b, value, axis]) => {
          group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, b]), lineMaterial));
          const label = document.createElement("span");
          label.className = "num pointer-events-none absolute left-0 top-0 whitespace-nowrap border border-on-block-2 bg-block px-1.5 py-0.5 font-mono text-2xs text-on-block";
          label.textContent = `${axis} ${new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 }).format(value)}`;
          overlay.current!.appendChild(label);
          labels.current.push({ el: label, at: a.clone().add(b).multiplyScalar(0.5), kind: "dim" });
        });
      }
    }
    redraw.current();
  }, [selectedProposal, hoverProposal, scene, theme]);

  if (failed) return <p className="p-s5 text-base text-on-block">{COPY.scene.webgl}</p>;
  return (
    <>
      <div ref={host} className="absolute inset-0" role="img" aria-label="Esquema de volúmenes de la revisión" />
      <div ref={overlay} className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true" />
    </>
  );
}
