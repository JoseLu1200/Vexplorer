# Protocolo de evaluación con técnicos

## Alcance de la evidencia

El protocolo mide el trabajo necesario para convertir un plano en una ficha aceptable. Registra piezas omitidas, correcciones, tiempo activo y error de coste u horas. El scorer publica agregados y omite identificadores de participantes, revisores y casos.

El repositorio no contiene sesiones observadas de técnicos ni planos empresariales. Los fixtures de pruebas llevan `evidence_kind: developer_fixture` y `actual_technicians_observed: false`. Solo una recogida ejecutada con participantes reales puede usar `observed_technician_study`.

`evaluation/technician_study.py` procesa la colección. `tools/evaluate_technician_study.py` ofrece la interfaz de línea de comandos:

```powershell
.venv\Scripts\python.exe -m tools.evaluate_technician_study `
  --input D:\private\technician-study.frozen.json `
  --output .runtime\evaluation\technician-study-report.json
```

El comando rechaza la misma ruta como entrada y salida. Escribe el informe mediante reemplazo atómico.

## Preparación de casos

La empresa selecciona planos autorizados antes de ejecutar el estudio. Cada caso declara proyecto, familia, grupo de duplicados, split y SHA-256 de los bytes entregados al participante. Un proyecto, familia o grupo de duplicados no puede cruzar splits.

La selección debe cubrir la variedad que la empresa espera procesar: familias, calidad documental y dificultad. Las variantes del mismo mueble permanecen dentro del mismo grupo. El equipo congela los casos, el protocolo y la configuración del producto antes de puntuar.

Un técnico participa una sola vez por caso. El estudio asigna condiciones `manual` y `assisted` entre participantes y casos. El protocolo previo a la recogida define:

- qué campos forman una ficha aceptable;
- cuándo inicia y termina el cronómetro;
- cómo registrar pausas;
- qué fuentes puede consultar cada condición;
- quién revisa la ficha y cómo resuelve desacuerdos.

El revisor usa un identificador distinto del participante. `reviewer_blinded_to_condition` registra si el revisor desconocía la condición. El informe cuenta estas sesiones y no convierte esa marca en una garantía de independencia.

## Registro de correcciones

Cada sesión conserva la duración total, las interrupciones, la aceptación y las correcciones observadas. El scorer admite estas clases:

- `missing_piece_added` y `extra_piece_removed`;
- `quantity_changed` y `dimension_changed`;
- `material_changed` y `finish_changed`;
- `assembly_changed`, `operation_changed` y `other`.

Cada evento declara `count` positivo y severidad `minor`, `major` o `critical`. `missing_piece_added` mide ocurrencias que faltaban antes de la revisión. El scorer no interpreta este recuento como recall de una BOM oculta. Para medir precisión y recall por ocurrencia se debe ejecutar también `tools.evaluate_cases` contra una referencia adjudicada y separada.

El scorer excluye sesiones con uno de estos motivos: `procedure_interrupted`, `technical_failure`, `invalid_assignment`, `participant_withdrew` o `unusable_source`. El informe conserva el número de exclusiones por motivo. Una sesión no aceptable sin motivo de exclusión permanece en el denominador de aceptación; su duración no entra en tiempo hasta ficha aceptable.

## Coste y horas

Cada observación económica apunta a un caso y clasifica la referencia como `actual`, `budget` o `quote`. Coste y horas usan pares separados de referencia y predicción.

El coste exige valor, moneda, alcance y fecha efectiva compatibles. Las horas exigen valor y alcance compatibles. El scorer descarta del error cada par con metadatos incompatibles y reduce la cobertura. El informe publica MAE, mediana del error absoluto, sesgo medio, MAPE para referencias distintas de cero y WAPE. También publica cuántas referencias y evaluaciones pertenecen a cada clase.

Un presupuesto académico sigue siendo `budget`. Una orden de trabajo cerrada con coste ejecutado puede usar `actual` si la fuente documenta el alcance. El protocolo no mezcla monedas, fechas ni alcances mediante conversiones implícitas.

