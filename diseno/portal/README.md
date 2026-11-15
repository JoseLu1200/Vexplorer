# Vexplorer · interfaz de producto

Aplicación del técnico con espacio de trabajo de carpetas y planos, subida de varios DXF a la vez con su cola, pantalla de análisis en la que el plano se dibuja con la traza, plano y despiece enlazados con herramientas de visor, revisión con historial, esquema 3D, similares y ficha para compras. Vite, React, TypeScript y Tailwind.

## Arrancar

```powershell
npm install
npm run dev          # modo mock por defecto, http://127.0.0.1:5173
npm run build        # tsc -b y build de producción en dist/
npm run build:single # un único dist-single/index.html en modo mock (el que se publica como Artifact)
node scripts/artifact.mjs                         # dist-single/vexplorer-app.html con el formato de Artifact
npx vite preview --outDir dist-single --port 4417 # sirve el build para las pruebas y las capturas
node scripts/pruebas.mjs http://localhost:4417/   # comprobaciones de comportamiento con Playwright
```

## Portal: mesa de trabajo

Rama `portal`. Cada plano se abre en una sola pantalla donde el lienzo ocupa casi todo, con el selector de vista arriba (original, limpio, piezas y 3D), las herramientas de visor en un bloque abajo a la derecha, la ficha plegable a la derecha (hoja inferior en móvil) y la barra de pasos abajo (plano, limpieza y cotas, piezas, coste y presupuesto). Revisión, Coste, Presupuesto y Similares se abren como panel encima de la mesa, y el segmento de la ruta (`#/planos/<id>/<pantalla>`) guarda la vista o el panel abierto.

- **Vistas.** Original dibuja el DXF en línea neutra con sus textos completos y las capas del archivo; Limpio agrupa los contornos por pieza y vista con las cotas normalizadas; Piezas pone la cara de cada uso del despiece a la misma escala con sus cifras y su clase de dato; 3D es la escena de `GET /runs/{id}/scene` y, antes de confirmar un montaje, dice que no hay escena y lleva a Revisión. No se construye ningún volumen en el cliente.
- **Selección cruzada.** La pieza seleccionada vive en `state.tsx` y se conserva al cambiar de vista. El puntero sobre un contorno, una fila de la ficha, una tarjeta de piezas o un volumen ilumina la misma pieza en las demás. Un contorno compartido por dos usos (K2 tapa y K2 base) alterna entre ellos con cada clic.
- **Acciones.** Salidas (Abrir en CAD, DXF anotado deshabilitado, CSV, JSON y láminas), Revisión (completar desconocidos y revisar montaje y medidas) y Más (similares, compras, traza, tema y atajos). Las láminas imprimen la vista de piezas separadas.
- **Comprobación.** `node scripts/portal.mjs http://127.0.0.1:5175/ capturas/portal [filtro]` hace las capturas de `capturas/portal/` a 1440 y 390 y avisa del scroll horizontal; `node scripts/portal-real.mjs http://127.0.0.1:5176/ <DXF>` recorre la mesa contra el backend real y lista los errores de consola y las respuestas `/api` con estado 400 o más.

## Cambiar al backend real

El interruptor es una sola variable, `VITE_USE_MOCK`. Crea `.env.local` con:

```dotenv
VITE_USE_MOCK=false
VITE_API_BASE=
VITE_API_PROXY=http://127.0.0.1:8000
```

`backend/app/main.py` no declara CORS, así que el navegador debe hablar con el mismo origen. En desarrollo, `VITE_API_BASE` vacío y Vite reenvía `/api` a `VITE_API_PROXY` (por ejemplo `uvicorn backend.app.main:app --port 8000` desde el repo de Vexplorer). En producción se sirve `dist/` detrás del mismo host que la API, o se añade CORS al backend y se rellena `VITE_API_BASE`.

## Espacio de trabajo

El backend no lista documentos ni análisis y no tiene carpetas, así que `src/workspace/` lleva ese registro en el navegador y habla con el servidor solo a través de la interfaz `VexplorerApi`, por lo que funciona igual con el mock que con el backend real.

