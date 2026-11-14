# Reconciliación completa de ramas

Base `4504adb`. Se incorporan transcript, CAD, reconstrucción, escena general y snapshot UX `0d1e133`. El snapshot conserva los archivos e índice del checkout raíz.

Para las ramas históricas, `git cherry` verifica equivalencia; las nueve variantes de contexto se contrastaron con funciones y regresiones existentes: cotas y rectangularidad, vistas mixtas y ocurrencias, fixtures, envolvente observada, límites de evidencia, círculos y catálogo de tarifas. Su merge de ascendencia conserva el árbol vigente, sin reintroducir versiones antiguas.

| Rama | Commit inspeccionado | Resultado |
|---|---|---|
| `audit/api-20261114` | `1ae40cdc0308` | Incluida por ascendencia |
| `audit/app-20261114` | `59623efa8c80` | Incluida por ascendencia |
| `demo/backend` | `845071f280a7` | Incluida por ascendencia |
| `demo/drawing-workbench` | `e703ae91a295` | Incluida por ascendencia |
| `demo/evaluacion` | `38c6c6b1321f` | Incluida por ascendencia |
| `demo/first-executable` | `40e5e40526a5` | Incluida por ascendencia |
| `demo/frontend` | `db2581f55c52` | Incluida por ascendencia |
| `demo/geometria` | `14eb3704cd60` | Incluida por ascendencia |
| `demo/viewer-backend` | `40a87567724f` | Incluida por ascendencia |
| `demo/viewer-evaluacion` | `68568a29856c` | Incluida por ascendencia |
| `demo/viewer-frontend` | `c74c33ce4304` | Incluida por ascendencia |
| `demo/viewer-geometria` | `f815b5569bd2` | Incluida por ascendencia |
| `experiment/semantic-furniture` | `dbd1bb61a47e` | Incluida por ascendencia |
| `feat/cad-completion` | `8e5f584aa052` | Incluida por ascendencia |
| `feat/conditional-hours` | `803faae7f91e` | Incluida por ascendencia |
| `feat/cost-catalog-setup` | `8bebfa04be12` | Incluida por ascendencia |
| `feat/dataset-evaluation` | `d0a43abfee82` | Incluida por ascendencia |
| `feat/mounted-table-drawings` | `443e9f1bef89` | Incluida por ascendencia |
| `feat/parts-backend` | `cb37d0a7bf61` | Incluida por ascendencia |
| `feat/parts-evaluation` | `9b5ef636b721` | Incluida por ascendencia |
| `feat/parts-frontend` | `6498ff0c170d` | Incluida por ascendencia |
| `feat/parts-geometry` | `eb6fe9e9cbe1` | Incluida por ascendencia |
| `feat/parts-integration` | `06cf51e453f3` | Incluida por ascendencia |
| `feat/plausibility-adaptation` | `ac766cbcb6b7` | Incluida por ascendencia |
| `feat/private-production` | `42095101ac93` | Incluida por ascendencia |
| `feat/reconstruction-3d` | `ddc28ab0c472` | Incluida por ascendencia |
| `feat/semantic-explorer` | `6ea3b64ffb67` | Incluida por ascendencia |
| `feat/table-backend` | `59693148d0e5` | Incluida por ascendencia |
| `feat/table-costs` | `6bb77abe5f81` | Incluida por ascendencia |
| `feat/table-cutlist` | `15f32dbff55a` | Incluida por ascendencia |
| `feat/table-evaluation` | `25d3134357ec` | Incluida por ascendencia |
| `feat/table-frontend` | `22f5b4958a14` | Incluida por ascendencia |
| `feat/table-geometry` | `577940538b47` | Incluida por ascendencia |
| `feat/table-renderer` | `90efde9048d8` | Incluida por ascendencia |
| `feat/transcript-completion` | `c94a88897ce0` | Incluida por ascendencia |
| `feat/transcript-final` | `0e65713e0125` | Incluida por ascendencia |
| `feat/vision-adaptation` | `751e4992a0ca` | Incluida por ascendencia |
| `fix/parts-candidate-unknown-fields` | `579e85cbdc31` | Incluida por ascendencia |
| `fix/parts-scene-reviewed-quantity` | `3bb8c825262d` | Incluida por ascendencia |
| `integration/cad-completion-final` | `72c63315ded8` | Incluida por ascendencia |
| `integration/cad-snapshot` | `41c5351d14a3` | Incluida por ascendencia |
| `integration/reconcile-all` | `5502d0470ac1` | Incluida por ascendencia |
| `integration/reconstruction-3d-final` | `07a48c65f027` | Incluida por ascendencia |
| `integration/reconstruction-panel-snapshot` | `9e74cfb0662a` | Incluida por ascendencia |
| `integration/ux-snapshot` | `0d1e133baf00` | Incluida por ascendencia |
| `main` | `4504adb94c71` | Incluida por ascendencia |

## Solapes

Se conservan UX responsive, fuentes locales, accesibilidad, ResizeObserver y acceso público explícito; resumen y decisiones CAD, dimensiones estimadas y exportaciones; explorador semántico y reconstrucción 3D. La escena general conserva identidad exacta de revisiones y advierte que el catálogo no es montaje físico. Docker incorpora los nuevos assets.

Las ramas activas se revisan otra vez antes del cierre. No se modifican sus worktrees. La herramienta nativa de creación falló al apuntar al directorio padre sin Git; se creó el worktree ignorado `.worktrees/reconcile-all` con Git.


## Cierre de integración

Se incorporó CAD `8e5f584` con resultados y procedencia completos. El snapshot CAD `72c6331` tiene exactamente el mismo árbol y se reconcilió por ascendencia. La reconstrucción incluye el snapshot `07a48c6`: respuestas anteriores editables y exportación revision.json. Las copias del overhaul UX en esa rama no sustituyen la versión integrada: se conservan CAD, navegación semántica y selección de revisiones. Los archivos originales y sus índices no se alteran.

Verificación: 187 pruebas JavaScript aprobadas; navegador Chromium sin errores JavaScript ni HTTP en navegación, 117 puntos semánticos/10 vecinos, reconstrucción y vista móvil. La última suite Python y CI se registran en el cierre de equipo.

Último corte de código: snapshot `9e74cfb`, panel 3D integrado en la interfaz existente, conservando su estilo. Suite final: 837 Python y 187 JavaScript aprobadas. Se contrastaron los snapshots UX y CAD con sus originales: sin diferencias. Los archivos sin commit de reconstrucción se capturaron hasta ese corte; cualquier edición posterior de otra sesión requiere una integración nueva.
