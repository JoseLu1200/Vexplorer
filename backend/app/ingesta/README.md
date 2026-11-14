# Adaptadores PDF y DWG

Estos adaptadores preservan el fichero original y producen artefactos derivados; no sustituyen el origen ni fabrican medidas.

## DWG

`convert_dwg_to_dxf(source, output_dir, ...)` ejecuta un proveedor seleccionado y valida su salida con `parse_dxf`. `VEXPLORER_DWG_CONVERTER=libredwg|oda|auto` lo fija de forma explícita; `auto` prefiere GNU LibreDWG. LibreDWG usa `VEXPLORER_DWG2DXF_EXECUTABLE` o `dwg2dxf` en `PATH`, con `dwg2dxf --as r2018 -o OUTPUT SOURCE`. ODA usa `VEXPLORER_ODA_EXECUTABLE`, el alias legado `ODA_FILE_CONVERTER` o `PATH`, y solo debe habilitarse con derechos de uso autorizados. Si el proveedor falta, expira, devuelve error o produce un DXF ilegible, la función lanza un error específico y no declara una conversión correcta.

`DwgConversionResult.dxf_path` es una entrada directa para `parse_dxf` o `extract_drawing`. El resultado conserva nombre, tamaño, tipo y SHA-256 del DWG, además del SHA-256 del DXF derivado.

## PDF

`ingest_pdf(source, artifact_dir, ...)` genera para cada página:

- un PNG de previsualización;
- paths y texto vectoriales con coordenadas originales en puntos PDF;
- un DXF separado si existen líneas, rectángulos, cuadriláteros o texto convertibles.

No se combinan páginas en un DXF: cada ledger se analiza por separado para que varias vistas o páginas no se conviertan por accidente en ocurrencias físicas adicionales. La capa `PDF_PAGE_####` conserva la página de origen.

Sin `PdfScaleConfirmation`, el DXF usa `$INSUNITS=0`; `parse_dxf` conserva unidad desconocida y no produce coordenadas métricas. Con una confirmación explícita y trazable, las coordenadas se escalan a milímetros y el DXF usa `$INSUNITS=4`. Una nota visible `DO NOT SCALE DRAWING` o `NO ESCALAR` genera un aviso de conflicto incluso si existe confirmación.

Los escaneos solo producen preview y revisión manual. No hay OCR ni reconocimiento de contornos ráster. Las curvas PDF se preservan como evidencia vectorial pero no se aproximan silenciosamente en DXF. Todos los resultados PDF quedan `needs_review`; el consumidor decide qué página vectorial enviar a `extract_drawing`.

La ingesta limita bytes, páginas, paths, segmentos, puntos y píxeles de preview. PyMuPDF materializa `get_drawings()` antes de que el adaptador pueda contar su contenido; para documentos hostiles, el despliegue debe complementar estos límites con timeout/memoria del proceso de trabajo.