- **Qué guarda.** Carpetas anidadas, planos con su nombre visible, el `document_id` y el `run_id` que devolvió el servidor, el último estado y revisión conocidos, la fecha, la miniatura (contornos de `GET /documents/{id}/drawing`), las peticiones de revisión enviadas y el DXF subido como `Blob`. Todo va a IndexedDB (`vexplorer-workspace`) dentro de try/catch; si el navegador lo bloquea, la app trabaja en memoria y avisa de que los planos se pierden al cerrar la pestaña.
- **Estados.** Analizando mientras dura la subida o el análisis, Requiere revisión y Revisado según `result.state` (Completo solo llega tras una revisión de persona) y Error con el código que devuelve el servidor, por ejemplo `unsupported_format` para un PDF.
- **Subida.** Arrastrar a la ventana añade los archivos a la carpeta abierta y arrastrar sobre una carpeta de la barra lateral los añade a esa carpeta. La cola analiza dos a la vez y cada fila recorre subida, lectura del plano, análisis, traza y resultado, con el error de cada archivo en su fila. Los planos y las carpetas también se arrastran sobre una carpeta para moverlos.
- **Abrir un plano.** Todo pasa por `ensureRun`. Si el servidor conserva el análisis lo lee con `GET /runs/{id}`, `/revisions` y `/drawing`; si responde 404, vuelve a subir el DXF guardado, lo analiza y repite las revisiones que se enviaron, en el mismo orden. Mientras tanto se ve el esqueleto de la pantalla.
- **Análisis.** La geometría de `GET /documents/{id}/drawing` llega antes que el análisis y se dibuja en discontinuo; con «Análisis iniciado» pasa a trazo firme, cada «Inspeccionar pieza» del modo con asistente dibuja las vistas de esa pieza con sus cotas, con «Resultado guardado» aparecen todas las cotas y con «Análisis terminado», los rótulos. No se inventan eventos. Con el análisis terminado, la pantalla vuelve a pedir `GET /runs/{id}/events` y el plano se dibuja otra vez con la traza.
- **Plano.** El puntero sobre un contorno marca su pieza en el despiece y al revés, y el clic selecciona. Las celdas desconocidas abren «Completar», que envía la misma petición `POST /runs/{id}/reviews` que Revisión con revisor, motivo y montaje. El visor tiene capas de contornos, cotas y textos, una herramienta de medir con imán a vértices y aristas de `points_mm` (en unidades de origen si el plano no está en mm), encajar y zoom.
- **Abrir en CAD.** Descarga el DXF original para que lo abra el programa de CAD del sistema: el archivo arrastrado desde IndexedDB y, en los planos de ejemplo, los seis DXF de `data/planos_demo` copiados tal cual en `src/assets/dxf/` (`.gitattributes` evita que git cambie sus finales de línea). El DXF con las piezas anotadas aparece deshabilitado porque necesita una ruta del servidor. Dentro del visor de Artifacts el marco no puede descargar por su cuenta, así que la descarga pasa por la capacidad `downloads` (hay que publicar con `capabilities: {downloads: true}`); esa capacidad no admite hoy la extensión `.dxf`, por lo que en el Artifact el botón avisa de que la descarga funciona en la aplicación servida aparte.
- **Detalles de sistema.** Búsqueda por nombre en todas las carpetas, orden por fecha, estado o nombre, migas de pan carpeta › plano › pantalla, atajos (`/` buscar, `?` atajos, `1` a `6` pantallas del plano, `M` medir, `F` encajar, `+` y `−` zoom, flechas para cambiar de pieza, `Esc`), estados vacíos y avisos al terminar un análisis o una revisión. El arranque con el logo dura 700 ms como mínimo y todo respeta `prefers-reduced-motion`.

### Siembra y límites del modo de ejemplo

En modo mock la primera visita siembra tres carpetas (Recibidos, Serie E-900 y Serie E-1000) con los seis DXF de ejemplo. `piezas_espesor_desconocido.dxf`, `piezas_qty_desconocida.dxf` y `piezas_ambigua_sin_id.dxf` se analizan de verdad contra el mock al arrancar. Los otros tres solo existen en el mock como elementos de la biblioteca con sus contornos (`GET /library` y `GET /runs/{id}/drawing`), así que se abren como ficha de la biblioteca de solo lectura, con su plano, su medición y Abrir en CAD, y sin Análisis, Revisión, Esquema, Similares ni Compras.

