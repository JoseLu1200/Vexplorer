# Agente reconstrucción 3D

Identidad: agente de IA, no identidad humana inferida. El usuario designó explícitamente este registro y autorizó reconstrucción paramétrica, evaluación de cuatro variantes e integración del visor en rama aislada el 2026-11-14.

## Alcance

Rama `feat/reconstruction-3d`, base `affe009`. Nuevos módulos `backend/app/reconstruction3d/`, `tools/reconstruction3d/`, pruebas correspondientes, documentación de esta tarea y adaptaciones mínimas de main/frontend para exponer el resultado. Datos, modelos y resultados externos en `D:/Vexplorer-idol-study/`. Se preservan cambios concurrentes en otras ramas/worktrees. Los contratos de experimentación son modelos Pydantic en el módulo nuevo; no se modifica `backend/app/contratos/` sin el acuerdo requerido. Registros de otros agentes son solo lectura.

## Estado

Continuación autorizada tras conclusión Idol: implementar aclaraciones y cotas generales comprobadas, revisiones inmutables y formulario en el visor del módulo propio. Base del incremento a9908bb; se mantiene aislamiento. Diseño/plan reconstruction-refinement. No hay cambios en contratos, economía o frontend ajeno a reconstruction.*.

Corrección explícita posterior del usuario: integrar sobre el overhaul UX ya terminado. Se amplía la adaptación de frontend para consumir su snapshot, con hashes y atribución en docs/reconstruction3d-ux-source.json; árbol principal intacto. Se conserva el estilo vigente y se abre el módulo como herramienta dentro del mismo espacio de trabajo. El primer ensayo aislado no se acepta como UI final.

Incremento verificado: 737 pruebas Python y 172 JS. Revisión independiente: corregidas edición de respuestas heredadas, exportación de procedencia y conservación de embedded/run en historial. Smoke real del modelo y navegador descritos en docs/RECONSTRUCCION_3D_INCREMENTO.md. Instancia separada 8875; sin despliegue ni merge.

Ruling: snapshot de UX ajeno en esta rama para respetar la corrección del usuario, sin escribir en el árbol original; las pruebas se repiten sobre la combinación. Coste: no integra automáticamente cambios futuros que hagan en el árbol principal.

Ruling: revisión descarta certificación industrial y criptografía contra escritura hostil; siguen fuera del alcance. El almacén mantiene el diseño de un proceso. Minor diferido: error de envolvente agotada no explica aún el eje incumplido en la UI.

Ruling: ejecución directa del incremento reversible ya autorizado; no repetir aprobaciones de enfoque. Se conserva stack y rama existente. Las cotas aportadas se tratan como declaraciones humanas y no como observaciones extraídas.

Comparación y revisión final completadas. 6 montajes B + 18 splats A/C/D, 144 vistas inspeccionadas, recuperación EmbeddingGemma2 completa y 30 clasificaciones Jev válidas con normalización común. Informe: `docs/RECONSTRUCCION_3D_RESULTADOS.md`. Conclusión: priorizar montaje por componentes; no se observa valor adicional de Idol para despiece, geometría o recuperación en esta muestra. Mantener rama aislada sin merge/push.

## Verificación

Implementados modelos, validación geométrica, harness con revisión visual, router con trabajos persistentes y visor interactivo; exportación GLB/BOM/SVG/DXF y contexto de recuperación marcado como hipótesis. Suite global: 722 pruebas Python y 153 frontend pasaron antes de las últimas adiciones del evaluador; pruebas focales se repiten después de ellas. Inspección real del visor en móvil/escritorio, corregido desbordamiento del canvas.

Experimento externo `D:/Vexplorer-idol-study/experiment-v1`: B completó seis casos desde entradas públicas. Tres fixtures funcionales sintéticos y tres controles ambiguos de PlankAssembly. Predicciones B congeladas y referencias separadas. Primera A real: dos vistas reconstruidas como formas separadas; primer D real: mesa reconocible. Idol base sigue ejecutando A/C/D, 50 pasos y 32768 gaussianas, sin optimización, semilla 42. No declarar comparación terminada hasta disponer de 18 resultados y revisión visual final.

Pruebas reales adicionales: sin escala devuelve relative; imagen vacía se abstiene. Ajuste posterior del prompt evita justificar marcos ambiguos mediante usos inventados y bloques de herraje ficticios; los dos controles ambiguos posteriores devuelven insufficient_evidence. No sustituir con ellos las predicciones B congeladas del benchmark.

Carga Idol secuencial de pesos para limitar compromiso de memoria Windows, sin cuantización; compatibilidad de nombres DINOv3 con Transformers 5.23. Primeros fallos por paginación y C casi lleno; posteriormente se liberó espacio y la inferencia funciona. Entorno aislado y requisitos en tools/reconstruction3d/requirements-idol-windows.txt.

Lotes terminados; logs en experiment-v1: idol-resume.*, retrieval-final.*, follow.*. La clave Jev se usó desde el archivo de Reto_Maisa indicado por el usuario, nunca se copió ni imprimió. Visor local en puerto 8873; todos los pesos/datos fuera de Git.

## Cierre de revisión independiente

Revisor fresco Astra: ningún Critical, seis Important y un Minor. Una pasada de corrección, tests RED→GREEN para entrega explícita del prompt, parciales accesibles, metadatos/referencias de vista, separación multivista, distancia de bordes y detección de manipulación del inventario privado. Suite final: **728 passed**, frontend **153 passed**, ruff limpio; galería 36 imágenes principales cargadas, visor interactivo con 9 piezas y despiece activado.

Ruling: los 149 hashes privados del ensayo existente se capturan como `post_execution_review`, no se retrofecha una congelación inexistente. Los nuevos datasets se congelan antes de inferencia y el evaluador verifica el inventario. Coste: este ensayo no demuestra integridad privada previa de un benchmark ciego; se mantiene diagnóstico.

Ruling: B v1 y sus métricas se conservan aunque el prompt posterior se abstenga en los controles 05/06. Coste: las cifras no miden la versión corregida del harness sobre un test independiente.

Minor diferido: label/intended_use admiten cadenas sólo de espacios. No aparece en las predicciones evaluadas; documentado sin bloquear la comparación.

## Solapes

La raíz contiene UX concurrente; esta rama no copia ni sobrescribe esos cambios. La nueva reconstrucción mantiene separado el diseño propuesto de los hechos y del presupuesto confirmado. Integrar en otra rama o desplegar requiere verificar su árbol definitivo.
