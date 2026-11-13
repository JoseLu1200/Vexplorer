# Geometría y lectura de planos

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

Estado: especificación futura, propuesta de contrato `0.1.0` pendiente de acuerdo explícito A/B y aviso a C. Los modelos Pydantic de `backend/app/contratos/` serán la única autoridad del formato; el Markdown no constituye un esquema implementado. No existe aquí un lector de producción ni se han ejecutado pruebas de producto. El corpus mecánico auxiliar `engineering-drawings-harness.zip` está auditado en [DATASET.md](DATASET.md); [PlankAssembly](PLANKASSEMBLY.md) añade referencias de mobiliario cuya preparación 2D sigue pendiente. La propuesta de datos está en [CONTRATOS_DATOS.md](CONTRATOS_DATOS.md), la interpretación en [SEMANTICA.md](SEMANTICA.md) y los controles en [VALIDACION.md](VALIDACION.md).

## Alcance y entrada

P0 propone extracción DXF lineal y rectangular, y despiece de mobiliario formado por paneles planos rectangulares mediante fixtures propios revisados. Los casos mecánicos seleccionados prueban extracción, no semántica de muebles. PDF no es entrada actual: Bench Vise es un piloto P1 pendiente. STEP solo será oráculo separado y oculto al agente en el modo de evaluación 2D. Se procesará modelspace. Paper space, perspectivas, escaneos, muebles curvos, ensambles complejos y fabricación CNC quedan fuera de P0. Su presencia se registrará como limitación con evidencia, sin fingir una lectura completa. DWG será P1 salvo que el conversor ODA externo esté instalado y verificado en la puerta de primera hora definida en [PLAN.md](../PLAN.md). Sin conversor se devolverá `conversion_unavailable` y se permitirá exportar DXF desde el CAD de origen.

Se conservarán original, ambos hashes y manifiesto de conversión: herramienta/versión, argumentos permitidos, salida, tiempos y advertencias. Los límites iniciales serán `max_upload_bytes=20971520`, `max_entities=100000`, `ingest_timeout_s=60` y `oda_timeout_s=30`, incluido este último en ingestión. Un límite agotado produce un estado explícito; no una extracción parcial presentada como completa.

| Entidad | Tratamiento previsto en P0 |
|---|---|
| `LINE` | Segmentos del contorno, previa comprobación de plano y coordenadas. |
| `LWPOLYLINE` | Segmentos rectos; `bulge` distinto de cero se señala como geometría no soportada para el contorno rectangular. |
| `CIRCLE`, `ARC` | Observaciones de anotaciones o características cuando se puedan interpretar; no reconstrucción general de paneles curvos. |
| `TEXT`, `MTEXT` | Evidencia textual vinculada espacialmente; nunca instrucciones ejecutables. |
| `DIMENSION` | Cotas tipadas y evidencia de su representación; no asumir que todo valor es una longitud. |
| `INSERT` | Expansión trazable con transformación uniforme positiva y compatible con el plano. |
| Otras entidades | Inventario, ubicación y motivo de no soporte; no descarte silencioso. |

## Corpus actual: evidencia y límites

El paquete contiene 14 DXF, 14 DWG y 14 STEP Orla de componentes mecánicos aislados, junto a 51 paquetes de conjuntos PDF: 50 Julius de Waal y uno Bench Vise. Son 74 PDF físicos al incluir detalles y representaciones Orla; no 74 conjuntos. Los 14 DXF se abrieron con `ezdxf.readzip`. DWG solo se inspeccionó por encabezado; STEP por texto, sin comprobación mediante kernel. No son ensayos del producto. La procedencia industrial o sintética no queda demostrada por el campo `origin=provided_step` ni por los headers de exportación.

Tres DXF declaran mm (`$INSUNITS=4`) y once carecen de unidad declarada (`0`). Hay 370 `DIMENSION` y cuatro `ARC_DIMENSION`; el cotejo por handle cubre las 370 primeras en `dimensions.json`, pero no las cuatro de arco. Los sidecars contienen además estilos: sus 419 registros no son 419 cotas. Catorce de las 370 cotas declaran grados y no deben convertirse a mm. Cincuenta tienen texto sobrescrito. Los JSON son derivados del CAD, no referencias semánticas independientes.