- `mock.ts` reconoce tres planos por el nombre del archivo y cualquier otro DXF recibe la respuesta grabada de `piezas_espesor_desconocido.dxf`.
- El mock reutiliza el mismo `document_id` y `run_id` para todos los planos de una misma respuesta grabada. Por eso cada plano tiene su propio id en el espacio de trabajo y `ensureRun` rehace el análisis cuando otro plano ha ocupado ese `run_id`; si es el plano abierto, lo rehace en segundo plano sin perder la pieza elegida.
- El mock vive en memoria: tras recargar, los análisis se rehacen al abrir cada plano y solo vuelven las revisiones que el mock sabe repetir, que son las del primer candidato en los planos con la respuesta de `piezas_espesor_desconocido.dxf`.

## Necesita backend

Para que el espacio de trabajo viva en el servidor y no en cada navegador, el backend tendría que añadir esto:

| Qué | Ruta propuesta | Por qué |
|---|---|---|
| Listar documentos | `GET /api/v1/documents` con `document_id`, nombre original, tamaño, sha256 y fecha de subida | `POST /documents` escribe `documents/{id}.dxf` pero no guarda el nombre original ni la fecha, así que hoy no se puede reconstruir la lista |
| Listar análisis | `GET /api/v1/runs?document_id=` con `id`, `state`, `result_revision`, `mode` y `created_at` | El estado de cada plano saldría del servidor y se compartiría entre personas |
| Carpetas | `GET/POST /api/v1/folders`, `PATCH /api/v1/folders/{id}` (nombre y `parent_id`), `DELETE /api/v1/folders/{id}`, y `PATCH /api/v1/documents/{id}` con `folder_id` y nombre visible | Crear, renombrar, mover y borrar sin depender del almacenamiento del navegador |
| DXF original | `GET /api/v1/documents/{id}/file` con `Content-Type: application/dxf` y `Content-Disposition: attachment; filename="<nombre original>"` | El archivo ya está en disco; falta servirlo y conservar su nombre |
| DXF anotado | `GET /api/v1/runs/{id}/exports?format=dxf&result_revision=` con una capa por pieza y el id de pieza como texto o atributo junto a cada contorno de origen | Abrir en CAD el despiece revisado con cada contorno identificado |

Con esas rutas, `src/workspace/store.tsx` cambiaría la lectura de IndexedDB por las listas del servidor y `downloadDxf` por la ruta del archivo, sin tocar las pantallas.

## Arquitectura

- `src/api/types.ts`: tipos que reflejan los modelos Pydantic de `backend/app/contratos/modelos.py` (contrato parts-only 0.4). Cada interfaz lleva el nombre del modelo Python.
- `src/api/client.ts`: una función por ruta real de `main.py`, con el mismo método y la misma ruta. Define la interfaz `VexplorerApi`.
- `src/api/mock.ts`: la misma interfaz con respuestas grabadas. Las respuestas salen de ejecutar el backend real en proceso (FastAPI `TestClient`) contra `piezas_espesor_desconocido.dxf`, `piezas_qty_desconocida.dxf`, `piezas_ambigua_sin_id.dxf`, `piezas_completo.dxf`, `piezas_dimensiones_variante.dxf` y `piezas_espesor_36.dxf` de `data/planos_demo`. Incluye los errores reales `observed_dimension_override` (422), `stale_result_revision` (409), `result_needs_review` (422), `semantic_embedding_missing` (409) y `recorded_replay_unavailable` (409).
- `src/api/index.ts`: el interruptor.
- `src/lib/domain.ts`: traduce estados del contrato a las cinco clases de dato. No calcula medidas, cantidades ni totales.
- `src/router.tsx`: rutas por hash (`#/`, `#/carpetas/<id>` y `#/planos/<id>/<pantalla>`).
- `src/workspace/`: tipos, IndexedDB con respaldo en memoria, DXF de ejemplo, siembra, cola de subida y `ensureRun`.
- `src/state.tsx`: el análisis del plano abierto, que leen las pantallas de un plano.

### Detalles del backend que condicionan el cliente

