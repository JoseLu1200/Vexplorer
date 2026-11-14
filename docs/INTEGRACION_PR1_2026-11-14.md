# Integración revisada de PR1

PR: [JoseLu1200/Vexplorer#1](https://github.com/JoseLu1200/Vexplorer/pull/1), rama `mejoras/cad-harness`, head revisado `0fe4be77847f93248ed18f01e9940e53fda8baf9`. Ancestro común `dab7ce5`; main al comenzar `10da225`; incremento privado preservado en `056ec71`.

Los 14 commits se contrastaron con la implementación actual. Los dos primeros bloques ya tenían adaptaciones; aplicar sus archivos completos habría eliminado contratos de mesa, límites de ingesta y revisiones posteriores. El árbol integrado conserva esas adaptaciones e incorpora las mejoras nuevas con regresiones. El merge conserva ambos historiales y el árbol revisado, sin reintroducir las implementaciones antiguas.

| Commit de PR1 | Resolución |
|---|---|
| `e201506` | Vistas inequívocas y linetype ya adoptados. Se conserva el detector de espesor corregido y la representación de cantos sin duplicación. |
| `2cb606c` | Contexto acotado y errores reparables ya adoptados; se conserva el runner actual. |
| `1d4b747` | Lista de corte genérica ya ligada a revisión; no se recupera metraje de canto duplicable. |
| `2db9092` | Registro histórico conservado en el historial; esta matriz documenta la integración vigente. |
| `ccbad2a` | Bloques, atributos, curvas, ordenadas y recuperación ya adaptados con límites tempranos y comprobaciones Z/OCS. |
| `c0d9db5` | Taladros exactos y revisión por aproximaciones ya adoptados; se mejora su asociación como evidencia neutral. |
| `7bb29ae` | Plausibilidad conservadora con catálogo no confirmado como desconocido; se añade contraste de cotas con geometría. |
| `26dbd15` | Paginación, tokens y visión optativa ya adaptados; se conserva el proveedor acotado actual. |
| `d29fec7` | Registro histórico del segundo bloque; decisiones vigentes en esta matriz. |
| `9ebaef0` | Paperspace distingue anotaciones y cotas; comparte presupuesto global incluso en bloques anidados. No transforma esas cotas a modelspace. |
| `dfefb4b` | Union-find determinista, curvas asociadas por región y evidencia neutral de taladros/líneas ocultas. |
| `43a238f` | Cotas contrastadas con segmentos y curvas reales. Corregido el falso pase por una coordenada de un vértice ajeno. |
| `5c7dbd8` | Replay adaptado a SQLite, acceso privado, jobs y los tres runners; comparación estricta de dos candidatas de la misma revisión. |
| `0fe4be7` | Extra `dev` con ruff. Se conserva el package-data vigente `*.json`, que ya incluye el catálogo. |

## Replay y comparación

Una ejecución live válida puede dejar una grabación autoritativa en el servidor, limitada en cantidad y bytes. El replay exige coincidencia del documento, ledger, configuración generativa, prompt, schemas, herramientas y registro; también valida transcript, outputs y, cuando procede, hashes de visión. Reejecuta las herramientas deterministas y rechaza divergencias. No acepta grabaciones ni identificadores de grabación proporcionados por el cliente.

La UI consulta disponibilidad exacta y rotula la reproducción offline con run live, actor, modelo y procedencia. El replay no importa decisiones humanas ni convierte propuestas en confirmaciones. `comparar_candidatas` exige exactamente dos IDs distintos anunciados para el flujo y revisión vigentes; no calcula con números propuestos por el modelo.

## Regresiones y revisión

El bloque CAD pasó 83 pruebas focales; la agrupación de 25.000 líneas desconectadas tardó 0,024–0,032 segundos en tres ejecuciones locales con idéntico orden. El bloque replay pasó 51 pruebas focales que incluyen los tres runners, visión, jobs privados, alteración de grabaciones y cuotas. Estos números son verificaciones de desarrollo, no medidas de precisión industrial.

Astra detectó y motivó correcciones adicionales: rechazo de tarifas asignadas a componentes inexistentes; rechazo de catálogos vacíos; preservación del enlace a un run ante fallos de red/proxy; unicidad de identificadores de confirmación; y trabajo scrypt equivalente para usuarios existentes e inexistentes. La verificación integrada y el dictamen final se registran en la aceptación del incremento privado.

Se mantienen fuera del subconjunto exacto HATCH, bulges y ARC con OCS Z negativo. Taladros, líneas ocultas y Sistema 32 no confirman roles, cantidades o uniones. Los planos derivados conservan procedencia completa en metadatos SVG/XDATA DXF y muestran un resumen legible en la hoja.
