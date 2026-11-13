# Agente backend — demo local

Identidad: agente B de IA; no representa a una persona. Autorización: solicitud explícita del usuario del 2026-11-13.

## Alcance y propiedad

- Único escritor de `backend/app/contratos/`.
- Backend salvo ingesta y geometría: `backend/app/api/`, `agente/`, `herramientas/`, `validador/`, `salida/`, `servicios/`, `backend/app/main.py` y `backend/app/__init__.py`.
- Configuración y pruebas propias: `pyproject.toml`, `.env.example`, `backend/tests/test_backend*.py`.
- Alcance adicional autorizado por coordinación: `backend/app/historico/` y `backend/app/estimacion/`.
- No editar `backend/app/ingesta/`, `backend/app/geometria/`, `frontend/`, `evaluation/`, `data/planos_demo/` ni archivos reservados a otros agentes.

## Tarea

Implementar el backend local completo de la primera demo: contrato Pydantic 0.2 acordado con A y comunicado a C/D; API FastAPI y persistencia local; revisión versionada; herramientas y bucle live configurable; modo `geometry_only`; comparables sintéticos; estimación explicada; exportación; pruebas de comportamiento sin red.

## Dependencias / avisos

- Bloqueo inicial: acordar con `/root/geometria` la interfaz `extract_drawing` y los modelos 0.2 antes de implementar contratos; avisar a `/root/frontend` antes de escribirlos.
- El fixture y los oráculos pertenecen a `/root/evaluacion`; el backend no leerá la referencia reservada ni codificará sus valores en extractor o prompt.
- El frontend pertenece a C y será servido por FastAPI sin modificar sus archivos.

## Estado

Vertical slice backend completo y verificado; pendiente únicamente integrar los commits en la rama coordinadora y repetir el recorrido navegador del equipo.

## Registro de trabajo

- 2026-11-13: identidad, alcance, dependencias y bloqueo contractual registrados antes de editar código.
- 2026-11-13: acuerdo explícito A/B 0.2: `extract_drawing(path: Path) -> DrawingExtraction`; geometría entrega solo observaciones/evidencia, sin propuestas; B mantiene escenarios hipotéticos y revisiones separadas. C y D avisados antes de implementar.
- 2026-11-13: consultada documentación oficial de OpenAI Responses/function calling; el adaptador live usará herramientas estrictas y correlación por `call_id`, sin herramientas integradas ni acceso libre a archivos.
- 2026-11-13: commit contractual `3346537`; `python -m pytest backend/tests/test_backend_contract.py -q` → 4 passed. Compartido con A/C/D.
- 2026-11-13: commits integrados de A/D para verificar extractor y fixture reales: `427b9c0`, `1130b4e`, `8c40471`, `f346c77`; no son autoría de B.
- 2026-11-13: commit servidor `df184a9`: upload DXF, escenarios incompatibles, revisión versionada, histórico sintético, estimación por conceptos, export, SSE, frontend estático y live configurable.
- 2026-11-13: commit hardening `a7ce394`: anti-traversal, dimensiones ortográficas consistentes, export bundle auditable, eventos de revisión/estimación, revisión atómica, tarifa compatible y herramientas live con evidencia vectorial estructurada.
- 2026-11-13: `python -m pytest -q` → 45 passed. Smoke live real con `gpt-6.1-sol` y fixture público → HTTP 201, resultado `needs_review`, dos escenarios; sin fallback ni exposición de secretos.

## Límites reales

- Modalidad live: evidencia vectorial estructurada, no visión ni imagen; la persona confirma escenario, espesor, material y acabado.
- Catálogo, costes y tarifas son sintéticos y se etiquetan como tales; horas permanecen desconocidas.
- `recorded_replay` se rechaza hasta disponer de una grabación real autorizada.
- Persistencia SQLite local de un host; sin promesa de alta disponibilidad ni autenticación multiusuario en esta demo.