- `POST /runs` es síncrono y devuelve 201 con `run` y `result`. No hay estado intermedio que sondear.
- `GET /runs/{id}/events` devuelve un `text/event-stream` finito con el historial y cierra. Con `EventSource` el navegador reconectaría y repetiría el historial sin fin, así que el cliente lee el cuerpo con `fetch`, interpreta los marcos y descarta duplicados por `sequence`. Con el backend real la traza llega de golpe al terminar el análisis; el mock la reparte en el tiempo para enseñar la traza en vivo.
- Los eventos llevan `timestamp` dentro de `data`. No existen `tool_started` ni `tool_call_id`, ni la ruta `/cancel` que tenía el frontend anterior.
- `/comparables` y `/exports` solo sirven la revisión vigente. `/parts`, `/scene`, `/explanations` y `/estimate` exigen `result_revision`.
- En parts-only, `result.pieces` llega vacío en la revisión 1. La tabla se construye con los `uses` del candidato de montaje unidos a sus observaciones, y desde la revisión 2 con `ResolvedPiece` y sus `field_states`.
- La revisión solo confirma campos desconocidos. Sustituir una medida observada devuelve `observed_dimension_override`, así que la interfaz bloquea esos campos.

### El modo `live` en el mock

Sin clave de proveedor no se pudo grabar una ejecución `live`. El mock habilita ese modo y compone sus eventos `tool_completed` con los nombres de herramienta y los textos de resumen literales de `backend/app/agente/runner.py` y con IDs de evidencia reales del ledger. Todo el modo mock lleva la etiqueta «Datos de ejemplo» en la barra superior.

## Endpoints por pantalla

| Pantalla | Endpoints | Estado |
|---|---|---|
| Planos | `GET /api/v1/config`, `POST /api/v1/documents`, `GET /api/v1/documents/{id}/drawing` (miniatura), `POST /api/v1/runs`, `GET /api/v1/runs/{id}/drawing`, `GET /api/v1/library` y `GET /api/v1/runs/{id}/drawing` de la biblioteca (siembra del modo de ejemplo) | Cableado |
| Análisis | `GET /api/v1/documents/{id}/drawing`, `GET /api/v1/runs/{id}/events`, y al abrir `GET /api/v1/runs/{id}`, `GET /api/v1/runs/{id}/revisions` y `GET /api/v1/runs/{id}/drawing` | Cableado |
| Plano y piezas | `GET /api/v1/runs/{id}/drawing`, `GET /api/v1/runs/{id}/explanations?result_revision=` (el resultado viene de `POST /runs` o de `POST /reviews`) | Cableado |
| Revisión | `POST /api/v1/runs/{id}/reviews`, `GET /api/v1/runs/{id}`, `GET /api/v1/runs/{id}/revisions` (recarga tras 409) | Cableado |
| Esquema 3D | `GET /api/v1/runs/{id}/scene?result_revision=` | Cableado |
| Similares | `POST /api/v1/runs/{id}/similarity`, `GET /api/v1/library`, `POST /api/v1/runs/{id}/library`, `POST /api/v1/library/groups`, `GET /api/v1/runs/{id}/drawing` del mueble similar para la miniatura | Cableado |
| Compras | `GET /api/v1/runs/{id}`, `POST /api/v1/runs/{id}/estimate`, `GET /api/v1/runs/{id}/comparables`, `GET /api/v1/runs/{id}/exports?format=json\|csv` | Cableado |
| Plano | Además, `POST /api/v1/runs/{id}/reviews` desde «Completar» | Cableado |
| Sin pantalla | `GET /api/v1/health`, `GET /api/v1/documents/{id}/preview.svg`, `GET /api/v1/runs/{id}/parts`, `GET /api/v1/runs/{id}/ledger` | En el cliente, sin uso en la interfaz |

`preview.svg` no se usa como miniatura porque el renderizador de ezdxf conserva los colores de pantalla del CAD (texto verde y relleno amarillo sobre blanco). Las miniaturas se dibujan con los contornos del ledger.

## Línea cobalto

La interfaz sigue la línea cobalto de la landing (rama `landing-cobalto-r12`) con papel de plano `#ece6da` de fondo, tinta azul noche `#1c2541`, cobalto `#2a4486` para el trazo del plano y el bloque del esquema 3D y tablero `#c79a68` solo para la acción principal, y sus equivalentes oscuros están en `src/styles.css`.

