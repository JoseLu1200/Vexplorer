# Agente similitud motor — comparación técnica

## Identidad y autorización

- Nombre declarado por el usuario: agente IA `similarity_backend`, delegado por `/root` dentro del swarm solicitado.
- Rol: backend de comparación técnica y agrupación.
- Archivo creado o designado explícitamente: delegación de `/root`, 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: separar parecido semántico de similitud técnica, explicar diferencias por pieza y evitar grupos homogéneos engañosos.
- Referencia del plan: T12, recuperación histórica y comparables explicables.
- Estado: terminado en alcance propio; integración API y revisión final corresponden a `/root`.

## Alcance y reservas

- Archivos que puedo editar: `backend/app/similarity/service.py`, pruebas backend nuevas y este registro.
- Dependencias que solo leeré: contratos Pydantic, descriptor semántico, API y pruebas existentes.
- Archivos compartidos que requieren coordinación: `backend/app/contratos/modelos.py` y `backend/app/main.py`; no se editarán aquí.
- Solapes detectados y acuerdo para resolverlos: la propiedad histórica de similitud era backend B; la delegación actual de `/root` reserva expresamente `service.py` y pruebas nuevas para este agente. Se preservan cambios locales concurrentes.

## Hecho en el último bloque

- Añadido `TechnicalComparison` puro con score, componentes, diferencias y avisos de cobertura.
- El coseno conserva `score_kind=cosine_similarity`; `technical_score` queda separado y el score geométrico histórico mantiene su fórmula retrocompatible.
- V2 compara `part_features` por largo/ancho/espesor/cantidad y detecta, entre otros, paneles 864→828; material/acabado globales se comparan sin fabricar campos por pieza.
- V3 agrega cantidades de roles repetidos y empareja todos los componentes de un mismo rol sin sobrescribirlos; material por componente queda explícito y acabado/proceso ausentes generan aviso.
- Agrupación sustituida por complete-link determinista con caché de pares; no convierte cadenas transitivas en grupos supuestamente homogéneos y omite espacios incompatibles.
- Añadidos clave canónica conservadora, deduplicación determinista y reranking semántico técnico con exclusión individual de embeddings incompatibles.
- Revisión Astra: sustituido el emparejado voraz por asignación húngara exacta O(n³), con padding seguro para números de piezas distintos y desempate determinista sobre features canonicalizadas.

## Siguiente bloque

- `/root/library_api` integra los helpers en API y `/root/similarity_evaluation` revalida la evaluación independiente.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | No modificar contratos ni API | Propiedad explícita limitada por `/root` | Delegación de la sesión |
| 2026-11-14 | Tratar desconocido como falta de evidencia, no como coincidencia | Evitar scores técnicos inflados | Reglas de arquitectura y caso de uso |

## Dependencias / avisos

- Necesito de: `/root` y agente API para exponer campos aditivos del comparador técnico.
- Afecta a: respuestas de similitud y agrupación de biblioteca.
- Aviso realizado: campos aditivos de match/grupo acordados con `/root` y API; firmas y shape comunicados a API, evaluación y UI.
- Cambio de `contratos/`: no aplica; expresamente fuera de alcance.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| RED inicial | `python -m pytest backend/tests/test_similarity_technical.py -q` | ImportError esperado por helpers ausentes; después 3 fallos conductuales esperados | ciclo registrado en la sesión |
| Focal similitud/API | `python -m pytest backend/tests/test_similarity_technical.py backend/tests/test_backend_semantic.py backend/tests/test_backend_embeddings.py backend/tests/test_backend_library_api.py -q` | 33 passed in 11.08s | integración global a cargo de `/root` |
| Estilo | `python -m ruff check backend/app/similarity/service.py backend/tests/test_similarity_technical.py` | All checks passed | archivos formateados con Ruff |
| Suite backend parcial | `python -m pytest backend/tests -q` | interrumpida por indicación de `/root` al 57%, sin fallos observados hasta ese punto | no acredita suite completa |
| Diff | `git diff --check -- ...` | sin errores; solo aviso LF→CRLF del worktree | no se hizo commit |
| Asignación óptima Astra | `python -m pytest backend/tests/test_similarity_technical.py -q -k piece_assignment` | 1 passed, 9 deselected; óptimo 0.597222 y permutación invariante | fixture independiente de tres piezas |
| Focal final del motor | `python -m pytest backend/tests/test_similarity_technical.py -q` | 10 passed in 0.40s | no se lanzó suite completa por indicación de `/root` |

## Bloqueos y cierre

- Bloqueos: ninguno en alcance propio.
- Pendientes: integración API, evaluación independiente y suite global por `/root`.
- Reservas liberadas: `service.py`, prueba propia y este registro tras esta entrega.
- Entrega a otra persona: helpers públicos, propuesta de contrato y evidencia de pruebas para `/root`.
