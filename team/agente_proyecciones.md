# Agente de hipótesis de proyección — apoyo geométrico

## Identidad y autorización

- Identidad: agente de IA de hipótesis de proyección; no representa ni deduce una persona.
- Rol: apoyo geométrico determinista para el swarm GPT-6.1 Sol.
- Archivo creado por la delegación explícita del coordinador el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: exponer regiones espaciales de fuente y candidatos ambiguos de correspondencia entre proyecciones a partir de geometría y medidas del ledger.
- Objetivo adicional delegado: serializar un contexto geométrico compacto compartido por proposer/crítico, sin pérdida numérica ni referencias silenciosamente descartadas.
- Estado: helper de proyecciones entregado; compactador de contexto en curso.
- No objetivo: confirmar identidad física, cantidad, rol de componente ni etiqueta FRONT/TOP/SIDE.

## Alcance y reservas

- Propiedad exclusiva: `backend/app/general_furniture/projection_hypotheses.py`, `backend/app/general_furniture/context_payload.py`, sus pruebas `test_general_furniture_projection_hypotheses.py`/`test_general_furniture_context_payload.py` y este registro.
- Solo lectura: contratos, `measurements.py`, ingesta, `visual_evidence.py`, proposer/verifier y los DXF públicos `plank-001.dxf`/`plank-006.dxf`.
- Prohibido: referencias privadas de evaluación, JSON/STEP/oráculos de PlankAssembly, contratos compartidos y módulos de otros agentes.
- Solapes: coordinación, backend general e ingesta confirmaron la frontera. Ingesta conserva recortes visuales; backend general integrará la salida en proposer/verifier.

## Plan de implementación

1. Caracterizar solo los dos DXF públicos mediante el parser de producto y fijar casos sintéticos independientes.
2. RED: regiones estables/trazables, correspondencias ambiguas por medidas y posición relativa, ausencia de candidatos sin medida comparable y límites de salida.
3. GREEN: dataclasses inmutables y funciones puras; sin lectura de archivo/píxeles ni IDs derivados del nombre de fichero.
4. Verificar focal, regresiones generales, lint/compilación y diff.
5. RED/GREEN del payload compacto: spans iniciales, consulta paginada de segmentos, cierre de referencias, unidades desconocidas, ambigüedad/truncación y reducción serializada medible.

## Decisiones y avisos

- Las tres proyecciones pueden compartir `view-unknown`; una región espacial no se presenta como vista semántica.
- Los scores son heurísticos y no probabilidades; se conservan empates mediante `ambiguity_group_id`.
- Toda referencia de medida debe ser exactamente un ID recibido de `GeometryMeasurement` y quedar cerrada contra `DrawingExtraction`.
- Firma acordada con backend general: `derive_projection_hypotheses(extraction, measurements) -> tuple[ProjectionHypothesis, ...]`; se expone además `derive_source_spatial_regions`.
- Cambio de `contratos/`: no aplica.

## Pruebas y cierre

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| TDD RED inicial | `.venv/Scripts/python.exe -m pytest backend/tests/test_general_furniture_projection_hypotheses.py -q` | 3 fallos esperados tras el scaffold: regiones/candidatos vacíos y referencia inválida no rechazada | antes de implementación |
| Mutación de presupuestos | prueba focal con límites temporalmente elevados | fallo esperado: 30 regiones frente al máximo 24 | constantes restauradas antes de GREEN |
| Focal final | `.venv/Scripts/python.exe -m pytest backend/tests/test_general_furniture_projection_hypotheses.py -q` | 7 passed | incluye rechazo temprano de 513 contornos; fixtures sintéticos, sin red |
| DXF públicos permitidos | parser + helper sobre `plank-001.dxf` y `plank-006.dxf` | 3 regiones ordenadas izquierda/centro/derecha y 59/69 hipótesis; ninguna salida truncada | diagnóstico, no oráculo de corrección física |
| Regresión mueble general | `.venv/Scripts/python.exe -m pytest backend/tests -k general_furniture -q` | primera pasada 47 passed/2 failed; pasada final no colecciona por 13 imports mientras `autonomous.py` está ausente en edición concurrente | estado ajeno comunicado a backend general y coordinación |
| Lint | `ruff check` sobre módulo y prueba propios | All checks passed | Ruff global; no instalado dentro del venv |
| Compilación/diff | `compileall -q` y `git diff --check --` sobre archivos propios | exit 0 | el worktree compartido contiene cambios ajenos |
| Contexto compacto RED/GREEN | `.venv/Scripts/python.exe -m pytest backend/tests/test_general_furniture_context_payload.py -q` | RED: 4 fallos de comportamiento/1 pase vacío; GREEN: 5 passed | valores exactos, unidades desconocidas, consulta, ambigüedad y tamaño |
| Mutación de score | redondeo temporal del score a entero + prueba de ambigüedad | fallo esperado: `0.596667` se convertía en `1.0`; restaurado | acredita ausencia de pérdida numérica |
| Reducción pública permitida | JSON compacto frente a `asdict` de medidas/regiones/hipótesis | 001: 168199→49369 (-70,65%); 006: 204841→59582 (-70,91%) | no incluye ni consulta referencias privadas |

- Bloqueos: ninguno propio. La suite compartida queda temporalmente bloqueada por la reescritura concurrente de `autonomous.py`, fuera de esta reserva.
- Entrega: firmas, presupuestos y API compacta comunicados a backend general; coordinación recibió resultados de los dos DXF públicos.
- Pendiente: integración del mismo payload en proposer/crítico por su propietario y suite conjunta tras estabilizar el worktree.
