# Reconciliación completa de ramas

Base `4504adb`. Se incorporan transcript, CAD, reconstrucción, escena general y snapshot UX `0d1e133`. El snapshot conserva los archivos e índice del checkout raíz.

Para las ramas históricas, `git cherry` verifica equivalencia; las nueve variantes de contexto se contrastaron con funciones y regresiones existentes: cotas y rectangularidad, vistas mixtas y ocurrencias, fixtures, envolvente observada, límites de evidencia, círculos y catálogo de tarifas. Su merge de ascendencia conserva el árbol vigente, sin reintroducir versiones antiguas.

| Rama | Commit inspeccionado | Resultado |
|---|---|---|
| `audit/api-20261114` | `1ae40cdc0308` | Equivalencia de parches |
| `audit/app-20261114` | `59623efa8c80` | Incluida por ascendencia |
| `demo/backend` | `845071f280a7` | Variante histórica verificada; funciones y regresiones presentes |
| `demo/drawing-workbench` | `e703ae91a295` | Incluida por ascendencia |
| `demo/evaluacion` | `38c6c6b1321f` | Equivalencia de parches |
| `demo/first-executable` | `40e5e40526a5` | Incluida por ascendencia |
| `demo/frontend` | `db2581f55c52` | Equivalencia de parches |
| `demo/geometria` | `14eb3704cd60` | Equivalencia de parches |
| `demo/viewer-backend` | `40a87567724f` | Equivalencia de parches |
| `demo/viewer-evaluacion` | `68568a29856c` | Equivalencia de parches |
| `demo/viewer-frontend` | `c74c33ce4304` | Equivalencia de parches |
| `demo/viewer-geometria` | `f815b5569bd2` | Equivalencia de parches |
| `experiment/semantic-furniture` | `dbd1bb61a47e` | Incluida por ascendencia |
| `feat/cad-completion` | `e628fbe59d44` | Avance activo pendiente de incorporar |
| `feat/conditional-hours` | `803faae7f91e` | Incluida por ascendencia |
| `feat/cost-catalog-setup` | `8bebfa04be12` | Equivalencia de parches |
| `feat/dataset-evaluation` | `d0a43abfee82` | Incluida por ascendencia |
| `feat/mounted-table-drawings` | `443e9f1bef89` | Incluida por ascendencia |
| `feat/parts-backend` | `cb37d0a7bf61` | Variante histórica verificada; funciones y regresiones presentes |
| `feat/parts-evaluation` | `9b5ef636b721` | Variante histórica verificada; funciones y regresiones presentes |
| `feat/parts-frontend` | `6498ff0c170d` | Equivalencia de parches |
| `feat/parts-geometry` | `eb6fe9e9cbe1` | Equivalencia de parches |
| `feat/parts-integration` | `06cf51e453f3` | Incluida por ascendencia |
| `feat/plausibility-adaptation` | `ac766cbcb6b7` | Equivalencia de parches |
| `feat/private-production` | `42095101ac93` | Incluida por ascendencia |
| `feat/reconstruction-3d` | `ddc28ab0c472` | Incluida por ascendencia |
| `feat/semantic-explorer` | `6ea3b64ffb67` | Incluida por ascendencia |
| `feat/table-backend` | `59693148d0e5` | Variante histórica verificada; funciones y regresiones presentes |
| `feat/table-costs` | `6bb77abe5f81` | Variante histórica verificada; funciones y regresiones presentes |
| `feat/table-cutlist` | `15f32dbff55a` | Equivalencia de parches |
| `feat/table-evaluation` | `25d3134357ec` | Equivalencia de parches |
| `feat/table-frontend` | `22f5b4958a14` | Equivalencia de parches |
| `feat/table-geometry` | `577940538b47` | Variante histórica verificada; funciones y regresiones presentes |
| `feat/table-renderer` | `90efde9048d8` | Equivalencia de parches |
| `feat/transcript-completion` | `c94a88897ce0` | Incluida por ascendencia |
| `feat/transcript-final` | `0e65713e0125` | Incluida por ascendencia |
| `feat/vision-adaptation` | `751e4992a0ca` | Equivalencia de parches |
| `fix/parts-candidate-unknown-fields` | `579e85cbdc31` | Equivalencia de parches |
| `fix/parts-scene-reviewed-quantity` | `3bb8c825262d` | Equivalencia de parches |
| `integration/ux-snapshot` | `0d1e133baf00` | Incluida por ascendencia |
| `main` | `4504adb94c71` | Incluida por ascendencia |

## Solapes

Se conservan UX responsive, fuentes locales, accesibilidad, ResizeObserver y acceso público explícito; resumen y decisiones CAD, dimensiones estimadas y exportaciones; explorador semántico y reconstrucción 3D. La escena general conserva identidad exacta de revisiones y advierte que el catálogo no es montaje físico. Docker incorpora los nuevos assets.

Las ramas activas se revisan otra vez antes del cierre. No se modifican sus worktrees. La herramienta nativa de creación falló al apuntar al directorio padre sin Git; se creó el worktree ignorado `.worktrees/reconcile-all` con Git.
