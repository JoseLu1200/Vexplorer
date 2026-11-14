# Agente de modelos semánticos — laboratorio aislado

## Identidad y autorización

- Identidad: agente de IA de modelos semánticos; no representa a una persona.
- Autorización explícita del usuario, 2026-11-14: swarm GPT-6.1 Sol para experimentar con embeddings, en especial EmbeddingGemma 2, y revisión final GPT-6 Astra.
- Archivo propio y alcance designados explícitamente por coordinación en esta sesión.

## Tarea de la sesión

- Implementar y ejecutar el runner reproducible de embeddings aprendidos del laboratorio semántico.
- Referencias: `docs/superpowers/specs/2026-11-14-semantic-lab.md` y plan correspondiente.
- Estado: ampliación autorizada terminada para sondas cruzadas con datasets públicos ya descargados.

## Alcance y reservas

- Propiedad exclusiva inicial: `tools/semantic_lab/encode.py`, `tests/test_semantic_lab_encode.py` y este registro.
- Ampliación autorizada, 2026-11-14: `tools/semantic_lab/probe_datasets.py`, `tests/test_semantic_lab_probe_datasets.py` y `docs/semantic-lab/PRUEBA_EMBEDDINGS_OTROS_DATASETS.md`.
- Solo lectura: manifiesto/corpus externo, resto del repositorio y cachés de modelos.
- Datos, pesos, NPZ y metadatos de ejecución quedan fuera de Git bajo `D:/Vexplorer-semantic-lab/`.
- No modificar contratos ni runtime de producto; no hacer commits.
- Solapes comprobados: ninguno. Evaluación y dataset tienen archivos distintos.

## Decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-11-14 | Los adaptadores reciben bytes de imagen y/o el texto neutral del sample, nunca label, source_path, group_id ni nombre de archivo | Evitar leakage |
| 2026-11-14 | Toda matriz se valida finita, bidimensional, no vacía y con cardinalidad exacta antes de persistir | Impedir artefactos plausibles pero corruptos |
| 2026-11-14 | Caché reutilizable solo con identidad completa: hashes de corpus, contenido, modelo/revisión, modo, precisión, dimensión y configuración | Reproducibilidad y no mezclar espacios |
| 2026-11-14 | Truncado permitido únicamente para EmbeddingGemma 2 en 128/256/512/768; DINOv3 y MiniLM no se presentan como MRL | Evitar atribuir a otros modelos una propiedad no declarada |
| 2026-11-14 | Todas las filas se renormalizan en float32 justo antes de persistir | El forward bf16 de EG2 dejó normas observadas 0.996–1.004; el postproceso queda versionado en la identidad de caché |
| 2026-11-14 | La ampliación se prerregistró antes de abrir métricas: EG2 mixed768, kNN5 coseno con pesos por distancia, sin PCA ni ajuste de rechazo | Separar ejecución confirmatoria de diagnósticos posteriores |
| 2026-11-14 | PlankAssembly usa Hit@1/Hit@2 y relevancia same-object, no Recall@1 ni familia semántica | Cada consulta tiene dos vistas relevantes y no existe ground truth de familia humana |
| 2026-11-14 | Engineering informa asignaciones closed-set forzadas sin accuracy | Ninguna de las cuatro clases de muebles constituye ground truth válido para esos 14 planos |

## Dependencias / avisos