La colección incluye vistas, bloques, layouts, curvas y grafismo de anotación. Inventariar su soporte antes de seleccionar casos; un dibujo mecánico no demuestra paneles rectangulares ni despiece de un conjunto. Los fixtures propios de mobiliario tendrán ocurrencias, BOM y medidas revisadas manualmente. El inventario, referencias y condiciones completos se conservan en [DATASET.md](DATASET.md).

## Normalización de unidades y coordenadas

Las coordenadas DXF no incorporan una unidad individual. La documentación de ezdxf distingue el contexto de unidades de documento, bloques y layouts; `$INSUNITS` corresponde al documento/modelspace. El formato visual de números no determina su unidad física. Fuente: [ezdxf, DXF Units](https://ezdxf.readthedocs.io/en/stable/concepts/units.html).

El servicio leerá la declaración de unidades, conservará su valor bruto y resolverá un factor `s` hacia milímetros. Para pulgadas, `s=25.4`; una distancia fuente de `10` equivale a `254 mm`. Si faltan unidades o existen declaraciones incompatibles, no se asignará milímetros por defecto: las magnitudes físicas permanecerán sin resolver y el resultado requerirá `needs_review`. La geometría podrá visualizarse en coordenadas fuente, etiquetadas como tales. Un override de unidad solo procederá de configuración explícitamente confirmada por el usuario, formará parte de la huella de ejecución y generará una nueva ejecución/revisión.

Se conservarán puntos originales y matrices compuestas. Primero se resolverá el sistema local de entidad, después cada transformación de bloque y finalmente la conversión de unidad del documento. `LINE` expresa sus extremos en WCS; `LWPOLYLINE` almacena vértices en OCS y puede tener elevación. No se mezclarán sus coordenadas brutas directamente. Fuentes: [LINE](https://ezdxf.readthedocs.io/en/stable/dxfentities/line.html) y [LWPOLYLINE](https://ezdxf.readthedocs.io/en/stable/dxfentities/lwpolyline.html).

Las unidades de un bloque no autorizan a aplicar una conversión adicional a ciegas: el DXF utiliza la escala de `INSERT` explícitamente y ezdxf no incorpora una conversión implícita entre unidades de bloque y documento. Se comprobará la coherencia declarada y se señalarán discrepancias; multiplicar dos veces la escala produciría medidas falsas. Las reflexiones y escalas no uniformes quedan fuera de P0.

## Bloques, procedencia e identidad

Cada `SourceEntity` se identificará mediante hash de documento, layout, handle e `insert_path`. Dos inserciones del mismo bloque comparten handles internos y son ocurrencias distintas. La ruta incluirá cada inserción anidada; si se soportan matrices de inserción se incluirá también su ocurrencia. Se detectarán referencias cíclicas o ausentes y se limitará su expansión conforme al presupuesto de entidades.

Se inspeccionarán copias. Las entidades virtuales carecen de handle propio; la procedencia se capturará antes de expandir. `virtual_entities()` tampoco resuelve por sí solo todas las ocurrencias de `MINSERT` e ignora clipping `XCLIP`. P0 deberá detectar estos casos y marcarlos, sin interpretar contenido oculto como parte confirmada. Fuente: [ezdxf, INSERT](https://ezdxf.readthedocs.io/en/stable/blocks/insert.html).

Las claves fuente quedarán congeladas para `candidate_revision`. Los IDs serán estables para entrada, configuración y revisión de pipeline, sin garantía entre cambios CAD.

## Extracción determinista de contornos

El módulo futuro `backend/app/geometria/contornos.py` seguirá esta secuencia:

1. Separar geometría de pieza, anotaciones y representación gráfica de cotas. Las líneas del bloque gráfico de una cota no generarán nuevos tableros.
2. Transformar entidades soportadas al marco de trabajo de cada vista. Rechazar la suposición de planaridad cuando sus residuos no sean compatibles con la tolerancia configurada.
3. Crear segmentos con procedencia. Colapsar duplicados solo en la representación de trabajo, conservando la unión de referencias fuente. Dos líneas coincidentes no prueban dos piezas.
4. Agrupar extremos cercanos e intersecciones compatibles en un grafo. Registrar cualquier unión aproximada; no cerrar huecos grandes ni ajustar el dibujo silenciosamente.
5. Buscar ciclos simples cerrados, eliminar segmentos colineales intermedios y detectar auto-intersecciones. Un rectángulo aceptable tendrá cuatro lados efectivos, lados opuestos paralelos, adyacentes perpendiculares y longitudes positivas.
6. Medir en los ejes locales del rectángulo. Su caja alineada con X/Y de pantalla no representa sus dimensiones si está girado. Generar mediciones y evidencia del contorno, sin asignar todavía un rol de mueble.

La comparación numérica usará los valores de [VALIDACION.md](VALIDACION.md), después de resolver unidades y marcos. Las tolerancias de detección se registrarán en configuración; cualquier criterio angular adicional deberá tener nombre y versión, sin reutilizar un valor en milímetros como ángulo. Un ciclo anidado puede ser hueco, detalle o proyección; su clasificación se mantendrá abierta si no hay evidencia.

## Cotas y texto sobreescrito

Para una cota lineal soportada se conservarán puntos de definición, dirección, estilo, factores aplicables, texto bruto y medición geométrica. `get_measurement()` entrega la medición lineal en unidades WCS sin escala aplicada; cotas angulares u ordenadas tienen otros tipos de retorno. `actual_measurement` puede faltar. En `dxf.text`, vacío o `<>` representa el valor calculado; un espacio suprime texto y otro contenido puede sobreescribirlo. Fuente: [ezdxf, DIMENSION](https://ezdxf.readthedocs.io/en/stable/dxfentities/dimension.html).

El caso real `drawing_1b79629adc20354daa449a9a`, handle `5319`, distingue `get_measurement()≈67`, `actual_measurement` y `raw_measurement≈44.6666666667`, factor `2/3` y texto mostrado `45`. No presuponer que `raw_measurement` es longitud geométrica ni volver a aplicar la escala al valor ya almacenado. Conservar los campos separados y contrastar tipo, estilo y marco antes de resolver una longitud. En cotas angulares conservar grados; no usar `value_mm` para representarlas ni aplicar tolerancia en mm.

El parser numérico será restrictivo: unidad reconocida, separador decimal documentado y sin evaluar expresiones. «600 aprox.» será evidencia textual, no un número verificado. La cota se asociará a un segmento o par de extremos mediante marco, orientación y puntos de extensión; la proximidad del rótulo por sí sola no basta.

Si un contorno mide `598 mm` y el texto sobreescrito indica `600`, se crearán mediciones separadas con evidencia y `status=conflict` cuando sean incompatibles. No se cambiará el contorno ni se reemplazará una medición existente. El agente podrá mostrar el conflicto; no resolverlo inventando una media. Tampoco se leerá el grosor de trazo o la altura del texto como espesor de tablero.

## Vistas y salida geométrica

`backend/app/geometria/vistas.py` propondrá agrupaciones espaciales usando regiones, orientación, capas y rótulos, conservando alternativas si la segmentación no es inequívoca. Una `Observation` contiene `view_id` y `contour_ids`; no representa por sí misma una pieza física. Tres vistas ortográficas pueden describir una misma ocurrencia. La asociación de vistas y las cantidades se decidirán como se especifica en [SEMANTICA.md](SEMANTICA.md).

La salida será un ledger de entidades, evidencia, mediciones, observaciones y candidatos. Las rutas son futuras. [TEST_PLAN.md](TEST_PLAN.md) describe pruebas y fixtures sintéticos aún no ejecutados.

## Vistas derivadas de PlankAssembly

La [auditoría](PLANKASSEMBLY.md) confirma coordenadas fuente en mm y una primera fila de `planks` que representa la envolvente global. El futuro generador debe proyectar los tableros posteriores, conservar asociaciones mediante un mapeo explícito y registrar cada transformación. El código oficial normaliza coordenadas al renderizar: una unidad SVG no equivale automáticamente a un milímetro.

Distinguir líneas visibles y ocultas; proyectar todos los rectángulos de cada tablero sin resolver visibilidad puede revelar componentes que el plano pobre no mostraría. Los IDs, colores o capas por pieza también pueden filtrar la respuesta. La exportación DXF, las cotas generales y la escala necesitan comprobación independiente. No se han generado esas vistas ni verificado su apertura en FreeCAD. La geometría referida a cuboides no incluye mecanizados o tolerancias industriales.
