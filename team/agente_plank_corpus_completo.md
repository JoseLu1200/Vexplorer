# Agente IA — corpus PlankAssembly completo

## Identidad y autorización
- Registro nuevo autorizado por el usuario el 2026-11-14: «venga vamos continua hazlo todo», tras solicitar designación o creación de registro.
- Rol: preparación y evaluación offline del corpus completo.
- Alcance: nuevos `tools/run_plank_corpus.py`, `tests/test_run_plank_corpus.py`, documentación y artefactos locales fuera de Git.
- Ampliación explícita del usuario: usar Codex con la suscripción activa, no API de pago. Añadidos `tools/codex_subscription_provider.py`, su prueba y opción de transporte en `tools/run_general_benchmark.py` con prueba.
- Sin modificaciones de contratos ni runtime del producto; el runner offline incorpora la selección de transporte. No hay solapes de escritura con las reservas históricas.
- Alcance adicional necesario: `tools/prepare_plankassembly.py` y su prueba para corregir separación de vistas antes de escalar. Los preparadores históricos ya están cerrados; los artefactos anteriores se conservan intactos y el nuevo generador tendrá versión propia.

## Plan
1. Inventariar todos los splits oficiales y congelar selección y hashes.
2. Preparar lotes de hasta 50 con el adaptador existente; conservar IDs en espacios separados por split/lote.
3. Ejecutar el harness público en procesos separados, congelar baseline/final y puntuar después.
4. Reanudar lotes terminados verificando hashes; conservar intentos interrumpidos sin sobrescribirlos.
5. Comparar métricas por split; no atribuir una mejora a ampliar el denominador ni usar referencias para inferencia.

## Estado
Preparación completa: 26.707 casos en 2.671 lotes, fuera de Git en `../plankassembly_full_v2`. La ejecución inicial se detuvo antes de inferir al detectar el cambio de código de transporte, preservando el corpus preparado.

La API respondió 429 `credit_balance_exhausted`. El usuario indicó usar su suscripción. `codex login status` confirmó ChatGPT; el adaptador local además verifica `account/read` antes de crear el thread. No se leen, copian ni exportan tokens de autenticación.

Primer caso real Codex terminado: `.runtime/plank-codex-smoke-v2`, baseline y final congelados, 95,413 segundos. Evaluación posterior: 4/4 tipos y 4/4 ocurrencias alineados en ambas fases, F1 1,0; solo un smoke, no mejora global. Referencias/score en `.runtime/plank-codex-smoke-score`.

Campaña completa con suscripción lanzada en segundo plano: PID lanzador 64344, coordinador 63132; salida `../plankassembly_full_codex_v2`, preparación compartida `../plankassembly_full_v2`, 2 workers. Logs en `.runtime/plank-codex-launch`. Revalida todos los archivos antes de continuar con inferencia. Sin publicación ni despliegue.

## Verificación
- RED: import del coordinador inexistente, vistas superpuestas, opción de proveedor inexistente, respuesta tardía aceptada.
- GREEN: 43 pruebas focalizadas de preparación, runner, suscripción, referencias y métricas.
- `git diff --check` correcto; ruff no instalado en el venv.
- Revisor independiente detectó reintentos bloqueados, numeración con logs, preparación unilateral, hashes de evaluador faltantes y ausencia de guardia de disco. Corregidos con pruebas; revisa ahora el transporte Codex.
- Reanudación verifica recibos de árboles preparados, selección/hashes de fuente y código del evaluador; crea intentos nuevos solo con solicitud explícita de reintento o intento incompleto. No sobrescribe predicciones congeladas.
- Revisión final independiente: sin defectos críticos pendientes. Verificó aislamiento de proveedor, cleanup sin alterar el resultado congelado, ausencia de lectura de `.env` en suscripción y lock de preparación compartida. Documentado procedimiento de recuperación de los dos locks tras cierre abrupto.
- Inventario posterior independiente: 26.707 ZIP públicos presentes, 2.671 lotes con conteos coincidentes; train 24.039, valid 1.329, test 1.339.
- Pendiente: finalizar campaña larga y concluir comparación agregada. Un smoke exitoso no demuestra mejora global; la ejecución está sujeta a los límites de uso de la suscripción.

## Publicación solicitada
- El usuario autorizó explícitamente `git add`, `git commit` y `git push` a `main`.
- La revisión previa al commit encontró `status.json: stopped` y `error.json: insufficient free disk space for next batch`. El lanzamiento descrito arriba es histórico; la campaña no está activa en esta comprobación. Esta publicación no la reanuda.
- `origin/main` avanzó 376 commits desde la base local. Se integra el cambio propio sobre el remoto vigente en una copia aislada, preservando el directorio original y sus artefactos.
- Integración sin conflictos sobre `ad43066`; se conservan los cambios remotos del runner y el hash público de referencias del adaptador.
- Verificación previa a publicar: suite original 809 aprobadas; suite Python integrada 1.420 aprobadas, 2 avisos de deprecación; frontend integrado 260 aprobadas tras `npm ci`; compilación focal y `git diff --check` correctos. No se incluyen corpus, credenciales ni resultados locales.
