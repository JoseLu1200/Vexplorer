// Generado por scripts/caso_f02.py desde origin/main del repo Vexplorer. No editar a mano.
// DXF: data/cad_completion_controls/public/F02.dxf
// Despiece: evaluation/results/cad_completion_live_2026-11-14/F02.repaired.outcome.json (derived.package.construction)
// Precio: lógica de backend/app/estimacion/table_costs.py con el catálogo de demo (tarifas sintéticas).

export type Pt = [number, number]
export interface DxfEnt { h: string; layer: string; kind: 'poly' | 'line' | 'text' | 'point' | 'arrow'; pts?: Pt[]; closed?: boolean; x?: number; y?: number; height?: number; rot?: number; text?: string; scale?: number }
export interface DxfDim { h: string; layer: string; block: string; p1: Pt; p2: Pt; at: Pt; rot: number; parts: DxfEnt[] }
export interface Campo { v: number | null; est: boolean; min: number | null; max: number | null; state: string }
export interface PiezaCaso { id: string; nombre: string; etiqueta: string; cantidad: number; cantidadEstado: string; largo: Campo; ancho: Campo; grosor: Campo; contornos: string[]; areaM2: number | null; importe: number | null; importeEstimado: boolean }

export const DXF: { layers: Record<string, { aci: number; ltype: string }>; entities: DxfEnt[]; dims: DxfDim[] } = {"layers": {"0": {"aci": 7, "ltype": "Continuous"}, "Defpoints": {"aci": 7, "ltype": "Continuous"}, "G01": {"aci": 7, "ltype": "Continuous"}, "A01": {"aci": 3, "ltype": "Continuous"}, "D01": {"aci": 2, "ltype": "Continuous"}, "H01": {"aci": 8, "ltype": "DASHED"}}, "entities": [{"h": "8E", "layer": "G01", "kind": "poly", "pts": [[0.0, 0.0], [900.0, 0.0], [900.0, 800.0], [0.0, 800.0]], "closed": true}, {"h": "8F", "layer": "G01", "kind": "poly", "pts": [[18.0, 18.0], [882.0, 18.0], [882.0, 782.0], [18.0, 782.0]], "closed": true}, {"h": "90", "layer": "G01", "kind": "poly", "pts": [[21.0, 21.0], [879.0, 21.0], [879.0, 271.0], [21.0, 271.0]], "closed": true}, {"h": "91", "layer": "G01", "kind": "poly", "pts": [[21.0, 275.0], [879.0, 275.0], [879.0, 525.0], [21.0, 525.0]], "closed": true}, {"h": "92", "layer": "G01", "kind": "poly", "pts": [[21.0, 529.0], [879.0, 529.0], [879.0, 779.0], [21.0, 779.0]], "closed": true}, {"h": "93", "layer": "A01", "kind": "text", "x": 0.0, "y": 850.0, "height": 22.0, "rot": 0.0, "text": "V01"}, {"h": "94", "layer": "G01", "kind": "poly", "pts": [[1200.0, 0.0], [1650.0, 0.0], [1650.0, 800.0], [1200.0, 800.0]], "closed": true}, {"h": "95", "layer": "G01", "kind": "line", "pts": [[1200.0, 18.0], [1650.0, 18.0]], "closed": false}, {"h": "96", "layer": "G01", "kind": "line", "pts": [[1200.0, 272.0], [1650.0, 272.0]], "closed": false}, {"h": "97", "layer": "G01", "kind": "line", "pts": [[1200.0, 526.0], [1650.0, 526.0]], "closed": false}, {"h": "98", "layer": "G01", "kind": "line", "pts": [[1200.0, 782.0], [1650.0, 782.0]], "closed": false}, {"h": "99", "layer": "A01", "kind": "text", "x": 1200.0, "y": 850.0, "height": 22.0, "rot": 0.0, "text": "V02"}, {"h": "9A", "layer": "G01", "kind": "poly", "pts": [[0.0, 1050.0], [900.0, 1050.0], [900.0, 1500.0], [0.0, 1500.0]], "closed": true}, {"h": "9B", "layer": "G01", "kind": "line", "pts": [[18.0, 1050.0], [18.0, 1500.0]], "closed": false}, {"h": "9C", "layer": "G01", "kind": "line", "pts": [[882.0, 1050.0], [882.0, 1500.0]], "closed": false}, {"h": "9D", "layer": "A01", "kind": "text", "x": 0.0, "y": 1550.0, "height": 22.0, "rot": 0.0, "text": "V03"}], "dims": [{"h": "9E", "layer": "D01", "block": "*D1", "p1": [0.0, 0.0], "p2": [900.0, 0.0], "at": [0.0, -100.0], "rot": 0.0, "parts": [{"h": "A2", "layer": "0", "kind": "line", "pts": [[0.0, 0.0], [0.0, -100.0]], "closed": false}, {"h": "A3", "layer": "0", "kind": "line", "pts": [[900.0, 0.0], [900.0, -100.0]], "closed": false}, {"h": "A4", "layer": "D01", "kind": "arrow", "x": 0.0, "y": -100.0, "scale": 0.25, "rot": 180.0}, {"h": "A6", "layer": "D01", "kind": "arrow", "x": 900.0, "y": -100.0, "scale": 0.25, "rot": 0.0}, {"h": "A8", "layer": "0", "kind": "line", "pts": [[0.25, -100.0], [448.5, -100.0]], "closed": false}, {"h": "A9", "layer": "0", "kind": "line", "pts": [[451.5, -100.0], [899.75, -100.0]], "closed": false}, {"h": "AA", "layer": "D01", "kind": "text", "x": 450.0, "y": -100.0, "height": 1.0, "rot": 0.0, "text": "900"}, {"h": "AB", "layer": "Defpoints", "kind": "point", "x": 0.0, "y": -100.0}, {"h": "AC", "layer": "Defpoints", "kind": "point", "x": 0.0, "y": 0.0}, {"h": "AD", "layer": "Defpoints", "kind": "point", "x": 900.0, "y": 0.0}]}, {"h": "AE", "layer": "D01", "block": "*D2", "p1": [0.0, 0.0], "p2": [0.0, 800.0], "at": [-120.0, 0.0], "rot": 90.0, "parts": [{"h": "B2", "layer": "0", "kind": "line", "pts": [[0.0, 0.0], [-120.0, 0.0]], "closed": false}, {"h": "B3", "layer": "0", "kind": "line", "pts": [[0.0, 800.0], [-120.0, 800.0]], "closed": false}, {"h": "B4", "layer": "D01", "kind": "arrow", "x": -120.0, "y": 0.0, "scale": 0.25, "rot": 270.0}, {"h": "B6", "layer": "D01", "kind": "arrow", "x": -120.0, "y": 800.0, "scale": 0.25, "rot": 90.0}, {"h": "B8", "layer": "0", "kind": "line", "pts": [[-120.0, 0.25], [-120.0, 398.5]], "closed": false}, {"h": "B9", "layer": "0", "kind": "line", "pts": [[-120.0, 401.5], [-120.0, 799.75]], "closed": false}, {"h": "BA", "layer": "D01", "kind": "text", "x": -120.0, "y": 400.0, "height": 1.0, "rot": 90.0, "text": "800"}, {"h": "BB", "layer": "Defpoints", "kind": "point", "x": -120.0, "y": 0.0}, {"h": "BC", "layer": "Defpoints", "kind": "point", "x": 0.0, "y": 0.0}, {"h": "BD", "layer": "Defpoints", "kind": "point", "x": 0.0, "y": 800.0}]}, {"h": "BE", "layer": "D01", "block": "*D3", "p1": [1200.0, 0.0], "p2": [1650.0, 0.0], "at": [1200.0, -100.0], "rot": 0.0, "parts": [{"h": "C2", "layer": "0", "kind": "line", "pts": [[1200.0, 0.0], [1200.0, -100.0]], "closed": false}, {"h": "C3", "layer": "0", "kind": "line", "pts": [[1650.0, 0.0], [1650.0, -100.0]], "closed": false}, {"h": "C4", "layer": "D01", "kind": "arrow", "x": 1200.0, "y": -100.0, "scale": 0.25, "rot": 180.0}, {"h": "C6", "layer": "D01", "kind": "arrow", "x": 1650.0, "y": -100.0, "scale": 0.25, "rot": 0.0}, {"h": "C8", "layer": "0", "kind": "line", "pts": [[1200.25, -100.0], [1423.5, -100.0]], "closed": false}, {"h": "C9", "layer": "0", "kind": "line", "pts": [[1426.5, -100.0], [1649.75, -100.0]], "closed": false}, {"h": "CA", "layer": "D01", "kind": "text", "x": 1425.0, "y": -100.0, "height": 1.0, "rot": 0.0, "text": "450"}, {"h": "CB", "layer": "Defpoints", "kind": "point", "x": 1200.0, "y": -100.0}, {"h": "CC", "layer": "Defpoints", "kind": "point", "x": 1200.0, "y": 0.0}, {"h": "CD", "layer": "Defpoints", "kind": "point", "x": 1650.0, "y": 0.0}]}, {"h": "CE", "layer": "D01", "block": "*D4", "p1": [900.0, 0.0], "p2": [900.0, 18.0], "at": [930.0, 0.0], "rot": 90.0, "parts": [{"h": "D2", "layer": "0", "kind": "line", "pts": [[900.0, 0.0], [930.0, 0.0]], "closed": false}, {"h": "D3", "layer": "0", "kind": "line", "pts": [[900.0, 18.0], [930.0, 18.0]], "closed": false}, {"h": "D4", "layer": "D01", "kind": "arrow", "x": 930.0, "y": 0.0, "scale": 0.25, "rot": 270.0}, {"h": "D6", "layer": "D01", "kind": "arrow", "x": 930.0, "y": 18.0, "scale": 0.25, "rot": 90.0}, {"h": "D8", "layer": "0", "kind": "line", "pts": [[930.0, 0.25], [930.0, 8.0]], "closed": false}, {"h": "D9", "layer": "0", "kind": "line", "pts": [[930.0, 10.0], [930.0, 17.75]], "closed": false}, {"h": "DA", "layer": "D01", "kind": "text", "x": 930.0, "y": 9.0, "height": 1.0, "rot": 90.0, "text": "18"}, {"h": "DB", "layer": "Defpoints", "kind": "point", "x": 930.0, "y": 0.0}, {"h": "DC", "layer": "Defpoints", "kind": "point", "x": 900.0, "y": 0.0}, {"h": "DD", "layer": "Defpoints", "kind": "point", "x": 900.0, "y": 18.0}]}]}

