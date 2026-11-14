# Agente semántica v2 — inferencia

## Identidad y autorización

- Identidad: agente de IA `semantica_v2_inferencia`; no representa a una persona.
- Rol: diagnosticar y corregir cobertura semántica de roles, ocurrencias y montaje.
- Archivo designado explícitamente por coordinación el 2026-11-14 dentro del swarm autorizado por el usuario.
- Última actualización: 2026-11-14.

## Alcance y reservas

- Propiedad: `backend/app/general_furniture/live.py`, `autonomous.py`, `proposal.py`, `visual_evidence.py`, pruebas focales correspondientes y este registro.
- Solo lectura: corpus público, salidas congeladas públicas y evaluación agregada.
- Fuera de alcance: referencias privadas/holdout, `review.py`, contratos y `assembly_semantics.py`.
- Se preservan todos los cambios locales anteriores; no se hará commit.

## Diagnóstico

- El humo público `sx-001` produjo roles libres en español y F1 de roles/ocurrencias 0: el prompt solo recomendaba vocabulario canónico y el contrato acepta cualquier cadena.
- El crítico solo puede dirigir checks a largo, ancho, espesor, cantidad, material y acabado. Una pieza omitida, un rol erróneo o un arco de montaje ausente no activa reparación.
- La instrucción de montaje trataba `supported_by` y `fixed_to` como alternativas incompatibles, aunque describen soporte funcional y fijación y pueden coexistir.
- Con varias vistas y presupuesto de cuatro artefactos, solo un recorte recibe marcas; los overviews contienen todos los contornos pero no sus IDs visuales.

## Plan RED→GREEN

1. Fijar con pruebas el contrato de prompt: roles canónicos exactos sin colapsar componentes dimensionalmente distintos, conteo de instancias y semántica correcta de apoyo/fijación.
2. Fijar con pruebas una auditoría crítica de completitud mediante directivas estructuradas y validadas en `unresolved` (`missing_component:<role>`, `role_correction:<id>:<role>`, `assembly_missing:<subject_id>:<relation>:<object_id>`) que abran una única reparación sin confirmar hechos.
3. Fijar con pruebas que cada overview CAD publique marcas de todos sus contornos, aun cuando los recortes opcionales se trunquen.
4. Ejecutar suites focales, suite completa, lint/compile y diff check; registrar resultados y límites.

## Dependencias y avisos

- La solución contractual limpia futura requiere targets tipados de nivel componente (`existence`, `role`) y relación; se comunicó a coordinación sin tocar `review.py` ni contratos.
- No se derivarán arcos desde roles ni cajas; toda relación sigue necesitando evidencia y premisa.

## Estado

- Implementación congelada para benchmark de desarrollo; focal verde.

## Cambios realizados

- `live.py`: vocabulario canónico cuando aplica, extensión custom `snake_case`, abstención `unknown`, no colapso de componentes distintos y separación entre apoyo funcional y joinery.
- `autonomous.py`: auditoría de inventario/rol/grafo mediante directivas cerradas; alta futura y arista en la misma reparación; texto libre sin autoridad; validación del delta de IDs, roles, aristas, campos y bindings; política `general-auto-review-v3`.
- `visual_evidence.py`: cada overview CAD marca todos sus contornos aunque los crops opcionales se trunquen.
- No se tocaron `review.py`, contratos, `assembly_semantics.py` ni referencias privadas/holdout. `proposal.py` ya tenía cambios locales ajenos y se preservó sin edición propia.

## Verificación

- RED: helper/directivas y validador ausentes; test adversarial de cambio no anunciado no elevaba error; overview sin marcas; prompts sin contrato suficiente.
- GREEN focal: `.venv\\Scripts\\python.exe -m pytest backend/tests/test_general_furniture_live.py backend/tests/test_general_furniture_autonomous.py backend/tests/test_general_furniture_visual_evidence.py backend/tests/test_general_furniture_proposal.py -q` → `55 passed, 1 warning`.
- Compilación focal: `compileall -q` → correcto.
- Integridad: `git diff --check -- <rutas propias>` → correcto; solo avisos de normalización LF/CRLF.
- Ruff del sistema: cuatro `F841` preexistentes en `test_general_furniture_autonomous.py` (líneas actuales 486, 628, 713, 802), ya informados por auditoría; no se amplió alcance para limpieza cosmética.
- Integración post-política v3: los tres mocks antiguos se hicieron coherentes con el delta autorizado, preservando IDs y procedencia; focal de tres regresiones → `3 passed`.
- Archivo integral completo: `.venv\\Scripts\\python.exe -m pytest backend/tests/test_integral_api_integration.py -q` → `14 passed, 1 warning`.

## Límites

- La corrección mejora la capacidad y cierra cambios silenciosos; no acredita por sí sola mejora de F1 hasta repetir inferencia congelada.
- Roles y montaje siguen siendo hipótesis; ninguna directiva los confirma.
