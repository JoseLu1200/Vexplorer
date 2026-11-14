import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { cameraZoomPosition, normaliseScene, sceneMeshCenter } from "../core/scene.js";

export function observeContainerSize(root, resize, ResizeObserverClass = globalThis.ResizeObserver) {
  resize();
  if (ResizeObserverClass) {
    const observer = new ResizeObserverClass(resize);
    observer.observe(root);
    return () => observer.disconnect();
  }
  globalThis.addEventListener?.("resize", resize, { passive: true });
  return () => globalThis.removeEventListener?.("resize", resize);
}

export function resizeRendererToContainer(root, renderer, camera, draw) {
  const { width, height } = root.getBoundingClientRect();
  if (!width || !height) return false;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  draw();
  return true;
}

export class SceneViewer {
  constructor(root, { onSelect = () => {} } = {}) {
    this.root = root;
    this.onSelect = onSelect;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xfffcf6);
    this.camera = new THREE.PerspectiveCamera(40, 1, 1, 50000);
    this.camera.position.set(1800, 1400, 1800);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "low-power" });
    this.renderer.setPixelRatio(Math.min(1.5, window.devicePixelRatio || 1));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    root.replaceChildren(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.boundControlsChange = () => this.draw();
    this.controls.addEventListener("change", this.boundControlsChange);
    this.group = new THREE.Group();
    this.scene.add(this.group, new THREE.HemisphereLight(0xffffff, 0x4b5563, 2.2));
    const directional = new THREE.DirectionalLight(0xffffff, 2.5); directional.position.set(1, 2, 3); this.scene.add(directional);
    this.boundPointerDown = (event) => this.pick(event);
    this.renderer.domElement.addEventListener("pointerdown", this.boundPointerDown);
    this.boundResize = () => this.resize();
    this.stopObservingSize = observeContainerSize(root, this.boundResize);
    this.syncTheme = () => {
      const dark = document.documentElement.dataset.theme === "dark";
      this.scene.background = new THREE.Color(dark ? 0x1a1a17 : 0xfffcf6);
      this.draw();
    };
    this.boundTheme = () => this.syncTheme();
    window.addEventListener("vexplorer-theme", this.boundTheme);
    this.syncTheme();
  }

  setScene(raw) {
    this.model = normaliseScene(raw);
    this.clearGroup();
    const material = () => new THREE.MeshStandardMaterial({ color: 0xb9c2c9, roughness: .72, metalness: 0, transparent: true, opacity: .94 });
    this.model.objects.forEach((item) => {
      const [width, height, depth] = item.dimensions;
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(width, height, depth), material());
      mesh.position.set(...sceneMeshCenter(item)); mesh.userData = item;
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry), new THREE.LineBasicMaterial({ color: 0x344048 }));
      mesh.add(edges); this.group.add(mesh);
    });
    this.fit(); this.draw(); return this.model;
  }

  setExploded(exploded) {
    const center = new THREE.Box3().setFromObject(this.group).getCenter(new THREE.Vector3());
    this.group.children.forEach((mesh) => {
      const item = mesh.userData; const base = new THREE.Vector3(...sceneMeshCenter(item));
      mesh.position.copy(base);
      if (exploded) mesh.position.add(base.clone().sub(center).normalize().multiplyScalar(Math.max(...item.dimensions) * .18));
    });
    this.draw();
  }

  select(pieceId) {
    this.group.children.forEach((mesh) => { mesh.material.color.set(mesh.userData.pieceId === pieceId || mesh.userData.proposalId === pieceId ? 0x4c67ff : 0xb9c2c9); });
    this.draw();
  }

  pick(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    const raycaster = new THREE.Raycaster(); raycaster.setFromCamera(pointer, this.camera);
    const hits = raycaster.intersectObjects(this.group.children, false);
    if (hits[0]?.object?.userData) this.onSelect(hits[0].object.userData);
  }

  fit() {
    const box = new THREE.Box3().setFromObject(this.group);
    if (box.isEmpty()) return;
    const size = box.getSize(new THREE.Vector3()); const center = box.getCenter(new THREE.Vector3()); const radius = Math.max(size.x, size.y, size.z, 1);
    this.controls.target.copy(center); this.camera.position.copy(center).add(new THREE.Vector3(radius * 1.4, radius, radius * 1.4));
    this.camera.near = Math.max(.1, radius / 1000); this.camera.far = radius * 20; this.camera.updateProjectionMatrix(); this.controls.update();
  }

  zoom(factor) {
    const position=cameraZoomPosition(this.camera.position.toArray(),this.controls.target.toArray(),factor);
    this.camera.position.fromArray(position); this.controls.update(); this.draw();
  }

  resize() {
    return resizeRendererToContainer(this.root, this.renderer, this.camera, () => this.draw());
  }

  draw() { this.renderer.render(this.scene, this.camera); }
  clearGroup() { this.group.children.slice().forEach((mesh) => { mesh.geometry?.dispose(); mesh.material?.dispose(); mesh.children.forEach((child)=>{ child.geometry?.dispose(); child.material?.dispose(); }); this.group.remove(mesh); }); }
  dispose() {
    this.stopObservingSize?.();
    window.removeEventListener("vexplorer-theme", this.boundTheme);
    this.renderer.domElement.removeEventListener("pointerdown", this.boundPointerDown);
    this.controls.removeEventListener("change", this.boundControlsChange);
    this.clearGroup();
    this.controls.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss?.();
  }
}
