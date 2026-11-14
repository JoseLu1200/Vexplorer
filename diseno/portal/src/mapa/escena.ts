// Escena three.js del mapa: nube de puntos en PC1-PC3, OrbitControls, picking por color fuera de pantalla,
// vecinos del punto fijado con líneas finas y anillos para raros, fijado y hover.
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { type DatosMapa, type Proyeccion, vecinosDe } from "./datos";
import { type Tema, colorGrupo } from "./paleta";

export interface Estado {
  familia: number | null;
  fijado: number | null;
  hover: number | null;
}

const VERT = /* glsl */ `
attribute vec3 tono;
attribute float escala;
attribute float alfa;
uniform float tam;
varying vec3 vTono;
varying float vAlfa;
void main() {
  vTono = tono;
  vAlfa = alfa;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = tam * escala;
}`;

const FRAG = /* glsl */ `
varying vec3 vTono;
varying float vAlfa;
void main() {
  float r = length(gl_PointCoord - 0.5);
  if (r > 0.5 || vAlfa < 0.01) discard;
  gl_FragColor = vec4(vTono, vAlfa * smoothstep(0.5, 0.4, r));
  #include <colorspace_fragment>
}`;

// Anillo: corona entre 0,34 y 0,5 del sprite.
const FRAG_ANILLO = /* glsl */ `
varying vec3 vTono;
varying float vAlfa;
void main() {
  float r = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.46, r) * smoothstep(0.30, 0.35, r);
  if (a < 0.02) discard;
  gl_FragColor = vec4(vTono, vAlfa * a);
  #include <colorspace_fragment>
}`;

const VERT_PICK = /* glsl */ `
attribute vec3 idColor;
attribute float activo;
uniform float tam;
varying vec3 vId;
varying float vActivo;
void main() {
  vId = idColor;
  vActivo = activo;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = tam;
}`;

const FRAG_PICK = /* glsl */ `
varying vec3 vId;
varying float vActivo;
void main() {
  if (vActivo < 0.5 || length(gl_PointCoord - 0.5) > 0.5) discard;
  gl_FragColor = vec4(vId, 1.0);
}`;

const PICK = 11; // ventana de picking en píxeles CSS
const FOV = 38;

const lin = (css: string) => new THREE.Color().setStyle(css);