## Contrato de colección

Este ejemplo muestra la forma mínima. Los hashes y valores son ilustrativos.

```json
{
  "schema_version": "1.0",
  "study": {
    "id": "pilot-company-2026-12",
    "protocol_id": "tech-study-v1",
    "evidence_kind": "observed_technician_study",
    "source_kind": "company_authorized",
    "actual_technicians_observed": true,
    "frozen_before_scoring": true
  },
  "cases": [{
    "id": "opaque-case-001",
    "split": "test",
    "project_id": "opaque-project-001",
    "family_id": "cabinet",
    "duplicate_group_id": "opaque-group-001",
    "plan_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }],
  "sessions": [{
    "id": "opaque-session-001",
    "case_id": "opaque-case-001",
    "participant_id": "participant-001",
    "condition": "assisted",
    "reviewer_id": "reviewer-001",
    "reviewer_blinded_to_condition": true,
    "duration_seconds": 1260,
    "interruption_seconds": 60,
    "acceptable": true,
    "corrections": [{
      "kind": "missing_piece_added",
      "count": 1,
      "severity": "major"
    }]
  }],
  "economics": [{
    "case_id": "opaque-case-001",
    "reference_kind": "actual",
    "cost": {
      "reference": {
        "value": 520,
        "currency": "EUR",
        "scope_id": "manufacturing-v1",
        "effective_date": "2026-12-01"
      },
      "prediction": {
        "value": 500,
        "currency": "EUR",
        "scope_id": "manufacturing-v1",
        "effective_date": "2026-12-01"
      }
    },
    "hours": {
      "reference": {"value": 9.5, "scope_id": "shop-hours-v1"},
      "prediction": {"value": 8.75, "scope_id": "shop-hours-v1"}
    }
  }]
}
```

## Interpretación

El informe separa `manual` y `assisted`. Para cada condición publica aceptación, tiempo activo hasta aceptación, correcciones, piezas añadidas y piezas retiradas. `descriptive_difference` resta la media manual a la asistida.

`savings_claim_supported` permanece en `false`. Una diferencia observada describe la muestra recogida. La empresa necesita una asignación controlada y un análisis acordado antes de atribuir la diferencia al producto o extrapolarla al equipo.

El informe no copia filas ni identificadores. La empresa conserva la colección original en un directorio privado con control de acceso y política de retención. Los IDs de participantes y revisores deben ser seudónimos; la tabla que los relacione con personas queda fuera del paquete de evaluación.

## Evidencia local disponible

La ejecución del 2026-11-14 reprodujo dos informes Blind20 desde predicciones congeladas y referencias privadas:

- baseline: `.runtime/evaluation-hallazgos/blind20-baseline-rerun.json`, SHA-256 `aeee1b68e563f6a8ad985557f6368491effecf54600f6e602a94ee4b57b7b662`;
- final: `.runtime/evaluation-hallazgos/blind20-final-rerun.json`, SHA-256 `1e420480e462d176639fb6c923a3f836716c8cd64ad8f21778bf98ba91072340`.

Ambos hashes coinciden con los informes anteriores. Blind20 contiene inferencia live sobre PlankAssembly paramétrico. Su `evidence_kind` es `development_diagnostic`; no contiene sesiones de técnicos, tiempos, costes ni horas compatibles.

La misma ejecución recalculó los cuatro folds económicos públicos desde el artefacto congelado y el fichero fuente cuyo hash declara el protocolo. El recibo vive en `.runtime/evaluation-hallazgos/public-economic-lopo-rerun.json`, SHA-256 `77291734d25eb5f535edc4b335a0b408f53b80effce6ece56ae54c634783f8c8`. Reproduce coste MAE 48,82 PLN y horas MAE 0,46775. Los cuatro registros son presupuestos de una publicación académica, no costes ejecutados de ERP.
