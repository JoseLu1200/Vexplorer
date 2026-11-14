import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { COPY } from "../copy";
import { useStore } from "../state";

/** Caja en coordenadas de three.js (y hacia arriba), en mm. `pieza` agrupa las ocurrencias de una misma pieza. */
export interface BoxItem {
  id: string; pieza: string; min: { x: number; y: number; z: number }; size: { x: number; y: number; z: number }; dashed: boolean;
  /** La caja entra en una penetración del validador de montaje: trazo y relleno en color de peligro. */
  conflict?: boolean;
}

function cssColor(name: string): THREE.Color {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim().split(/\s+/).map(Number);
  return new THREE.Color(raw[0] / 255, raw[1] / 255, raw[2] / 255);
}
const NUM = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });
const NO_COLORS: Record<string, string> = {};

/**
 * Visor 3D de cajas sobre el bloque cobalto: trazo claro, la pieza elegida en tablero y lo estimado en discontinuo.
 * El puntero sobre una caja ilumina su pieza; el clic la selecciona.
 */
export function BoxViewer({ boxes, selected, hover, onPick, onHover, resetTick, front = 1, overhead = false, glbUrl = null, solid = false, colors = NO_COLORS, exploded = false, shiftX = 0, visibles = null }: {
  boxes: BoxItem[]; selected: string | null; hover: string | null; onPick: (pieza: string | null) => void; onHover: (pieza: string | null) => void; resetTick: number;
  /** Lado desde el que mira la cámara en z: 1 para +z, -1 cuando el frente del mueble está en z = 0 (vistas montadas). */
  front?: 1 | -1;
  /** Piezas tumbadas en fila (piezas sin montar): la cámara mira más desde arriba y más cerca. */
  overhead?: boolean;
  /**
   * GLB del montaje (Construcción 3D: metros, y hacia arriba, un nodo por componente con su id). Si carga, sustituye a
   * las cajas con la misma selección por nombre de nodo; si no carga, se quedan las cajas, que son la misma geometría.
   */
  glbUrl?: string | null;
  /** Sólido con caras rellenas, luz ambiente y direccional y aristas finas (visor de Construcción 3D). */
  solid?: boolean;
  /** Color de cada pieza en modo sólido (p. ej. por confianza). */
  colors?: Record<string, string>;
  /** Despiece: separa cada pieza del centro un 18 % de su mayor medida, como el visor del equipo. */
  exploded?: boolean;
  /** Píxeles que se desplaza el centro del encuadre a la derecha (panel abierto encima). */
  shiftX?: number;
  /** Solo se ven estas piezas (montaje que se va construyendo); null para todas. */
  visibles?: Set<string> | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const meshes = useRef<{ mesh: THREE.Mesh; edges: THREE.LineSegments; box: BoxItem; base?: THREE.Vector3; escala?: number }[]>([]);
  const labels = useRef<{ el: HTMLElement; at: THREE.Vector3 }[]>([]);
  const dimGroup = useRef<THREE.Group | null>(null);
  const redraw = useRef<() => void>(() => {});
  const reset = useRef<() => void>(() => {});
  const handlers = useRef({ onPick, onHover });
  handlers.current = { onPick, onHover };
  const [failed, setFailed] = useState(false);
  const [glbTick, setGlbTick] = useState(0);
  const { theme } = useStore();

  const bounds = useMemo(() => {
    const b = new THREE.Box3();
    boxes.forEach((c) => b.expandByPoint(new THREE.Vector3(c.min.x, c.min.y, c.min.z)).expandByPoint(new THREE.Vector3(c.min.x + c.size.x, c.min.y + c.size.y, c.min.z + c.size.z)));
    return b;
  }, [boxes]);

  useEffect(() => {
    const el = host.current;
    if (!el || !boxes.length) return;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true }); } catch { setFailed(true); return; }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const three = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 10, 200000);
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z) || 1000;
    const controls = new OrbitControls(camera, renderer.domElement);
    reset.current = () => {
      if (overhead) {
        // Distancia para que la fila entera quepa a lo ancho, mirando desde unos 50° de altura.
        const aspect = el.clientWidth / Math.max(el.clientHeight, 1);
        const d = Math.max(size.x * 1.1, size.z * 1.6) / (2 * Math.tan((15 * Math.PI) / 180) * Math.max(aspect, 0.5));
        camera.position.set(center.x, center.y + d * 0.75, center.z + front * d * 0.66);
      }
      // Sólido: el encuadre del visor de Construcción 3D, en diagonal y más lejos.
      else if (solid) camera.position.set(center.x + radius * 1.5, center.y + radius * 1.1, center.z + front * radius * 2.1);
      else camera.position.set(center.x + radius * 0.9, center.y + radius * 0.8, center.z + front * radius * 1.9);
      controls.target.copy(center);
      controls.update();
    };
    reset.current();
    controls.enableDamping = true;
    if (solid) {
      // Luces del visor de Construcción 3D del equipo: hemisférica y direccional.
      three.add(new THREE.HemisphereLight(0xffffff, 0x4b5563, 2.2));
      const directional = new THREE.DirectionalLight(0xffffff, 2.5);
      directional.position.set(center.x + radius, center.y + radius * 2, center.z + radius * 3);
      three.add(directional);
    } else three.add(new THREE.HemisphereLight(0xffffff, 0x888888, 1.6));
    const solidMaterial = (pieza: string) => new THREE.MeshStandardMaterial({ color: new THREE.Color(colors[pieza] ?? "#b9c2c9"), roughness: 0.72, metalness: 0, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const solidEdges = () => new THREE.LineBasicMaterial({ color: 0x4a2f1c });
    const ink = new THREE.Color("#4a2f1c"); // aristas en marrón oscuro, no blancas
    const floor = cssColor("on-block-2").lerp(cssColor("block"), 0.72);
    const grid = new THREE.GridHelper(radius * 2.4, 24, floor, floor);
    grid.position.set(center.x, bounds.min.y, center.z);
    three.add(grid);
    meshes.current = boxes.map((box) => {
      const geometry = new THREE.BoxGeometry(Math.max(box.size.x, 0.5), Math.max(box.size.y, 0.5), Math.max(box.size.z, 0.5));
      const mesh = new THREE.Mesh(geometry, solid ? solidMaterial(box.pieza) : new THREE.MeshStandardMaterial({ color: ink, roughness: 0.9, transparent: true, opacity: 0.14, depthWrite: false }));
      mesh.position.set(box.min.x + box.size.x / 2, box.min.y + box.size.y / 2, box.min.z + box.size.z / 2);
      const edgeMaterial = solid ? solidEdges() : box.dashed ? new THREE.LineDashedMaterial({ color: ink, dashSize: 24, gapSize: 18 }) : new THREE.LineBasicMaterial({ color: ink });
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), edgeMaterial);
      if (box.dashed && !solid) edges.computeLineDistances();
      edges.position.copy(mesh.position);
      three.add(mesh, edges);
      return { mesh, edges, box, base: mesh.position.clone(), escala: 1 };
    });
    dimGroup.current = new THREE.Group();
    three.add(dimGroup.current);
    let disposed = false;
    if (glbUrl) {
      new GLTFLoader().load(glbUrl, (gltf) => {
        if (disposed) return;
        const model = gltf.scene;
        model.scale.setScalar(1000); // metros del GLB a los mm de la escena
        model.updateMatrixWorld(true);
        const loaded: typeof meshes.current = [];
        model.traverse((node) => {
          if (!(node instanceof THREE.Mesh)) return;
          const id = node.name || node.parent?.name || "";
          const box = boxes.find((item) => item.pieza === id || item.id === id);
          if (!box) return;
          // El GLB del backend no trae normales: sin ellas la luz no actúa. Caras planas, como cajas.
          if (!node.geometry.getAttribute("normal")) { node.geometry = node.geometry.index ? node.geometry.toNonIndexed() : node.geometry; node.geometry.computeVertexNormals(); }
          node.material = solid ? solidMaterial(box.pieza) : new THREE.MeshStandardMaterial({ color: ink, roughness: 0.9, transparent: true, opacity: 0.14, depthWrite: false });
          const edges = new THREE.LineSegments(new THREE.EdgesGeometry(node.geometry), solid ? solidEdges() : box.dashed ? new THREE.LineDashedMaterial({ color: ink, dashSize: 0.024, gapSize: 0.018 }) : new THREE.LineBasicMaterial({ color: ink }));
          if (box.dashed && !solid) edges.computeLineDistances();
          node.add(edges);
          // Las coordenadas del nodo van en metros dentro del modelo escalado ×1000.
          loaded.push({ mesh: node, edges, box, base: node.position.clone(), escala: 0.001 });
        });
        if (!loaded.length) return;
        meshes.current.forEach(({ mesh, edges }) => { mesh.visible = false; edges.visible = false; });
        meshes.current = loaded;
        three.add(model);
        setGlbTick((value) => value + 1);
      }, undefined, () => { /* sin GLB: se quedan las cajas */ });
    }
    const resize = () => {
      renderer.setSize(el.clientWidth, el.clientHeight); camera.aspect = el.clientWidth / Math.max(el.clientHeight, 1);
      // Con un panel encima a la izquierda, el centro del encuadre se desplaza a la derecha.
      if (shiftX) camera.setViewOffset(el.clientWidth, el.clientHeight, -shiftX, 0, el.clientWidth, el.clientHeight); else camera.clearViewOffset();
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    let frame = 0;
    const place = () => labels.current.forEach(({ el: label, at }) => {
      const v = at.clone().project(camera);
      label.style.transform = `translate(${((v.x + 1) / 2) * el.clientWidth}px, ${((1 - v.y) / 2) * el.clientHeight}px) translate(-50%, -50%)`;
      label.style.display = v.z > 1 ? "none" : "";
    });
    const loop = () => { controls.update(); renderer.render(three, camera); place(); frame = requestAnimationFrame(loop); };
    loop();
    redraw.current = () => renderer.render(three, camera);
    const raycaster = new THREE.Raycaster();
    const pick = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      raycaster.setFromCamera(new THREE.Vector2(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1), camera);
      const hit = raycaster.intersectObjects(meshes.current.map((item) => item.mesh))[0];
      return hit ? meshes.current.find((item) => item.mesh === hit.object)?.box.pieza ?? null : null;
    };
    let downAt = { x: 0, y: 0 }, dragging = false, hovered: string | null = null, pending = 0;
    const onDown = (event: PointerEvent) => { downAt = { x: event.clientX, y: event.clientY }; dragging = true; };
    const onUp = (event: PointerEvent) => { dragging = false; if (Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y) <= 4) handlers.current.onPick(pick(event)); };
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
    const canvas = renderer.domElement;
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame); cancelAnimationFrame(pending); ro.disconnect(); controls.dispose();
      canvas.removeEventListener("pointerdown", onDown); canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointermove", onMove); canvas.removeEventListener("pointerleave", onLeave);
      renderer.dispose(); labels.current.forEach((item) => item.el.remove()); labels.current = []; el.removeChild(canvas);
    };
  }, [boxes, bounds, theme, front, overhead, glbUrl, solid, colors, shiftX]);

  // Despiece: cada pieza se aparta del centro del conjunto en la dirección de su propio centro, con transición suave.
  useEffect(() => {
    const center = bounds.getCenter(new THREE.Vector3());
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const tramos = meshes.current.filter((m) => m.base).map(({ mesh, edges, box, base, escala = 1 }) => {
      const own = new THREE.Vector3(box.min.x + box.size.x / 2, box.min.y + box.size.y / 2, box.min.z + box.size.z / 2);
      const dir = own.sub(center);
      if (dir.lengthSq() < 1e-6) dir.set(0, 1, 0);
      const offset = exploded ? dir.normalize().multiplyScalar(Math.max(box.size.x, box.size.y, box.size.z) * 0.18 * escala) : new THREE.Vector3();
      return { mesh, edges, from: mesh.position.clone(), to: base!.clone().add(offset) };
    });
    const aplicar = (k: number) => {
      tramos.forEach(({ mesh, edges, from, to }) => {
        mesh.position.lerpVectors(from, to, k);
        if (edges.parent !== mesh) edges.position.copy(mesh.position);
      });
      redraw.current();
    };
    if (reduce) { aplicar(1); return; }
    const dur = 900, t0 = performance.now();
    let raf = 0;
    const paso = (t: number) => {
      const x = Math.min(1, (t - t0) / dur);
      aplicar(x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
      if (x < 1) raf = requestAnimationFrame(paso);
    };
    raf = requestAnimationFrame(paso);
    return () => cancelAnimationFrame(raf);
  }, [exploded, bounds, glbTick, boxes]);

  useEffect(() => {
    meshes.current.forEach(({ mesh, edges, box }) => {
      const ver = !visibles || visibles.has(box.pieza);
      mesh.visible = ver;
      if (edges.parent !== mesh) edges.visible = ver;
    });
    redraw.current();
  }, [visibles, glbTick, boxes]);

  useEffect(() => { if (resetTick) reset.current(); }, [resetTick]);

  useEffect(() => {
    const wood = cssColor("wood");
    const ink = new THREE.Color("#4a2f1c"); // aristas en marrón oscuro, no blancas
    const danger = cssColor("danger").lerp(new THREE.Color(1, 1, 1), 0.25);
    const any = meshes.current.some(({ box }) => box.pieza === selected);
    meshes.current.forEach(({ mesh, edges, box }) => {
      const active = box.pieza === selected;
      const hot = !active && box.pieza === hover;
      const base = box.conflict ? danger : ink;
      const material = mesh.material as THREE.MeshStandardMaterial;
      if (solid) {
        material.emissive = active || hot ? cssColor("cobalt") : new THREE.Color(0, 0, 0);
        material.emissiveIntensity = active ? 0.55 : hot ? 0.28 : 0;
        if (material.transparent !== (any && !active)) { material.transparent = any && !active; material.needsUpdate = true; }
        material.opacity = any && !active ? 0.55 : 1;
        return;
      }
      material.color = active || hot ? wood : base;
      material.opacity = active ? 0.5 : hot ? 0.3 : box.conflict ? (any ? 0.16 : 0.34) : any ? 0.06 : 0.14;
      const line = edges.material as THREE.LineBasicMaterial;
      line.color = active || hot ? wood : ink;
      line.transparent = true;
      line.opacity = active || hot || !any ? 1 : 0.3;
    });
    // Cotas de la primera ocurrencia de la pieza elegida, con el tamaño de su caja.
    labels.current.forEach((item) => item.el.remove());
    labels.current = [];
    const group = dimGroup.current;
    if (group) {
      group.clear();
      const target = meshes.current.find(({ box }) => box.pieza === selected)?.box;
      if (target && overlay.current) {
        const { min, size } = target;
        const max = { x: min.x + size.x, y: min.y + size.y, z: min.z + size.z };
        const off = Math.max(size.x, size.y, size.z) * 0.05 + 10;
        const segments: [THREE.Vector3, THREE.Vector3, number][] = [
          [new THREE.Vector3(min.x, min.y - off, max.z + off), new THREE.Vector3(max.x, min.y - off, max.z + off), size.x],
          [new THREE.Vector3(min.x - off, min.y, max.z + off), new THREE.Vector3(min.x - off, max.y, max.z + off), size.y],
          [new THREE.Vector3(max.x + off, min.y - off, min.z), new THREE.Vector3(max.x + off, min.y - off, max.z), size.z],
        ];
        const material = new THREE.LineBasicMaterial({ color: ink });
        segments.forEach(([a, b, value]) => {
          group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, b]), material));
          const label = document.createElement("span");
          label.className = "num pointer-events-none absolute left-0 top-0 whitespace-nowrap border border-on-block-2 bg-block px-1.5 py-0.5 font-mono text-2xs text-on-block";
          label.textContent = NUM.format(value);
          overlay.current!.appendChild(label);
          labels.current.push({ el: label, at: a.clone().add(b).multiplyScalar(0.5) });
        });
      }
    }
    redraw.current();
  }, [selected, hover, boxes, theme, glbTick]);

  if (failed) return <p className="p-s5 text-base text-on-block">{COPY.scene.webgl}</p>;
  return (
    <>
      <div ref={host} className="absolute inset-0" role="img" aria-label={COPY.portal.viewTitles.esquema} />
      <div ref={overlay} className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true" />
    </>
  );
}