export class Escena {
  readonly renderer: THREE.WebGLRenderer;
  readonly camera = new THREE.PerspectiveCamera(FOV, 1, 0.01, 100);
  readonly controls: OrbitControls;
  private scene = new THREE.Scene();
  private pickScene = new THREE.Scene();
  private pickTarget = new THREE.WebGLRenderTarget(PICK, PICK);
  private pickBuf = new Uint8Array(PICK * PICK * 4);
  private geo = new THREE.BufferGeometry();
  private mat: THREE.ShaderMaterial;
  private matPick: THREE.ShaderMaterial;
  private destacados = new THREE.BufferGeometry();
  private matDestacados: THREE.ShaderMaterial;
  private anillos = new THREE.BufferGeometry();
  private matAnillos: THREE.ShaderMaterial;
  private lineas = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ transparent: true, opacity: 0.5, depthTest: false }));
  private ejes = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ transparent: true, opacity: 0.55 }));
  private d: DatosMapa | null = null;
  private tema: Tema | null = null;
  private est: Estado = { familia: null, fijado: null, hover: null };
  private w = 1;
  private h = 1;
  private desp = { x: 0, y: 0 };
  private sucio = true;
  private raf = 0;
  private vuelo: { t0: number; ms: number; de: THREE.Vector3; a: THREE.Vector3; dDe: number; dA: number; dir: THREE.Vector3 } | null = null;
  /** posiciones actuales (se interpolan al cambiar de proyección). */
  private pos = new Float32Array(0);
  private morph: { t0: number; ms: number; de: Float32Array; a: Float32Array } | null = null;
  private visibles: Uint8Array | null = null;
  private dims: 2 | 3 = 3;
  tiempos: number[] = [];
  medir = false;
  onDibujo?: () => void;

  constructor(
    canvas: HTMLCanvasElement,
    private rotulos: HTMLElement[],
  ) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    const uni = () => ({ tam: { value: 3 } });
    this.mat = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms: uni(), transparent: true, depthWrite: true });
    this.matDestacados = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms: uni(), transparent: true, depthTest: false });
    this.matAnillos = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG_ANILLO, uniforms: uni(), transparent: true, depthTest: false });
    this.matPick = new THREE.ShaderMaterial({ vertexShader: VERT_PICK, fragmentShader: FRAG_PICK, uniforms: { tam: { value: 8 } }, blending: THREE.NoBlending });
    const nube = new THREE.Points(this.geo, this.mat);
    const sobre = new THREE.Points(this.destacados, this.matDestacados);
    const aros = new THREE.Points(this.anillos, this.matAnillos);
    nube.frustumCulled = sobre.frustumCulled = aros.frustumCulled = this.lineas.frustumCulled = false;
    this.lineas.renderOrder = 1;
    sobre.renderOrder = 2;
    aros.renderOrder = 3;
    this.scene.add(this.ejes, nube, this.lineas, sobre, aros);
    const pick = new THREE.Points(this.geo, this.matPick);
    pick.frustumCulled = false;
    this.pickScene.add(pick);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.14;
    this.controls.screenSpacePanning = true;
    this.controls.minDistance = 0.03;
    this.controls.maxDistance = 30;
    this.controls.zoomSpeed = 1.1;
    this.controls.addEventListener("start", () => (this.vuelo = null));
    this.controls.addEventListener("change", () => (this.sucio = true));
    const ejes = new Float32Array([-1.2, 0, 0, 1.2, 0, 0, 0, -1.2, 0, 0, 1.2, 0, 0, 0, -1.2, 0, 0, 1.2]);
    this.ejes.geometry.setAttribute("position", new THREE.BufferAttribute(ejes, 3));
    this.encuadrar(false);
    const bucle = () => {
      this.raf = requestAnimationFrame(bucle);
      this.paso();
    };
    this.raf = requestAnimationFrame(bucle);
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    this.controls.dispose();
    this.geo.dispose();
    this.destacados.dispose();
    this.anillos.dispose();
    this.pickTarget.dispose();
    this.renderer.dispose();
  }

  private tamBase() {
    const n = this.d?.n ?? 1;
    return n > 5000 ? 3.4 : n > 1000 ? 5 : 8;
  }

  datos(d: DatosMapa) {
    this.d = d;
    this.pos = new Float32Array(d.pos);
    this.ejes.visible = true;
    this.morph = null;
    this.visibles = null;
    this.modo(3, true);
    this.geo.setAttribute("position", new THREE.BufferAttribute(this.pos, 3));
    this.geo.setAttribute("tono", new THREE.BufferAttribute(new Float32Array(d.n * 3), 3));
    this.geo.setAttribute("escala", new THREE.BufferAttribute(new Float32Array(d.n).fill(1), 1));
    this.geo.setAttribute("alfa", new THREE.BufferAttribute(new Float32Array(d.n).fill(1), 1));
    this.geo.setAttribute("activo", new THREE.BufferAttribute(new Float32Array(d.n).fill(1), 1));
    const id = new Float32Array(d.n * 3);
    for (let i = 0; i < d.n; i++) {
      const v = i + 1;
      id[3 * i] = (v & 255) / 255;
      id[3 * i + 1] = ((v >> 8) & 255) / 255;
      id[3 * i + 2] = ((v >> 16) & 255) / 255;
    }
    this.geo.setAttribute("idColor", new THREE.BufferAttribute(id, 3));
    this.geo.computeBoundingSphere();
    this.est = { familia: null, fijado: null, hover: null };
    this.pintar();
    this.encuadrar(false);
  }

  setTema(t: Tema) {
    this.tema = t;
    this.renderer.setClearColor(lin(t.bg), 1);
    (this.lineas.material as THREE.LineBasicMaterial).color = lin(t.ink);
    (this.ejes.material as THREE.LineBasicMaterial).color = lin(t.muted);
    this.pintar();
  }

  setEstado(e: Estado) {
    this.est = e;
    this.pintar();
  }

  /** Desplazamiento del centro de la vista cuando un panel tapa parte del lienzo (en píxeles CSS). */
  setDesplazamiento(x: number, y: number) {
    this.desp = { x, y };
    this.aplicarVista();
  }

  tam(w: number, h: number) {
    this.w = Math.max(1, w);
    this.h = Math.max(1, h);
    this.renderer.setSize(this.w, this.h, false);
    this.camera.aspect = this.w / this.h;
    this.aplicarVista();
  }

  private aplicarVista() {
    if (this.desp.x || this.desp.y) this.camera.setViewOffset(this.w, this.h, this.desp.x, this.desp.y, this.w, this.h);
    else this.camera.clearViewOffset();
    this.camera.updateProjectionMatrix();
    this.sucio = true;
  }

  private pintar() {
    const d = this.d;
    const t = this.tema;
    if (!d || !t || !this.geo.getAttribute("tono")) return;
    const { familia, fijado } = this.est;
    const tono = this.geo.getAttribute("tono") as THREE.BufferAttribute;
    const alfa = this.geo.getAttribute("alfa") as THREE.BufferAttribute;
    const activo = this.geo.getAttribute("activo") as THREE.BufferAttribute;
    const colores = d.familias.map((_, g) => lin(colorGrupo(t, g, d.otras)));
    const gris = lin(t.otras);
    for (let i = 0; i < d.n; i++) {
      const g = d.familia[i];
      const dentro = familia === null || g === familia;
      const c = dentro ? colores[g] : gris;
      tono.setXYZ(i, c.r, c.g, c.b);
      const vis = !this.visibles || this.visibles[i] === 1;
      alfa.setX(i, !vis ? 0 : fijado !== null ? 0.22 : dentro ? 1 : 0.45);
      activo.setX(i, dentro && vis ? 1 : 0);
    }
    tono.needsUpdate = alfa.needsUpdate = activo.needsUpdate = true;
    this.seleccion();
  }

  // Fijado y sus vecinos, encima de todo y unidos por líneas, sobre la proyección activa.
  private seleccion() {
    const d = this.d;
    const t = this.tema;
    if (!d || !t) return;
    const { fijado } = this.est;
    const colores = d.familias.map((_, g) => lin(colorGrupo(t, g, d.otras)));
    const vec = fijado !== null ? vecinosDe(d, fijado) : [];
    const sel = fijado !== null ? [...vec, fijado] : [];
    const pos = new Float32Array(sel.length * 3);
    const ton = new Float32Array(sel.length * 3);
    const esc = new Float32Array(sel.length);
    const alf = new Float32Array(sel.length).fill(1);
    sel.forEach((i, k) => {
      pos.set(this.pos.subarray(3 * i, 3 * i + 3), 3 * k);
      const c = colores[d.familia[i]];
      ton.set([c.r, c.g, c.b], 3 * k);
      esc[k] = i === fijado ? 2.8 : k < 6 ? 2.2 : 1.6;
    });
    this.destacados.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.destacados.setAttribute("tono", new THREE.BufferAttribute(ton, 3));
    this.destacados.setAttribute("escala", new THREE.BufferAttribute(esc, 1));
    this.destacados.setAttribute("alfa", new THREE.BufferAttribute(alf, 1));
    const lp = new Float32Array(vec.length * 6);
    if (fijado !== null)
      vec.forEach((j, k) => {
        lp.set(this.pos.subarray(3 * fijado, 3 * fijado + 3), 6 * k);
        lp.set(this.pos.subarray(3 * j, 3 * j + 3), 6 * k + 3);
      });
    this.lineas.geometry.setAttribute("position", new THREE.BufferAttribute(lp, 3));
    this.aros();
  }

  /** Solo cambia el anillo de hover: no repinta los 26.707 puntos. */
  setHover(i: number | null) {
    if (this.est.hover === i) return;
    this.est = { ...this.est, hover: i };
    this.aros();
  }

  // Anillos: raros (madera), fijado y hover (tinta).
  private aros() {
    const d = this.d;
    const t = this.tema;
    if (!d || !t) return;
    const { familia, fijado, hover } = this.est;
    const aros: [number, string, number][] = [];
    d.raros.forEach((i) => (familia === null || d.familia[i] === familia) && aros.push([i, t.raro, i === fijado ? 2.3 : 1.6]));
    if (fijado !== null) aros.push([fijado, t.ink, 1.75]);
    if (hover !== null && hover !== fijado) aros.push([hover, t.ink, 1.5]);
    const ap = new Float32Array(aros.length * 3);
    const at = new Float32Array(aros.length * 3);
    const ae = new Float32Array(aros.length);
    aros.forEach(([i, col, e], k) => {
      ap.set(this.pos.subarray(3 * i, 3 * i + 3), 3 * k);
      const c = lin(col);
      at.set([c.r, c.g, c.b], 3 * k);
      ae[k] = e;
    });
    this.anillos.setAttribute("position", new THREE.BufferAttribute(ap, 3));
    this.anillos.setAttribute("tono", new THREE.BufferAttribute(at, 3));
    this.anillos.setAttribute("escala", new THREE.BufferAttribute(ae, 1));
    this.anillos.setAttribute("alfa", new THREE.BufferAttribute(new Float32Array(aros.length).fill(1), 1));
    this.sucio = true;
  }

  /** Punto bajo el puntero (coordenadas CSS del lienzo), o null. Picking por color en una ventana de 11 px. */
  pick(x: number, y: number): number | null {
    if (!this.d) return null;
    // El render target fija su propio viewport: un píxel del objetivo es un píxel CSS.
    this.matPick.uniforms.tam.value = Math.max(7, this.tamBase() + 4);
    const ox = this.desp.x + x - PICK / 2;
    const oy = this.desp.y + y - PICK / 2;
    this.camera.setViewOffset(this.w, this.h, ox, oy, PICK, PICK);
    this.camera.updateProjectionMatrix();
    this.renderer.setRenderTarget(this.pickTarget);
    const clear = this.renderer.getClearColor(new THREE.Color());
    const ca = this.renderer.getClearAlpha();
    this.renderer.setClearColor(0x000000, 1);
    this.renderer.render(this.pickScene, this.camera);
    this.renderer.readRenderTargetPixels(this.pickTarget, 0, 0, PICK, PICK, this.pickBuf);
    this.renderer.setRenderTarget(null);
    this.renderer.setClearColor(clear, ca);
    this.aplicarVista();
    let mejor: number | null = null;
    let md = Infinity;
    for (let py = 0; py < PICK; py++)
      for (let px = 0; px < PICK; px++) {
        const o = 4 * (py * PICK + px);
        const v = this.pickBuf[o] | (this.pickBuf[o + 1] << 8) | (this.pickBuf[o + 2] << 16);
        if (!v) continue;
        const dd = (px - PICK / 2 + 0.5) ** 2 + (py - PICK / 2 + 0.5) ** 2;
        if (dd < md) {
          md = dd;
          mejor = v - 1;
        }
      }
    return mejor !== null && mejor < this.d.n ? mejor : null;
  }

  /** Posición en pantalla (CSS, relativa al lienzo) de un punto. */
  pantalla(i: number) {
    if (!this.d) return null;
    const v = new THREE.Vector3().fromArray(this.pos, 3 * i).project(this.camera);
    return { x: ((v.x + 1) / 2) * this.w, y: ((1 - v.y) / 2) * this.h };
  }

  private distanciaEncuadre(radio: number) {
    const v = THREE.MathUtils.degToRad(FOV) / 2;
    const hz = Math.atan(Math.tan(v) * this.camera.aspect);
    return radio / Math.sin(Math.min(v, hz));
  }

  /**
   * Ajusta la cámara a la extensión de los puntos visibles de la proyección de destino.
   * 2D: caja de percentiles 0,5-99,5 en x/y, encajada en alto y ancho de la vista libre. 3D: esfera del percentil 98.
   */
  encuadrar(animar = true, pos: Float32Array = this.morph?.a ?? this.pos) {
    const n = pos.length / 3;
    const vis = this.visibles;
    const xs: number[] = [];
    const ys: number[] = [];
    const zs: number[] = [];
    for (let i = 0; i < n; i++) {
      if (vis && !vis[i]) continue;
      xs.push(pos[3 * i]);
      ys.push(pos[3 * i + 1]);
      zs.push(pos[3 * i + 2]);
    }
    if (!xs.length) return;
    const rango = (v: number[]) => {
      const o = v.slice().sort((a, b) => a - b);
      const m = o.length;
      return [o[Math.floor((m - 1) * 0.005)], o[Math.ceil((m - 1) * 0.995)]] as const;
    };
    const [x0, x1] = rango(xs);
    const [y0, y1] = rango(ys);
    const [z0, z1] = rango(zs);
    const centro = new THREE.Vector3((x0 + x1) / 2, (y0 + y1) / 2, this.dims === 2 ? 0 : (z0 + z1) / 2);
    const libreW = this.w - 2 * this.desp.x;
    const libreH = this.h - 2 * this.desp.y;
    const tv = Math.tan(THREE.MathUtils.degToRad(FOV) / 2);
    const th = tv * (Math.max(1, libreW) / Math.max(1, libreH));
    let dist: number;
    let dir: THREE.Vector3;
    if (this.dims === 2) {
      dir = new THREE.Vector3(0, 0, 1);
      dist = Math.max((y1 - y0) / 2 / tv, (x1 - x0) / 2 / th) * 1.1;
    } else {
      dir = new THREE.Vector3(0.95, 0.55, 1.35).normalize();
      const r = rango(xs.map((x, k) => Math.hypot(x - centro.x, ys[k] - centro.y, zs[k] - centro.z)))[1];
      dist = (r * 1.05) / Math.sin(Math.min(Math.atan(tv), Math.atan(th)));
    }
    this.volar(centro, THREE.MathUtils.clamp(dist, 0.05, 30), animar ? 560 : 0, dir);
  }

  /** Centra un punto y acerca la cámara hasta que quepan sus vecinos. */
  enfocar(i: number, animar = true, pos: Float32Array = this.morph?.a ?? this.pos) {
    const d = this.d;
    if (!d) return;
    const p = new THREE.Vector3().fromArray(pos, 3 * i);
    let r = 0;
    for (const j of vecinosDe(d, i)) r = Math.max(r, p.distanceTo(new THREE.Vector3().fromArray(pos, 3 * j)));
    const dist = THREE.MathUtils.clamp(this.distanciaEncuadre(Math.max(r, 0.02) * 1.5), 0.08, 6);
    this.volar(p, dist, animar ? 560 : 0, this.dims === 2 ? new THREE.Vector3(0, 0, 1) : undefined);
  }

  /** 2D: cámara fija en planta, el arrastre desplaza. 3D: órbita. */
  private modo(dims: 2 | 3, inmediato = false) {
    this.dims = dims;
    this.controls.enableRotate = dims === 3;
    this.controls.mouseButtons.LEFT = dims === 3 ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN;
    this.controls.touches.ONE = dims === 3 ? THREE.TOUCH.ROTATE : THREE.TOUCH.PAN;
    if (inmediato) return;
  }

  /** Cambia de proyección con transición: los puntos viajan de una posición a otra y la cámara se recoloca. */
  setProyeccion(p: Proyeccion, animar = true) {
    if (!this.d || p.pos.length !== this.pos.length) return;
    this.morph = { t0: performance.now(), ms: animar ? 800 : 0, de: this.pos.slice(), a: p.pos };
    this.visibles = p.visibles;
    this.modo(p.dims);
    this.ejes.visible = p.clave === "pca3";
    this.pintar();
    const fijado = this.est.fijado;
    if (fijado !== null && (!p.visibles || p.visibles[fijado])) this.enfocar(fijado, animar, p.pos);
    else this.encuadrar(animar);
    if (!animar) this.avanzarMorph(1);
  }

  private avanzarMorph(forzar?: number) {
    const m = this.morph;
    if (!m) return;
    const u = forzar ?? (m.ms ? Math.min(1, (performance.now() - m.t0) / m.ms) : 1);
    const e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
    for (let k = 0; k < this.pos.length; k++) this.pos[k] = m.de[k] + (m.a[k] - m.de[k]) * e;
    (this.geo.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
    this.seleccion();
    if (u >= 1) this.morph = null;
    this.sucio = true;
  }

  zoom(f: number) {
    const off = this.camera.position.clone().sub(this.controls.target);
    this.volar(this.controls.target.clone(), THREE.MathUtils.clamp(off.length() / f, 0.03, 30), 220);
  }

  private volar(a: THREE.Vector3, dist: number, ms: number, dir?: THREE.Vector3) {
    const off = this.camera.position.clone().sub(this.controls.target);
    const d0 = off.length() || 1;
    const v = { t0: performance.now(), ms, de: this.controls.target.clone(), a, dDe: d0, dA: dist, dir: (dir ?? off.normalize()).clone() };
    if (ms <= 0 || !this.d) {
      this.controls.target.copy(a);
      this.camera.position.copy(a).addScaledVector(v.dir, dist);
      this.camera.lookAt(a);
      this.vuelo = null;
      this.sucio = true;
      return;
    }
    v.dir = dir ? dir.clone().normalize() : off.normalize();
    this.vuelo = v;
  }

  private paso() {
    if (this.vuelo) {
      const v = this.vuelo;
      const u = Math.min(1, (performance.now() - v.t0) / v.ms);
      const e = u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
      const off = this.camera.position.clone().sub(this.controls.target).normalize();
      const dir = off.lerp(v.dir, e).normalize();
      const dist = Math.exp(Math.log(v.dDe) + (Math.log(v.dA) - Math.log(v.dDe)) * e);
      this.controls.target.lerpVectors(v.de, v.a, e);
      this.camera.position.copy(this.controls.target).addScaledVector(dir, dist);
      if (u >= 1) this.vuelo = null;
      this.sucio = true;
    }
    if (this.morph) this.avanzarMorph();
    if (this.controls.update()) this.sucio = true;
    if (!this.sucio || !this.d) return;
    this.sucio = false;
    const t0 = performance.now();
    const pr = this.renderer.getPixelRatio();
    const base = this.tamBase();
    this.mat.uniforms.tam.value = base * pr;
    this.matDestacados.uniforms.tam.value = base * pr;
    this.matAnillos.uniforms.tam.value = Math.max(base, 4) * 2.4 * pr;
    this.renderer.render(this.scene, this.camera);
    if (this.medir) {
      this.tiempos.push(performance.now() - t0);
      if (this.tiempos.length > 5000) this.tiempos.shift();
    }
    // Rótulos de los ejes en el extremo positivo de cada uno.
    const ext = [new THREE.Vector3(1.05, 0, 0), new THREE.Vector3(0, 1.05, 0), new THREE.Vector3(0, 0, 1.05)];
    ext.forEach((p, k) => {
      const el = this.rotulos[k];
      if (!el) return;
      if (!this.ejes.visible) {
        el.style.display = "none";
        return;
      }
      const v = p.project(this.camera);
      const visible = v.z < 1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05;
      el.style.display = visible ? "" : "none";
      el.style.transform = `translate(${((v.x + 1) / 2) * this.w + 4}px, ${((1 - v.y) / 2) * this.h - 8}px)`;
    });
    this.onDibujo?.();
  }
}
