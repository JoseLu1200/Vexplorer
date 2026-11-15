import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type FormEvent, type ChangeEvent } from 'react'
import Crosshair from './components/rb/Crosshair'
import Topography from './components/rb/Topography'
import Recorrido from './Recorrido'
import Schema3D from './Schema3D'
import { W } from './lib/pieces'
import { PIEZAS, RESUMEN } from './lib/caso-presentacion'
import { useTheme, useTrackProgress, useMode, prefersReduced, smooth } from './lib/scroll'
// Veta de tablero de Wikimedia Commons, de Kurt Kaiser, CC0. Créditos en src/assets/CREDITOS.md.
import tallerImg from './assets/workshop-machines.webp'
import qrPortal from './assets/qr-portal.svg'
import vetaImg from './assets/wood-texture-light.webp'

/** Símbolo de Vexplorer: dos tableros que forman una V; el derecho está desplazado, como en un despiece. */
function Symbol({ size = 28 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true" className="symbol">
      <path d="M3.5 4.5 H9 L16 26.5 H12.6 Z" fill="currentColor" />
      <path d="M22.4 2 H27.9 L21 22.5 H17.6 Z" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M16.6 26.5 H20.2" stroke="var(--wood)" strokeWidth="1.6" />
    </svg>
  )
}

function ThemeToggle() {
  const theme = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  return (
    <button
      type="button"
      className="theme-btn"
      aria-label={`Cambiar a tema ${next === 'light' ? 'claro' : 'oscuro'}`}
      onClick={() => document.documentElement.setAttribute('data-theme', next)}
    >
      <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
        <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path d="M10 3 A7 7 0 0 1 10 17 Z" fill="currentColor" />
      </svg>
    </button>
  )
}

/** Logo elegido por Martín: dos tableros de borde fino y una flecha de cota que pasa por detrás de ellos. */
function Logo({ size = 30, stroke = 5 }: { size?: number; stroke?: number }) {
  const A = '4,24 20,24 50,80 34,80'
  const B = '28,24 44,24 74,80 58,80'
  const id = `lm${size}`
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden="true" style={{ overflow: 'visible' }}>
      <defs>
        <mask id={id} maskUnits="userSpaceOnUse" x="-10" y="-10" width="120" height="120">
          <rect x="-10" y="-10" width="120" height="120" fill="white" />
          <polygon points={A} fill="black" />
          <polygon points={B} fill="black" />
        </mask>
      </defs>
      <g mask={`url(#${id})`} stroke="currentColor" strokeWidth={stroke + 1.5} fill="none">
        <path d="M34 80 L74 24" />
        <path d="M60 24 L74 24 L74 38" strokeLinecap="square" strokeLinejoin="miter" />
      </g>
      <polygon points={A} fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinejoin="miter" />
      <polygon points={B} fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinejoin="miter" />
    </svg>
  )
}

/** Sin cabecera: logo pequeño arriba a la izquierda y menú de tres líneas a la derecha, en modo diferencia para no chocar con lo que pase por debajo. */
// Puente a la demo: el portal de Vexplorer. En local, el servidor del portal; publicado, su artifact.
const PORTAL_URL = 'https://gex-dashboard.hopto.org/vexplorer/demo/'

function Nav() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const close = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [open])
  return (
    <>
      <a href="#top" className="corner-logo" aria-label="Vexplorer, inicio">
        <Logo />
      </a>
      <button type="button" className="corner-menu" aria-expanded={open} aria-controls="menu-panel" aria-label="Más opciones" onClick={() => setOpen(o => !o)}>
        <span /><span /><span />
      </button>
      {open && (
        <div id="menu-panel" className="menu-panel">
          <a href={PORTAL_URL} target="_blank" rel="noopener" className="menu-portal">Probar Vexplorer</a>
          <a href="#desglose" onClick={() => setOpen(false)}>Cómo funciona</a>
          <a href="#esquema" onClick={() => setOpen(false)}>Esquema 3D</a>
          <a href="#demo" onClick={() => setOpen(false)}>Contacto</a>
          <div className="menu-tema"><span>Tema</span><ThemeToggle /></div>
        </div>
      )}
    </>
  )
}

