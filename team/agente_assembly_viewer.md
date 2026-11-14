# Agente assembly viewer — visor por instancia

## Identidad y autorización

- Nombre declarado por el usuario: agente de IA `assembly_viewer`; no representa a una persona.
- Rol: frontend del montaje general por ocurrencia.
- Archivo creado o designado explícitamente: encargo de `/root` del 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo concreto: renderizar una caja por instancia con transformación ortogonal real, selección por ocurrencia, estados/errores visibles y reintento durable.
- Referencia del plan: `docs/superpowers/specs/2026-11-14-general-assembly-design.md` y plan coordinado de montaje general.
- Estado: terminado; pendiente QA de navegador coordinada por raíz.

## Alcance y reservas

- Archivos editables: `frontend/core/scene.js`, `frontend/components/SceneViewer.js`, `frontend/app.js`, `frontend/api/client.js`, pruebas frontend asociadas y este registro.
- Dependencias de solo lectura: contrato Pydantic y endpoints mantenidos por `assembly_core` y `assembly_runtime`.
- Solapes detectados: existen cambios concurrentes ya presentes en los archivos frontend; se conservarán y los nuevos hunks serán acotados.

## Hecho en el último bloque

- Implementé normalización estricta de ejes firmados con determinante +1, centro desde AABB mundial y matriz de rotación aplicada al mesh real.
- El centro conserva `size_mm`, la extensión AABB validada por servidor, aunque difiera levemente de la permutación de medidas locales dentro de tolerancia.
- El montaje general usa una caja por ocurrencia, claves únicas, selección individual agrupada con su tipo y fallback legado separado.
- Añadí GET revisionado sin gasto, POST de reintento idempotente mediante job durable y presentación visible de aceptado/incompleto/rechazado y errores.
- Adapté el GET al wrapper `GeneralAssemblyState`, con compatibilidad para intentos legados directos, escena solo del `current` aceptado y listado de todas las alternativas aceptadas; la ambigüedad nunca se oculta.
- Conecté cancelación explícita del job de reintento: botón temporal, POST sin cuerpo y mensaje persistente al solicitar/interrumpir.
- Agrupé diagnósticos de montaje por código con resumen español y recuento; mensajes originales, IDs de instancia y referencias permanecen accesibles en un detalle colapsable.
- Añadí inspección 3D opt-in del candidato rechazado/incompleto con placements persistidos: rótulo no validado, sin overlay por defecto, sin acciones de fabricación y retorno al esquema normal; se reinicia en cada run/revisión/respuesta.
- Añadí selector explícito de eje vertical de inspección X/Y/Z. La opción Z aplica una única rotación global propia `(x,y,z)→(x,z,-y)` a posiciones, AABB y orientaciones, sin mutar el payload evaluado.

## Siguiente bloque

- QA de navegador central: comprobar escena real, explode, selección, recarga y consola contra backend integrado.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | Transformar alrededor del centro calculado desde AABB min + extensión mundial/2 | Cumplir el contrato coordinado sin reinterpretar `position_mm` como centro | Handoff `/root` y confirmación de `assembly_core` |
| 2026-11-14 | Mantener BoxGeometry en largo/ancho/grosor y aplicar la matriz firmada | Permutar solo dimensiones no representa orientación ni signos | Especificación y revisión independiente |
| 2026-11-14 | GET nunca reintenta; el gasto solo nace del botón POST durable | Evitar coste silencioso al abrir o recargar el visor | Contrato `assembly_runtime` |
| 2026-11-14 | Un `current` rechazado/incompleto no muestra su escena, aunque existan alternativas aceptadas conservadas | No convertir historial alternativo en selección silenciosa | Contrato `GeneralAssemblyState` y revisión independiente |

## Dependencias / avisos

- Necesito de: backend integrado y caso real para QA de navegador.
- Afecta a: render 3D y consumo de API de montaje general.
- Aviso realizado: coordinación directa con `assembly_core` el 2026-11-14.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Comando | Resultado | Limitación |
|---|---|---|---|
| RED geometría | `node --test tests/scene.test.js --test-name-pattern="mounted furniture|repeated quantities|invalid or duplicate|legacy scenes"` | 4 fallos esperados | antes de implementar transformación |
| RED mesh real | `node --test tests/scene.test.js --test-name-pattern="viewer applies"` | fallo esperado: helper ausente | prueba matriz y centro |
| RED API | `node --test tests/client.test.js --test-name-pattern="general assembly"` | fallo esperado: métodos ausentes | sin red |
| Suite frontend | `npm test` | 192 passed, 0 failed | no sustituye QA WebGL en navegador |
| Sintaxis | `node --check app.js`; `node --check components/SceneViewer.js` | exit 0 | sintaxis solamente |

## Bloqueos y cierre

- Bloqueos: ninguno en frontend.
- Pendientes: QA WebGL/Chrome con servicio integrado y fixture real.
- Reservas liberadas: rutas frontend al entregar a raíz.
