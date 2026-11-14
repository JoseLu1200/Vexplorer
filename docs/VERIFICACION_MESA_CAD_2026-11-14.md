# Verificación de mesa y adaptación CAD — 14/11/2026

Este informe corresponde al incremento 0.5 sobre la demo de piezas separadas. El primer checkpoint verificado y subido a `main` es `23b8e01` (código `56f6f96`). El código final revisado es `5241a86`, con dictamen **SHIP de GPT-6 Astra** y sin hallazgos críticos o importantes abiertos. Las comprobaciones siguientes distinguen ejecución real de pruebas simuladas.

Resultado final: **313 pruebas Python, 82 JavaScript, 26 comprobaciones HTTP de geometría/revisión/exportación y 20 peticiones HTTP del ensayo live**, todas correctas. `compileall`, `pip check` y `git diff --check` correctos. Se conserva un aviso conocido de deprecación TestClient/httpx. Astra reprodujo además 31 regresiones focales de visión, runner e ingesta y la suite de frontend.

Merge fast-forward y push final confirmados en `443e9f1`. La demo local se actualizó y verificó en `http://127.0.0.1:8765`, con visión desactivada por defecto. El resultado live ya revisado puede abrirse con `?run=run-4cd41770b1254f2185f01f9a6430086a` en esta instancia; una instalación nueva debe cargar su propio DXF y crear su ejecución.

Evidencias: [API](auditoria/2026-11-14/table-api.json), [programa y embeddings reales](auditoria/2026-11-14/table-live-vector.json), [visión nativa real](auditoria/2026-11-14/table-live-vision.json), [navegador](auditoria/2026-11-14/table-browser.json) y [captura del plano ampliado](auditoria/2026-11-14/table-general-browser.png).

## Recorrido implementado

Entrada: DXF propio con alzado, planta y perfil de una mesa rectangular, cotas parciales y evidencia geométrica de secciones. El runtime recibe el plano y un perfil de tarea explícito; no recibe el despiece reservado. El programa propone bindings `copy/add/subtract`, componentes y reglas versionadas. El evaluador calcula valores, deriva procedencia y comprueba coherencia de dimensiones y colocaciones.

La revisión registra decisiones sobre programa, componentes y premisas y permite aportar valores desconocidos o resolver conflictos con motivo. Las revisiones anteriores y el ledger observado se conservan. Una aceptación no puede convertir una contradicción geométrica en un resultado completado.

Las salidas incluyen vistas generales de los componentes, detalles por tipo de pieza, hoja de despiece por ocurrencias con cotas y espesor, SVG y DXF en mm, reconstrucción esquemática, explicación de fórmulas y una lista de corte CSV genérica. Cantidad y dimensiones no se deducen del número de vistas. Material, acabado, veta y cantos desconocidos siguen identificados como tales.

El coste usa tarifas sintéticas por concepto y contribuciones por componente, con preparación fija catalogada una sola vez. Un concepto desconocido impide presentar el subtotal como total completo. La biblioteca usa el descriptor `furniture-v3`, separado de las versiones de estantería; no se ha medido relevancia empresarial sobre un histórico real.

## Evidencia del primer checkpoint

| Comprobación | Resultado observado |
| --- | --- |
| Python integrado en `56f6f96` | 287 passed, un aviso de deprecación conocido de TestClient/httpx |
| Frontend en el mismo checkpoint | 81 passed |
| `compileall`, `git diff --check` | Correctos |
| Auditoría HTTP con fixtures públicos | 26 comprobaciones, 0 fallos; sin proveedor ni lectura de referencia |
| DXF derivados | Reabiertos con ezdxf, unidades mm y valores de cotas contrastados |
| Wheel del paquete | Construido, instalado en directorio aislado y catálogo JSON cargado desde esa instalación |
| Revisión GPT-6 Astra | SHIP incremental tras reproducir y corregir los hallazgos importantes |
| Git remoto | Fast-forward y push `164356b..23b8e01` a `main` |

