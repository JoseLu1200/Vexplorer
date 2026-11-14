# Verificación de reparación UX — 14 de noviembre de 2026

## Solicitud y alcance

El usuario pidió revisar la adaptación visual de Reto_Maisa, después corregir mediante un swarm los controles que fallaban, el scroll inaccesible, la densidad de texto y los radios excesivos. Añadió el cambio de tipografía y autorizó levantar/desplegar servidor y web, probándolos con Playwright y revisión visual.

La auditoría documental recorrió 94 Markdown propios y la transcripción; su mapa de recorridos y límites está en [AUDITORIA_UX_DOCUMENTAL_2026-11-14.md](AUDITORIA_UX_DOCUMENTAL_2026-11-14.md). Las modificaciones se reparten entre layout/HTML, interacción y visor, con QA y revisión independientes. No se modifican contratos ni se atribuyen a este trabajo los cambios concurrentes de evaluación/benchmark.

## Defectos reproducidos y correcciones

| Defecto | Causa y resultado |
|---|---|
| Scroll/solape móvil | Una fila de altura limitada era menor que los mínimos de sus hijos. En 390×844, piezas sobrepasaba 23 px el comienzo del inspector. El layout ahora usa altura natural en móvil y scroll propio delimitado en escritorio. |
| Controles y texto apelotonados | Se reducen radios y se separa resumen de diagnóstico/correcciones avanzadas. Los controles importantes conservan estado y accesibilidad. |
| Tipografía inconsistente | Segoe/Cascadia dependían del sistema. Geist/Geist Mono se sirven localmente con licencia OFL; el navegador confirmó ambas fuentes cargadas. |
| Guardar biblioteca HTTP 422 | El cliente enviaba `descriptor_version` a un contrato que no lo acepta. El nuevo payload conserva únicamente los campos admitidos. |
| Guardar/buscar mesa sin revisión válida | Se habilitaban acciones antes de existir un descriptor. Ahora quedan deshabilitadas y explican la revisión necesaria. |
| Navegación móvil aparentemente inactiva | Cambiaba el panel fuera de pantalla. Ahora desplaza y enfoca el panel elegido, respetando movimiento reducido. |
| 3D deformado por el raíl | Solo escuchaba resize de ventana. Ahora observa el contenedor, conserva proyección al ocultarse y se adapta al reaparecer. |
| 3D provisional rotulado revisado | El pie no atendía al estado real. Ahora conserva la condición de hipótesis y revisión pendiente. |
| Avisos anteriores al cargar PDF | El reset no limpiaba warning, checkbox ni modelo 3D. Se limpian al cambiar documento y se conserva la fuente PDF. |
| Teclado y semántica | Se corrigen roles/teclado de pestañas, nombres de campos, estado activo y `inert` del cajón cerrado. |
| Procedencia/copias engañosas | Restaurar sin formato original no inventa DXF; geometría de mueble general no se presenta como revisión visual automática. |

## Evidencia local observada

Instancia aislada: `http://127.0.0.1:8771`, almacenamiento `.runtime/ui-review-maisa/`. El puerto 8765 correspondía a una versión anterior y no se usó para aceptar estos cambios.

