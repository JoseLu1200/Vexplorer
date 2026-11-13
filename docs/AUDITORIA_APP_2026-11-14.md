# Auditoría de la aplicación — 14 de noviembre de 2026

**Código evaluado: `dab7ce5` (main antes del flujo de piezas separadas).** Auditoría por agentes de IA; decisiones introducidas en el formulario son ensayos funcionales, no aprobaciones de una persona ni validación industrial. Este informe conserva la situación anterior a futuras correcciones.

La demo ejecuta un recorrido integrado para la estantería propia, pero **no cumple todavía la entrada aclarada por el usuario: solo vistas DXF de piezas separadas, sin mueble montado**. La implementación auditada genera escenarios a partir de vistas del conjunto montado. El nuevo recorrido debe verificarse por separado; no puede darse por cubierto por los resultados siguientes.

## Método

Instancia real `http://127.0.0.1:8767`, datos separados en `.runtime/audit-20261114/`; frontend servido por FastAPI. Python 3.14.2, Node 25.8.1, Windows y Chrome. Ningún cambio de producto durante estas comprobaciones. Se utilizaron fixtures propios públicos, nunca PlankAssembly ni referencias del evaluador como entrada del runtime.

Estados: **PASS** observado correcto; **FAIL** fallo reproducido; **LIMITACIÓN** comportamiento acotado previsto; **NO IMPLEMENTADO** y **NO VERIFICADO**. Las pruebas de librerías no sustituyen pruebas de navegador.

| Verificación | Resultado | Evidencia |
|---|---|---|
| HTTP real, casos positivos y negativos | 64 PASS, 0 FAIL | [api.json](auditoria/2026-11-14/api.json), [runner](../tools/audit_api.py) |
| Suite Python completa | 119 pasan; un aviso TestClient/httpx | Ejecutada por evaluación y frontend sobre el producto auditado |
| Suite JavaScript | 46 pasan | Son pruebas de módulos/cliente, no de todo el DOM de `app.js` |
| Proveedor live real | 201; resultado pendiente de revisión | [live.json](auditoria/2026-11-14/live.json) |
| Embeddings reales | Dos generados, traslado y repetición desde caché | Mismo archivo; `text-embedding-3-small`, 256 dimensiones |
| Contraejemplos geométricos | Tres defectos reproducidos | [geometry.txt](auditoria/2026-11-14/geometry.txt), [repro](../tools/audit_geometry_baseline.py) |
| Navegador | Recorrido principal operativo con fallos de vistas/traza/responsive | Observaciones y capturas abajo |

## API: qué funciona

- **PASS** Health/config; carga DXF, lectura del dibujo y SVG original; vínculo entre documento, extracción, ejecución y revisión.
- **PASS** `geometry_only` produce dos hipótesis excluyentes; tres vistas no se convierten en tres unidades. Seis ocurrencias físicas en cuatro grupos, espesor desconocido antes de revisión.
- **PASS** Revisión versionada, conservación de revisiones anteriores y rechazo 409 de una revisión obsoleta. La revisión entre laterales con espesor 18 calcula `900 − 2 × 18 = 864 mm`.
- **PASS** Explicaciones y escenas por revisión; sin sólidos antes de confirmar información suficiente. Escena revisada con seis ocurrencias y referencias a piezas/evidencias.
- **PASS** Tres comparables sintéticos; estimación por revisión con conceptos únicos: tablero `1,7568 m² × 50 EUR/m² = 87,84 EUR` y preparación `40 EUR`; total `127,84 EUR`. Horas desconocidas. Se rechaza material/acabado sin tarifa compatible.
- **PASS** Ficha JSON, CSV, eventos persistidos, biblioteca, similitud y grupos geométricos; sin proveedor para este modo.
- **PASS** Casos negativos incluidos en el runner: archivo/ruta/ID inválidos, DXF corrupto, unidades desconocidas, geometría no admitida, revisión/estimación incompleta y replay no habilitado. El rechazo previsto cuenta como PASS, no como funcionalidad implementada.
- **PASS** Las rutas probadas no exponen la referencia privada; el runtime usa solo documentos públicos. Esto no equivale a una auditoría de seguridad completa.

### Harness y semántica reales

Run `run-23303f6ef7c8412c81cca2f70eb2c157`, modo `live`, configuración `gpt-6.1-sol`: `inspeccionar_evidencia`, dos llamadas `explicar_pieza` y `entregar_despiece`, todas con `ok:true`; eligió `scenario-cap-sides`. Se comprobó también su traza en el navegador. Es inferencia real, no replay. El modelo recibe el ledger vectorial estructurado y selecciona un escenario existente; **no recibió imágenes ni inventó medidas**.