Comandos reproducibles desde la raíz:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix frontend
.\.venv\Scripts\python.exe -m compileall -q backend tools
.\.venv\Scripts\python.exe -m tools.audit_table --base-url http://127.0.0.1:8769 --output .runtime/table-api.json
```

El último comando requiere una instancia local de ensayo y crea documentos y revisiones. `tools/audit_table.py` solo utiliza los DXF públicos. La prueba de evaluación congela la salida antes de abrir la referencia privada.

## Proveedor real y navegador

La primera ejecución real de mesa falló porque el esquema estricto generado no marcaba los campos con valores predeterminados como requeridos. Se corrigió la normalización del JSON Schema de Pydantic conforme al [modo estricto de herramientas de OpenAI](https://developers.openai.com/api/docs/guides/function-calling#strict-mode).

La segunda ejecución real de `gpt-6.1-sol` produjo un programa con tapa y soportes laterales, cinco bindings y referencias al ledger. Tardó 12,712 segundos en crear el run. La revisión de ensayo llegó a `completed`, se generaron planos y escena, y `text-embedding-3-small` produjo un embedding de 256 dimensiones que la segunda escritura reutilizó desde caché. No fue replay ni una respuesta prefijada. Esta ejecución precede a algunas correcciones de validación posteriores y no sustituye su repetición final.

La repetición final vectorial también llegó a revisión 2 `completed`. Un ensayo con visión habilitada decidió inicialmente no utilizarla; se registró como vectorial, sin atribuirle una inspección de imágenes. Tras hacer explícita la política de activación —ON exige al menos una vista, OFF permanece vectorial— el run `run-4cd41770b1254f2185f01f9a6430086a` llamó realmente a `visualizar_vista` antes de inspeccionar y proponer. Recibió FRONT con cinco marcas y SHA-256 `3d05e20e5b45ed2a9c0ff805128984c45b3b76adf61f848b6b68f7a20ac6490b`; la creación del run tardó 15,051 segundos. Programa y evaluación terminaron `completed`, sin issues, tras la aceptación de ensayo. El informe conserva metadatos y traza, no secretos ni base64 de imágenes.

Los ensayos de biblioteca generaron embeddings reales y verificaron caché, invariancia de la ficha equivalente y cambio de descriptor al cambiar dimensiones. El ensayo visual final reutilizó esos vectores en caché. No se presenta el coseno ni la agrupación de estos pocos ejemplos como calidad estadística o empresarial acreditada.

```powershell
.\.venv\Scripts\python.exe -m tools.audit_table_live --base-url http://127.0.0.1:8769 --output .runtime/table-live.json --invoke-paid-provider
```

Para exigir evidencia de uso visual en esa auditoría, arrancar el servidor con `OPENAI_VISION_ENABLED=1` y añadir `--require-vision`. Si no hay una llamada nativa visual correcta registrada, la auditoría falla; anunciar la herramienta no basta.

Este comando invoca el proveedor configurado y crea registros de ensayo. Las decisiones de aceptación se atribuyen a un agente auditor, no a un técnico industrial. No lee credenciales ni referencias reservadas; solo llama a la API local.

En navegador se recorrieron carga de DXF, selección y evidencia, revisión 1→2, planos SVG/DXF, tres ocurrencias en 3D y coste parcial explicado. Se corrigieron un solape que interceptaba el botón Abrir, solicitudes de medidas desconocidas no bloqueantes, falta de zoom y pérdida de nitidez al ampliar. El visor ofrece desplazamiento, zoom vectorial y Ampliar/Reducir con Escape. Se comprobaron anchuras CSS de 1042 y 501 px sin desbordamiento; el coordinador también inspeccionó 1140 px.

## Correcciones detectadas durante la integración

- Permutar largo/ancho de la tapa podía aprobar una geometría incompatible con la envolvente: ahora bloquea la finalización.
- El primer refuerzo de esa regla rechazaba todos los programas live sin plantilla: se corrigió derivando la topología desde reglas y roles, con regresión API.
- La evidencia declarada por el modelo podía quedar vacía: el servidor deriva las fuentes transitivas de los bindings.
- IDs repetidos entre categorías confundían decisiones de revisión: se exige un espacio de identificadores disjunto.
- Algunas referencias de cotas generales y de tarifas no existían: ahora resuelven a fuentes y catálogo reales.
- Las explicaciones omitían valores humanos y presentaban cantidades no revisadas como calculadas: ahora usan valores efectivos y distinguen hipótesis.
- Los defectos y decisiones de adaptación de Pablo se detallan en [INTEGRACION_CAD_HARNESS](INTEGRACION_CAD_HARNESS.md).

## Límites

El perfil admite tapa y dos soportes laterales o cuatro patas, no muebles arbitrarios. Las salidas son revisables y esquemáticas, sin uniones, holguras industriales, herrajes, certificación estructural ni optimización de corte. Los costes sintéticos no son un presupuesto empresarial ni un precio de venta.

Las curvas ELLIPSE/SPLINE se representan como aproximaciones visuales declaradas; no aportan medidas exactas de paneles. HATCH, segmentos bulge y paperspace permanecen fuera del lector admitido. La recuperación de DXF exige revisión y no garantiza reparar cualquier archivo dañado. El catálogo de taller no confirmado no acredita compatibilidad con Sistema 32.

La visión opcional y las ampliaciones CAD descritas están integradas y verificadas en el segundo incremento, con las exclusiones anteriores. El primer checkpoint permanece identificado como histórico. No hay despliegue al VPS, datos externos publicados ni replay habilitado.