export const PIEZAS: PiezaCaso[] = [
 {
  "id": "costados",
  "nombre": "Costado",
  "etiqueta": "Costados completos",
  "cantidad": 2,
  "cantidadEstado": "estimated",
  "largo": {
   "v": 800.0,
   "est": false,
   "min": null,
   "max": null,
   "state": "deduced"
  },
  "ancho": {
   "v": 450.0,
   "est": false,
   "min": null,
   "max": null,
   "state": "deduced"
  },
  "grosor": {
   "v": 18.0,
   "est": false,
   "min": null,
   "max": null,
   "state": "deduced"
  },
  "contornos": [
   "contour-entity-94"
  ],
  "areaM2": 0.72,
  "importe": 30.24,
  "importeEstimado": false
 },
 {
  "id": "horizontales",
  "nombre": "Tapa y base",
  "etiqueta": "Tapa y base entre costados",
  "cantidad": 2,
  "cantidadEstado": "estimated",
  "largo": {
   "v": 864.0,
   "est": false,
   "min": null,
   "max": null,
   "state": "deduced"
  },
  "ancho": {
   "v": 450.0,
   "est": false,
   "min": null,
   "max": null,
   "state": "deduced"
  },
  "grosor": {
   "v": 18.0,
   "est": false,
   "min": null,
   "max": null,
   "state": "deduced"
  },
  "contornos": [],
  "areaM2": 0.7776,
  "importe": 32.66,
  "importeEstimado": false
 },
 {
  "id": "frentes",
  "nombre": "Frente",
  "etiqueta": "Tres frentes interiores",
  "cantidad": 3,
  "cantidadEstado": "estimated",
  "largo": {
   "v": 858.0,
   "est": false,
   "min": null,
   "max": null,
   "state": "deduced"
  },
  "ancho": {
   "v": 250.0,
   "est": false,
   "min": null,
   "max": null,
   "state": "deduced"
  },
  "grosor": {
   "v": 18.0,
   "est": true,
   "min": 16.0,
   "max": 20.0,
   "state": "estimated"
  },
  "contornos": [
   "contour-entity-90",
   "contour-entity-91",
   "contour-entity-92"
  ],
  "areaM2": 0.6435,
  "importe": 27.03,
  "importeEstimado": false
 },
 {
  "id": "trasera",
  "nombre": "Trasera",
  "etiqueta": "Trasera interior estimada",
  "cantidad": 1,
  "cantidadEstado": "estimated",
  "largo": {
   "v": 862.0,
   "est": true,
   "min": 860.0,
   "max": 863.0,
   "state": "estimated"
  },
  "ancho": {
   "v": 762.0,
   "est": true,
   "min": 760.0,
   "max": 763.0,
   "state": "estimated"
  },
  "grosor": {
   "v": 6.0,
   "est": true,
   "min": 5.0,
   "max": 8.0,
   "state": "estimated"
  },
  "contornos": [],
  "areaM2": 0.656844,
  "importe": 27.59,
  "importeEstimado": true
 },
 {
  "id": "caja_lados",
  "nombre": "Lado de cajón",
  "etiqueta": "Costados de cajas",
  "cantidad": 6,
  "cantidadEstado": "estimated",
  "largo": {
   "v": 400.0,
   "est": true,
   "min": 380.0,
   "max": 410.0,
   "state": "estimated"
  },
  "ancho": {
   "v": 180.0,
   "est": true,
   "min": 160.0,
   "max": 200.0,
   "state": "estimated"
  },
  "grosor": {
   "v": 18.0,
   "est": true,
   "min": 15.0,
   "max": 19.0,
   "state": "estimated"
  },
  "contornos": [],
  "areaM2": 0.432,
  "importe": 18.14,
  "importeEstimado": true
 },
 {
  "id": "caja_testeros",
  "nombre": "Testero de cajón",
  "etiqueta": "Testeros delanteros y posteriores",
  "cantidad": 6,
  "cantidadEstado": "estimated",
  "largo": {
   "v": 802.0,
   "est": true,
   "min": 798.0,
   "max": 810.0,
   "state": "estimated"
  },
  "ancho": {
   "v": 180.0,
   "est": true,
   "min": 160.0,
   "max": 200.0,
   "state": "estimated"
  },
  "grosor": {
   "v": 18.0,
   "est": true,
   "min": 15.0,
   "max": 19.0,
   "state": "estimated"
  },
  "contornos": [],
  "areaM2": 0.86616,
  "importe": 36.38,
  "importeEstimado": true
 },
 {
  "id": "caja_fondos",
  "nombre": "Fondo de cajón",
  "etiqueta": "Fondos inferiores",
  "cantidad": 3,
  "cantidadEstado": "estimated",
  "largo": {
   "v": 838.0,
   "est": true,
   "min": 836.0,
   "max": 840.0,
   "state": "estimated"
  },
  "ancho": {
   "v": 400.0,
   "est": true,
   "min": 380.0,
   "max": 410.0,
   "state": "estimated"
  },
  "grosor": {
   "v": 6.0,
   "est": true,
   "min": 5.0,
   "max": 8.0,
   "state": "estimated"
  },
  "contornos": [],
  "areaM2": 1.0056,
  "importe": 42.24,
  "importeEstimado": true
 },
 {
  "id": "guias",
  "nombre": "Juego de guías",
  "etiqueta": "Juegos de dos guías laterales",
  "cantidad": 3,
  "cantidadEstado": "estimated",
  "largo": {
   "v": null,
   "est": false,
   "min": null,
   "max": null,
   "state": "unknown"
  },
  "ancho": {
   "v": null,
   "est": false,
   "min": null,
   "max": null,
   "state": "unknown"
  },
  "grosor": {
   "v": null,
   "est": false,
   "min": null,
   "max": null,
   "state": "unknown"
  },
  "contornos": [],
  "areaM2": null,
  "importe": null,
  "importeEstimado": false
 }
]

export const RESUMEN = {
 "preparacion": 25.0,
 "tarifaTablero": 42.0,
 "tableroTotal": 214.28,
 "subtotal": 239.28,
 "subtotalEstimado": true,
 "piezasTablero": 23,
 "catalogo": "synthetic-table-costs-2026-11-14",
 "estado": "Escenario constructivo cajonera",
 "authority": "provisional_not_manufacturing"
} as const