- **Tipografía:** Sofia Sans Semi Condensed para la interfaz, Sofia Sans Extra Condensed para el logotipo y Martian Mono a `wdth` 87,5 para cifras, cotas e IDs, incrustadas con licencia OFL en `src/assets/fonts/`. La escala va de 12 a 32 px, con el texto corrido a 14 y 15 px y los rótulos, las cifras y los IDs a 12 y 13 px.
- **Espacio:** la escala de la landing, 4 · 8 · 12 · 20 · 32 · 52 · 84 · 136, como clases `s1` a `s8` de Tailwind, y cantos rectos en todo.
- **Clases de dato:** las cinco palabras de la landing (Observado, Calculado, Hipótesis, Confirmado y Desconocido) con su muestra de tablero, y «grosor» en vez de «espesor». En las celdas Observado va sin muestra porque es el caso por defecto y Desconocido se escribe con la palabra. El tono de Hipótesis baja de `#8f5418` a `#86501a` para llegar a 4,5:1 sobre la fila seleccionada.
- **Fondo:** tablas, paneles, formularios, miniaturas, listas de planos y esquema 3D van sobre fondo liso, la única retícula es la de dibujo del lienzo del plano y las curvas de nivel (Topography de React Bits, copiada de la landing con su cabecera) solo salen en la carpeta vacía de Planos desde 1024 px y en «Sin esquema en esta revisión». La interfaz del espacio de trabajo no usa componentes de terceros nuevos.
- **Esquema 3D:** trazo claro sobre el bloque cobalto de la landing, con la pieza seleccionada en tablero y el aviso «No apto para fabricación» dentro del bloque.
- **Candidato de montaje:** en Plano pasa de desplegable a tarjetas con los tres primeros a la vista y el resto a un clic, y con el montaje confirmado solo queda su tarjeta.
- **Texto:** fuera la numeración decorativa, los subtítulos que repetían el estado de la barra, las leyendas y pies repetidos, las premisas en párrafo y las puntuaciones parciales de Similares, que pasan a desplegables junto con el desglose de la fórmula y los IDs.
- **Comprobación:** `node scripts/contraste.mjs` mide cada color de clase y cada gris sobre papel, hoja y fila seleccionada en los dos temas, y todos los pares de texto pasan de 4,5:1. Las capturas a 1440 y a 390 están en `capturas/cobalto/` y ninguna tiene scroll horizontal.

## Comportamiento del backend comprobado (solo lectura)

- **Similares no se compara consigo mismo.** `POST /runs/{id}/similarity` filtra `item.run_id != run_id` antes de puntuar (`backend/app/main.py`, función `similar`). El resultado con parecido 1 en los datos de ejemplo es otro análisis, `piezas_completo.dxf`, con las mismas medidas. La interfaz repite el filtro por si acaso, marca cada resultado como «Otro análisis» y deja el `run_id` en «Detalles técnicos». No es un fallo que deba corregir B.
- **Fórmula de tablero.** `backend/app/estimacion/service.py` calcula `coste de tablero del comparable × (área de las piezas ÷ área del comparable)`; la tarifa en €/m² que aparece en el texto es ese coste dividido por el área del comparable. Compras muestra los dos términos que llegan (`base_amount` y `factor`) y el área del comparable que llega en `GET /comparables`, sin recalcular nada.
- **Altura de las baldas.** La escena marca las baldas como `placement_status = human_selected` aunque su `placement_basis` diga «height not observed». La interfaz las dibuja con trazo discontinuo y la etiqueta «altura hipotética» leyendo los dos campos. Propuesta para B: que esas ocurrencias lleguen como `hypothesis`.
- **Vistas sin etiqueta.** `ReviewRequest` solo admite decisiones sobre `AssemblyPartUse` existentes, así que una vista sin `PART` no se puede asignar a una pieza desde la revisión. La interfaz explica que hay que etiquetarla en el DXF y volver a analizar.
- **Conflicto de espesor.** El backend rechaza sustituir una medida observada (`observed_dimension_override`), así que de las dos salidas solo «Usar el valor observado» crea una revisión. «Mantener el confirmado» queda deshabilitado con el motivo.

## Material y acabado

`backend/app/historico/service.py` tiene el histórico sintético fijo en código y no hay endpoint de catálogo. La estimación exige que material y acabado coincidan con los de un comparable, y esos valores sí llegan por `GET /runs/{id}/comparables`. Revisión los ofrece como selects con esos valores. Si aun así faltan o no coinciden, Compras muestra el 422 `missing_compatible_material_or_finish` con el acceso a Revisión.

## Decisiones frente a `frontend/UX_SPEC.md`

Donde la especificación del repo y el encargo de diseño chocan, manda el encargo: hay reconstrucción 3D esquemática (la spec la marcaba como no objetivo), el fondo es papel neutro en vez de marfil, y los controles miden de 32 a 44 px en vez de 44 px fijos.

