# Agente UX funcional — corrección de interfaz

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA UX funcional; no representa a una persona.
- Rol: diagnóstico y corrección funcional del frontend dentro del swarm solicitado.
- Archivo creado y designado explícitamente: `team/agente_ux_funcional.md`, delegación de `/root` del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: corregir navegación de paneles, estado accesible, densidad funcional, acciones/estados vacíos y errores engañosos sin alterar contratos de negocio.
- Referencia del plan: QA integral de la interfaz y estados UI-01–UI-03.
- Estado: implementado y verificado en pruebas; QA de navegador integrado a cargo de `/root`.

## Alcance y reservas

- Archivos o carpetas que puedo editar: `frontend/app.js`, helpers nuevos estrictamente necesarios en `frontend/core/`, pruebas funcionales frontend asociadas y este registro.
- Dependencias que solo leeré: `frontend/index.html`, `frontend/styles.css`, `frontend/components/SceneViewer.js`, backend, contratos y documentación.
- Archivos compartidos que requieren coordinación: hooks de `index.html` y estilos con `/root/layout_scroll`.
- Solapes detectados y acuerdo para resolverlos: la reserva histórica de `frontend/` fue liberada al coordinador; la delegación actual asigna `app.js` a este agente y `index.html`/`styles.css` a `layout_scroll`. Se preservarán los cambios locales de tema/rail existentes en `app.js`.

## Hecho en el último bloque

- Leídas reglas, transcripción, README, especificación UX y registros de coordinación/interfaz.
- Coordinado el límite de ownership con `layout_scroll`; no se modificará marcado ni CSS desde este alcance.
- Confirmado el diff local ajeno de tema/rail que debe preservarse.
- Reproducida la densidad de mesa: medidas, warnings, supuestos, pares de radios y correcciones se renderizaban todos expandidos.
- Identificada la causa del guardado 422: `saveCurrentToLibrary` enviaba `descriptor_version`, campo que `LibrarySaveRequest` prohíbe aunque sí pertenezca a búsqueda/agrupación.
- Corregida navegación de herramientas con `aria-current`, `aria-controls`, estado de panel y desplazamiento al panel activo en viewport compacto.
- Compactada revisión de mesa: una selección por objetivo, resumen visible y diagnóstico/corrección avanzada bajo divulgación progresiva; evidencia completa sigue accesible.
- Traducidos warnings/códigos conocidos sin reinterpretar códigos desconocidos.
- Evitadas consultas GET automáticas de planos/costes mientras la revisión está pendiente; se conserva la generación provisional explícita al abrir una pestaña disponible.
- Corregida etiqueta 3D: una escena `needs_review` ya no se presenta como revisada.
- Eliminado estado arrastrado al cambiar de una escena 3D a un PDF pendiente: se vacía escena, aviso y control de explosión; la vista previa PDF y el tipo de entrada cambian de inmediato.
- Bloqueadas acciones de biblioteca que requieren descriptor mientras una mesa sigue pendiente; guardado y búsqueda se habilitan al completar la revisión.
- Añadidos nombres estables a controles dinámicos, semántica/teclado de pestañas, `inert` al cajón cerrado y foco del panel elegido en móvil.
- Ajustada la copia de mueble general: solo una ejecución live con revisor de máquina se presenta como revisión visual automática.
- Compactadas las diferencias de similitud de biblioteca: dimensiones conocidas y cambio de componentes quedan resumidos; el `repr` técnico completo permanece disponible bajo `Datos de comparación` sin parsearlo ni insertarlo como HTML.

## Siguiente bloque

- Entregar causas, cambios, verificación y límites a `/root`; atender cualquier regresión de QA integrado.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia del acuerdo, si se necesita |
|---|---|---|---|
| 2026-11-14 | Limitar cambios funcionales a JS y tests | Evitar conflicto con el trabajo concurrente de layout/scroll | Delegación de `/root` y coordinación directa |
| 2026-11-14 | Usar payload allowlist al guardar biblioteca | El contrato de guardado rechaza extras; descriptor se deriva del resultado en backend | 422 reproducido por QA y `LibrarySaveRequest` |
| 2026-11-14 | Mantener desconocidos y evidencia tras compactar | Reducir densidad no puede convertir hipótesis o ausencia en confirmación | UX_SPEC y contratos vigentes |

## Dependencias / avisos

- Necesito de: hallazgos de QA Chrome y estabilidad de IDs/hooks del marcado.
- Afecta a: navegación lateral, estados de acciones, biblioteca, costes y revisión.
- Aviso realizado: mensaje a `/root/layout_scroll` antes de editar código.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando ejecutado | Resultado observado | Limitación |
|---|---|---|---|
| Baseline frontend | `npm test` | 147 passed | Antes de cambios funcionales |
| Reproducciones RED | `node --test tests/ui-behavior.test.js` | 4 fallos iniciales; luego 1 fallo de payload y 1 de etiqueta 3D, todos por comportamiento ausente | Prueba pura/contrato estático, sin navegador |
| Suite frontend final | `npm test` | 162 passed, 0 failed | QA visual/interactiva coordinada aparte |
| Sintaxis | `node --check frontend/app.js` | exit 0 | No sustituye navegador |
| Integridad del diff propio | `git diff --check -- frontend/app.js frontend/core/ui.js frontend/tests/ui-behavior.test.js team/agente_ux_funcional.md` | exit 0 | El worktree contiene cambios concurrentes ajenos preservados |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendientes: confirmación de navegador integrado por `/root` sobre el servidor compartido.
- Reservas liberadas: `frontend/app.js`, `frontend/core/ui.js` y pruebas propias tras entrega a `/root`.
- Entrega a otra persona: `/root`, con causas, cambios, pruebas y límites.