- Suite Python del árbol base de runtime: **596 aprobadas**, 75,26 s; dos avisos externos de deprecación. Los cambios de esta reparación son frontend.
- Suite frontend inicial: **147 aprobadas**, que no detectaban los defectos visuales descritos.
- Suite frontend final, repetida por coordinación y revisión: **162 aprobadas**. Sintaxis y `git diff --check -- frontend` correctos. Revisión independiente adicional: 17 pruebas backend focales de biblioteca/mesa/semántica aprobadas.
- Playwright del coordinador: carga real de mesa 001, revisión a R2, lámina derivada, material demo y subtotal conocido de **102,62 EUR**, conservando horas desconocidas y carácter parcial. Mesa 002 revisada y guardada; recuperación geométrica de mesa 001 con puntuación **0,931**, no probabilidad.
- Visor 3D: al contraer el raíl, canvas pasó de 836 a 996 px y el buffer se sincronizó con el contenedor.
- Tema oscuro persistente después de recarga; fuente Geist cargada desde la propia app.
- Matriz visual: 390×844, 1100×800, 1440×900/600, 720×450 y 320×640; comprobación adicional de layout a 1100×500. Sin desbordamiento horizontal del documento en las verificaciones finales de layout; tablas/tabs conservan desplazamiento interno cuando procede.
- QA independiente: mesa, piezas completas, cantidad/grosor/unidad desconocidos, asociación ambigua, PDF sin escala, biblioteca, coste e histórico sintético. Los desconocidos siguen explícitos y la falta de propuestas conserva el plano.
- Exportaciones verificadas por contenido: DXF, SVG, ficha JSON, lista de corte CSV y traza JSON; todas ligadas a la revisión probada.
- Importación aislada de histórico: un registro sintético aceptado, cero rechazados, procedencia visible.
- Último Lighthouse móvil local: accesibilidad, buenas prácticas, SEO y agentic browsing **100**; 41 comprobaciones aprobadas, cero fallidas. Es cobertura automática de esa pantalla, no certificación completa de accesibilidad.
- Teclado del cajón: foco inicial en cerrar, Tab contenido en modal, Escape cierra, `inert=true` al cerrar y foco restaurado al disparador.

Capturas y datos de prueba locales quedan en `.runtime/ui-review-maisa/`, fuera de Git. Los registros de agentes detallan los recorridos y resultados.

## Skills instaladas

Selección complementaria evaluada en esta sesión, no un ranking universal de noviembre de 2026:

- [Vercel web-design-guidelines](https://github.com/vercel-labs/agent-skills/tree/ba46938889d4e58635362fb8f618e1178ac3ec46/skills/web-design-guidelines), commit `ba46938889d4e58635362fb8f618e1178ac3ec46`.
- [Anthropic webapp-testing](https://github.com/anthropics/skills/tree/b9e19e6f44773509fbdd7001d77ff41a49a486c1/skills/webapp-testing), commit `b9e19e6f44773509fbdd7001d77ff41a49a486c1`.
- [Addy Osmani accessibility](https://github.com/addyosmani/web-quality-skills/tree/c6b06ad1285cd6b129b58455b2eec96ab6b67fa7/skills/accessibility), commit `c6b06ad1285cd6b129b58455b2eec96ab6b67fa7`.

Instaladas en el directorio personal `.codex/skills`; las skills existentes se preservan. Las nuevas entradas estarán disponibles automáticamente en el siguiente turno. Sus pautas de foco, reflow, contraste, formularios y pruebas ya se han aplicado tras leerlas. La skill de Vercel consulta reglas vigentes remotas aunque el paquete instalado esté fijado por commit.

## Cierre y despliegue del candidato UX autenticado

El revisor independiente emitió **SHIP** sobre el árbol final. La biblioteca muestra dimensiones comparadas en español y conserva la representación técnica completa bajo «Datos de comparación», cerrada inicialmente. Coordinación lo comprobó con dos mesas y respuesta real del servidor.

Paquete candidato: `a61f97a89a86-treec58bbe42140dd03c`. Incluye el backend runtime de HEAD y los bytes finales del frontend, incluidos `core/ui.js`, ambas fuentes y licencia aunque todavía no estén en un commit. Excluye secretos, bases de datos, datasets, herramientas de benchmark y datos QA. SHA-256 del archivo: `ed367c28920af79111350f68ae72580bbf975c7b09b09045b621cc6f988b05b6`.

Se creó y restauró una copia de seguridad antes de iniciar el candidato aislado en el VPS. Playwright autenticado contra ese candidato comprobó una revisión existente R2, paneles a 1440/1100/390 px, fuente Geist, igualdad de hashes JS/CSS/fuentes con el árbol probado, foco/Escape/inert de Traza y persistencia del tema. **Cero errores JavaScript y cero respuestas HTTP fallidas** en ese recorrido. Las capturas del candidato se inspeccionaron visualmente. La cuenta QA temporal se usa exclusivamente para aceptación y se retira al terminar.

**Publicado en https://gex-dashboard.hopto.org/vexplorer/** con el paquete exacto anterior. Coordinación verificó de forma independiente el symlink de release, el servicio activo y health HTTP 200. El acceso anónimo continúa protegido con HTTP 401.

Playwright autenticado contra la URL pública repitió recuperación R2, paneles a 1440/1100/390 px, comparación de hashes de JS/CSS/fuentes con el árbol local, foco/Escape/inert y persistencia del tema. **Cero errores JavaScript y cero respuestas HTTP fallidas**; capturas públicas inspeccionadas visualmente. El reporte local es `remote-public-results.json`.

El ensayo adicional de carga de un DXF en la instancia restaurada detectó primero un 403 por origen: el túnel local no estaba en la lista de orígenes permitidos de la configuración privada copiada. Se preparó TLS efímero para el candidato y se permitió únicamente su origen HTTPS exacto; no se relajó el guard de producción ni se ampliaron sus orígenes.

**Carga DXF remota repetida y aprobada:** Playwright subió `mesa_demo_001.dxf` a la copia restaurada en el servidor: documentos HTTP 201, job HTTP 202, resultado R1 con tapa `1200 × 700 × 30 mm` y dos soportes `720 × 700 × 18 mm`, todos como propuesta. Modo `geometry_only`; cero errores JavaScript o respuestas HTTP fallidas. El informe es `remote-candidate-upload-results.json`. No se añadieron fixtures al almacenamiento productivo.

**Limpieza completada:** cuenta QA retirada y credencial antigua comprobada con HTTP 401; el archivo de usuarios vuelve a una entrada y su hash coincide exactamente con la copia anterior al QA. Candidato y túnel detenidos; puertos de ensayo sin listener. Se eliminaron credencial local, netrc, copia candidata de usuarios y clave/certificado TLS efímeros. Se conservaron backups, restauraciones y releases. El servicio productivo sigue activo en el release aceptado, health público 200 y raíz anónima 401.

Las pruebas de esta reparación no reevalúan la calidad de inferencia con modelos live, embeddings, conversiones DWG ni precisión industrial. Esos límites no se sustituyen por resultados sintéticos ni por puntuaciones de auditoría visual.

## Cambio operativo posterior: acceso público

La evidencia anterior corresponde al candidato UX `a61f97a89a86-treec58bbe42140dd03c` mientras la autenticación seguía activa; por eso sus comprobaciones de 401 y Playwright autenticado continúan siendo correctas como historia. Después, el usuario solicitó expresamente retirar usuario/contraseña. El backend incorporó `VEXPLORER_AUTH_ENABLED=false` como opt-out explícito, conservando autenticación por defecto, validación estricta de la variable, guard de origen de mutaciones, límites y jobs de producción.

El estado operativo posterior apunta a `/home/kripta/apps/vexplorer/releases/public-access-20261114-071821`. Las comprobaciones anónimas registradas por coordinación devolvieron 200 para raíz, sesión y config en VPS y localhost, sin `WWW-Authenticate`; Playwright mostró ambas interfaces sin credenciales y sin errores JavaScript. La comprobación read-only de este cierre volvió a observar HTTP 200 en raíz y health. Este cambio supersede el requisito operativo de 401, no borra la aceptación del paquete UX anterior ni amplía sus pruebas de inferencia.

Tras el cambio de acceso, coordinación registró 11 pruebas focales de autenticación y 162 de frontend aprobadas. La primera suite Python terminó con 605 aprobadas y un `MemoryError` al leer evidencia visual; el nodo aislado pasó después. La verificación fresca de cierre sobre el árbol posterior registró 606 pruebas Python y 162 JavaScript aprobadas, con dos avisos de deprecación. La segunda ejecución completa es la evidencia vigente; el fallo transitorio se conserva para no reescribir la cronología.
