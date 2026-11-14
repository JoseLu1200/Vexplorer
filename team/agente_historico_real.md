# Agente de histórico económico real

## Identidad y autorización

- Identidad: agente de IA de histórico y estimación; no representa a una persona.
- Autorización: delegación explícita del swarm GPT-6.1 Sol renovada por el usuario el 2026-11-14.
- Rol: completar T12 con ingesta de registros empresariales, comparables y coste/horas trazables.

## Alcance y reservas

- Propiedad: nuevos módulos bajo `backend/app/historico/`, nuevo router autónomo bajo `backend/app/api/`, pruebas focales de histórico y documentación del formato de importación.
- No editar: `backend/app/main.py`, `backend/app/contratos/modelos.py`, frontend, geometría, despliegue ni registros de otros agentes.
- El router se entregará listo para que integración lo monte; la autenticación y auditoría globales de la aplicación se heredan del montaje.

## Objetivo verificable

- Importar JSON y CSV validados con procedencia, fecha, moneda y estado `actual|synthetic`.
- Persistir registros sin fabricar datos empresariales y mantener el demo existente inequívocamente sintético.
- Recuperar comparables por atributos/geométricos con diferencias concretas; embeddings, si se integran, se identificarán como un método distinto.
- Inferir coste y horas desde conceptos compatibles mediante fórmulas explícitas, incertidumbre y datos ausentes.
- Cubrir entradas adversas, persistencia, exclusión de revisiones/proyectos y oráculos matemáticos independientes.

## Dependencias y avisos

- Integración posee `main.py` y montará `create_history_router(store)` con `VEXPLORER_HISTORY_DB`.
- Backend general construirá el target exclusivamente desde componentes revisados `confirmed|derived`, conservando `None`.
- No hay histórico empresarial incluido en el repositorio: la capacidad de importarlo no acredita precisión económica hasta recibir registros reales compatibles.

## Estado

- Servicio SQLite, modelos estrictos, importación JSON/CSV, recuperación por atributos/semántica y estimación por escenarios implementados.
- Semántica opcional reutiliza el proveedor de embeddings real y cachea por hash/modelo/dimensión sin mezclar su score con el geométrico.
- Router con actor autenticado autoritativo, aliases coordinados y documentación de operación entregados.
- Revisión Astra aplicada: compatibilidad y overrides por concepto, drivers fijo/unidad/longitud/área/volumen, completitud coste/horas independiente, revisiones de proyecto deduplicadas, escenarios no sumados, caché validada y conexiones SQLite cerradas.
- Segunda revisión Astra aplicada: la analogía global/CSV exige material y acabado compatibles, y los comparables explícitos respetan exclusión de proyecto propio e IDs antes de estimar.
- Tercera revisión Astra aplicada: alcance de coste y horas separado, obligatorio en registros/target, coincidencia exacta y abstención sin selección humana; el alcance efectivo se publica en la estimación.
- Endurecimiento de alcance: abstención recursiva sin cifras derivadas, filtro automático anterior al ranking y combinación independiente de registros cost-only/hours-only. `published` separa fuentes públicas de registros empresariales `actual` y fixtures `synthetic`.
- Procedencia final identifica contribución/scopes por métrica; coste y horas publican incertidumbre separada. Astra revalidó 30 pruebas y cerró el backend económico sin bloqueos.
- `quantity` queda definido como muebles terminados del lote; consumos totales pueden escalar sin inventar esa cantidad, mientras conceptos por unidad se abstienen.
- Interfaces comunicadas a coordinación, integración, backend general, frontend y operaciones.
- Fixture contractual solicitado por frontend generado desde los modelos reales en `frontend/tests/fixtures/history-contract.json`, tras autorización explícita de su propietario.

## Verificación

- RED inicial: colección falló por ausencia de `backend.app.api.history`.
- GREEN inicial: `9 passed`; ciclos posteriores reprodujeron ausencia de `cost_basis`, cache, escenarios alternativos, rechazo no finito, actor y aliases.
- Focal actual tras revisión: `24 passed` (un aviso externo de deprecación TestClient/httpx).
- Integración focal histórico + router/auth: `31 passed` antes del último ajuste aditivo de consumo total.
- Suite completa fresca final tras segunda revisión: `522 passed`, un aviso externo TestClient/httpx, 67,63 s.
- `compileall` y `git diff --check` pasan sin salida; `ruff` no está instalado en el entorno.
- Fixture revalidado con `HistoricalRecordPage`, `ComparableResponse` y `HistoricalEstimate`; suite frontend `128 passed`.
- Último full-suite intentado quedó bloqueado en colección por `GeneralAutoReviewCheck` ausente en trabajo concurrente de mobiliario autónomo, fuera del alcance económico; focal propio permanece verde.
- QA semántica real ejecutada con el proveedor configurado en `.env`, sin registrar secretos: modelo `text-embedding-3-small`, 256 dimensiones, cuatro registros `published/budget` recuperados y cuatro vectores persistidos en `.runtime/transcript-qa/public-history/history.sqlite3`.
- Evidencia reproducible guardada en `.runtime/transcript-qa/public-history/semantic_real_report.json`: scores coseno, procedencia/fecha, hashes de payload y vector, scopes efectivos y estimación construida exclusivamente desde los IDs semánticos compatibles. El informe declara expresamente que la fuente son presupuestos académicos publicados, no costes empresariales ejecutados.
- Evaluación económica leave-one-project-out ejecutada sin tuning: cuatro folds aislados, tres proyectos y tres embeddings reales por fold, exclusión del proyecto/registro objetivo y targets sin coste, horas ni conceptos retenidos. Las predicciones fueron congeladas con SHA antes de comparar outcomes.
- Resultado LOPO: coste con cobertura 4/4, MAE 48,82 PLN, MAPE 32,250755 % y cobertura de rango 2/4; horas con cobertura 4/4, MAE 0,46775 h, MAPE 16,292619 % y cobertura de rango 3/4; cero no finitos. Esto solo describe cuatro presupuestos de un caso académico, no precisión ERP.
- Vía separada `/history/scenarios` implementada para snapshots generales auto-revisados: carga server-side de revisión exacta, validación cerrada de hipótesis/checks/procedencia y una tarjeta condicional por referencia sin promediar monedas/scopes. Nunca promueve el target confirmado ni escribe historial.
- Verificación final escenarios: 41 pruebas históricas, 55 history+integración, suite Python completa 578 y frontend completo 144, todas verdes. Astra revalidó el handoff sin bloqueos económicos residuales.
