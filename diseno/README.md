# Diseño de Vexplorer

Prototipos de frontend hechos fuera de `frontend/`, que es de C. No sustituyen al frontend del equipo.

| Carpeta | Qué es | Arranque |
|---|---|---|
| `portal/` | Portal tipo visor CAD: catálogo de muebles procesados, mesa de trabajo con plano, piezas y 3D enlazados, «Ver el proceso», Construcción 3D con GLB, mapa de muebles y embeddings | `cd diseno/portal && npm ci && npm run dev` (datos de ejemplo). Contra el backend: `VITE_USE_MOCK=false VITE_API_PROXY=http://127.0.0.1:18864 npm run dev` con la demo `data/full_app_demo` restaurada |
| `landing/` | Landing de Vexplorer (línea cobalto, variante Ensamble) | `cd diseno/landing && npm ci && npm run dev` |
| `logos/` | Hojas de propuestas de logo; el elegido es la variante Diagonal de `logos-cota.html` | Abrir el HTML |

El mapa de muebles y los casos de PlankAssembly se generan en local (`portal/scripts/mapa_*.py`) en `portal/public/local/`, que no se versiona: PlankAssembly es CC BY-NC-ND 4.0.
