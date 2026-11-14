# Agente de IA de integración semántica

## Identidad y autorización

El usuario autorizó explícitamente esta identidad, la creación de este archivo y el alcance de búsqueda, visualizador, documentación y pruebas el 2026-11-14. Trabajo en `feat/semantic-explorer`, worktree `semantic-explorer`, desde `83df72d`.

## Alcance y coordinación

- Integración aditiva del explorador semántico, su API, frontend, herramientas de publicación y pruebas; actualización de decisión/diseño e investigación documental.
- Los cambios sin commit del checkout raíz, la evaluación en curso y los registros personales ajenos quedan fuera de esta reserva.
- La integración toca mínimamente `main.py` (reserva liberada en el registro de integración integral) e `index.html`; los módulos nuevos se mantienen separados del trabajo UX concurrente.
- No cambiar `backend/app/contratos/`, modelos de inferencia ni cálculo económico. Los modelos nuevos del explorador vivirán en su propio módulo Pydantic, sin redefinir contratos existentes.
- No atribuir al incremento las 510 pruebas, CI o revisión Astra de `dbd1bb6`: requiere verificación propia.

## Estado

Implementación del piloto, documentación y verificación completadas; entrega conservada en la rama local `feat/semantic-explorer`. El usuario amplió el alcance a los modelos y arquitecturas ensayados con mayor aporte por coste, delegando la selección. Remoto consultado: main `dbd1bb6`, integración `83df72d`. No se ha desplegado, fusionado ni publicado este incremento en remoto.

Se leyeron los 112 Markdown versionados de la base, incluidos transcripción, contratos, planes y equipo; se contrastaron 38 ramas locales y ocho refs remotas. El [inventario con hashes](../docs/semantic-lab/INVENTARIO_DOCUMENTAL.md) fija qué se investigó. [Diseño y trazabilidad](../docs/semantic-lab/INTEGRACION_EXPLORADOR.md), [operación](../docs/semantic-lab/OPERACION_EXPLORADOR.md).

Entregado: mapa PCA y lista/teclado, recuperación exacta por coseno, biblioteca vigente, renders, comparación de representaciones, clasificación cacheada kNN/logística, Jev opcional con presupuesto durable, importación portable, preparación offline de DXF y releases con activación/rollback/retirada. La reproducción de clasificadores usa solo train con recetas fijas y exporta Pydantic/JSON v2; no carga Joblib legado ni abre otra evaluación sobre test.

Dependencias/avisos: NumPy pasa a runtime; el contenedor incluye los nuevos estáticos; backup incorpora `semantic_explorer.sqlite3`. Los cambios en `main.py`, `index.html` y backup son aditivos. No se modifican contratos compartidos ni cálculo económico. La integración posterior deberá conciliar el enlace con la UX concurrente del checkout raíz.

## Verificación

Base integrada: 683 pruebas Python en 85,41 s y 147 JavaScript. Incremento: tests focales observados primero en rojo y después en verde para coseno, PCA, hashes, identidad, retirada/rollback, clasificación, autenticación, presupuesto externo y backup.

Revisión independiente de GPT-6 Astra: cuatro hallazgos importantes comprobados y corregidos con regresiones: identidad encoder/features del clasificador, rutas fuera del corpus, redondeo antes de ordenar vecinos y caché PCA sin validación. Además se cubrieron activación concurrente y respuestas tardías de la UI. No se atribuye a este árbol la aprobación Astra ni el CI de `dbd1bb6`; esta revisión produjo hallazgos y las correcciones se verificaron localmente.

Pruebas del árbol del incremento:

- `python -m pytest -q`: 721 aprobadas en 458,63 s (7 min 38 s), con los contratos Pydantic y la copia transaccional de renders finales. La pasada previa de 720 había tardado 70,88 s; hubo contención del equipo durante la repetición final.
- `npm test --prefix frontend`: 151 aprobadas, cero fallos.
- `python -m ruff check` sobre todos los módulos/tests nuevos: aprobado. `compileall` focal y `git diff --check`: aprobados. Los 252 enlaces locales de los Markdown modificados/nuevos resuelven a archivos existentes.
- Playwright/Chromium con embeddings reales: selección, diez vecinos, clasificación kNN, comparación EG2/DINO, filtros, zoom, teclado, exportación JSON, escritorio y móvil 390 px sin desbordamiento; recorrido aprobado sin errores de consola ni solicitudes fallidas. Respuestas lentas, comparación desactivada hasta recibir ranking, limpieza de estados vacíos y montaje real bajo `/vexplorer/`: aprobados. La repetición visual final posterior a la suite pasó sin errores de consola ni peticiones fallidas; se verificó también la carga del primer render de vecinos. Se amplió la espera del harness a 90 s por contención del equipo, sin acreditar un SLO de latencia.
- Los dobles de proveedor se limitan a la frontera HTTP Jev y a los casos de biblioteca de prueba. No se ejecutó Jev pagado.

Datos locales fuera de Git: ocho espacios de 117 planos (EG2 texto/imagen/mixto 256/768, DINOv3 y MiniLM) y un espacio CAD adicional de 373. NPZ preexistentes conservados byte a byte en la copia portable; renders e inputs verificados por hash. kNN reproducido sobre 82 train; logística C=0,1 sobre 262 train. Sin métricas nuevas de calidad ni referencias privadas abiertas.

Artefactos de QA: `.runtime/semantic-explorer-qa/` contiene logs, capturas escritorio/móvil, exportación y SQLite local. Los corpus portables y clasificadores numéricos están en `D:/Vexplorer-semantic-lab/explorer-portable-20261114/`; no se incluyen planos, pesos ni bases en Git.

Límites observados: el primer intento de nueva inferencia EG2 falló por error Windows 1455 (paginación insuficiente, C con unos 236 MiB libres). Un recorrido HTTP también encontró `MemoryError` transitorio; al repetirlo con más recursos pasó. No se cambió la paginación ni se eliminaron archivos/procesos ajenos. El segundo intento finalizó correctamente con pesos locales: dos DXF demo identificados como sintéticos, EG2 mixto 768d, `cache_status=miss`, 6,63 s de codificación (no incluye carga de pesos). El NPZ tiene SHA256 `aa204f37a7d110297b283d7686193b1dd6a2c0373f56d972b1d5f5791ea03aeb`. Publicados con clasificación kNN en `pilot-eg2-demo`: 119 entradas, release `d39469752d745212afa91ec2c5f05f594a34e97ec37f1ecca2cd5b5f97d07aa9`. Ambos recuperan diez vecinos por HTTP, incluidos planos CAD del catálogo. Esta es una prueba funcional, no una validación de relevancia. Al ampliar se detectó lectura redundante de cada render; se sustituyó por una transacción única y se comprobó hash, retirada y versión con regresión. La aceptación de carga y la calibración industrial siguen pendientes. Docker se verificó por archivos/dependencias, sin construir otra imagen en este equipo limitado.
