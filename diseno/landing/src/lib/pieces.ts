import type { DataClass } from './scroll'

/** Estantería de ejemplo: 1800 × 900 × 400 mm, tablero de 18 mm. Coordenadas en mm, origen abajo a la izquierda (vista frontal). */
export interface Piece {
  id: string
  name: string
  qty: number
  /** rectángulo en la vista frontal */
  x: number
  y: number
  w: number
  h: number
  /** medidas de despiece: largo × ancho × grosor (null = desconocido) */
  dims: [number, number, number | null]
  cls: DataClass
  /** desplazamiento del despiece en unidades de dibujo */
  dx: number
  dy: number
  hidden?: boolean
  /** caja 3D: x, y, z (mm) y tamaño */
  box: [number, number, number, number, number, number]
}

export const W = 900
export const H = 1800
export const D = 400
export const T = 18

export const PIECES: Piece[] = [
  { id: 'P1', name: 'Lateral izq.', qty: 2, x: 0, y: 0, w: T, h: H, dims: [1800, 400, 18], cls: 'observado', dx: -80, dy: 0, box: [0, 0, 0, T, H, D] },
  { id: 'P2', name: 'Lateral der.', qty: 2, x: W - T, y: 0, w: T, h: H, dims: [1800, 400, 18], cls: 'observado', dx: 80, dy: 0, box: [W - T, 0, 0, T, H, D] },
  { id: 'P3', name: 'Base', qty: 1, x: T, y: 0, w: W - 2 * T, h: T, dims: [864, 400, 18], cls: 'confirmado', dx: 0, dy: 70, box: [T, 0, 0, W - 2 * T, T, D] },
  { id: 'P4', name: 'Techo', qty: 1, x: T, y: H - T, w: W - 2 * T, h: T, dims: [864, 400, 18], cls: 'calculado', dx: 0, dy: -70, box: [T, H - T, 0, W - 2 * T, T, D] },
  { id: 'P5', name: 'Balda', qty: 3, x: T, y: 441, w: W - 2 * T, h: T, dims: [864, 380, 18], cls: 'hipotesis', dx: 0, dy: 26, box: [T, 441, 20, W - 2 * T, T, D - 20] },
  { id: 'P6', name: 'Balda', qty: 3, x: T, y: 891, w: W - 2 * T, h: T, dims: [864, 380, 18], cls: 'hipotesis', dx: 0, dy: 0, box: [T, 891, 20, W - 2 * T, T, D - 20] },
  { id: 'P7', name: 'Balda', qty: 3, x: T, y: 1341, w: W - 2 * T, h: T, dims: [864, 380, 18], cls: 'hipotesis', dx: 0, dy: -26, box: [T, 1341, 20, W - 2 * T, T, D - 20] },
  { id: 'P8', name: 'Trasera', qty: 1, x: 9, y: 9, w: W - 18, h: H - 18, dims: [1782, 882, null], cls: 'desconocido', dx: 0, dy: 0, hidden: true, box: [9, 9, 0, W - 18, H - 18, 4] },
]

export const CLASS_INFO: Record<DataClass, { label: string; note: string; color: string; def: string }> = {
  observado: { label: 'Observado', note: 'Laterales: cota del plano, 1800 mm', color: 'var(--c-obs)', def: 'cota leída en el plano.' },
  calculado: { label: 'Calculado', note: 'Techo: 900 − 2 × 18 = 864 mm', color: 'var(--c-calc)', def: 'sale de otras cotas con una operación visible.' },
  hipotesis: { label: 'Hipótesis', note: 'Baldas: ¿tres o cuatro?', color: 'var(--c-hip)', def: 'propuesta que falta confirmar.' },
  confirmado: { label: 'Confirmado', note: 'Base: confirmada por un técnico', color: 'var(--c-conf)', def: 'revisado por una persona.' },
  desconocido: { label: 'Desconocido', note: 'Trasera: grosor desconocido', color: 'var(--ink-2)', def: 'el plano no lo da y nadie lo rellena.' },
}