- Coordinación corrigió el entorno aislado tras el preflight `ImportError: ResolvedRevision`; este agente no instaló dependencias en paralelo.
- Corpus congelado consumido: `D:/Vexplorer-semantic-lab/data/core/manifest.json`, SHA-256 `15f2448895806c85c0647da72413bfc8de39f5a6fe71d535121303f1d03f00fe`, 117 muestras.
- Artefactos entregados fuera de Git en `D:/Vexplorer-semantic-lab/embeddings/`: cinco espacios principales y EG2 256d para text/image/mixed.
- Modelos/revisiones: DINOv3-small `114c1379950215c8b35dfcd4e90a5c251dde0d32`; MiniLM `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`; EmbeddingGemma 2 `f9972ac22e696a105c482202646979e33e4b5a1e`.
- Investigación y fuentes primarias consolidadas en `docs/semantic-lab/INVESTIGACION_SOTA.md`; distingue métodos consultados, ejecutados y pendientes.
- Prerregistro cruzado: SHA-256 `8ffdf3e0244ba64d4780d9288b8f3f9a0595e0a0884f437dfe22e7a78047cc2c`; 373 CAD-extra, 30 vistas públicas Plank y 14 DXF de ingeniería.
- CAD-extra conservó 373/379 candidatos; el manifiesto registra tres exclusiones `nonzero_z_geometry` y tres fallos `DXFAttributeError` de `3DFACE`/`SOLID` sin abortar el lote.
- Artefactos cruzados permanecen fuera de Git en `D:/Vexplorer-semantic-lab/cross-dataset/`; el resumen compacto sin rutas personales está en `docs/experiments/cross-dataset-2026-11-14/embeddings-summary.json`.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| Preflight entorno aprendido | `D:/Vexplorer-semantic-lab/venv/Scripts/python.exe -c "import transformers"` | falla por dependencia incompatible | coordinación corrige el entorno |
| TDD frontera/validación/caché | `python -m pytest tests/test_semantic_lab_encode.py -q` | 11 passed | encoders reales se verifican aparte |
| Regresión completa | `python -m pytest -q` | 462 passed, 1 warning externo de Starlette/anyio | sin métricas de test abiertas por este agente |
| Estática propia | `compileall`; `git diff --check`; `ruff check tools/semantic_lab/encode.py tests/test_semantic_lab_encode.py` | pasa sin errores | archivos propios |
| Smoke sintético aislado | EG2 image/text/mixed, DINOv3 image y MiniLM text sobre fixture marcado `synthetic:true` | carga GPU, inferencia y metadatos pasan | no acredita calidad |
| Corpus real, 5 espacios | CLI sobre 117 muestras | DINO image384 0.492 s; MiniLM text384 0.299 s; EG2 text768 0.570 s; image768 14.053 s; mixed768 17.815 s | tiempos de encoding, excluyen carga |
| EG2 MRL 256 | CLI sobre 117 muestras | text 0.628 s; image 15.637 s; mixed 17.749 s | comparación opcional |
| Integridad artefactos | script independiente NPZ+JSON | 117 IDs únicos, matrices finitas, dimensiones exactas, hash de manifiesto común y normas 0.999999881–1.000000119 | no inspecciona etiquetas ni métricas |
| TDD sondas cruzadas | `python -m pytest tests/test_semantic_lab_probe_datasets.py -q` | 10 passed | fixtures reales DXF, sin red ni modelos |
| CAD-extra congelado | EG2 mixed768 + kNN5 fijo | validation F1 0.7261/BA 0.7644/P@5 0.7643/Hit@5 0.9643; test F1 0.7780/BA 0.7719/P@5 0.7745/Hit@5 0.9273 | misma fuente CADBlock y labels proxy |
| Plank cross-view | 10 objetos públicos, 3 capas por objeto | Hit@1 0.300; Hit@2 0.300 | identidad de objeto, no semántica; top 0/10 |
| Engineering closed-set | 14 DXF públicos contra train core | buffets 11, sofas 2, simple-tables 1, beds 0 | sin accuracy ni umbral de rechazo |
| Integridad cruzada | tres NPZ + metadatos | 417 ids únicos, float32, finitos, 768d, normas 0.999999881–1.000000119, revisión exacta | cero OOM; tiempos excluyen carga |
| Estática propia ampliada | `compileall`; `ruff check`; `git diff --check`; `json.tool` | pasa | root ejecuta regresión completa final |

## Bloqueos y cierre

- Bloqueos: ninguno del alcance propio.
- Pendientes: ninguno del alcance propio; integración Git pertenece a coordinación.
- Reservas liberadas: `tools/semantic_lab/encode.py`, `tests/test_semantic_lab_encode.py` y este registro tras entrega.
- Entrega: NPZ contienen solo `ids` y `embeddings`; los JSON adjuntos registran modelo/revisión, precisión, modo, dimensión, hashes ordenados de entradas, identidad de configuración, timing, errores y hash del NPZ.
