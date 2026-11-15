# Agente de integración PR y CI

## Identidad y autorización
Agente IA de esta sesión, sin identidad humana atribuida. El usuario autoriza el 2026-11-14 «tienes permiso absoluto para todo» tras solicitar registro propio para corregir CI, revisar, fusionar PR útiles y cerrar el resto.

## Alcance y plan
Checkout aislado Vexplorer-review-pablo, rama integration/pr-ci-review-20261114. Integrar PR7 con main bc3a17f preservando seguridad, jobs, frontend y EmbeddingGemma 2. Resolver conflictos API/regeneración; adaptar PR3; corregir concurrencia PR5; retirar evaluador duplicado PR4. Revisar código nuevo, ejecutar Python, frontend, navegador, empaquetado y CI remoto antes de merge. Cerrar PR redundantes con explicación.

## Coordinación
Los incrementos de hallazgos ya están publicados en bc3a17f. No se editan registros ajenos ni otros checkouts. Se conservan contratos vigentes; no se modifica contratos/. Revisor independiente en lectura del código nuevo de PR7.

## Estado
En curso. Detectados conflictos API/regeneración, caché antigua en PR3/7, carrera de idempotencia PR5 y duplicación de métricas PR4. CI main y PR7 en curso al inicio; Python/frontend y navegador de main ya verdes.


## Correcciones verificadas (2026-11-15)
- API: reserva SQLite previa a ejecutar, rechazo de duplicados en vuelo, WAL; se conserva endpoint de jobs en producción.
- Biblioteca: identidad completa EG2, CAS atómico, reintento de revisiones automáticas concurrentes, replay de revisión sin mutar snapshot re-guardado explícitamente.
- Seguridad: normalización de prefijo también en ownership, preservando orden del middleware acotado.
- Regeneración: caché valida space_id persistido, snapshot/revisión completa y sello; CAS evita pisar guardados.
- Revisión delegada: cuatro hallazgos de corpus, aislamiento, sellado y unidades corregidos por agentes registrados. Evaluador duplicado PR4 retirado y PR cerrada.
- RED reproducido para doble ejecución, ownership con prefijo, pérdida de guardado, cambio de snapshot EG2, caché sin identidad, replay y revisiones solapadas.
- Verificación parcial: 273 frontend, 6 Chromium, 64 focales API/embeddings/repositorio; evaluación 115 y mantenimiento/lotes 50. Suite completa inicial: 1696 pasan, 1 fallo de ruta aislada ya corregido y revalidado en las 115. Pendiente repetir suite completa y CI remoto del commit final.
- Compilación, pip check, wheel y Ruff F pasan. No se cambia workflow para ocultar fallos.
- Nuevos commits main 8022ac6/a467280 de Martín: se integrarán íntegros diseno/** y team/martin.md antes de publicar. Usuario exige preservarlos expresamente.
- Limpieza de tmp pytest-9448 bloqueada por política automática; no se eludió. Pruebas de evaluación repetidas correctamente cuando volvió a haber espacio.