/** «Pide una demo» fijo abajo a la derecha; se esconde mientras el formulario está en pantalla. */
function DemoFlotante() {
  const [oculto, setOculto] = useState(false)
  useEffect(() => {
    const el = document.getElementById('demo')
    if (!el) return
    const io = new IntersectionObserver(([e]) => setOculto(e.isIntersecting), { threshold: 0.15 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <a href="#demo" className={`demo-flotante${oculto ? ' is-oculto' : ''}`} aria-hidden={oculto} tabIndex={oculto ? -1 : 0}>
      Pide una demo
    </a>
  )
}

/** Filtros SVG del duotono: niveles ajustados al rango de la veta (luminancia 0,38 a 0,76), con los nudos en cobalto y las luces en el papel de cada tema. */
function DuotoneFilters() {
  return (
    <svg width="0" height="0" aria-hidden="true" focusable="false" style={{ position: 'absolute' }}>
      <filter id="duo-light" colorInterpolationFilters="sRGB">
        <feColorMatrix type="matrix" values="0.2126 0.7152 0.0722 0 0 0.2126 0.7152 0.0722 0 0 0.2126 0.7152 0.0722 0 0 0 0 0 1 0" />
        <feComponentTransfer>
          <feFuncR type="table" tableValues="0.102 0.102 0.102 0.102 0.102 0.102 0.102 0.102 0.145 0.254 0.362 0.47 0.579 0.687 0.795 0.904 0.925 0.925 0.925 0.925 0.925" />
          <feFuncG type="table" tableValues="0.165 0.165 0.165 0.165 0.165 0.165 0.165 0.165 0.204 0.301 0.398 0.495 0.592 0.689 0.786 0.883 0.902 0.902 0.902 0.902 0.902" />
          <feFuncB type="table" tableValues="0.369 0.369 0.369 0.369 0.369 0.369 0.369 0.369 0.394 0.458 0.522 0.586 0.65 0.714 0.778 0.842 0.855 0.855 0.855 0.855 0.855" />
        </feComponentTransfer>
      </filter>
      <filter id="duo-dark" colorInterpolationFilters="sRGB">
        <feColorMatrix type="matrix" values="0.2126 0.7152 0.0722 0 0 0.2126 0.7152 0.0722 0 0 0.2126 0.7152 0.0722 0 0 0 0 0 1 0" />
        <feComponentTransfer>
          <feFuncR type="table" tableValues="0.075 0.075 0.075 0.075 0.075 0.075 0.075 0.075 0.098 0.155 0.213 0.271 0.329 0.387 0.444 0.502 0.514 0.514 0.514 0.514 0.514" />
          <feFuncG type="table" tableValues="0.102 0.102 0.102 0.102 0.102 0.102 0.102 0.102 0.128 0.192 0.256 0.32 0.383 0.447 0.511 0.575 0.588 0.588 0.588 0.588 0.588" />
          <feFuncB type="table" tableValues="0.173 0.173 0.173 0.173 0.173 0.173 0.173 0.173 0.205 0.285 0.366 0.446 0.527 0.607 0.688 0.768 0.784 0.784 0.784 0.784 0.784" />
        </feComponentTransfer>
      </filter>
    </svg>
  )
}

/** Curvas de nivel de React Bits detrás del titular. Se apagan con el hero (P 0,03 a 0,07), antes de que entre la caja del plano: ni el plano, ni la tabla, ni los filtros tienen nada orgánico detrás. */
function Relieve({ o }: { o: number }) {
  const theme = useTheme()
  const [ok] = useState(() => {
    if (new URLSearchParams(location.search).get('nowebgl') === '1') return false
    try {
      return !!document.createElement('canvas').getContext('webgl2')
    } catch {
      return false
    }
  })
  const reduced = prefersReduced()
  if (!ok) return null
  const light = theme === 'light'
  return (
    <div className="relieve" aria-hidden="true" style={{ opacity: o, visibility: o < 0.01 ? 'hidden' : 'visible' }}>
      <Topography
        color={light ? '#9a6a3c' : '#cfa477'}
        lightMode={light}
        lineCount={16}
        lineWidth={1.25}
        majorLines
        tilt={90}
        elevation={1.3}
        scale={0.75}
        detail={0.3}
        speed={reduced ? 0 : 0.05}
        morph={reduced ? 0 : 0.3}
        glow={0}
        depthOfField={0}
        fog={0}
        opacity={light ? 0.28 : 0.24}
        hoverEffect="lift"
        mouseStrength={0.9}
        mouseRadius={1.4}
        clickEffect="none"
        parallax={0}
        intro={false}
      />
    </div>
  )
}

/** Estilo de una capa de texto del escenario: aparece y desaparece en ventanas que no se solapan. */
const layer = (o: number): CSSProperties => ({
  opacity: o,
  visibility: o < 0.02 ? 'hidden' : 'visible',
  transform: `translateY(${((1 - o) * 14).toFixed(1)}px)`,
})

/** Titular: «Vexplorer» quieto, con una cota fina debajo que mide la palabra y se dibuja al cargar. La cifra es el ancho real de la estantería de ejemplo. */
// Titular en Instrument Serif, elegida por Martín entre cinco opciones.
const fuente = { family: '"Instrument Serif"', vs: 'normal', weight: 400 }

/** Ajusta el cuerpo para que la palabra ocupe todo el ancho, con tope por alto para no pisar la veta. */
function useAjuste(ref: React.RefObject<HTMLSpanElement | null>) {
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const fit = () => {
      const box = el.parentElement?.parentElement
      if (!box) return
      el.style.fontSize = '100px'
      const ratio = el.scrollWidth / 100
      const byWidth = box.clientWidth / ratio
      const nav = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h')) || 68
      const veta = document.querySelector('.veta')?.getBoundingClientRect().height ?? 240
      const lede = document.querySelector('.hero-foot')?.getBoundingClientRect().height ?? 0
      // 1,16: caja del titular más el hueco del descendente de la «p», que se reserva como margen para no pisar la entradilla.
      const byHeight = (window.innerHeight - nav - veta - lede - 40) / 1.12
      const fs = Math.max(40, Math.min(byWidth, byHeight))
      el.style.fontSize = `${fs}px`
      box.style.marginBottom = `${Math.round(fs * 0.1)}px`
    }
    fit()
    document.fonts?.ready?.then(fit)
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [ref])
}

function Titular() {
  const ref = useRef<HTMLSpanElement>(null)
  useAjuste(ref)
  return (
    <h1 className="hero-title">
      <span className="wordmark-box">
        <span className="wordmark" ref={ref} style={{ fontFamily: fuente.family, fontVariationSettings: fuente.vs, fontWeight: fuente.weight }}>Vexplorer</span>
        <span className="cota" aria-hidden="true">
          <span className="cota-label">{W}</span>
        </span>
      </span>
    </h1>
  )
}

/** Alto del tramo en svh (también en .plano-track). Los umbrales del hero se escribieron para 300svh, así que se reescalan para que el hero salga exactamente igual en píxeles de scroll. */
const TRACK_SVH = 700
const HERO_K = (TRACK_SVH - 100) / 200

/** Por paso: lo que recibe la empresa y, debajo, cómo lo hace Vexplorer. */
const PASOS: [string, string][] = [
  ['Leemos el plano tal como llega del cliente.', 'Trabajamos sobre el DXF original con sus capas mezcladas y sus vistas sin nombre, y tu oficina técnica no tiene que limpiarlo antes.'],
  ['Separamos alzado, planta y perfil con todas sus cotas.', 'Descartamos la geometría que no pertenece al mueble y medimos sobre el dibujo las cotas que el plano no trae.'],
  ['Proponemos el despiece con nombre, cantidad y medidas de cada pieza.', 'Costados, frentes, fondos de cajón y guías salen ligados al contorno del plano del que vienen, y lo que el plano no define aparece marcado como estimado para que lo revises.'],
  ['Calculamos el coste de material de cada pieza.', 'Multiplicamos la superficie de cada pieza por tu tarifa de tablero y ves el resultado línea a línea en la misma tabla del despiece.'],
  ['Montamos el presupuesto listo para revisar y pasar a compras.', 'Preparación, tableros y guías van en una hoja que exportas en CSV o JSON, con los datos que faltan señalados como pendientes.'],
]

/** Tramo con escenario fijo: el hero con el titular y la veta, y después la demo de la cajonera en cinco pasos dentro de la caja del plano. */
function PlanoTrack() {
  const P = useTrackProgress('track')
  // Progreso en la escala del tramo original de 300svh: rige todo lo que comparte con el hero.
  const Ph = Math.min(1, P * HERO_K)
  const mode = useMode()
  const box = useRef<HTMLDivElement>(null)
  const theme = useTheme()
  const reduced = prefersReduced()
  const [fine, setFine] = useState(false)
  const slots = useRef<(HTMLDivElement | null)[]>([])
  const [slotBottoms, setSlotBottoms] = useState<number[]>(() => [0, ...PASOS.map(() => 0)])

  useEffect(() => setFine(window.matchMedia('(pointer: fine)').matches && !prefersReduced()), [])
  useLayoutEffect(() => {
    // Fondo del contenido de cada franja de texto, sin contar el desplazamiento del fundido.
    const measureSlots = () => setSlotBottoms(slots.current.map(el => (el ? el.offsetTop + el.offsetHeight : 0)))
    measureSlots()
    const ro = new ResizeObserver(measureSlots)
    slots.current.forEach(el => el && ro.observe(el))
    document.fonts?.ready?.then(measureSlots)
    return () => ro.disconnect()
  }, [mode])

  // El hero sale del todo (Ph 0,07) antes de que entre la caja del plano, para que el titular no la pise.
  const heroO = 1 - smooth(0.03, 0.07, Ph)
  // Paso continuo de 0 a 5: empieza cuando la caja ya ha entrado del todo (Ph 0,12).
  const P0 = 0.12 / HERO_K
  const s = Math.max(0, Math.min(5, ((P - P0) / (1 - P0)) * 5))
  // Con movimiento reducido cada frase cambia de golpe en el mismo punto que el dibujo (i + 0,75).
  const snap = (a: number, b: number, x: number) => (reduced ? (x >= Math.floor(a) + 0.75 ? 1 : 0) : smooth(a, b, x))
  const pasoO = PASOS.map((_, i) => {
    const inn = i === 0 ? smooth(0.09, 0.12, Ph) : snap(i - 1 + 0.78, i - 1 + 0.95, s)
    const out = i === PASOS.length - 1 ? 0 : snap(i + 0.55, i + 0.72, s)
    return inn * (1 - out)
  })
  const ops = [heroO, ...pasoO]

  // Caja del dibujo: entra con el primer scroll en la columna derecha y crece hacia abajo cuando la veta sale.
  const t = smooth(0.05, 0.12, Ph)
  const boxO = smooth(0.07, 0.11, Ph)
  // El logotipo de la cabecera cede el nombre al titular mientras se ve el hero.
  useEffect(() => {
    document.documentElement.dataset.hero = heroO > 0.5 ? '1' : '0'
  }, [heroO])
  // En móvil la caja empieza justo debajo del texto visible, para no dejar huecos.
  const wsum = ops.reduce((a, b) => a + b, 0)
  const lastTop = useRef(0)
  const mobileTop = wsum > 0.05 ? ops.reduce((a, o, i) => a + o * (slotBottoms[i] ?? 0), 0) / wsum + 16 : lastTop.current || (slotBottoms[0] ?? 0) + 16
  lastTop.current = mobileTop
  const boxTop = mode === 'mobile' ? `${Math.round(mobileTop)}px` : '96px'
  const boxBottom = `calc(var(--box-gap) + var(--veta-h) * ${(1 - t).toFixed(3)})`

  return (
    <div id="track" className="plano-track">
      <span id="top" className="anchor" style={{ top: 0 }} />
      <span id="desglose" className="anchor" style={{ top: '300svh' }} />
      <span id="coste" className="anchor" style={{ top: '404svh' }} />
      <div className="plano-stage">
        <Relieve o={heroO} />
        <div className="plano-box" ref={box} style={{ top: boxTop, bottom: boxBottom, opacity: boxO, visibility: boxO < 0.02 ? 'hidden' : 'visible' }}>
          {fine && boxO > 0.5 && s < 1.6 && <Crosshair containerRef={box} color={theme === 'dark' ? '#e6e1d6' : '#1c2541'} opacity={0.35} smoothing={0.25} showCoordinates targetEffect="lock" />}
          <Recorrido s={s} reduced={reduced} />
        </div>

        <figure className="veta" style={{ transform: `translateY(${(t * 105).toFixed(1)}%)` }} aria-hidden={t > 0.98}>
          <img src={vetaImg} alt="Veta de un tablero de madera con una fila de nudos" />
          <div className="qr-veta" style={{ opacity: heroO }}>
            <a href="https://gex-dashboard.hopto.org/vexplorer/" target="_blank" rel="noopener">
              <img src={qrPortal} alt="Código QR de la landing de Vexplorer" />
            </a>
            <a href={PORTAL_URL} target="_blank" rel="noopener">Pruébalo</a>
          </div>
          <p className="lede lede-veta" style={{ opacity: heroO }}>Sacamos de cada plano DXF el despiece y el coste de material, listos para que tu oficina técnica los revise.</p>
        </figure>

        <div className="slot slot-hero band" ref={el => { slots.current[0] = el }} style={layer(heroO)} aria-hidden={heroO < 0.02}>
          <Titular />
        </div>

        {PASOS.map(([frase, apoyo], i) => (
          <div key={i} className="slot slot-col band" ref={el => { slots.current[i + 1] = el }} style={layer(pasoO[i])} aria-hidden={pasoO[i] < 0.02}>
            <h2 className="paso-frase">{frase}</h2>
            <p className="paso-apoyo">{apoyo}</p>
            {i === PASOS.length - 1 && <a className="paso-portal" href={PORTAL_URL} target="_blank" rel="noopener">Probar Vexplorer</a>}
          </div>
        ))}

        <table className="sr-only">
          <thead>
            <tr>
              <th scope="col">Pieza</th>
              <th scope="col">Cantidad</th>
              <th scope="col">Largo × ancho × grosor (mm)</th>
              <th scope="col">Importe</th>
            </tr>
          </thead>
          <tbody>
            {PIEZAS.map(p => (
              <tr key={p.id}>
                <th scope="row">{p.nombre}</th>
                <td>{p.cantidad}</td>
                <td>{p.largo.v === null ? 'sin medida' : [p.largo, p.ancho, p.grosor].map(c => `${c.est ? 'aprox. ' : ''}${c.v}`).join(' × ')}</td>
                <td>{p.importe === null ? 'sin precio' : `${p.importeEstimado ? 'aprox. ' : ''}${p.importe.toFixed(2)} €`}</td>
              </tr>
            ))}
            <tr>
              <th scope="row">Preparación fija</th>
              <td>1</td>
              <td></td>
              <td>{RESUMEN.preparacion.toFixed(2)} €</td>
            </tr>
            <tr><th scope="row">Mano de obra</th><td>3 h</td><td>28 €/h</td><td>{RESUMEN.manoObra.toFixed(2)} €</td></tr>
            <tr><th scope="row">Acabado</th><td>3,20 m²</td><td>12 €/m²</td><td>{RESUMEN.acabado.toFixed(2)} €</td></tr>
            <tr>
              <th scope="row">Total estimado, sin impuestos</th>
              <td></td>
              <td></td>
              <td>aprox. {RESUMEN.subtotal.toFixed(2)} €</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** Esquema 3D en un tramo fijo: entra explosionado y el scroll lo monta pieza a pieza. Con movimiento reducido es un bloque normal con el mueble montado. */
function Reconstruccion() {
  const p = useTrackProgress('esquema')
  const reduced = prefersReduced()
  return (
    <section id="esquema" className={reduced ? 'esquema-track is-static' : 'esquema-track'}>
      <div className="track3d band">
        <div className="stage3d-copy">
          <h2 className="statement">Las ocho piezas montadas una a una en un esquema 3D de comprobación.</h2>
        </div>
        <div className="stage3d">
          <Schema3D progress={p} />
        </div>
      </div>
    </section>
  )
}

function Demo() {
  const [sent, setSent] = useState(false)
  const [fileMsg, setFileMsg] = useState('')
  const [fileName, setFileName] = useState('')
  const [motivo, setMotivo] = useState('demo')
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (fileMsg) return
    setSent(true)
  }
  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    setFileName(f ? f.name : '')
    if (!f) return setFileMsg('')
    if (f.size > 20 * 1024 * 1024) setFileMsg('El archivo pasa de 20 MiB. Elige un DXF más ligero.')
    else if (!/\.dxf$/i.test(f.name)) setFileMsg('El archivo tiene que ser un DXF.')
    else setFileMsg('')
  }
  return (
    <section id="demo" className="demo">
      {/* Maqueta: este formulario no envía datos a ningún sitio. Al enviarlo solo muestra un aviso en la página. */}
      <div className="band demo-inner">
        <div className="demo-foto">
          <img src={tallerImg} alt="" aria-hidden="true" loading="lazy" />
          <h2 className="statement demo-head">Cuéntanos tu caso.</h2>
        </div>
        <form className="demo-form" onSubmit={onSubmit}>
          <div className="field field-wide">
            <label htmlFor="f-motivo">Motivo</label>
            <select id="f-motivo" name="motivo" value={motivo} onChange={e => setMotivo(e.target.value)}>
              <option value="demo">Pedir demo</option>
              <option value="pregunta">Una pregunta</option>
              <option value="talento">Trabajar en Vexplorer</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="f-nombre">Nombre</label>
            <input id="f-nombre" name="nombre" autoComplete="name" required />
          </div>
          <div className="field">
            <label htmlFor="f-empresa">Empresa</label>
            <input id="f-empresa" name="empresa" autoComplete="organization" required={motivo === 'demo'} />
          </div>
          <div className="field field-wide">
            <label htmlFor="f-correo">Correo de trabajo</label>
            <input id="f-correo" name="correo" type="email" autoComplete="email" required />
          </div>
          {motivo !== 'demo' && (
            <div className="field field-wide">
              <label htmlFor="f-mensaje">Mensaje</label>
              <textarea id="f-mensaje" name="mensaje" rows={4} required />
            </div>
          )}
          {motivo === 'demo' && <div className="field field-wide">
            <span className="file-label" id="f-dxf-t">
              Plano DXF (opcional, hasta 20 MiB)
            </span>
            <div className="file-row">
              <input id="f-dxf" name="dxf" type="file" accept=".dxf" onChange={onFile} className="file-input" aria-labelledby="f-dxf-t" />
              <label htmlFor="f-dxf" className="file-btn">
                Elegir DXF
              </label>
              {fileName && <span className="file-name">{fileName}</span>}
            </div>
          </div>}
          {fileMsg && (
            <p className="file-error" role="alert">
              {fileMsg}
            </p>
          )}
          <button type="submit" className="btn">
            {motivo === 'demo' ? 'Pedir demo' : 'Enviar'}
          </button>
          <div aria-live="polite">
            {sent && <p className="form-sent">Gracias. Esta página es una maqueta y todavía no envía datos, así que nadie ha recibido la solicitud.</p>}
          </div>
        </form>
      </div>
    </section>
  )
}

// TODO Martín: los enlaces sin bloque en la página apuntan a anclas hasta que existan sus páginas.
const PIE: [string, [string, string][]][] = [
  ['Producto', [['Probar Vexplorer', PORTAL_URL], ['Cómo funciona', '#desglose'], ['Esquema 3D', '#esquema'], ['Formatos admitidos', '#formatos'], ['Pedir demo', '#demo']]],
  ['Empresa', [['Quiénes somos', '#quienes'], ['Trabajar en Vexplorer', '#talento'], ['Contacto', '#demo']]],
  ['Legal', [['Aviso legal', '#aviso-legal'], ['Privacidad', '#privacidad'], ['Cookies', '#cookies']]],
]

function Footer() {
  return (
    <footer className="band foot">
      <div className="foot-top">
        <span className="foot-logo">
          <Logo size={24} stroke={4} />
          Vexplorer
        </span>
        <nav className="foot-cols" aria-label="Pie">
          {PIE.map(([t, links]) => (
            <div key={t} className="foot-col">
              <p className="foot-h">{t}</p>
              <ul>
                {links.map(([l, h]) => (
                  <li key={l}><a href={h} {...(h.startsWith("http") ? { target: "_blank", rel: "noopener" } : {})}>{l}</a></li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </div>
      <div className="foot-bottom">
        <p className="foot-small">
          Vexplorer propone el despiece a partir de lo que trae el plano y una persona tiene que revisarlo antes de cortar ningún tablero. Los formularios de esta página todavía no envían datos.
        </p>
        <p className="foot-small">Foto del taller: Shixart1985, Wikimedia Commons, CC BY 2.0.</p>
        <p className="foot-copy">© 2026 Vexplorer</p>
      </div>
    </footer>
  )
}

/** Foto de taller a todo el ancho en duotono cobalto, entre el esquema y el formulario. */
function Taller() {
  return (
    <figure className="taller" aria-hidden="true">
      <img src={tallerImg} alt="" loading="lazy" />
    </figure>
  )
}

export default function App() {
  return (
    <>
      <a className="skip" href="#desglose">
        Saltar al contenido
      </a>
      <DuotoneFilters />
      <Nav />
      <main>
        <PlanoTrack />
        <Reconstruccion />
        <Demo />
      </main>
      <Footer />
      <DemoFlotante />
    </>
  )
}
