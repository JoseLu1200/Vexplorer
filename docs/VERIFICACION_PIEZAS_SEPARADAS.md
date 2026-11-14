# Verificación del recorrido desde piezas separadas

Fecha: 14/11/2026. Hito 0.4 integrado en `feat/parts-integration`. Entrada confirmada: **DXF 2D con vistas de piezas separadas**, sin dibujo del conjunto ni modelo 3D. La [auditoría anterior](AUDITORIA_APP_2026-11-14.md) conserva la evidencia de `dab7ce5`.

Revisión final del agente GPT-6 Astra: **SHIP**, código `cbc549a`; [dictamen y correcciones](REVISION_FINAL_PIEZAS_2026-11-14.md).

## Implementado y comprobado

| Componente | Comportamiento observado |
|---|---|
| Ingesta | Nueve vistas, tres observaciones K1/K2/K3 y cantidad 2 por observación: seis ejemplares |
| Medidas | K1: 1200 × 300 × 18 mm; K2/K3: 864 × 300 × 18 mm, con evidencias y estados |
| Asociación | Claves visibles `PART <clave> FRONT/TOP/SIDE`; cantidad `QTY <clave> <n>`. No agrupa contornos sin asociación suficiente |
| Propuestas | Dos asignaciones compatibles de K2/K3 a tapa/base o baldas; familia y roles hipotéticos |
| Revisión | Candidato, autor, motivo, material/acabado y faltantes; versión nueva con control de revisión base |
| Derivación | Ancho montado `864 + 18 + 18 = 900 mm`, con operandos referenciados; alto 1200 y fondo 300 |
| Escena | Seis ejemplares tras revisión; órbita, selección y separación visual. Alturas de baldas esquemáticas; colisiones no evaluadas |
| Incógnitas | Cantidad/espesor ausentes conservados como `null`. Asociación ambigua conserva el plano sin forzar montaje |
| Biblioteca | Descriptor `furniture-v2`, perfil canónico de piezas y estados. No mezcla espacios v1/v2 |
| Embeddings | Proveedor real `text-embedding-3-small`, 256 dimensiones: invariancia a claves/traslación, sensibilidad a espesor con igual envolvente y caché |
| Harness live | Ejecución real `gpt-6.1-sol`: tres llamadas a `inspeccionar_pieza` y una a `entregar_candidato_montaje`; propuesta pendiente de revisión |
| Economía | Comparables sintéticos; material `1,7568 m² × 50 EUR/m² = 87,84 EUR` + preparación `40 EUR` = `127,84 EUR`, sin duplicar conceptos |
| Salida | JSON/CSV revisables y traza de revisión, estimación y biblioteca; observaciones separadas de confirmaciones |

El harness recibe el ledger estructurado permitido y candidatos deterministas; **no recibe imágenes ni genera muebles libremente**. El 3D muestra una solución revisada dentro del alcance, no prueba que sea el montaje original único.

## Evidencia reproducible

- [API real](auditoria/2026-11-14/parts-api.json), producida por [audit_parts.py](../tools/audit_parts.py), sin proveedor ni referencias privadas.
- [Proveedor y embeddings reales](auditoria/2026-11-14/parts-live.json), producidos por [audit_live.py](../tools/audit_live.py). No publica vectores ni credenciales.
- [Plano 2D seleccionado](auditoria/2026-11-14/parts-browser-2d.png), captura real de Chrome sin modificar la imagen.
- [Registro de navegador](auditoria/2026-11-14/parts-browser.json) y [captura 3D](auditoria/2026-11-14/parts-browser-3d.png). Incluye revisión posterior de cantidad 2 → 3, siete ejemplares y recálculo a 140,80 EUR.
- Suites integradas: **188 pruebas Python y 66 JavaScript pasan**; auditoría HTTP: **58 pasan, ninguna falla**. `compileall` correcto. Python emite una advertencia de deprecación Starlette/httpx, sin fallos.
- Nueva ejecución real del proveedor sobre el código integrado: 22 solicitudes HTTP correctas; tres embeddings generados y dos accesos a caché. Las tres aserciones de invariancia, sensibilidad al espesor y herramientas live pasan.

Comandos sobre la aplicación arrancada:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test --prefix frontend
.\.venv\Scripts\python.exe -m compileall -q backend tools
.\.venv\Scripts\python.exe tools/audit_parts.py --base-url http://127.0.0.1:8765 --output .runtime/parts-api.json
```

La comprobación live tiene coste de proveedor y requiere la clave local:

```powershell
.\.venv\Scripts\python.exe tools/audit_live.py --base-url http://127.0.0.1:8765 --output .runtime/parts-live.json --invoke-paid-provider --input-kind separated_part_views
```

## Defectos encontrados durante la integración

La primera auditoría HTTP registró 43 comprobaciones correctas y una fallida: completar una cantidad desconocida dejaba una escena lista con dos ejemplares omitidos. Se corrigió la reconstrucción por cantidad efectiva. Otra pasada detectó que el espesor confirmado no recalculaba el ancho del montaje: ahora se recalcula el candidato seleccionado con referencias a piezas de esa revisión, conservando el ledger y versiones anteriores. La auditoría final verifica ambas correcciones.

También se corrigieron el descriptor tras completar incógnitas, la pérdida de vistas sin asociar en entradas mixtas y las decisiones que contradicen dimensiones, cantidades observadas o roles del candidato. Las revisiones posteriores del mismo candidato conservan los datos humanos que no se modifican.

En navegador se corrigieron encuadre, etiquetas cortadas, alternativas indistinguibles, ausencia de fórmulas, premisas 3D que desbordaban la barra, ocultación del modo actual y cabecera en pantallas estrechas. La selección del agente y la humana permanecen separadas.

## Límites y pendientes

- Familia acotada a estantería rectangular de tableros. No reconoce cualquier mueble, formato o plano sin etiquetas; no acredita clasificación general ni comprensión visual directa.
- Sin unidades, asociación o medidas suficientes se conserva incertidumbre. No hay fabricación automática, resistencia, uniones ni validación de colisiones.
- Completar una dimensión no garantiza resolver todas las relaciones montadas; los faltantes restantes conservan `needs_review`.
- Cambiar dimensiones/cantidades ya observadas que las contradiga requiere corregir la entrada; dividir/unir libremente componentes sigue pendiente.
- Biblioteca sintética de desarrollo sin medida de relevancia empresarial. Costes verifican aritmética, no precisión económica; horas y operaciones industriales desconocidas.
- Idempotencia y enlaces históricos a una revisión exacta, hallados en baseline, no forman parte de las correcciones acreditadas aquí.
- `recorded_replay` deshabilitado. Sin publicación de PlankAssembly ni derivados; sin despliegue al VPS.
- La mesa desde vistas montadas, los planos acotados derivados y el coste por pieza son la siguiente ampliación solicitada; no se cuentan como capacidad de este hito.
