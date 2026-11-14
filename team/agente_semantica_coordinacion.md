# Agente de coordinación semántica

## Identidad y autorización
- Identidad: agente de IA coordinador; no se atribuye identidad humana.
- Solicitud explícita de esta sesión (2026-11-14): lanzar swarm GPT-6.1 Sol, investigar y probar técnicas hasta obtener agrupación/clasificación semánticamente coherente, con GPT-6 Astra como revisión final.
- Registro nuevo para esa tarea y alcance experimental; no se reutilizan registros ajenos.

## Alcance
- Worktree aislado `.worktrees/semantic-lab`, rama `experiment/semantic-furniture`, base `4209510`.
- Coordinador: documentación de experimento, dependencias experimentales en pyproject.toml e integración/verificación.
- Agentes Sol: archivos nuevos disjuntos en `tools/semantic_lab/`, pruebas propias y registros personales.
- No se modifica `backend/app/contratos`, no se publica ni despliega, no se mezcla esta rama en main.

## Estado
- Base: suite previa 423 tests aprobados; tres commits posteriores inspeccionados (despliegue y schema de comparación).
- Scout de datos y scout de modelos/hardware iniciados con GPT-6.1 Sol.
- La creación nativa del worktree falló porque el cwd de la tarea es el directorio padre sin Git; creado mediante Git dentro del repo correcto.
- Segmentación se interpreta como agrupación/clasificación de objetos, no segmentación de píxeles.
- Resultados de categorías del proveedor se tratarán como etiquetas proxy, no aceptación de técnicos ni equivalencia económica.

## Verificación y cierre
- Completados cuatro lanes de implementación GPT-6.1 Sol y revisión independiente GPT-6 Astra.
- Corpus real: 117 DXF, 89 grupos; train82/validation17/test18. Ocho conjuntos de embeddings con hashes/revisiones; 228 configuraciones de selección.
- Ganador: EmbeddingGemma 2 mixto768+kNN5 sin PCA. Test abierto una vez: 16/18, macro-F1 0,826128, BA 0,833333, P@5 0,888889. Diagnóstico posterior no cambió etiquetas, configuración ni resultados.
- Revisión corrigió guard de congelación para corridas futuras, emparejamiento de afinidad cero en componentes y dependencia directa SciPy. Artefactos históricos originales conservados; Astra verificó config/hashes manualmente.
- Verificación fresca tras fixes: 466 tests aprobados en 60,66 s, Ruff limpio, compileall y diff-check correctos; consulta CLI validada.
- Astra: aprobado como spike experimental, sin bloqueantes pendientes; no listo para uso industrial/precios. Límites de etiquetas, tamaño, independencia y clustering transductivo explícitos.
- Entregables: `docs/SEMANTIC_LAB_2026-11-14.md`, evidencia pequeña bajo `docs/experiments/semantic-lab-2026-11-14/`, artefactos grandes en `D:/Vexplorer-semantic-lab`.
- Cierre local sin commit, merge ni despliegue. Sin cambios al runtime/contratos productivos.

## Ampliación documental y pruebas adicionales

- Petición explícita posterior: organizar todos los hallazgos en Markdown y ejecutar git add/commit/push. Alcance: rama `experiment/semantic-furniture`; no mezclar cambios ajenos de `feat/transcript-completion`.
- Nueva petición mientras se prepara la publicación: probar otros datasets descargados con app y embeddings. Se conserva el objetivo de publicar al cerrar esas pruebas; no se cancela ni se reabre el test inicial.
- Coordinación mantiene índice, metodología, reproducción y revisión. Agentes Sol de datos/modelos documentan auditoría/SOTA y amplían probes. Otro agente Sol prueba una instantánea identificada de la app actual en almacenamiento aislado.
- Datos, renders, pesos, entorno y snapshots ajenos permanecen fuera de Git. Se versionan runners propios, tests, Markdown y evidencia pequeña seleccionada.
- Estado de esta ampliación: ejecución y verificación en curso; commit/push pendientes hasta disponer de resultados y revisión.
- Ampliación de datasets ejecutada: CAD-extra 373/379 (262/56/55), modelo fijo macro-F1 test 0,777966 y P@5 0,774545; Plank 10 objetos/30 vistas Hit@1 0,30; Engineering14 fuerza clases de muebles. No se ajustó rechazo tras observar esos datos.
- App: segunda captura acotada de rama ajena con hashes estables; 53 casos offline sin propuestas/piezas, importación pública 4/4 aceptada. La primera captura rechazó el histórico por esquema y se conserva como contraste. No se ejecutó live por configuración incompleta.
- Petición adicional: comparar con un clasificador como el proyecto Jev. Se inspeccionó el repo sólo en lectura y se verificó que la API actual admite imágenes, aunque el cliente histórico usaba texto. El usuario designó explícitamente otra configuración local para autenticación; se comprobó acceso sin registrar el valor de la credencial.
- Comparación Jev y clasificadores locales delegada a Sol, con revisión Astra y protocolo retrospectivo explícito. Continúa pendiente la publicación de todo el trabajo al cerrar esa comparación.

## Cierre ampliado para publicación

- Clasificadores locales: kNN conserva F1 core 0,826128; logística sobre EG2+27 features mejora CAD-extra a F1 0,844471, seleccionada por validation. Comparación retrospectiva, no nuevo test ciego.
- Jev 1.14 real: 320/320 respuestas válidas; con imagen F1 core 0,914286 y CAD-extra 0,524892; elección abierta rechaza 13/14 mecánicos. Auditoría posterior confirma paridad de 160 entradas y 320 payloads con los artefactos fijados.
- Se corrigieron los hallazgos de Astra sobre paridad métrica, caché/presupuesto/contabilidad HTTP, dependencia joblib, persistencia y precisión documental. Sin repetir la batería pagada.
- Verificación final root: 509 passed en 90,64 s, Ruff sin hallazgos, compileall correcto; documentación y JSON comprobados. Dictamen Astra ampliado: válido como spike aislado y exploratorio, no industrial/económico.
- Documentación organizada en `docs/semantic-lab/README.md` y resúmenes bajo `docs/experiments/`. Sin datos/pesos/credenciales ni cambios ajenos de la app dentro de la entrega.
- Trabajo completo y autorizado para commit/push a `experiment/semantic-furniture`. El commit de entrega y la confirmación del remoto identifican la publicación; no se autoriza merge ni despliegue por esta operación.
