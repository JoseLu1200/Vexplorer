import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { PIECES, W, H, D } from './lib/pieces'
import { prefersReduced } from './lib/scroll'

const ORDER = ['P3', 'P1', 'P2', 'P8', 'P5', 'P6', 'P7', 'P4']
/** Vista explosionada: cada pieza sale por su propio eje, en mm. Los laterales a los lados, base y techo arriba y abajo, las baldas hacia delante y la trasera hacia atrás. */
const EXPLODE: Record<string, [number, number, number]> = {
  P1: [-320, 0, 0], P2: [320, 0, 0], P3: [0, -280, 0], P4: [0, 280, 0],
  P5: [0, 0, 460], P6: [0, 0, 460], P7: [0, 0, 460], P8: [0, 0, -360],
}
const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const easeInOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)
/** Cierre del despiece: 0 explosionado, 1 montado. Se cierra entre el 6 % y el 84 % del tramo y el resto se queda montado con las cotas. */
const closing = (progress: number) => clamp01((progress - 0.06) / 0.78)
/** Avance 0..1 de la pieza i de n: se cierran de una en una, en el orden de montaje. */
const pieceStep = (c: number, i: number, n: number) => easeInOut(clamp01(c * n - i))

function webglOk(): boolean {
  if (new URLSearchParams(location.search).get('nowebgl') === '1') return false
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

/** Fallback SVG: proyección isométrica de las mismas cajas, que también se cierra con el scroll. */
function IsoFallback({ c }: { c: number }) {
  const iso = (x: number, y: number, z: number): [number, number] => {
    const s = 0.16
    return [300 + (x - z) * 0.866 * s, 330 - y * s + (x + z) * 0.5 * s]
  }
  const edges = (b: number[]) => {
    const [x, y, z, w, h, d] = b
    const v = [
      [x, y, z], [x + w, y, z], [x + w, y + h, z], [x, y + h, z],
      [x, y, z + d], [x + w, y, z + d], [x + w, y + h, z + d], [x, y + h, z + d],
    ].map(p => iso(p[0], p[1], p[2]))
    const e = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]]
    return e.map(([a, c]) => `M${v[a][0].toFixed(1)} ${v[a][1].toFixed(1)}L${v[c][0].toFixed(1)} ${v[c][1].toFixed(1)}`).join('')
  }
  // Encuadre fijo que cubre a la vez el mueble explosionado y el montado, para que no salte al cerrarse.
  const xs: number[] = []
  const ys: number[] = []
  PIECES.forEach(p => {
    const [ex, ey, ez] = EXPLODE[p.id]
    for (const e of [0, 1]) for (const dx of [0, p.box[3]]) for (const dy of [0, p.box[4]]) for (const dz of [0, p.box[5]]) {
      const [px, py] = iso(p.box[0] + ex * e + dx, p.box[1] + ey * e + dy, p.box[2] + ez * e + dz)
      xs.push(px)
      ys.push(py)
    }
  })
  const m = 16
  const vb = [Math.min(...xs) - m, Math.min(...ys) - m, Math.max(...xs) - Math.min(...xs) + 2 * m, Math.max(...ys) - Math.min(...ys) + 2 * m]
  return (
    <svg className="iso-fallback" viewBox={vb.map(n => n.toFixed(1)).join(' ')} role="img" aria-label="Esquema isométrico de la estantería, que se monta pieza a pieza">
      {ORDER.map((id, i) => {
        const p = PIECES.find(q => q.id === id)!
        const e = 1 - pieceStep(c, i, ORDER.length)
        const [ex, ey, ez] = EXPLODE[id]
        const b = [p.box[0] + ex * e, p.box[1] + ey * e, p.box[2] + ez * e, p.box[3], p.box[4], p.box[5]]
        return <path key={id} d={edges(b)} fill="none" stroke="var(--on-cobalt)" strokeWidth="0.9" />
      })}
    </svg>
  )
}

