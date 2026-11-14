# Agente de interfaz de similitud

## Identidad y autorización

- Identidad: agente de IA de interfaz; no representa a una persona.
- Autorización: delegación explícita del coordinador dentro del swarm solicitado por el usuario el 2026-11-14.
- Rol: corregir exclusivamente la presentación y controles de similitud/biblioteca.

## Alcance y reservas

- Propiedad: `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`, pruebas frontend dirigidas y este registro.
- Solo lectura: backend, contratos, modelos y registros ajenos.
- Se preservan todos los cambios locales previos. Sin commit, push ni despliegue.

## Objetivo

- No presentar una similitud coseno redondeada como identidad.
- Separar tipología de comparación técnica y advertir material, acabado y fabricación no comparados.
- Distinguir diseños únicos, registros almacenados y duplicados.
- Separar biblioteca vacía de disponibilidad del proveedor e historial.
- Mostrar diferencias por pieza, incluido grosor ×2, y miniaturas lado a lado cuando existan.
- Rotular con precisión el criterio de agrupación y ofrecer controles de umbral útiles.

## Dependencias / avisos

- Coordina contratos aditivos de respuesta con `/root/library_api` y helpers puros con `/root/similarity_backend` mediante `/root`.
- No cambia `backend/app/contratos/`.

## Estado y pruebas

- Estado: implementación terminada; pendiente revisión integrada del coordinador.
- Causa confirmada: la interfaz usaba `score.toFixed(3)`, un contador genérico de miembros y un único vacío, perdiendo precisión y significado de los campos del proveedor.
- Se consume el contrato coordinado: `technical_score`, componentes, advertencias, conteos exactos, `linkage=complete` y `minimum_pair_score`; las peticiones optan por `include_summary=true` para preservar el contrato legado.
- La puntuación conserva hasta seis decimales y declara que no implica identidad ni certifica compatibilidad; tipología y técnica se presentan por separado.
- La biblioteca pública vacía pide guardar mobiliario real revisado y aclara que los fixtures de demo no se publican; proveedor e histórico mantienen estados separados.
- Las diferencias granulares V2/V3 se presentan por pieza y calculan relaciones de grosor (incluido ×2); miniaturas se muestran lado a lado solo cuando el servidor las ofrece.
- El umbral cambia su rótulo entre similitud geométrica y coseno, parte de 0,95 y explica enlace completo y carácter orientativo.
- Corrección Astra: `score_kind`/modo decide si la puntuación es geométrica o coseno; las diferencias por pieza nombran campo y unidad y solo el grosor muestra relación; no quedan textos `undefined`.
- Las miniaturas ya no aceptan URLs arbitrarias: usan el documento activo y resuelven la ejecución candidata con `api.getRun`, generando ambos recursos mediante `api.documentPreviewUrl`; una referencia sin preview muestra indisponibilidad.
- En producción, `library_requires_real_reviewed` revela declaración explícita y referencia; solo entonces se envía `publication` como mobiliario real autorizado. Local omite el campo.
- Tipologías y advertencias conocidas se traducen al castellano; claves desconocidas quedan como detalle técnico. `equivalent_record_ids` conserva enlaces a todas las repeticiones.
- RED observado: 6/6 pruebas nuevas fallaron antes de la implementación.
- GREEN final: `node --test tests/similarity-ui.test.js` → 8/8; `npm test` → 173/173; `node --check app.js` correcto.
- QA de navegador automatizada intentada contra servidores aislados 8773/8774: la ejecución Playwright no devolvió evidencia antes del timeout; no se afirma validación visual. El coordinador realizará la revisión independiente.