## Prueba contra el backend real

Esta prueba es anterior al espacio de trabajo. `scripts/backend-real.mjs` está adaptado al recorrido nuevo (subir desde Planos y abrir el plano) pero no se ha vuelto a ejecutar contra el backend.

Última ejecución: 14 de noviembre de 2026, tras la sexta ronda de revisión de diseño (quinta ejecución; las cinco dieron el mismo resultado). Un build con `VITE_USE_MOCK=false` (`dist-real/`) se sirvió desde el propio FastAPI con `create_app(data_dir=<scratchpad>, frontend_dir=dist-real)`, en el mismo origen, en el puerto 4391, sin proveedor de IA configurado y con los datos fuera del repo. `scripts/backend-real.mjs` recorre la interfaz con `piezas_espesor_desconocido.dxf` como lo haría una persona:

| Pantalla | Acción | Llamadas |
|---|---|---|
| Carga | Elegir el DXF y pulsar «Analizar DXF» | `GET /config`, `POST /documents`, `POST /runs`, `GET /runs/{id}/drawing`, `GET /runs/{id}/events` |
| Plano | Seleccionar K3 | `GET /runs/{id}/explanations?result_revision=1` |
| Revisión | Confirmar espesor 18 mm, material y acabado desde los selects, «Crear revisión 2» | `GET /runs/{id}/comparables`, `POST /runs/{id}/reviews` |
| Esquema | Ver los volúmenes de la revisión 2 | `GET /runs/{id}/scene?result_revision=2` |
| Compras | «Calcular estimación» y exportar CSV | `GET /runs/{id}/comparables`, `GET /runs/{id}`, `POST /runs/{id}/estimate`, `GET /runs/{id}/exports?format=csv` |
| Similares | Guardar en biblioteca | `GET /library`, `POST /library/groups`, `POST /runs/{id}/similarity`, `POST /runs/{id}/library` y de nuevo las tres de lectura |

Resultado: 20 llamadas, todas 2xx (15 con 200 y 5 con 201: `documents`, `runs`, `reviews`, `estimate`, `library`). Los valores de material y acabado que ofrece Revisión, tomados de `/comparables`, son los que la estimación acepta: el `POST /estimate` respondió 201 con 127,84 € provisionales (60,00 € × 1,464 = 87,84 € de tablero más 40,00 € fijos). En este modo no aparece la etiqueta de datos de ejemplo y los modos deshabilitados se explican sin mencionar el servidor. El registro completo está en `capturas/backend-real/registro-http.txt` y las capturas de cada paso en la misma carpeta.

Sin verificar contra el backend real: el modo `live` (no hay clave de proveedor), la exportación JSON, la similitud por descripción y los caminos de error (409 por revisión obsoleta, 422 por conflicto o por material ausente), que solo se han probado con las respuestas grabadas del mock.

## Pruebas de comportamiento

`node scripts/pruebas.mjs http://localhost:4417/` recorre el build de un solo archivo con el Chrome instalado y comprueba la siembra, el arrastre de dos DXF y un PDF a la ventana con la cola y el error por archivo, el arrastre a una carpeta, la descarga de Abrir en CAD comparando su sha256 con el DXF de origen, la persistencia tras recargar (el plano arrastrado se vuelve a abrir y su archivo se descarga desde IndexedDB), la recarga de un plano con revisión (vuelve con la revisión 2 repetida), el arrastre de dos DXF con un plano abierto que comparte su `run_id` en el mock (sigue a la vista y con la pieza elegida), el enlace por hover en los dos sentidos, la medición entre dos vértices de K1 (1200 mm), las capas, la revisión creada desde el despiece, el 422 del mock en un plano sin revisión grabada, el funcionamiento con IndexedDB bloqueada y el movimiento reducido.

## Capturas

`node scripts/capturas.mjs http://localhost:4417/ capturas/sistema` con `npx vite preview --outDir dist-single --port 4417` en marcha tras `npm run build:single`. Usa el Chrome instalado, abre un contexto nuevo por captura (espacio de trabajo recién sembrado) y para el flujo de revisión usa parámetros de URL que solo atiende el modo mock (`?auto=principal&review=18&go=plano&sel=K3&theme=dark`). Las capturas de esta fase están en `capturas/sistema/` y las de la línea cobalto en `capturas/cobalto/`.