El script de auditoría tuvo inicialmente un error propio de lectura de `run_id` en vez de `id`, después del 201. Se corrigió el script y se continuó mediante `--reuse-live-run`, sin repetir la llamada live. No fue un fallo de la API.

El script guardó tres casos: original, variante dimensional y original trasladado. Original/traslado comparten huella y caché; la variante genera otro vector. La sesión del navegador añadió una cuarta entrada (el run revisado desde la interfaz). La búsqueda mostró puntuaciones 1,000 para equivalentes y aproximadamente 0,999 para la variante, con diferencias dimensionales. Agrupación semántica con umbral 0,70 produjo un grupo de esas cuatro revisiones cuando todas tenían embedding. Estas observaciones del DOM, separadas de las llamadas del script, se conservan en [browser.json](auditoria/2026-11-14/browser.json). **No demuestra calidad de clasificación entre familias ni un umbral comercial útil**: se probaron solo estanterías muy similares. Las puntuaciones no son probabilidades.

## Navegador: recorrido observado

Run principal `run-bbd9cded5fd94648866c0814478b4f3d`. El DXF se suministró al campo de fichero con sus bytes reales mediante `File`/`DataTransfer` y se envió con el botón normal del formulario. El conector no admitía la ruta local para `upload_file`; no se simuló la respuesta de la aplicación.

| Acción | Estado y observación |
|---|---|
| Cargar DXF | PASS: tres vistas y cotas 900/1200/300/18; seis piezas propuestas; espesor aún desconocido |
| Seleccionar Tapa en tabla | PASS: inspector y tres contornos de respaldo resaltados. Evidencia de región del conjunto, no contorno individual de la tapa |
| Zoom y capa Cotas | PASS: zoom reduce el viewBox; desactivar cotas deja cero elementos de cota visibles |
| Alzado | FAIL: solo contorno exterior visible; desaparecen líneas interiores. Encajar mantiene bounds globales |
| CAD original | PASS: imagen SVG cargada (`naturalWidth=6125`), separada de las evidencias seleccionables |
| Revisar | PASS: revisión 2, espesor 18 y largos calculados 864. Cantidad/espesor confirmados; dimensiones observadas/calculadas distinguibles |
| 3D | PASS de renderizado: seis paneles visibles, aviso «Colisiones no evaluadas». El toggle de despiece cambia de estado. Órbita/picking por puntero no se validaron exhaustivamente en esta auditoría |
| Coste sin tarifa | PASS de rechazo: total Pendiente; mensaje genérico «No hay evidencia suficiente para estimar» |
| Coste con tarifa sintética | PASS: revisión 3, 127,84 EUR explicado en dos conceptos; horas desconocidas |
| Biblioteca semántica | PASS: guardar, buscar y agrupar con vectores reales y diferencias visibles |
| Exportaciones | PASS de generación en navegador: JSON 37.002 bytes con revisión 3 y diez claves; CSV 902 bytes/5 líneas; traza JSON de 7 eventos. Se inspeccionó el Blob producido por botones manteniendo la descarga original; no se verificó su ubicación final en disco |
| Traza tras guardar biblioteca | FAIL: servidor tiene 7 eventos, UI conserva 6 hasta recargar |
| Recargar URL del run | PASS: restaura revisión 3, tabla, coste 127,84 y los 7 eventos |
| DXF sin unidades | PASS de abstención: plano permanece visible, «Unidad sin resolver», cotas en `source-unit`, ninguna pieza inferida ni mm inventados |
| Pantalla estrecha | FAIL: viewport CSS medido 501 px, documento 619 px, botón Abrir en x=532–589 fuera del ancho visible. El tamaño efectivo difirió del solicitado al conector; no se afirma prueba de 390 px |

Capturas: [Alzado sin líneas interiores](auditoria/2026-11-14/browser-front-missing-lines.png) y [desbordamiento](auditoria/2026-11-14/browser-overflow.png). La consola registró el 422 provocado deliberadamente al estimar con tarifa incompatible; no se observó una excepción JavaScript durante el recorrido normal.

## Fallos reproducidos y prioridad

