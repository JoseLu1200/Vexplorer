# Agente coordinador — demo local

Identidad: agente coordinador de IA; no representa a una persona. Autorización: solicitud explícita del usuario del 2026-11-13.

## Alcance y propiedad
- Coordinador: integración, README.md, .gitignore, docs/DEMO_IMPLEMENTACION.md, docs/VERIFICACION_DEMO.md y este archivo.
- A: backend/app/ingesta/, backend/app/geometria/, backend/tests/test_geometry.py, team/agente_geometria.md.
- B: backend/app/contratos/, api/, agente/, herramientas/, validador/, salida/, servicios/, backend/app/main.py y __init__.py; pyproject.toml, .env.example; backend/tests/test_backend*.py; team/agente_backend.md. Único escritor de contratos.
- C: frontend/ y team/agente_frontend.md.
- D: data/planos_demo/, evaluation/, tools/build_demo_fixture.py, tests/test_demo*.py, team/agente_evaluacion.md.
- No hay reservas personales previas; cada agente crea y mantiene su propio registro.

## Plan autorizado
1. Partir de main actualizado; baseline: 13 tests pasan, commit c09a6f9.
2. A/B acuerdan contrato 0.2 de demo y comunican a C antes de código contractual.
3. D crea fixture propio de estantería montada y variante incompleta; referencia reservada separada.
4. A implementa geometría determinista sin leer referencia; B implementa API, revisiones, herramientas, live configurable, comparables y estimación sintética.
5. C integra plano, evidencia, propuestas, revisión, histórico, estimación, exportación y traza.
6. Coordinador integra commits, ejecuta suite y recorrido navegador; GPT-6 Astra revisa diff final; corregir y repetir checks afectados.

## Decisiones
- Familia: estantería rectangular de tableros. UX español, servidor local FastAPI sirve JS/HTML para arranque único.
- geometry_only siempre disponible; live requiere proveedor real configurado. recorded_replay no se habilita sin grabación real.
- PlankAssembly permanece fuera del runtime y sin publicar; adaptación futura acotada se documentará.
- Se siguen la especificación del usuario y PLAN.md; decisiones rutinarias autónomas según autorización expresa.

## Estado
En curso. Contrato y fixture aún pendientes de acuerdo; ninguna capacidad de aplicación verificada todavía.
