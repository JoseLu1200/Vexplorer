import { PIEZAS as original, RESUMEN as resumen, type Campo } from './caso'
export { DXF } from './caso'
export type { Campo, DxfEnt, Pt } from './caso'
const medida = (v: number): Campo => ({ v, est: true, min: null, max: null, state: 'estimated' })
export const PIEZAS = original.map(p => p.id === 'guias' ? { ...p, largo: medida(400), ancho: medida(45), grosor: medida(13), importe: 54, importeEstimado: true } : p)
export const RESUMEN = { ...resumen, manoObra: 84, acabado: 38.40, subtotal: 415.68 }