/** Esquema 3D en wireframe: empieza en vista explosionada y el scroll cierra el despiece pieza a pieza, en el orden de montaje. */
export default function Schema3D({ progress }: { progress: number }) {
  const host = useRef<HTMLDivElement>(null)
  const progRef = useRef(progress)
  progRef.current = progress
  const [ok] = useState(webglOk)
  const reducedNow = prefersReduced()

  useEffect(() => {
    if (!ok || !host.current) return
    const el = host.current
    const reduced = prefersReduced()
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    } catch {
      return
    }
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio))
    el.appendChild(renderer.domElement)
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 200)
    const root = new THREE.Group()
    scene.add(root)
    const k = 0.01
    const ink = new THREE.Color('#dde3ee')
    const amber = new THREE.Color('#cfa477')

    const items = ORDER.map(id => {
      const p = PIECES.find(q => q.id === id)!
      const [x, y, z, w, h, d] = p.box
      // Cada caja se encoge 1,5 mm por lado para que las aristas de piezas vecinas no coincidan y no parpadeen.
      const inset = 3
      const geo = new THREE.EdgesGeometry(new THREE.BoxGeometry(Math.max(1, w - inset) * k, Math.max(1, h - inset) * k, Math.max(1, d - inset) * k))
      const mat = new THREE.LineBasicMaterial({ color: ink.clone(), transparent: true, opacity: 1 })
      const line = new THREE.LineSegments(geo, mat)
      const home = new THREE.Vector3((x + w / 2 - W / 2) * k, (y + h / 2 - H / 2) * k, (z + d / 2 - D / 2) * k)
      const off = new THREE.Vector3(...EXPLODE[id]).multiplyScalar(k)
      line.position.copy(home).add(off)
      root.add(line)
      let face: THREE.Mesh | null = null
      if (id === 'P8') {
        // La trasera se lee como cara: un plano translúcido además de sus aristas.
        face = new THREE.Mesh(
          new THREE.PlaneGeometry(w * k, h * k),
          new THREE.MeshBasicMaterial({
            color: 0xdde3ee,
            transparent: true,
            opacity: 0.12,
            side: THREE.DoubleSide,
            depthWrite: false,
            polygonOffset: true,
            polygonOffsetFactor: 2,
            polygonOffsetUnits: 2,
          })
        )
        line.add(face)
      }
      return { line, mat, face, home, off, id, w, h, d }
    })

    // Rótulos P1 a P8 y cotas, proyectados sobre la escena en cada fotograma.
    const overlay = document.createElement('div')
    overlay.className = 's3-overlay'
    overlay.setAttribute('aria-hidden', 'true')
    el.appendChild(overlay)
    const SVGNS = 'http://www.w3.org/2000/svg'
    const guides = document.createElementNS(SVGNS, 'svg')
    guides.setAttribute('class', 's3-guides')
    overlay.appendChild(guides)
    const mk = (text: string, cls: string) => {
      const d = document.createElement('span')
      d.className = cls
      d.textContent = text
      overlay.appendChild(d)
      return d
    }
    // Punto de la pieza del que sale la guía de su rótulo (en unidades de escena, respecto a su centro).
    const offsetFor = (id: string, w: number, h: number, d: number): THREE.Vector3 => {
      if (id === 'P1') return new THREE.Vector3(-w * k * 0.5, h * k * 0.18, d * k * 0.5)
      if (id === 'P2') return new THREE.Vector3(w * k * 0.5, h * k * 0.18, d * k * 0.5)
      if (id === 'P3') return new THREE.Vector3(-w * k * 0.3, 0, d * k * 0.5)
      if (id === 'P4') return new THREE.Vector3(-w * k * 0.3, 0, d * k * 0.5)
      // P8 en el panel trasero, en el hueco entre P5 y P6, donde solo se ve la trasera.
      if (id === 'P8') return new THREE.Vector3(w * k * 0.3, (675 - 900) * k, 0)
      // Baldas: la guía sale de la esquina delantera derecha; mientras están fuera, de la izquierda (ver tick).
      return new THREE.Vector3(w * k * 0.5, 0, d * k * 0.5)
    }
    const labels = items.map(it => {
      const anchor = new THREE.Object3D()
      anchor.position.copy(offsetFor(it.id, it.w, it.h, it.d))
      it.line.add(anchor)
      const guide = document.createElementNS(SVGNS, 'line')
      guides.appendChild(guide)
      return { anchor, node: mk(it.id, 's3-id'), guide, x: NaN, y: NaN, s: NaN }
    })
    const BALDAS = new Set(['P5', 'P6', 'P7'])
    // Cotas con el mismo patrón que el plano: línea paralela a la arista y marcas oblicuas en los extremos. Salen cuando el mueble está montado.
    const DIMS = [
      { text: '1800 mm', a: [-W / 2, -H / 2, D / 2], b: [-W / 2, H / 2, D / 2], off: [-26, 0] },
      { text: '900 mm', a: [-W / 2, -H / 2, D / 2], b: [W / 2, -H / 2, D / 2], off: [-14, 22] },
      { text: '400 mm', a: [W / 2, -H / 2, D / 2], b: [W / 2, -H / 2, -D / 2], off: [18, 16] },
    ]
    const dims = DIMS.map(dm => {
      const g = document.createElementNS(SVGNS, 'g')
      g.setAttribute('class', 's3-dim')
      const ln = document.createElementNS(SVGNS, 'line')
      const t1 = document.createElementNS(SVGNS, 'line')
      const t2 = document.createElementNS(SVGNS, 'line')
      g.append(ln, t1, t2)
      guides.appendChild(g)
      return { ...dm, g, ln, t1, t2, node: mk(dm.text, 's3-cota') }
    })
    const v = new THREE.Vector3()
    const proj = (p3: number[]) => {
      v.set(p3[0] * k, p3[1] * k, p3[2] * k).applyMatrix4(root.matrixWorld).project(camera)
      return [(v.x * 0.5 + 0.5) * el.clientWidth, (-v.y * 0.5 + 0.5) * el.clientHeight]
    }
    // Esquinas de cada pieza en el espacio de root, para la silueta en pantalla y el encuadre.
    const SIGNS = [-1, 1]
    type Item = (typeof items)[number]
    const cornersOf = (it: Item, e: number, out: THREE.Vector3[]) => {
      for (const sx of SIGNS) for (const sy of SIGNS) for (const sz of SIGNS)
        out.push(
          new THREE.Vector3(
            it.home.x + it.off.x * e + (sx * it.w * k) / 2,
            it.home.y + it.off.y * e + (sy * it.h * k) / 2,
            it.home.z + it.off.z * e + (sz * it.d * k) / 2
          )
        )
    }

    const DIR = new THREE.Vector3(0.36, 0.18, 0.92).normalize()
    const ROT_OPEN = -0.8
    const ROT_SHUT = -0.55
    // Distancia de cámara para que todas las esquinas quepan en el margen pedido (coordenadas normalizadas), con el mueble explosionado (e = 1) o montado (e = 0).
    const fitDistance = (e: number, rot: number, tx: number, ty: number) => {
      const pts: THREE.Vector3[] = []
      items.forEach(it => cornersOf(it, e, pts))
      const m = new THREE.Matrix4().makeRotationY(rot)
      pts.forEach(p => p.applyMatrix4(m))
      let dist = 20
      for (let iter = 0; iter < 5; iter++) {
        camera.position.copy(DIR).multiplyScalar(dist)
        camera.lookAt(0, 0, 0)
        camera.updateMatrixWorld()
        let mx = 0
        let my = 0
        pts.forEach(p => {
          v.copy(p).project(camera)
          mx = Math.max(mx, Math.abs(v.x))
          my = Math.max(my, Math.abs(v.y))
        })
        dist *= Math.max(mx / tx, my / ty)
      }
      return dist
    }
    let distOpen = 20
    let distShut = 20
    const resize = () => {
      const w = el.clientWidth
      const h = el.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      // Margen lateral para las columnas de rótulos, más estrecho en vertical.
      const portrait = w / h < 0.9
      distOpen = fitDistance(1, ROT_OPEN, portrait ? 0.66 : 0.6, 0.84)
      distShut = fitDistance(0, ROT_SHUT, portrait ? 0.56 : 0.42, 0.74)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)

    let raf = 0
    let t0 = performance.now()
    let pointer = 0
    let rotY = ROT_OPEN
    const onMove = (e: PointerEvent) => {
      pointer = (e.clientX / window.innerWidth - 0.5) * 2
    }
    window.addEventListener('pointermove', onMove)
    const scratch: THREE.Vector3[] = []
    // Columna de cada rótulo con el mueble montado. Con las baldas fuera, sus rótulos van a la izquierda, donde quedan ellas, y cruzan al cerrarse.
    const LEFT = new Set(['P1', 'P3', 'P4'])

    const tick = () => {
      raf = requestAnimationFrame(tick)
      if (!el.isConnected) return
      const now = performance.now()
      const dt = Math.min(0.1, (now - t0) / 1000)
      t0 = now
      const c = reduced ? 1 : closing(progRef.current)
      const n = items.length
      const steps = items.map((_, i) => pieceStep(c, i, n))
      items.forEach((it, i) => {
        const step = steps[i]
        it.line.position.copy(it.home).addScaledVector(it.off, 1 - step)
        // La pieza que se está cerrando va en ámbar; las que esperan, más tenues que las ya montadas.
        const moving = step > 0.001 && step < 0.999
        it.mat.color.copy(moving ? amber : ink)
        it.mat.opacity = step >= 0.999 || moving ? 1 : 0.55
        if (it.face) (it.face.material as THREE.MeshBasicMaterial).opacity = step >= 0.999 ? 0.12 : 0.07
        labels[i].node.classList.toggle('is-moving', moving)
      })

      // Cámara: se acerca a medida que el despiece se cierra y gira de tres cuartos a la vista frontal.
      const g = easeInOut(c)
      const dist = distOpen + (distShut - distOpen) * g
      camera.position.copy(DIR).multiplyScalar(dist)
      camera.lookAt(0, 0, 0)
      camera.updateMatrixWorld()
      const target = ROT_OPEN + (ROT_SHUT - ROT_OPEN) * g + (reduced ? 0 : pointer * 0.18)
      rotY += (target - rotY) * (reduced ? 1 : Math.min(1, dt * 4))
      root.rotation.y = rotY
      root.updateMatrixWorld(true)

      // Silueta actual de todas las piezas en pantalla: los rótulos van en dos columnas por fuera de ella.
      scratch.length = 0
      items.forEach((it, i) => cornersOf(it, 1 - steps[i], scratch))
      let minX = Infinity
      let maxX = -Infinity
      scratch.forEach(p => {
        v.copy(p).applyMatrix4(root.matrixWorld).project(camera)
        const x = (v.x * 0.5 + 0.5) * el.clientWidth
        minX = Math.min(minX, x)
        maxX = Math.max(maxX, x)
      })
      const narrow = el.clientWidth < 560
      const LABEL_W = narrow ? 30 : 36
      const leftX = Math.max(LABEL_W + 2, minX - (narrow ? 44 : 38))
      const rightX = Math.min(el.clientWidth - LABEL_W - 2, maxX + (narrow ? 12 : 32))
      const pts = items.map((it, i) => {
        const lb = labels[i]
        if (BALDAS.has(it.id)) lb.anchor.position.x = it.w * k * (steps[i] - 0.5)
        // P1: con las baldas fuera, la guía baja al hueco entre P6 y P7 para no terminar sobre P7.
        if (it.id === 'P1') lb.anchor.position.y = it.h * k * (0.06 + 0.12 * steps[i])
        lb.anchor.getWorldPosition(v)
        v.project(camera)
        const left = LEFT.has(it.id) || (BALDAS.has(it.id) && steps[i] < 0.5)
        return { i, left, x: (v.x * 0.5 + 0.5) * el.clientWidth, y: (-v.y * 0.5 + 0.5) * el.clientHeight }
      })
      // Columnas ordenadas por altura y sin solaparse, para que las guías no se crucen. El rótulo se desliza hacia su sitio.
      const ease = reduced ? 1 : Math.min(1, dt * 9)
      ;[pts.filter(p => p.left), pts.filter(p => !p.left)].forEach((col, ci) => {
        col.sort((a, b) => a.y - b.y)
        let last = -Infinity
        col.forEach(p => {
          const ty = Math.max(p.y, last + 30)
          last = ty
          const lb = labels[p.i]
          // Borde del rótulo que mira al mueble: el derecho en la columna izquierda y el izquierdo en la derecha.
          const tx = ci === 0 ? leftX : rightX
          lb.x = Number.isNaN(lb.x) ? tx : lb.x + (tx - lb.x) * ease
          lb.y = Number.isNaN(lb.y) ? ty : lb.y + (ty - lb.y) * ease
          // Lado 0 = columna izquierda (rótulo a la izquierda de su borde) y 1 = derecha; también se desliza para que el cruce no salte.
          lb.s = Number.isNaN(lb.s) ? ci : lb.s + (ci - lb.s) * ease
          lb.node.style.transform = `translate(${lb.x.toFixed(1)}px, ${lb.y.toFixed(1)}px) translate(${(-100 * (1 - lb.s)).toFixed(1)}%, -50%)`
          lb.node.style.opacity = '1'
          lb.guide.setAttribute('x1', p.x.toFixed(1))
          lb.guide.setAttribute('y1', p.y.toFixed(1))
          lb.guide.setAttribute('x2', (lb.x + 4 - 8 * lb.s).toFixed(1))
          lb.guide.setAttribute('y2', lb.y.toFixed(1))
          lb.guide.style.opacity = '1'
        })
      })

      const cotasO = c >= 0.995 ? 1 : 0
      dims.forEach(dm => {
        const [ax, ay] = proj(dm.a)
        const [bx, by] = proj(dm.b)
        const [ox, oy] = dm.off
        const x1 = ax + ox, y1 = ay + oy, x2 = bx + ox, y2 = by + oy
        const set = (l: SVGLineElement, a: number, b: number, cc: number, d: number) => {
          l.setAttribute('x1', a.toFixed(1)); l.setAttribute('y1', b.toFixed(1)); l.setAttribute('x2', cc.toFixed(1)); l.setAttribute('y2', d.toFixed(1))
        }
        set(dm.ln, x1, y1, x2, y2)
        set(dm.t1, x1 - 5, y1 + 5, x1 + 5, y1 - 5)
        set(dm.t2, x2 - 5, y2 + 5, x2 + 5, y2 - 5)
        dm.g.style.opacity = String(cotasO)
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2
        const vertical = Math.abs(y2 - y1) > Math.abs(x2 - x1)
        // La cota vertical va girada, como la de 1800 en el plano, para no robar ancho a los rótulos.
        dm.node.style.transform = vertical
          ? `translate(${(mx - 14).toFixed(1)}px, ${my.toFixed(1)}px) translate(-50%, -50%) rotate(-90deg)`
          : `translate(${mx.toFixed(1)}px, ${(my + 8).toFixed(1)}px) translate(-50%, 0)`
        dm.node.style.opacity = String(cotasO)
      })
      renderer.render(scene, camera)
    }
    tick()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('pointermove', onMove)
      items.forEach(it => {
        it.line.geometry.dispose()
        it.mat.dispose()
      })
      renderer.dispose()
      renderer.domElement.remove()
      overlay.remove()
    }
  }, [ok])

  return (
    <div className="schema3d" ref={host}>
      {!ok && <IsoFallback c={reducedNow ? 1 : closing(progress)} />}
    </div>
  )
}