| ID | Prioridad | Reproducción / impacto | Localización |
|---|---|---|---|
| A01 | Alta | LINE con Z distintos y polilíneas OCS fuera de XY se aplanan. Tres proyecciones OCS producen dos escenarios aunque no pertenecen al plano XY admitido | `backend/app/ingesta/dxf_reader.py`, `backend/app/geometria/extraction.py` y `backend/app/servicios/decomposition.py`; repro geométrico |
| A02 | Alta | DIMLFAC=2 con tramo 600: ledger abstiene, texto CAD dice 1200, gráfico simplificado dice 600 mm. La cota visible resulta engañosa | `backend/app/ingesta/dxf_reader.py`; repro geométrico |
| A03 | Alta | Espesor 18/largo horizontal 864 y espesor 36/largo 828, ambos coherentes, generan descriptor/texto/huella idénticos | `semantic/descriptor.py`, contratos; repro geométrico. El espesor ni su ausencia están representados |
| A04 | Alta | Abrir fixture montada → Alzado: desaparecen líneas interiores. Encajar no ajusta la vista seleccionada | `frontend/core/drawing.js:33`, `frontend/app.js:125`; captura y DOM real |
| A05 | Media | Guardar biblioteca → abrir Traza: falta el evento que sí aparece en SSE; recargar lo recupera | `frontend/app.js:449`; 6 eventos UI frente a 7 API |
| A06 | Media | UI estrecha desborda y deja acciones fuera de pantalla | Captura y rectángulos DOM medidos |
| A07 | Media | Repetir POST `/runs` con mismo `Idempotency-Key` crea dos IDs diferentes | [Repro aislado TestClient](auditoria/2026-11-14/idempotency.json); cliente envía clave, backend no la consume |
| A08 | Media | «Abrir rev. N» solo enlaza `?run=...`; se carga la revisión más reciente si el run avanzó | Confirmado por lectura de `frontend/app.js:436` y `main.py:get_run`; no recorrido histórico completo en navegador |

Otros límites de UX comprobados: enum de fórmula `overall_width_minus_two_thickness` y texto inglés de evidencia; etiquetas de biblioteca basadas en `drawing_id`; aviso de colisiones persiste al volver a 2D; los detalles del descriptor y premisas de colocación no se muestran completos. No se corrigieron durante la auditoría baseline.

## Implementado, pendiente y no verificado

**Implementado con alcance acotado:** ingestión DXF vectorial, unidades admitidas, vistas/cotas/evidencias, dos montajes de estantería, revisión con recálculo, reconstrucción esquemática de paneles, harness con herramientas nativas, biblioteca local/embeddings/coseno, histórico y aritmética sintéticos, exportación y traza persistida.

**NO IMPLEMENTADO en `dab7ce5`:** entrada y asociación de vistas de piezas separadas; inferencia libre de muebles o ensamblajes desde esa entrada; visión de PDF/imágenes; DWG; colisiones, mecanizados y uniones reales; edición libre para dividir/unir componentes desde UI; cancelación de ejecución; navegación a una revisión histórica concreta; replay admitido. El endpoint de eventos entrega un historial finito, no progreso en vivo durante la inferencia.

**NO VERIFICADO:** generalización a muebles reales o varias familias, precisión empresarial del coste, ahorro de tiempo con técnicos, rendimiento bajo carga, accesibilidad completa por teclado, todos los casos de respuesta tardía al cambiar de sesión, órbita/picking 3D exhaustivos. Hay cobertura unitaria de algunos de esos mecanismos, pero no basta para afirmarlos en uso completo.

## Reproducir

Desde la raíz, con las dependencias del README instaladas. La auditoría crea datos de prueba. No reutilizar el directorio de una sesión de trabajo real.

```powershell
# Instancia aislada, sin proveedor
.\.venv\Scripts\python.exe -c "from pathlib import Path; import uvicorn; from backend.app.main import create_app; uvicorn.run(create_app(data_dir=Path('.runtime/audit-20261114')),host='127.0.0.1',port=8767)"
# Otra terminal
.\.venv\Scripts\python.exe tools/audit_api.py --base-url http://127.0.0.1:8767 --output .runtime/audit-api-repeat.json
.\.venv\Scripts\python.exe tools/audit_geometry_baseline.py
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix frontend
```

Para proveedor real, detener solo esa instancia y arrancarla cargando `.env` local (ignorado). Este ensayo hace llamadas facturables; las claves nunca se imprimen ni se guardan en las evidencias:

```powershell
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv(); import os; os.environ['OPENAI_MODEL']='gpt-6.1-sol'; from pathlib import Path; import uvicorn; from backend.app.main import create_app; uvicorn.run(create_app(data_dir=Path('.runtime/audit-20261114')),host='127.0.0.1',port=8767)"
.\.venv\Scripts\python.exe tools/audit_live.py --base-url http://127.0.0.1:8767 --output .runtime/audit-live-repeat.json --invoke-paid-provider
```

Los scripts geométricos reproducen la versión auditada; correcciones posteriores pueden cambiar su salida. Las evidencias fechadas no se sobrescriben para presentar un resultado posterior como si fuera el baseline.
