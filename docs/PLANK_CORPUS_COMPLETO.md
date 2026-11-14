# PlankAssembly completo: preparación y comparación pareada

El inventario local oficial contiene 26.707 entradas: train 24.039, valid 1.329 y test 1.339. `tools.run_plank_corpus` recorre todas, sin recortar la selección a los 16 ensayos históricos. Usa el preparador y el harness existentes en lotes independientes de hasta 50 casos.

El generador `plankassembly-adapter-2` corrige la colocación de las vistas: frontal y superior ocupan ambas el ancho; la lateral empieza después de ambas. Normaliza el origen de cada proyección conservando sus medidas. La versión anterior podía superponer superior y lateral en muebles anchos. Los artefactos históricos no se reescriben; sus métricas no son una comparación controlada con esta versión.

## Ejecución local

Desde la raíz del repositorio:

```powershell
.venv/Scripts/python.exe -u -m tools.run_plank_corpus --source ../plankassembly_dataset --prepared-root ../plankassembly_full_v2 --output ../plankassembly_full_codex_v2 --batch-size 10 --live --workers 2 --provider codex-subscription
```

Omitir `--live` prepara todo sin llamar al proveedor. `--prepared-root` reutiliza el corpus ya generado tras verificarlo; puede omitirse en una preparación nueva. El comando live prepara o verifica primero todo el corpus y luego ejecuta valid, test y train. Los modelos por defecto son `gpt-6.1-sol` tanto para la propuesta como para la revisión. Cada caso conserva el plazo total de 300 segundos, cinco llamadas de revisión y dos reparaciones. La ejecución completa puede prolongarse durante días y está sujeta al uso disponible en la suscripción.

`codex-subscription` es el transporte predeterminado del coordinador completo. Usa `codex app-server --stdio`, exige login ChatGPT mediante `account/read` y registra herramientas nativas dinámicas equivalentes a las del harness. Cada proponente/crítico tiene un thread efímero nuevo; las respuestas de herramientas vuelven a ese mismo thread. No se copian credenciales. Se retiran variables de API del subproceso, se fija proveedor OpenAI, se desactivan conectores/plugins y herramientas externas, y se configura un directorio temporal sin acceso a entornos. Solo las imágenes públicas y el contexto del harness entran como mensajes. El cierre del caso termina el proceso local.

El CLI local no expone el mismo límite duro de salida de 16.384 tokens que Responses API. La configuración registra `output_token_cap_enforced: false` para Codex; plazos y límites de herramientas se conservan. El runner individual mantiene `openai` por defecto por compatibilidad y permite `--provider codex-subscription`. Elegir `--provider openai` en el coordinador usaría la API y su facturación; no es la campaña solicitada.

Repetir exactamente el comando reanuda lotes congelados después de comprobar sus hashes. `--retry-failed` permite volver a ejecutar lotes con algún caso fallido y conserva intentos anteriores. Se selecciona el intento completamente exitoso más reciente, si existe; en otro caso el último intento congelado. El score registra el intento elegido. Un intento interrumpido permanece intacto y genera otro intento; puede repetir llamadas de ese lote. Una preparación interrumpida entre las dos carpetas se mueve a cuarentena y se regenera. Recibos separados fijan los hashes de ambos árboles; las referencias se enlazan además a la selección y hashes de origen.

No se deben lanzar dos coordinadores sobre la misma salida ni modificar una preparación compartida mientras está en uso. Hay dos locks: `output/running.lock` y `prepared-root/preparation.lock`, ambos con el PID real del coordinador. Tras una terminación abrupta, comprobar que los procesos de **ambos PIDs y todos sus hijos** han terminado antes de retirar esos dos archivos concretos. Comprobar también la identidad del proceso para no confundir un PID reutilizado por Windows; nunca borrar locks de una campaña activa. Con los locks retirados, repetir el comando reanuda. Una terminación normal, incluida por error, retira ambos automáticamente.

Los cambios en fuentes, código o configuración requieren otra salida para no mezclar versiones. Antes de cada lote se comprueba un mínimo de 2 GiB libres, configurable mediante `--minimum-free-mb`.

## Artefactos y aislamiento

Todos los datos derivados quedan fuera de Git en el directorio de salida:

- `plan-private.json`: selección completa, hashes de modelos y splits, código y configuración.
- `public/<split-offset>/agent_cases`: único directorio entregado al proceso de inferencia.
- `private/<split-offset>`: referencias del adaptador, nunca argumentos del harness.
- `runs/<split-offset>/attempt-NNN`: predicciones, trazas y congelación, con logs adyacentes.
- `scores-private`: alineaciones construidas después de congelar las predicciones.
- `scores`: informes completos baseline/final por lote, incluidos errores dimensionales y cobertura.
- `summary.json`: métricas microagregadas de tipos y cantidades por split oficial, con denominadores y avance.
- `status.json`, `error.json`: último progreso y error, si existe. Un lote con cero resultados pareados exitosos detiene la campaña para evitar repetir un fallo sistémico en todo el corpus.

Las rutas separadas y los subprocesos restringen qué se entrega al modelo; no constituyen un sandbox de permisos del sistema operativo. Los IDs locales pueden repetirse entre splits: la clave externa de lote evita mezclar casos.

## Interpretación

La comparación principal es baseline frente a final sobre los mismos planos y casos. Los fallos permanecen en el denominador. Una mayor muestra por sí sola no entrena el modelo ni garantiza mejores resultados. La corrección del layout es un cambio adicional respecto a los pilotos históricos.

Los splits oficiales se reportan por separado; las etiquetas development/holdout del adaptador son otra partición por firma dimensional. No se utiliza ningún caso como ejemplo de entrenamiento ni se introduce su referencia en prompts. No se certifica independencia semántica entre familias de los splits oficiales. Esta campaña es diagnóstico del corpus sintético, no validación industrial de montaje, materiales, coste o fabricabilidad.

## Comprobaciones

Las pruebas cubren el inventario completo de splits, IDs por lote, reanudación con verificación de integridad, conservación de fallos en el denominador, puntuación posterior a la congelación y separación de vistas en modelos anchos con origen trasladado. El estado de ejecución observado se registra en `team/agente_plank_corpus_completo.md`.
