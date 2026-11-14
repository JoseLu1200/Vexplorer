# Agente replay PR1 — adaptación productiva

## Identidad y autorización

- Identidad: agente de IA de replay/harness; no representa a una persona.
- Autorización: delegación explícita del coordinador del 2026-11-14 sobre snapshot `056ec71`.
- Rol: adaptar el bloque replay y `comparar_candidatas` de PR1 al producto privado, sin trasplantar el árbol legado.

## Alcance y reservas

- Propiedad: `backend/app/agente/*`, `backend/app/main.py`, `backend/app/servicios/repository.py`, `backend/app/herramientas/tools.py`, pruebas nuevas de replay/comparación y, por transferencia explícita tras el cierre de economía, `backend/app/contratos/modelos.py`.
- Fuera de alcance: frontend, ingesta, geometría, validador y despliegue.
- Sin commits ni llamadas de red/proveedor pagado; el coordinador integra y verifica el conjunto.

## Contrato A/B cerrado antes de código

- Aceptadas las cuatro condiciones de A: replay sólo desde un live real e inmutable; compatibilidad 0.5/0.6; comparación estricta por revisión y dos IDs; ningún cambio CAD/union-find/paperspace en este bloque.
- `CompareCandidatesArgs` exige `candidate_revision` y exactamente dos IDs distintos.
- `RunSnapshot` añade modo `recorded_replay` y procedencia verificable del live fuente; el cliente no puede subir ni seleccionar grabaciones.
- Geometría sigue siendo autoridad. Replay recalcula tool outputs y rechaza cualquier divergencia de transcript, entrada, configuración, schema, registry o artefacto visual.

## Dependencias y avisos

- A geometría recibió y aceptó la forma contractual antes de editar.
- C frontend fue avisado de jobs durables, 409 por ausencia y procedencia visible; se enviará el payload final tras pruebas verdes.
- El agente CAD paralelo no toca estas rutas salvo `pyproject.toml`, fuera de esta reserva.

## Estado

- Implementación terminada por TDD, sin commits.
- Replay: transcript request/response por hashes, metadatos seguros, tool outputs recalculados, fingerprint de documento/ledger/config/prompt/schema/registry/visión y output terminal; SQLite es la fuente autoritativa y el live run + recording se confirman en una transacción.
- Tres runners cubiertos, incluida identidad del PNG visual; jobs durables locales y producción autenticada; 409 por ausencia/divergencia; procedencia del live fuente en snapshot/eventos.
- Cuota total real configurable: `VEXPLORER_RECORDING_MAX_COUNT` (1000 por defecto) y `VEXPLORER_RECORDING_MAX_BYTES` (256 MiB por defecto). Cada live reserva conservadoramente el máximo de 4 MiB antes del proveedor; SQLite serializa admisión, el commit del run consume la reserva atómicamente y errores/reinicio la liberan. No se eliminan grabaciones existentes ni referenciadas. `/config` desactiva live y explica mantenimiento/ampliación de cuota cuando no cabe otra reserva; el gate transaccional previo a proveedor sigue siendo autoritativo.
- `comparar_candidatas`: schema común estricto, revisión exacta, dos IDs distintos y handlers conservadores separados para legacy/parts/table; sin tolerancias nuevas ni cifras del modelo.
- Hallazgo Astra adicional corregido: IDs no nulos de confirmación únicos por request y owner map actualizado dentro del lote, con defensa de repositorio ante modelos legacy/bypass.
- Verificación focal integrada final: 75 pruebas aprobadas en 14,95 s sobre tests nuevos, harness, API legacy/parts/table, jobs, auth y repositorio privado. `compileall` y `git diff --check` pasan; sólo aparecen avisos de normalización LF→CRLF del worktree.
