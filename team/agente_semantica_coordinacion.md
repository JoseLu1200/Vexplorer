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

## Decisión de arquitectura e integración posterior

- El laboratorio se publicó en `14a6514ddd82e8914aa128ff5787d029517a3f3f`; se verificaron HEAD remoto y árbol limpio. Ese cierre no incluía autorización de merge.
- Petición explícita posterior del usuario: registrar decisión final y diseño en dos Markdown, hacer push y merge a `main`. Esta autorización sustituye el límite de integración anterior; no pide activar el nuevo runtime en un servidor.
- Dirección aceptada: EG2 mixto 768 sin PCA para búsqueda, logística EG2/geometría como candidato de clasificación amplia, Jev visual opcional para revisión y validación independiente de comparables económicos.
- Root mantiene `DECISION_ARQUITECTURA_PRODUCCION.md` e índice. Agente GPT-6.1 Sol mantiene sólo `DISENO_ARQUITECTURA_PRODUCCION.md`; revisión final GPT-6 Astra. Sin cambios de contratos ni del runtime.
- Preflight de integración: `origin/main` sigue en `4209510`, ancestro del laboratorio; rama principal del workspace contiene trabajo ajeno y no se toca. La integración se verificará en un worktree aislado.
- Se detectó fallo real en CI de `14a6514` (run `43559606234`): el workflow instala sólo `requirements-demo.txt` y faltan joblib/SciPy/scikit-learn al recoger tests. Corrección acotada delegada a Sol sobre `.github/workflows/ci.yml`, usando el extra de tests ya declarado y conservando restricciones del entorno. Se exige CI verde antes del merge.
- Verificación local del incremento documental y CI: `python -m pytest -q` terminó con **509 passed en 71,65 s**; los enlaces de los 13 Markdown del directorio semántico resolvieron. El ajuste de CI instala `.[test]` bajo constraints del entorno demo; no modifica el contenedor productivo ni descarga pesos.
- Diseño revisado por root: categorías predichas no eliminan vecinos, etiquetas siguen propuestas hasta calibración, ACL se comprueban antes de recuperar y al responder, y ningún rollback puede reactivar datos retirados o permisos revocados.
- Astra aprobó el delta sin bloqueantes, incluida la corrección mínima de dependencias de tests. Pendientes al escribir esta anotación: nuevo CI remoto e integración comprobada; no se fusionará hasta observar el run verde. El historial remoto y la respuesta de entrega identificarán el commit integrado y la ejecución comprobada.
