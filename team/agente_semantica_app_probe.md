# Agente de prueba cruzada de la app — laboratorio aislado

## Identidad y autorización

- Identidad: agente de IA encargado de probar la app real sobre otros datasets; no representa a una persona.
- Autorización explícita del usuario, 2026-11-14: probar los datasets descargados con la app y el embedding, documentarlo y dejar el commit/push a coordinación.
- Registro propio y alcance designados por coordinación en esta sesión.

## Tarea de la sesión

- Objetivo: ejecutar una instantánea local y reproducible de la app actual contra muestras públicas deterministas de los corpus mecánico, PlankAssembly y CADBlock, sin modificar producto ni usar oráculos privados.
- Estado: terminado.

## Alcance y reservas

- Propiedad exclusiva: `tools/semantic_lab/probe_app.py`, `tests/test_semantic_lab_probe_app.py`, `docs/semantic-lab/PRUEBA_APP_OTROS_DATASETS.md` y este registro.
- Artefactos externos: `D:/Vexplorer-semantic-lab/cross-dataset/app-snapshot` y `D:/Vexplorer-semantic-lab/cross-dataset/app`.
- Solo lectura: app actual en la rama `feat/transcript-completion`, datasets públicos autorizados, resto del laboratorio semántico y sus embeddings.
- Fuera de alcance: arreglar producto, contratos, backend/frontend, datasets `_private`, oráculos de piezas, servicios o datos de producción, commits y push.
- Solapes comprobados: ninguno en los archivos reservados; otros agentes poseen módulos y pruebas distintos de `tools/semantic_lab/`.

## Hecho en el último bloque

- Ejecutadas dos instantáneas aisladas por cambio concurrente de cuatro archivos de histórico/contrato; v2 es la referencia final y quedó estable 68/68 hashes.
- Probados 53 archivos públicos: 14 mecánicos, 16 PlankAssembly, 20 CADBlock fuera del core y 3 PDF.
- Guardadas respuestas y runtime hermético bajo `D:/Vexplorer-semantic-lab/cross-dataset/app-v2`.
- Documentado el contraste: ingesta/extracción parcial, cero propuestas/piezas, abstención del pipeline legado e importación final de cuatro registros históricos públicos.

## Siguiente bloque

- Integración, commit y push por coordinación; no quedan acciones de producto en este alcance.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-11-14 | Probar una copia congelada fuera del repo, sin `.env`, `.git`, persistencia ni servicios productivos | Evitar alterar o depender de la rama activa y conservar procedencia |
| 2026-11-14 | Informar HTTP, ingesta, geometría, propuestas y revisión por separado | Un HTTP 2xx no acredita un despiece correcto |
| 2026-11-14 | Hacer una sola recaptura v2 tras detectar drift concurrente | Contrastar el arreglo de histórico sin perseguir indefinidamente una rama móvil |
| 2026-11-14 | No ejecutar live | Configuración incompleta: falta `OPENAI_MODEL`; no inventar modelo |

## Dependencias / avisos

- Necesito de: contratos de API y muestras públicas presentes en disco.
- Afecta a: coordinación semántica, que integrará, hará commit y push.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Preflight | `git -C <app> rev-parse HEAD`, `branch --show-current`, `status --short` | HEAD/rama confirmados; múltiples cambios sin commit | La identidad Git no describe el contenido no confirmado; se registrarán hashes |
| TDD runner | `python -m pytest tests/test_semantic_lab_probe_app.py -q` | 7 passed | Helpers/orquestador; app real se valida aparte |
| App v2 | `python -m tools.semantic_lab.probe_app run ...app-snapshot-v2 ...app-v2` | 53 muestras; proceso 0; snapshot 68/68 estable | Geometry-only; sin LLM live |
| Histórico v2 | dry-run, import y list reales | 200/200/200; 4 aceptados y listados | Presupuestos académicos, no actuals cerrados ni validación de precio |
| Regresión completa | `python -m pytest -q` | 483 passed en 57,17 s | Estado concurrente visible de la rama semántica |
| Estática | Ruff, `compileall`, `git diff --check` y auditoría de rutas personales | correcto | Archivos propios |

## Bloqueos y cierre

- Bloqueos: live no ejecutable por configuración incompleta; no bloquea la prueba offline.
- Pendientes: commit/push por coordinación.
- Reservas liberadas: `tools/semantic_lab/probe_app.py`, `tests/test_semantic_lab_probe_app.py`, `docs/semantic-lab/PRUEBA_APP_OTROS_DATASETS.md` y este registro tras la entrega.
