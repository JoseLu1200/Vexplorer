# Agente demo local

- Identidad: agente IA de esta sesión, sin atribución a una persona.
- Autorización: usuario, 2026-11-14: «crea todo lo que necesites de teams sin problema», en respuesta al requisito para corregir los fallos de la demo.
- Objetivo: preparar localhost con biblioteca/histórico y corregir fallos reproducidos.
- Alcance: backend/app/general_furniture/live.py, backend/app/main.py, frontend/core/table.js y sus pruebas; documentación operativa.
- Coordinación: reservas anteriores de UX funcional y cierre montaje liberadas; cierre PDF consta cerrado. Se preserva todo el trabajo local existente. Sin cambios en contratos/.
- Estado: diagnóstico confirmado; implementación mediante regresiones RED/GREEN y aceptación real.
- Causas: refs de montaje sin prefijo y document refs no autorizadas en respuestas reales; GET run consulta almacén legado de costes; replay de mesa envía proposal_mode=none aunque API exige model_generated.
- Datos preparados: 19 registros published, biblioteca con embeddings reales, mesa baseline y mesa live revisadas como demo automatizada.
- Pendientes: pruebas, reinicio controlado, ensayo general live, guía final.
- Ampliación explícita del usuario: pulsar una fila de componentes debe mostrar visualmente la pieza. Alcance adicional: frontend/app.js, frontend/core/table.js y pruebas; selección 2D por lámina exacta y resaltado 3D existente, inspector visible y teclado.

- Cierre 2026-11-14: demo production local activa; guía docs/demo-local-2026-11-14.md. Extensión autorizada al caso complejo: review.py, escena general/selección frontend, validación de biblioteca. 175 pruebas frontend y 42 backend focalizadas pasan. Caso plank-030: 16/16 dimensiones/cantidades, revisión automática incompleta por incógnitas reales. Montaje y valoración económica no certificados.

- Nueva solicitud explícita: implementar y probar montaje general razonado desde planos. Diagnóstico y diseño revisado en docs/superpowers/specs/2026-11-14-general-assembly-design.md. Se requiere ampliación aditiva del contrato central por instancia; pendiente aprobación del diseño y autorización contractual conforme a CLAUDE.md. No se ha modificado código para esta nueva fase. Se preserva la reserva semántica vigente.
