# Datasets de muebles: descarga directa desde GitHub

Todos los enlaces siguientes apuntan a archivos de una [Release del repositorio](https://github.com/JoseLu1200/Vexplorer/releases/tag/datasets-demo-2026-11-14). No necesitan HF, sus herramientas ni sus tokens. Los archivos grandes viven como assets de Release; los manifiestos, datos normalizados y documentación se conservan en Git.

| Paquete | Contenido | Uso |
|---|---|---|
| [Demo procesada](https://github.com/JoseLu1200/Vexplorer/releases/download/datasets-demo-2026-11-14/vexplorer-demo-procesada.zip) | Backup nativo de 4 runs, planos, revisiones, despieces, escenas, explicaciones, costes sintéticos, biblioteca geométrica y 19 registros publicados; exports y documentación | Restaurar en la web app, sin modelo ni reprocesamiento; [guía](DEMO_DATOS_PROCESADOS.md) |
| [PlankAssembly original](https://github.com/JoseLu1200/Vexplorer/releases/download/datasets-demo-2026-11-14/plankassembly-original.zip) | ZIP original sin modificar, 26.707 modelos en splits oficiales y 985 JSON adicionales; 19.607.117 bytes | Programas de forma de muebles en mm; **no** es un backup de Vexplorer ni contiene DXF o resultados procesados |
| [Mobiliario: costes publicados](https://github.com/JoseLu1200/Vexplorer/releases/download/datasets-demo-2026-11-14/furniture-costs-published.zip) | 4 productos, presupuesto y ventas separados, import JSON, CSV, PDF/XML original y atribución | Datos académicos `published`; el presupuesto no es coste real cerrado |
| [Mobiliario: tiempos publicados](https://github.com/JoseLu1200/Vexplorer/releases/download/datasets-demo-2026-11-14/furniture-hours-published.zip) | 15 productos, coeficientes de tiempo, import JSON, CSV, PDF/XML original y atribución | Horas/coeficientes publicados; sin inventar dimensiones, material o costes |

Descargar también [SHA256SUMS.txt](https://github.com/JoseLu1200/Vexplorer/releases/download/datasets-demo-2026-11-14/SHA256SUMS.txt) y [las atribuciones/licencias](../data/datasets/LICENSES.md). El [índice verificable](https://github.com/JoseLu1200/Vexplorer/blob/main/data/datasets/downloads.json) fija nombres, tamaños y hashes.

```powershell
curl.exe -L --fail -o vexplorer-demo-procesada.zip https://github.com/JoseLu1200/Vexplorer/releases/download/datasets-demo-2026-11-14/vexplorer-demo-procesada.zip
Get-FileHash .\vexplorer-demo-procesada.zip -Algorithm SHA256
Expand-Archive .\vexplorer-demo-procesada.zip -DestinationPath .\demo-descargada
```

En Linux, `curl -L --fail -O URL` descarga cada archivo y `sha256sum -c SHA256SUMS.txt --ignore-missing` verifica los presentes. Comparar siempre con el manifiesto publicado.

## Datos normalizados ya en el repo

- [Costes: JSON importable](../data/datasets/furniture_costs/historical_import.json), [CSV](../data/datasets/furniture_costs/production_budget.csv) y [alcance](../data/datasets/furniture_costs/README.md).
- [Tiempos: JSON importable](../data/datasets/furniture_hours/historical_import.json), [CSV](../data/datasets/furniture_hours/published_hours.csv) y [alcance](../data/datasets/furniture_hours/README.md).

Estos 19 registros **ya están importados en el backup de demo**. Para otro entorno privado, los JSON conservan el contrato `HistoricalImport` del endpoint existente `POST /api/v1/history/import/json`; puede validarse primero con `?dry_run=true`. No son planos y no se cargan por «Cargar plano». No enviarlos al histórico de producción sin seleccionar expresamente ese destino.

## PlankAssembly y procedencia

El espejo conserva exactamente el ZIP de la revisión `d1d4308f0ee0aac2f9f407b3533ff83ecee22d34`; no requiere descargar desde el Hub. [Auditoría del dataset](PLANKASSEMBLY.md). También existe una [descarga directa del publicador](https://manycore-research-azure.kujiale.com/manycore-research/PlankAssembly/data.zip).

PlankAssembly está bajo **CC BY-NC-ND 4.0**: conservar atribución, uso no comercial y no redistribuir adaptaciones. Por eso se ofrece el original, no los DXF/renders derivados locales. Los datasets de costes/tiempos están bajo **CC BY 4.0**, con PDF/XML y atribuciones en sus ZIP. Ver [LICENSES.md](../data/datasets/LICENSES.md). Las restricciones del original no se eliminan al alojarlo en GitHub.
