# Despiece, cotas y recuperación: plan de implementación

> For agentic workers: usar desarrollo por subagentes con propiedad disjunta y revisión final independiente.

**Objetivo:** alcanzar al menos 90 % de cobertura de paneles físicos y 90 % de cotas correctas en una muestra ciega declarada, evitando falsos positivos y conservando incertidumbre constructiva; explicar y recuperar revisiones interrumpidas.

**Autorización:** solicitud del usuario de corregir los problemas diagnosticados y alcanzar ambos umbrales. Continúa el swarm Sol con revisor Astra autorizado en esta conversación. La solicitud amplía el alcance anterior a generación, recuperación e interfaz; no requiere importar datos sintéticos a Biblioteca.

**Arquitectura:** mantener geometría y mediciones deterministas, propuesta con referencias de evidencia, revisión independiente y validación del servidor. Añadir cobertura de evidencia sin convertir vistas en ocurrencias. Persistir el enlace job/run y reanudar desde propuestas guardadas. Mantener valores numéricos originales y formatear solo la presentación.

**Base:** `.worktrees/similarity-public`, runtime V4 publicado `d0ea7a85e787-tree518ad7d881403b9b`; conservar íntegros Biblioteca, CAD, reconstrucción y operación. Python/FastAPI/Pydantic y JS existentes.

## Decisiones y alternativas

- No basta con elevar el timeout: no detecta piezas omitidas y repetiría llamadas ya realizadas.
- No se permite completar respuestas desde el oráculo ni añadir candidatos indiscriminadamente para aumentar recall.
- Implementación elegida: cobertura trazable de contornos/proyecciones, evaluación independiente por ocurrencia, checkpoints y reanudación, presentación legible y separación paneles/herrajes.

## Criterios de aceptación

- Evaluador separado del runtime. Entradas del runtime: únicamente dibujos permitidos; referencias privadas se consultan después de congelar salidas.
- Medir recall de paneles, precisión de paneles y cotas por ocurrencia, exigiendo >= 0,90 en cada caso y en el holdout, no solo en promedio. Publicar numeradores, denominadores, tolerancias, cantidades y falsos positivos. Solo excluir auxiliares con clasificación respaldada; los auxiliares sin respaldo bloquean el gate.
- Matching óptimo 1:1 con dimensiones canonizadas; una pieza con al menos dos cotas conocidas compatibles puede emparejarse, pero la cota desconocida penaliza cobertura dimensional. Con una sola cota no se acredita identidad. Medir cotas correctas sobre denominador de referencia y predicho; exactitud entre cotas conocidas emparejadas es solo diagnóstico.
- Incluir los dos casos diagnosticados y al menos un caso complejo distinto reservado. No descartar fallos ni sustituir casos después de ver puntuaciones.
- Usar presupuesto general 600 s como producción en las pruebas live finales; registrar presupuesto efectivo de cada fase y estado terminal. Un borrador no acredita entrega final revisada.
- Las tolerancias de evaluación se fijan antes de la ejecución y no se cambian para aprobar resultados; propuesta inicial: 1 mm para largo/ancho y 0,2 mm para espesor, sujetas a revisión del evaluador/Astra.
- No reclamar un 90 % general o garantía industrial a partir de esta muestra.

## Trabajo y propiedad

- [ ] Motor (`similarity_backend`): investigar omisiones, contexto de geometría, hipótesis de proyección y revisión; probar causas con fixtures propios; implementar cobertura genérica en `backend/app/general_furniture/`, salvo persistencia reservada a API. No valores de respuestas privadas.
- [ ] API (`library_api`): `main.py`, repositorio/jobs y persistencia. Enlace durable job/run, diagnóstico de fase y checkpoint, reanudación actor-scoped e idempotente que no repita proponente. Probar interrupción, permisos, concurrencia y revisión posterior.
- [ ] UI (`similarity_ui`): `app.js`, `core/general.js`, `core/format.js`, cliente API coordinado. Formato de cotas sin mutar raw; cantidades de paneles/herrajes separadas; motivo de fallo y acción de recuperación explícitos. Pruebas de comportamiento y navegador.
- [ ] Evaluación (`complex_visual_audit`): harness y métricas ciegas, casos congelados, resultados completos/parciales, imágenes y comparación antes/después. No llamadas live hasta congelar implementación.
- [ ] Revisión (`astra_review`): métricas, independencia del oráculo, geometría, autoridad de medidas/revisiones, privacidad y recuperación; veredicto sobre diff y evidencia.
- [ ] Coordinación: integrar, ejecutar suites necesarias, inspección multimodal, paquete reproducible, backup/restore y despliegue con CAS solo tras verificación. No sobrescribir cambios externos ni poblar Biblioteca.

## Riesgos que deben probarse

- Proyecciones repetidas no son piezas repetidas; cantidades repetidas reales no deben colapsarse.
- Huecos, rebajes y contornos interiores pueden no representar material.
- IDs, orden de entidades o posición del plano no deben codificar la respuesta.
- Fallos o reinicios durante revisión conservan propuesta y no producen exportaciones aprobadas artificialmente.
- Reanudación repetida o concurrente no duplica llamadas ni sobreescribe una revisión más nueva.
- Formato de cotas distingue desconocido, estimado y deducido; cero/no finito/rangos no se convierten en números inventados.

## Verificación

Cada propietario registra reproducción antes del cambio y pruebas focales después. Coordinación ejecuta las suites globales una vez integradas y únicamente repite las afectadas por cambios posteriores. La evaluación live se ejecuta con configuración registrada y no oculta fallos. Si no se alcanzan umbrales, se informa la brecha y se investiga antes de afirmar cumplimiento.
