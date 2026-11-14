# Auditoría completa — 14 de noviembre de 2026

Base `10da225`: main y origin/main sincronizados al comenzar. Auditoría de solo lectura, anterior al incremento de producción. El historial combina contribuciones humanas, agentes y cherry-picks; no se atribuye todo su trabajo al asistente.

## Cobertura

Se recorrieron **495/495 commits** accesibles con mensajes y estadísticas; 220 pertenecen a main. Hay 232 asuntos distintos; 254 de 274 commits no-merge fuera de main tienen un parche equivalente en main. Se inspeccionaron las diferencias no equivalentes y las mejoras CAD: fusionar esa rama completa reintroduciría contratos y defectos antiguos; sus aportaciones válidas ya se habían adaptado selectivamente.

Se leyeron 51 Markdown de raíz/team/docs/datos (4.483 líneas, excluida plantilla), tres documentos exclusivos de la rama CAD, documentos frontend/evaluation y README de datasets hermanos. Se analizaron todos los módulos propios backend, frontend, herramientas y pruebas mediante reparto por dominio. No se presentan dependencias/vendor ni todos los binarios externos como auditados.

Verificación fresca: **313 pruebas Python y 82 JavaScript aprobadas**; un aviso conocido de deprecación TestClient/httpx. Las pruebas no cubrían los defectos nuevos siguientes. Las 82 pruebas focales ejecutadas por el auditor backend forman parte de esas 313, no se suman como pruebas nuevas.

## Evolución

| Etapa | Commits representativos | Entrega |
|---|---|---|
| Plan/requisitos | f9abaf2, 6d6229d | Arquitectura y objetivo empresarial |
| Piloto mecánico | c8f1f63..d0a43ab | Preparación, hashes, referencias separadas |
| Mobiliario paramétrico | c09a6f9 | Descarga/auditoría PlankAssembly |
| Demo/visor 0.3 | dab7ce5, 59623ef | Aplicación, revisión, visor y biblioteca |
| Piezas separadas 0.4 | 06cf51e, 164356b | Asociación de vistas/cantidades y reconstrucción |
| Mesa 0.5 | 4ba95e6, 9c0bb51, 23b8e01 | Programa generativo acotado y planos derivados |
| CAD/visión/cierre | 5241a86, 443e9f1, 10da225 | Adaptación selectiva y evidencia live |

## Implementado en la base

DXF → evidencia y geometría determinista → programa referenciado → revisión versionada → planos generales, por componente y despiece por ocurrencias en SVG/DXF → CSV, escena esquemática, explicaciones, costes y biblioteca geométrica/semántica. El perfil de mesa admite tapa y dos soportes laterales o cuatro patas; los bindings usan copy/add/subtract. El recorrido parts-only depende de asociación explícita y familias limitadas.

Existe evidencia guardada de proveedor real vectorial/visual y embeddings reales. No se repitieron llamadas pagadas durante la auditoría. Los fixtures demuestran mecanismos, no precisión industrial general ni ahorro empresarial.

## Hallazgos de la base

| Prioridad | Hallazgo | Evidencia e impacto |
|---|---|---|
| Alta | Eventos no atómicos | repository.append_event calcula MAX+1: 100 escrituras/20 hilos dieron 41 IntegrityError. Puede guardar una mutación sin evento y devolver 500 |
| Alta | Deadline no vinculante | Un límite de 10 ms aceptó respuesta tras 57 ms; falta comprobar después del proveedor |
| Alta | Trabajo persistido después del LLM | POST /runs síncrono pierde estado ante caída previa al guardado; sin idempotencia |
| Alta | Acceso e identidad no autenticados | reviewer_name viene del cliente; la base solo era apta para loopback |
| Alta | SSE no vivo | Se conecta después de POST; /events devuelve un historial finito |
| Alta | DIMENSION fuera de XY | Defpoints con Z=10 producen observación XY de 100 sin warning |
| Alta | ATTRIB perdido en extracción | Reader conserva atributo PART/QTY, pero ledger de textos/parts-only lo omite |
| Media | Recuperación no vincula cierre | recovered_dxf produce análisis needs_review, pero aceptar targets puede dar completed sin una decisión específica sobre recuperación |
| Media | Tolerancias incompatibles | Ensamble admite 0,1 mm; reconstrucción compara floats exactos y falla con +0,05 mm |
| Alta | Economía solo sintética | Catálogo fijo; trabajo/acabado siempre desconocidos, no permite presupuesto completo por esa vía |
| Media | Telemetría incompleta | Se descartan usage, response/model/call IDs y duración |
| Media | Seguimiento/interfaz | Sesiones restauradas sin conexión, eventos de mesa sin etiqueta, huecos de secuencia invisibles |
| Media | Revisiones humanas limitadas | Corrección de confirmaciones previas difícil; al extender, conservar evidencia fuente |
| Alta | Operación privada ausente | Sin imagen/configuración TLS, usuarios, backup/restore y CI verificados |

La severidad se refiere al uso compartido solicitado. El README de la base declaraba correctamente que era una demo local sin autenticación. La auditoría describe estado anterior: no acredita correcciones hasta verificar el incremento.

## Evaluación y datos

Los pilotos externos v1/v2 están obsoletos. V1 agrupa variantes de una pieza en el ZIP público. V2 separa casos, pero `agent_inputs/cases.json` conserva instrucciones que revelan respuestas esperadas: `read_dimensions_with_abstention` y qué espesor/cantidad faltan. El preparador actual neutraliza estos metadatos; los artefactos no se habían regenerado. No usarlos como evaluación ciega.

Las pruebas de catálogo de mesa seleccionan plantilla y aceptan premisas: validan cálculo/materialización, no descubrimiento libre. El oráculo económico privado no se contrasta con la tarifa real usada por ese runtime. La separación de referencias se comprueba dentro del proceso y por rutas/hashes; no constituye una frontera completa de permisos.

PlankAssembly aporta 26.707 modelos oficiales, pero la base no tenía adaptador 2D ni evaluación. La primera fila de planks es envolvente y algunos casos carecen de normal. CADBlock sirve de auxiliar sin BOM ni histórico económico anotado. No se ejecutaron scripts recibidos en ZIP ni se auditó cada binario.

## Pendientes empresariales

T11 tiene un mecanismo limitado de generación, sin validación en planos nuevos representativos. T12 tiene biblioteca y aritmética sintética, sin histórico empresarial coste/horas ni relevancia evaluada. T13 no tiene comparación con técnicos, tiempos de lectura ni aceptación medida.

El checklist histórico conserva 1/22 casillas T11–T13 marcada. **No es un porcentaje de producto implementado**: el plan no se actualizó al ritmo del código. El incremento solicitado aborda los huecos implementables: operación privada, economía configurable, revisión, fiabilidad y preparación/evaluación reproducible. Tarifas reales, planos del equipo, validación técnica y servidor/dominio son evidencias externas; no se sustituyen por fixtures.

## Documentación histórica

AGENTS, CLAUDE, initial-plan y documentos de arquitectura/contrato mantienen frases anteriores a la aplicación. Contratos 0.1 y planes amplios son históricos; README, contrato mesa 0.5 y verificaciones recientes describen mejor la base. Los registros personales mezclan checkpoints fechados que no deben interpretarse como estado actual.

El trabajo posterior se sigue en [plan de producción](superpowers/plans/2026-11-14-private-production.md) y su aceptación. Este informe preserva los hallazgos originales para contrastarlos con las correcciones.
