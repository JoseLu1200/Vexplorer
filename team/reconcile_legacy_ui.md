# Reconciliación del frontend legado

Identidad: agente IA `/root/reconcile_legacy_ui`, delegado por `/root`.

Alcance autorizado: portar por hunks las correcciones funcionales pendientes de R13 bajo `frontend/**`, preservando los cambios posteriores de `main` en arranque, recuperación, cola/cancelación, reconstrucción y visor. `diseno/**`, backend, contratos, datos y configuración quedan fuera del alcance y no se modifican.

Base de integración: `.worktrees/cutlist-design-integration` en `a467280`. Fuente de contraste de solo lectura: `.worktrees/similarity-public`, cambios locales frente a `f32021d`.

Resultado: se portaron por hunks los mensajes y acciones seguras de recuperación, la separación entre disponibilidad y completitud de artefactos, controles de lectura del SVG derivado con cercado de cargas, layout de recuperación sin encogimiento y restauración sin consultas históricas automáticas. Se conservaron la cancelación y cola durable, la reconstrucción 3D y los cambios de visor presentes en `main`.

Verificación observada:

- `node --test tests/general.test.js tests/image-viewport.test.js tests/jobs.test.js tests/ui-behavior.test.js`: 69/69.
- `npm test`: 283/283.
- `npx playwright test --reporter=line`: 6/6.
- `git diff --check -- frontend team/reconcile_legacy_ui.md`: sin errores; solo aviso de conversión futura LF/CRLF en la licencia vendorizada no modificada.
