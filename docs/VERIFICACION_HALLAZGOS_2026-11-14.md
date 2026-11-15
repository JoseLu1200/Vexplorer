# Correcciones de auditoría y recuperación de proyectos

Estado: implementación, revisión agregada Astra y verificación integrada terminadas, sin hallazgos P1/P2 abiertos. El usuario autorizó después guardar y publicar todos los cambios en `main`; esa publicación Git no implica despliegue del servicio.

Base inspeccionada: `b2bc33d`, rama `data/offline-pipeline-demo`. Seis implementadores GPT-6.1 Sol y revisión independiente GPT-6 Astra, autorizados explícitamente por el usuario. [Plan](superpowers/plans/2026-11-14-hallazgos.md) y [coordinación](../team/agente_hallazgos_coordinacion.md).

## Alcance

1. Terminar el middleware JSON al desconectarse el cliente y conservar la señal de desconexión tras entregar el cuerpo.
2. Autorizar proyectos, resultados y artefactos por propietario, también cuando el identificador llega en el cuerpo o mediante un job derivado.
3. Migrar el runtime semántico a EmbeddingGemma 2 con snapshot fijado y espacios incompatibles aislados.
4. Ofrecer el explorador sólo según capacidad real y explicar su configuración.
5. Mantener sesión y navegación funcionales sin localStorage.
6. Cancelación cooperativa, concurrencia acotada y posición en cola.
7. Proyectos y ejecuciones recientes, protección de revisiones sin guardar, recorrido real de navegador en CI y protocolo de evaluación con técnicos.

## Límites de producto

El modo local/anónimo sigue siendo una instancia compartida. El aislamiento por propietario requiere autenticación individual. La Biblioteca es un catálogo publicado explícitamente; compartir una ficha no concede acceso al documento fuente ni a resultados privados. Los propietarios ambiguos de datos antiguos no se asignan arbitrariamente a un usuario.

Cancelar no revierte fases ya persistidas ni mata una petición HTTP externa ya iniciada. Se impiden las llamadas y fases posteriores cuando se observa la solicitud de cancelación. El estado durable distingue cancelación de éxito.

El runtime textual de EmbeddingGemma 2 y el espacio mixto del explorador tienen identidades distintas. No se mezclan entre sí ni con cachés OpenAI. La ausencia del snapshot o dependencias debe mostrarse como indisponibilidad, conservando las rutas geométricas.

No hay sesiones observadas de técnicos ni órdenes de fabricación de empresa en los datos disponibles. El protocolo y el evaluador permiten recoger y puntuar esas pruebas; no demuestran por sí mismos ahorro de tiempo ni precisión industrial.

## Evidencia inicial

- Antes de integrar los cambios: `npm test --prefix frontend`: 260 correctas.
- Suite Python inicial: `.venv/Scripts/python.exe -m pytest -q`: 1420 correctas, 2 avisos de deprecación, 162,67 s.
- Los registros individuales contienen las pruebas focales y el orden real de ejecución. La verificación final se añadirá tras cerrar implementación y revisión.

## Comprobaciones del incremento

- Seguridad: 88 pruebas focales correctas y aprobación Astra. Jobs/recientes: 147 pruebas conjuntas correctas y aprobación Astra.
- Interfaz: `npm test --prefix frontend`, 273 correctas. `npm run test:browser --prefix frontend`, 6 correctas en Chromium, con servidor aislado y sin proveedor externo. El sexto caso encontró y verificó la corrección del refresco de recientes tras completar un trabajo.
- Navegador: carga y resultado, revisión 2 y recarga, cambios sin guardar, getter y métodos de localStorage bloqueados, explorador deshabilitado, cancelación de cola y recuperación desde recientes sin otro POST de análisis. Captura local inspeccionada: `.runtime/browser-ci/workflow-success.png`.
- Evaluación: 5 pruebas del nuevo scorer y 37 de integración correctas. Los informes Blind20 de 20 casos se reprodujeron byte por byte; los cuatro folds económicos publicados reprodujeron MAE de coste 48,82 PLN y horas 0,46775. Son presupuestos académicos, no costes empresariales ejecutados. [Protocolo y denominadores](ESTUDIO_TECNICOS.md).
- Embeddings: smoke real CPU con snapshot fijado, red deshabilitada, 768 dimensiones, valores finitos y norma L2 1,0; arranque en frío 17,93 s. Biblioteca e histórico usan espacio textual; el explorador mantiene su espacio mixto.
- Embeddings tras el ajuste de calibración: 107 pruebas focales correctas. Los gates de EmbeddingGemma 2 exigen una calibración para el espacio completo y versión de descriptor; sin ella responden `409 semantic_threshold_uncalibrated`, o admiten el umbral explícito del solicitante. No se aplican silenciosamente los valores heredados de OpenAI.
- Empaquetado local: `pip check` sin dependencias rotas; `pip wheel --no-deps .` produjo `vexplorer-0.2.0-py3-none-any.whl`; compilación de backend, tools y evaluation correcta.
- Ruff sobre API, configuración, runners, jobs, repositorio, embeddings, umbrales, histórico y nuevo evaluador: correcto. `git diff --check`: correcto.
- Suite global intermedia: 1465 correctas, 2 avisos de deprecación, 231,12 s. La última pasada incluye también el ajuste final de calibración y manifiestos dañados.
- Suite global final: `.venv/Scripts/python.exe -m pytest -q` → **1470 passed**, 2 avisos de deprecación (Starlette/httpx y Pillow), **188,00 s**. Incluye los últimos ajustes de calibración y robustez de manifiestos.
- Dictamen agregado GPT-6 Astra: **APPROVE**, sin P1/P2 pendientes. Los límites de entorno y de validación empresarial se conservan abajo.

## Verificación que depende del entorno

El nuevo job de GitHub Actions está configurado y su recorrido se ejecutó localmente; no se ha publicado ni ejecutado remotamente en esta entrega. La construcción Docker no se pudo ejecutar porque el daemon Docker Desktop no estaba activo. No se ha desplegado el código ni reiniciado el servicio público anterior.

La prueba real de embeddings reutilizó el entorno del laboratorio y los pesos locales. La disponibilidad en otra instalación exige las dependencias `semantic-runtime` y configurar el snapshot indicado en `.env.example`; el servidor informa de la ausencia sin descargar pesos silenciosamente. Los umbrales de similitud necesitan calibración para el espacio y corpus usados; la generación de vectores no prueba calidad de recuperación.
