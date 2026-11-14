# Cierre de abstención evitable

## Identidad y autorización
Agente de IA `cierre_abstencion`, delegado por el agente raíz conforme a la solicitud explícita del usuario del 2026-11-14. No representa una identidad humana.

## Alcance y reservas
- Propiedad exclusiva durante este incremento: `backend/app/general_furniture/autonomous.py`, `backend/app/general_furniture/context_payload.py` si resulta necesario y pruebas autónomas relacionadas.
- Ampliación posterior: `backend/app/general_furniture/visual_evidence.py` y pruebas, para corregir el presupuesto de crops sin relajar límites.
- `backend/app/contratos/modelos.py` solo podrá modificarse tras acuerdo explícito con `cierre_corpus` (A) y aviso al agente raíz (C).
- No editar `provider/live.py`, propiedad de `cierre_pdf`, ni referencias privadas del corpus.
- Preservar semántica del runtime, incertidumbre honesta, validación dimensional y estados de hipótesis.

## Tarea
Investigar las trazas públicas de `.runtime/transcript-qa/blind20-paired`, distinguir desconocidos honestos, incompletitud global errónea, abstención de campos y fallos del proveedor, y corregir solo abstenciones evitables mediante pruebas rojo-verde.

## Dependencias / avisos
- Coordinar cualquier necesidad de salida adicional con `cierre_semantica`.
- Coordinar cualquier cambio de frontera del proveedor con `cierre_pdf`; este agente no escribirá ese archivo.
- No ejecutar ensayos de pago hasta autorización coordinada por el agente raíz.

## Estado
Corrección acotada implementada y pruebas focales verdes. Pendiente integrar, repetir suite conjunta cuando finalicen los cambios concurrentes de proveedor/PDF y atender, si A lo acuerda explícitamente, el delta contractual aditivo de montaje.

## Registro
- 2026-11-14: leídas reglas de repositorio, plan de cierre y registros de coordinación; creado este registro antes de editar producto.
- 2026-11-14: activados los flujos de depuración sistemática y TDD; pendiente reproducir el defecto con trazas no privadas.
- 2026-11-14: analizadas las 19 finales y el fallo de proveedor de `.runtime/transcript-qa/blind20-paired`, sin leer referencias privadas. Todas las finales tenían material/acabado abstained; seis además tenían al menos un campo geométrico desconocido/abstenido. El gate mezclaba completitud económica con aceptación geométrica y aceptaba checks cruzados no dirigidos al campo.
- 2026-11-14: TDD en `test_general_furniture_autonomous.py`: material/acabado honestamente desconocidos no borran geometría totalmente revisada; identidad entre proyecciones, montaje u otros faltantes estructurales siguen incompletos; campos geométricos desconocidos siguen incompletos; un check debe apuntar al target exacto; ocurrencias de cantidad exigen `quantity_basis` y `duplicate_scan` dirigidos a esa cantidad; prueba de frontera de proveedor conserva paquete derivado incompleto.
- 2026-11-14: `python -m pytest backend/tests/test_general_furniture_autonomous.py -q` → 21 passed. Reaplicación offline del clasificador a las 19 trazas públicas → 19 incomplete, coherente porque todas conservan además ambigüedad estructural; no se infló aceptación.
- 2026-11-14: intento amplio sobre 81 pruebas relacionadas → 79 passed, 2 fallos concurrentes en `general_furniture/live.py` ya propiedad de `cierre_pdf`; colección global también quedó temporalmente bloqueada por `ProviderError` durante cambios concurrentes del proveedor. No se editaron esos archivos.
- 2026-11-14: informado `cierre_semantica` de la interfaz real (roles/cantidades provisionales, sin grafo nativo) y solicitado a `cierre_montaje` constancia de acuerdo A antes de cualquier cambio contractual.
- 2026-11-14: A (`cierre_corpus`) y B acordaron el delta aditivo de montaje y se avisó a C (raíz) antes de editar contrato. `GeneralAssemblyRelation`/`GeneralAssemblyAlternative`, incluidos `hinged_to` hipotético y alternativas incompatibles, quedan cerrados por IDs, premisas y fuentes; no certifican mecanismos ni suman ocurrencias. La reparación autónoma conserva proposal/draft efectivos y no el snapshot inicial obsoleto.
- 2026-11-14: añadida reinspección dimensional acotada: solo para length/width/thickness `unknown+abstained` cuando existen segmentos métricos observados; expone como máximo 64 candidatos una sola vez y solicita una propuesta reparada con bindings. No se activa para quantity/material/finish ni sin evidencia y nunca acepta por sí sola.
- 2026-11-14: verificación final fresca `python -m pytest backend/tests/test_general_furniture_assembly_semantics.py backend/tests/test_general_furniture_autonomous.py backend/tests/test_general_furniture_proposal.py backend/tests/test_general_furniture_live.py -q` → 41 passed; `ruff check` sobre contrato/autonomía → clean; `git diff --check` sin errores (solo aviso de futura normalización LF→CRLF). Runtime congelado y comunicado a raíz antes del ensayo de pago.
- 2026-11-14: sx-016/017/018 del primer heldout fallaron antes del proveedor porque `_cad_artifacts` contaba todos los crops opcionales. Fuente previo archivado en `.runtime/poc-closure-code-v1/visual_evidence.py.before`, SHA-256 `B24A1BF8C9C89E83F3EE2380E79B22C5D5EC08C5B3F02B58C0A9AED2D80285E9`.
- 2026-11-14: fix v2 SHA-256 `A39661394A94CBFC67F493A246AB7281B6E3A1464BB41888B080F0162D1805EA`: overviews obligatorios primero; rechazo intacto si ellos exceden el presupuesto; slots restantes seleccionan crops por número de contornos y orden estable, con warning de truncación. Límites de vistas, artefactos, píxeles, PNG y dimensión intactos.
- 2026-11-14: visual evidence 7 passed, ruff/diff-check limpios. Replay público sx-013..018 sin proveedor: artefactos `1,3,3,4,4,4`; warnings sx-016 `3_of_4`, sx-017 `3_of_4`, sx-018 `3_of_6`. No se leyó oráculo.
