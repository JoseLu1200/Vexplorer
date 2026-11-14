# Agente UX QA — auditoría visual independiente

## Identidad y autorización

- Identidad: agente de IA de QA visual; no representa ni deduce una persona.
- Rol: auditor independiente del swarm solicitado por el usuario.
- Archivo creado por delegación explícita del coordinador el 2026-11-14.
- Última actualización: 2026-11-14.

## Tarea de la sesión

- Objetivo: probar visualmente todas las funciones relevantes de Vexplorer en el servidor QA aislado `http://127.0.0.1:8771`, informar bloqueadores reproducibles y revalidar las correcciones.
- Estado: auditoría inicial completada; revalidación de fixes en curso.

## Alcance y reservas

- Propiedad exclusiva: este registro y evidencias bajo `.runtime/ui-review-maisa/`.
- Solo lectura: código de producto, documentación, fixtures y datos del servidor QA.
- No editaré código de producto; las correcciones corresponden a los agentes propietarios.
- Solapes: ninguno; QA usa MCP Chrome DevTools y un contexto propio, sin interferir con la página Playwright del coordinador.

## Hecho en el último bloque

- Mesa completa: carga, geometría, revisión humana, derivados SVG/DXF y 3D observados en navegador real.
- Piezas completas: K2 conserva 864 × 300 × 18 mm y cantidad 2; cantidad desconocida y asociación ambigua conservan desconocidos y abstención.
- PDF vectorial: selección de página y preparación sin escala conservan unidad desconocida y bloquean correctamente geometría métrica.
- Tema oscuro persiste tras recarga; modal Traza atrapa foco, cierra con Escape y restaura el foco al disparador; el último botón de revisión es alcanzable al final del scroll móvil.
- Evidencias: `qa-mesa-1440x900.png`, `qa-mobile-390x844.png` y `qa-ambiguous-mobile.png`.
- Exportaciones verificadas por contenido: DXF 63.549 bytes y SVG 8.583 bytes con revisión/título; JSON 56.817 bytes con snapshot R2, dibujos y cinco eventos; CSV de corte con dos componentes y estados/procedencia; Traza JSON con cinco eventos tipados.
- Importado el fixture aislado `.runtime/ui-review-maisa/qa-history.csv`: 1 aceptado, 0 rechazados, rotulado como sintético con coste/presupuesto y horas.

## Siguiente bloque

- Revalidar reseteo de estado al cambiar de run, rótulo 3D provisional, guardado de biblioteca y correcciones de accesibilidad tras los cambios de otros agentes.

## Decisiones

| Fecha | Decisión | Motivo | Evidencia |
|---|---|---|---|
| 2026-11-14 | Usar exclusivamente `8771` y `geometry_only` salvo necesidad justificada | Aislar QA y evitar gasto de proveedor | Delegación del coordinador |

## Dependencias / avisos

- Afecta a: frontend funcional, CSS/scroll y visor 3D.
- Aviso realizado: se enviará cada hallazgo con pasos, selector y severidad a su propietario.
- Cambio de `contratos/`: no aplica.

## Pruebas y revisión

| Caso | Método | Resultado observado | Limitación |
|---|---|---|---|
| Preparación | Lectura documental y comprobación de fixtures | Correcto | Auditoría UI pendiente |
| Mesa 1440×900 | Chrome DevTools, run `run-4cf40e...` | Revisión 2, derivados y escena correctos | Biblioteca 422 hallada en paralelo por coordinación |
| Piezas completo | Chrome DevTools, run `run-db4386...` | K1/K2/K3, evidencia y montaje provisional visibles | Rótulo 3D decía «revisado» antes de revisión |
| Cantidad desconocida | Chrome DevTools, run `run-b7f525...` | K3 conserva cantidad desconocida y ofrece confirmación opcional | Ninguna |
| Asociación ambigua | Chrome DevTools, run `run-7c680e...` | Tres vistas sin asociar; no fuerza montaje | Ninguna |
| PDF sin escala | PDF QA vectorial, normalización HTTP 200 | Conserva escala desconocida y explica bloqueo | Estado visual previo no se limpia |
| Modal y tema | Teclado, recarga y localStorage | Focus trap/Escape/restauración y tema persistente pasan | Drawer cerrado conserva descendiente focusable para axe |
| Lighthouse móvil | Snapshot 390×844 | A11y 87, BP/SEO 100 | roles tab, drawer oculto y nombre de marca |
| Consola/red | Mensajes y 140 requests preservados | Sin errores JS; assets y fuentes 200 | GET table-costs 404 esperado ensucia consola |
| Exportaciones | Botones y lectura de respuestas | DXF/SVG/JSON/CSV/Traza válidos y ligados a R2 | Coste ausente se conserva como desconocido |
| Histórico CSV | Importación UI de fixture aislado | 1 aceptado, 0 rechazados; filtro sintético correcto | QA no contenía fuentes publicadas en este data dir |
| Revalidación fixes | Biblioteca, reset PDF, 3D provisional | Los tres pasan en navegador real | Ninguna |
| Lighthouse final | Snapshot móvil tras recarga definitiva | Accesibilidad, buenas prácticas, SEO y agentic browsing: 100; 41 pases, 0 fallos | Ninguna |
| Drawer final | Abrir, Tab, Escape | Abierto `inert=false`, foco en cerrar; cerrado `inert=true`, foco restaurado y `aria-expanded=false` | Ninguna |

## Bloqueos y cierre

- Bloqueos: ninguno.
- Pendientes: ninguno propio; QA del navegador cerrada.
- Reservas liberadas: no aplica todavía.
