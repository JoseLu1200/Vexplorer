import { useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { DXF, PIEZAS, RESUMEN, type Campo, type DxfEnt, type Pt } from './lib/caso'
import { smooth } from './lib/scroll'

/**
 * Demo de la cajonera F02 en cinco pasos dentro de la caja del plano.
 * `s` va de 0 a 5: la parte entera es el paso (0 plano en bruto, 1 limpieza y cotas, 2 piezas, 3 precio, 4 presupuesto)
 * y el paso i pasa al siguiente entre i + 0,55 e i + 0,95. Todo se dibuja en píxeles CSS de la caja medida.
 */

// Encuadre del espacio modelo del DXF (mm, y hacia arriba): las tres vistas, sus cotas y las cotas medidas del paso 2.
const MB = { x0: -240, x1: 1740, y0: -170, y1: 1600 }

/** Cotas del paso 2. Las cuatro primeras son las del DXF; las tres últimas las mide la geometría de los contornos 90, 9A y 92. */
const COTAS: { a: Pt; b: Pt; at: number; dir: 'h' | 'v'; txt: string; fuera?: boolean }[] = [
  { a: [0, 0], b: [900, 0], at: -100, dir: 'h', txt: '900' },
  { a: [0, 0], b: [0, 800], at: -120, dir: 'v', txt: '800' },
  { a: [1200, 0], b: [1650, 0], at: -100, dir: 'h', txt: '450' },
  { a: [900, 0], b: [900, 18], at: 930, dir: 'v', txt: '18', fuera: true },
  { a: [21, 779], b: [879, 779], at: 880, dir: 'h', txt: '858' },
  { a: [879, 21], b: [879, 271], at: 1060, dir: 'v', txt: '250' },
  { a: [0, 1050], b: [0, 1500], at: -120, dir: 'v', txt: '450' },
]

/** Contornos del DXF que el despiece revisado cita como origen de una pieza: solo esos viajan de la vista a la pieza. */
const ORIGEN: Record<string, string> = {}
PIEZAS.forEach(p => p.contornos.forEach(c => (ORIGEN[c.replace('contour-entity-', '')] = p.id)))

/** Tamaño de la miniatura de cada pieza en mm, en la orientación de la vista donde aparece. */
const MINI: Record<string, [number, number] | null> = {
  costados: [450, 800],
  horizontales: [864, 450],
  frentes: [858, 250],
  trasera: [862, 762],
  caja_lados: [400, 180],
  caja_testeros: [802, 180],
  caja_fondos: [838, 400],
  guias: null,
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const eur = (v: number) => `${v.toFixed(2).replace('.', ',')} €`
const mm = (c: Campo) => (c.v === null ? '' : `${c.est ? '≈' : ''}${Math.round(c.v)}`)
const medidas = (p: (typeof PIEZAS)[number]) => (p.largo.v === null ? 'sin medida' : `${mm(p.largo)} × ${mm(p.ancho)} × ${mm(p.grosor)}`)
const m2 = (p: (typeof PIEZAS)[number]) => (p.areaM2 === null ? '' : `${p.importeEstimado ? '≈' : ''}${p.areaM2.toFixed(2).replace('.', ',')} m²`)
const precio = (p: (typeof PIEZAS)[number]) => (p.importe === null ? 'sin precio' : `${p.importeEstimado ? '≈ ' : ''}${eur(p.importe)}`)
// Solo oculta: nunca fuerza visible, para no pintar dentro de la caja mientras está oculta bajo el hero.
const vis = (o: number): CSSProperties => ({ opacity: o, visibility: o < 0.01 ? 'hidden' : undefined })

/** Colores de capa ACI oscurecidos para que pasen de 3:1 sobre el papel en los dos temas. */
const ACI: Record<number, string> = { 7: 'var(--aci-7)', 3: 'var(--aci-3)', 2: 'var(--aci-2)', 8: 'var(--aci-8)' }

function useSize(ref: React.RefObject<SVGSVGElement | null>) {
  const [size, setSize] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const read = () => setSize({ w: el.clientWidth, h: el.clientHeight })
    read()
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return size
}

export default function Recorrido({ s, reduced }: { s: number; reduced: boolean }) {
  const ref = useRef<SVGSVGElement>(null)
  const { w, h } = useSize(ref)

  // Transición del paso i al i + 1. Con movimiento reducido salta de golpe y cada paso se ve estático.
  const T = [0, 1, 2, 3].map(i => (reduced ? (s >= i + 0.75 ? 1 : 0) : smooth(i + 0.55, i + 0.95, s)))
  // Con movimiento reducido, todo lo que pertenece a una transición salta en el mismo punto que ella (i + 0,75).
  const late = (a: number, b: number) => (reduced ? (s >= Math.floor(a) + 0.75 ? 1 : 0) : smooth(a, b, s))

  // Espacio modelo → píxeles de la caja.
  const sd = Math.min(w / (MB.x1 - MB.x0), h / (MB.y1 - MB.y0)) * 0.97
  const X = (x: number) => w / 2 + (x - (MB.x0 + MB.x1) / 2) * sd
  const Y = (y: number) => h / 2 - (y - (MB.y0 + MB.y1) / 2) * sd
  const pts = (p: Pt[]) => p.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join(' ')

  // Lista de piezas (pasos 3 y 4) y hoja de presupuesto (paso 5).
  const narrow = w < 480
  // En móvil el botón flotante «Pide una demo» tapa el pie de la caja: la lista y la leyenda acaban por encima.
  const bottom = narrow ? 72 : 0
  const legendH = 62
  const rowH = Math.min(92, (h - bottom - legendH - 6) / PIEZAS.length)
  const tw = Math.min(150, w * 0.26)
  const st = Math.min((tw - 10) / 864, (rowH - 14) / 800)
  const x0 = tw + 12
  const rowTop = (i: number) => 4 + i * rowH
  const nameY = (i: number) => rowTop(i) + rowH / 2 - 3
  const dimY = (i: number) => rowTop(i) + rowH / 2 + 15
  const titleH = 50
  const lh = Math.min(30, (h - titleH - 114) / 12)
  const lineY = (k: number) => titleH + (k + 0.5) * lh + 5
  const colM2 = w - (narrow ? 82 : 120)

  const mini = (id: string, i: number) => {
    const m = MINI[id]
    if (!m) return null
    const [mw, mh] = m
    return { x: (tw - mw * st) / 2, y: rowTop(i) + (rowH - mh * st) / 2, w: mw * st, h: mh * st }
  }

  const raw = 1 - T[0]
  const clean = T[0] * (1 - T[1])
  const list = late(1.75, 1.95)
  const draw = late(1.55, 1.95)
  const prices = late(2.75, 2.95)
  const sheet = late(3.75, 3.95)
  const legend3 = list * (1 - T[2])
  const legend4 = prices * (1 - T[3])

  return (
    <svg ref={ref} className="recorrido" viewBox={`0 0 ${Math.max(1, w)} ${Math.max(1, h)}`} role="img" aria-labelledby="rec-t rec-d">
      <title id="rec-t">Plano DXF de una cajonera convertido en despiece y presupuesto</title>
      <desc id="rec-d">
        Cajonera de 900 por 800 por 450 milímetros en tres vistas. Al bajar, el plano en bruto se limpia, se acota, se separa en 23 tableros y tres juegos de guías, cada pieza recibe su precio y todo acaba en una hoja de presupuesto con subtotal de 239,28 euros, aproximado.
      </desc>
      {w > 0 && (
        <>
          {/* Paso 1: el DXF tal como llega, con los colores de capa del CAD, los rótulos V01 a V03, los puntos de definición y las cotas con texto de una unidad de alto. */}
          <g className="rec-raw" style={vis(raw)} aria-hidden="true">
            {DXF.entities.map(e => <Ent key={e.h} e={e} X={X} Y={Y} sd={sd} pts={pts} color={ACI[DXF.layers[e.layer]?.aci ?? 7]} />)}
            {DXF.dims.map(d => (
              <g key={d.h}>
                {d.parts.map((e, k) => <Ent key={k} e={e} X={X} Y={Y} sd={sd} pts={pts} color={e.layer === 'Defpoints' ? ACI[7] : ACI[DXF.layers[d.layer]?.aci ?? 2]} />)}
              </g>
            ))}
          </g>

          {/* Tabla de capas del DXF, como la lista de capas de un CAD. */}
          <g className="rec-capas" style={vis(raw)} aria-hidden="true">
            {Object.entries(DXF.layers).map(([name, l], k, all) => {
              const col = narrow ? k % 3 : k
              const row = narrow ? Math.floor(k / 3) : 0
              const cw = narrow ? w / 3 : Math.min(110, w / all.length)
              return (
                <g key={name} transform={`translate(${col * cw} ${14 + row * 20})`}>
                  <rect x={0} y={-9} width={10} height={10} fill={ACI[l.aci] ?? ACI[7]} />
                  <text x={16} y={0}>{name}</text>
                </g>
              )
            })}
          </g>

          {/* Paso 2: vistas en limpio, en trazo cobalto, y las cotas que se dibujan. */}
          <g className="rec-clean" style={vis(clean)} aria-hidden="true">
            {DXF.entities
              .filter(e => e.layer === 'G01' && !ORIGEN[e.h])
              .map(e => (e.pts ? <polyline key={e.h} points={pts(e.closed ? [...e.pts, e.pts[0]] : e.pts)} className="rec-line" /> : null))}
            {COTAS.map((c, j) => (
              <Cota key={j} c={c} X={X} Y={Y} p={reduced ? (s >= 0.75 ? 1 : 0) : smooth(0.62 + j * 0.07, 0.95 + j * 0.07, s)} />
            ))}
          </g>

          {/* Pasos 3 a 5: piezas. Los contornos de origen (94 para los costados, 90 a 92 para los frentes) viajan desde su vista. */}
          <g aria-hidden="true">
            {PIEZAS.map((p, i) => {
              const m = mini(p.id, i)
              if (!m) return null
              const thumbO = 1 - T[3]
              const fromIds = DXF.entities.filter(e => ORIGEN[e.h] === p.id)
              if (fromIds.length) {
                return fromIds.map(e => {
                  const xs = e.pts!.map(q => q[0])
                  const ys = e.pts!.map(q => q[1])
                  const vx = X(Math.min(...xs))
                  const vy = Y(Math.max(...ys))
                  const vw = (Math.max(...xs) - Math.min(...xs)) * sd
                  const vh = (Math.max(...ys) - Math.min(...ys)) * sd
                  const t = T[1]
                  return (
                    <rect
                      key={e.h}
                      className="rec-line rec-pieza"
                      x={lerp(vx, m.x, t)}
                      y={lerp(vy, m.y, t)}
                      width={lerp(vw, m.w, t)}
                      height={lerp(vh, m.h, t)}
                      style={{ ...vis(T[0] * thumbO), fillOpacity: T[1] }}
                    />
                  )
                })
              }
              return (
                <rect
                  key={p.id}
                  className={`rec-line rec-pieza${p.importeEstimado && draw >= 1 ? ' is-est' : ''}`}
                  x={m.x}
                  y={m.y}
                  width={m.w}
                  height={m.h}
                  pathLength={draw < 1 ? 1 : undefined}
                  style={{ ...vis(Math.min(1, draw * 4) * thumbO), strokeDasharray: draw < 1 ? 1 : undefined, strokeDashoffset: draw < 1 ? 1 - draw : undefined }}
                />
              )
            })}
          </g>

          {/* Rótulos de las piezas: en los pasos 3 y 4 junto a la miniatura; en el 5 bajan a una línea de la hoja. */}
          <g className="rec-txt" aria-hidden="true">
            {PIEZAS.map((p, i) => {
              const k = i + 1
              const t = T[3]
              const ny = lerp(nameY(i), lineY(k), t)
              return (
                <g key={p.id}>
                  <text className="rec-name" x={lerp(x0, 0, t)} y={ny} style={vis(list)}>
                    {p.nombre} <tspan className="rec-qty">×{p.cantidad}</tspan>
                  </text>
                  <text className={p.largo.v === null ? "rec-dim rec-pend" : "rec-dim"} x={x0} y={dimY(i)} style={vis(list * (1 - t))}>
                    {medidas(p)}
                  </text>
                  <text className={p.importe === null ? "rec-price rec-pend" : "rec-price"} x={w} y={ny} textAnchor="end" style={vis(prices)}>
                    {precio(p)}
                  </text>
                  <text className={p.areaM2 === null ? "rec-m2 rec-pend" : "rec-m2"} x={lerp(w, colM2, t)} y={lerp(dimY(i), lineY(k), t)} textAnchor="end" style={vis(prices)}>
                    {p.areaM2 === null ? (t > 0.5 && !narrow ? 'sin medida' : '') : m2(p)}
                  </text>
                </g>
              )
            })}
          </g>

          {/* Leyendas de los pasos 3 y 4. */}
          <g className="rec-legend" aria-hidden="true">
            <text x={0} y={h - bottom - legendH + 18} style={vis(legend3)}>≈ medida estimada</text>
            <text x={0} y={h - bottom - legendH + 36} style={vis(legend3)}>Cantidades del escenario propuesto</text>
            <text x={0} y={h - bottom - legendH + 18} style={vis(legend4)}>≈ importe con alguna medida estimada</text>
            <text x={0} y={h - bottom - legendH + 36} style={vis(legend4)}>Tarifa de tablero por m², de ejemplo</text>
            <text x={0} y={h - bottom - legendH + 54} style={vis(legend4)}>Cantidades del escenario propuesto</text>
          </g>

          {/* Paso 5: hoja de presupuesto. */}
          <g className="rec-sheet" style={vis(sheet)} aria-hidden="true">
            <text className="rec-title" x={0} y={titleH - 14}>Presupuesto</text>
            <text className="rec-ejemplo" x={w} y={titleH - 16} textAnchor="end">Tarifas de ejemplo</text>
            <line className="rec-rule-strong" x1={0} x2={w} y1={titleH} y2={titleH} />
            <text className="rec-name" x={0} y={lineY(0)}>Preparación fija</text>
            <text className="rec-price" x={w} y={lineY(0)} textAnchor="end">{eur(RESUMEN.preparacion)}</text>
            {[...Array(10)].map((_, k) => (
              <line key={k} className="rec-rule" x1={0} x2={w} y1={titleH + (k + 1) * lh} y2={titleH + (k + 1) * lh} />
            ))}
            <text className="rec-name" x={0} y={lineY(9)}>Mano de obra</text>
            <text className="rec-price rec-pend" x={w} y={lineY(9)} textAnchor="end">sin horas</text>
            <text className="rec-name" x={0} y={lineY(10)}>Acabado</text>
            <text className="rec-price rec-pend" x={w} y={lineY(10)} textAnchor="end">sin superficie</text>
            <line className="rec-rule-strong" x1={0} x2={w} y1={titleH + 11 * lh} y2={titleH + 11 * lh} />
            <text className="rec-total" x={0} y={titleH + 11 * lh + 36}>Subtotal conocido</text>
            <text className="rec-total rec-total-num" x={w} y={titleH + 11 * lh + 36} textAnchor="end">
              {RESUMEN.subtotalEstimado ? '≈ ' : ''}
              {eur(RESUMEN.subtotal)}
            </text>
            <text className="rec-note" x={0} y={titleH + 11 * lh + 64}>Tarifa de tablero por m², de ejemplo. Sin impuestos.</text>
            <text className="rec-note" x={0} y={titleH + 11 * lh + 82}>≈ con alguna medida estimada</text>
            <text className="rec-note" x={0} y={titleH + 11 * lh + 100}>Cantidades del escenario propuesto</text>
          </g>
        </>
      )}
    </svg>
  )
}

function Ent({ e, X, Y, sd, pts, color }: { e: DxfEnt; X: (x: number) => number; Y: (y: number) => number; sd: number; pts: (p: Pt[]) => string; color: string }) {
  if (e.kind === 'poly' || e.kind === 'line') {
    const p = e.closed ? [...e.pts!, e.pts![0]] : e.pts!
    return <polyline points={pts(p)} fill="none" stroke={color} strokeWidth={1} />
  }
  if (e.kind === 'text') {
    // Altura real del DXF: los rótulos miden 22 y el texto de las cotas 1, así que este último casi no se ve.
    const size = Math.max(0.5, e.height! * sd)
    return (
      <text x={X(e.x!)} y={Y(e.y!)} fill={color} fontSize={size} className="rec-cad" transform={e.rot ? `rotate(${-e.rot} ${X(e.x!)} ${Y(e.y!)})` : undefined} textAnchor={e.height! < 2 ? 'middle' : undefined}>
        {e.text}
      </text>
    )
  }
  if (e.kind === 'point') return <circle cx={X(e.x!)} cy={Y(e.y!)} r={1.6} fill={color} />
  if (e.kind === 'arrow') {
    // Bloque _CLOSEDFILLED: triángulo de una unidad escalado a 0,25 en el DXF.
    const a = Math.max(0.6, e.scale! * sd)
    return <path d={`M0 0 L${-a} ${-a / 6} L${-a} ${a / 6} Z`} fill={color} transform={`translate(${X(e.x!)} ${Y(e.y!)}) rotate(${-(e.rot ?? 0)})`} />
  }
  return null
}

function Cota({ c, X, Y, p }: { c: (typeof COTAS)[number]; X: (x: number) => number; Y: (y: number) => number; p: number }) {
  const ext = 8
  if (c.dir === 'h') {
    const y = Y(c.at)
    const xa = X(c.a[0])
    const xb = X(c.b[0])
    const ya = Y(c.a[1])
    const sgn = y > ya ? 1 : -1
    return (
      <g className="rec-cota">
        <line pathLength={1} x1={xa} y1={ya + sgn * 3} x2={xa} y2={y + sgn * ext} className="rec-ext" style={dash(p)} />
        <line pathLength={1} x1={xb} y1={Y(c.b[1]) + sgn * 3} x2={xb} y2={y + sgn * ext} className="rec-ext" style={dash(p)} />
        <line pathLength={1} x1={xa} y1={y} x2={xb} y2={y} style={dash(p)} />
        <path d={`M${xa - 4} ${y + 4} L${xa + 4} ${y - 4} M${xb - 4} ${y + 4} L${xb + 4} ${y - 4}`} style={vis(p >= 0.98 ? 1 : 0)} />
        <text x={(xa + xb) / 2} y={sgn > 0 ? y + 15 : y - 6} textAnchor="middle" className="rec-cota-txt" style={vis(smooth(0.7, 1, p))}>
          {c.txt}
        </text>
      </g>
    )
  }
  const x = X(c.at)
  const ya = Y(c.a[1])
  const yb = Y(c.b[1])
  const xa = X(c.a[0])
  const sgn = x > xa ? 1 : -1
  return (
    <g className="rec-cota">
      <line pathLength={1} x1={xa + sgn * 3} y1={ya} x2={x + sgn * ext} y2={ya} className="rec-ext" style={dash(p)} />
      <line pathLength={1} x1={X(c.b[0]) + sgn * 3} y1={yb} x2={x + sgn * ext} y2={yb} className="rec-ext" style={dash(p)} />
      <line pathLength={1} x1={x} y1={ya} x2={x} y2={yb} style={dash(p)} />
      <path d={`M${x - 4} ${ya + 4} L${x + 4} ${ya - 4} M${x - 4} ${yb + 4} L${x + 4} ${yb - 4}`} style={vis(p >= 0.98 ? 1 : 0)} />
      {c.fuera ? (
        <text x={x - 2} y={ya + 15} className="rec-cota-txt" style={vis(smooth(0.7, 1, p))}>
          {c.txt}
        </text>
      ) : (
        <text x={0} y={0} textAnchor="middle" className="rec-cota-txt" transform={`translate(${x + (sgn < 0 ? -6 : 14)} ${(ya + yb) / 2}) rotate(-90)`} style={vis(smooth(0.7, 1, p))}>
          {c.txt}
        </text>
      )}
    </g>
  )
}

const dash = (p: number): CSSProperties => ({ strokeDasharray: 1, strokeDashoffset: 1 - p, visibility: p < 0.01 ? 'hidden' : undefined })
