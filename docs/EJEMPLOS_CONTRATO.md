# Ejemplos documentales del contrato

> **Alcance actualizado:** las referencias a P0 y al contrato 0.1.0 describen el hito técnico T1–T10. La prueba de concepto completa exige además T11–T13: inferencia desde planos pobres, histórico y estimación. Véase [CASO_DE_USO_Y_EVALUACION](CASO_DE_USO_Y_EVALUACION.md). Las ampliaciones siguen pendientes de implementación y acuerdo de contratos.

**Propuesta pendiente de acuerdo A/B y aviso C.** Los modelos Pydantic futuros serán la única fuente de verdad. Estos ejemplos explican relaciones y estados; no son salidas ejecutadas de Vexplorer ni datos del corpus recibido.

## Escenario y oráculo manual

Un panel de 600 × 400 × 18 mm está dibujado en tres proyecciones ortogonales: frontal 600 × 400, superior 600 × 18 y lateral 18 × 400. Para este ejemplo la asociación está confirmada manualmente como una sola ocurrencia. Su función dentro de un mueble no se conoce, por eso el rol sigue `unknown`. Cambiar esa asociación por una deducción geométrica sin evidencia invalidaría la cantidad confirmada.

Los puntos de cada contorno están en su marco de vista. No se superponen para evaluar colisión ni para montar un sólido exacto. Los hashes de ceros y handles de ejemplo son marcadores sintéticos. La futura prueba del lector deberá crear un DXF propio y compararlo con un oráculo independiente.

## Libro de evidencias

```json
{
  "schema_version": "0.1.0",
  "candidate_revision": "rev-synthetic-panel-001",
  "synthetic": true,
  "document": {
    "document_id": "doc-synthetic-panel",
    "input_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "normalized_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "original_format": "DXF",
    "source_unit": "mm",
    "effective_unit": "mm",
    "unit_origin": "document",
    "unit_scale_to_mm": 1.0,
    "conversion": {
      "status": "not_required",
      "converter": null,
      "version": null
    },
    "entity_count": 3
  },
  "entities": [
    {
      "id": "ent-front",
      "layout": "Model",
      "handle": "F1",
      "insert_path": [],
      "entity_type": "LWPOLYLINE",
      "layer": "PANELS",
      "source_to_document_transform": [
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1
      ]
    },
    {
      "id": "ent-top",
      "layout": "Model",
      "handle": "F2",
      "insert_path": [],
      "entity_type": "LWPOLYLINE",
      "layer": "PANELS",
      "source_to_document_transform": [
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1
      ]
    },
    {
      "id": "ent-side",
      "layout": "Model",
      "handle": "F3",
      "insert_path": [],
      "entity_type": "LWPOLYLINE",
      "layer": "PANELS",
      "source_to_document_transform": [
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        1
      ]
    }
  ],
  "views": [
    {
      "id": "view-front",
      "label": "front",
      "orientation_status": "confirmed",
      "projection": "orthographic",
      "frame_id": "frame-front",
      "alignment_group_id": "alignment-panel-001"
    },
    {
      "id": "view-top",
      "label": "top",
      "orientation_status": "confirmed",
      "projection": "orthographic",
      "frame_id": "frame-top",
      "alignment_group_id": "alignment-panel-001"
    },
    {
      "id": "view-side",
      "label": "side",
      "orientation_status": "confirmed",
      "projection": "orthographic",
      "frame_id": "frame-side",
      "alignment_group_id": "alignment-panel-001"
    }
  ],
  "contours": [
    {
      "id": "cont-front",
      "view_id": "view-front",
      "source_entity_ids": [
        "ent-front"
      ],
      "closed": true,
      "geometry_type": "rectangle",
      "points_mm": [
        [
          0,
          0
        ],
        [
          600,
          0
        ],
        [
          600,
          400
        ],
        [
          0,
          400
        ]
      ]
    },
    {
      "id": "cont-top",
      "view_id": "view-top",
      "source_entity_ids": [
        "ent-top"
      ],
      "closed": true,
      "geometry_type": "rectangle",
      "points_mm": [
        [
          0,
          0
        ],
        [
          600,
          0
        ],
        [
          600,
          18
        ],
        [
          0,
          18
        ]
      ]
    },
    {
      "id": "cont-side",
      "view_id": "view-side",
      "source_entity_ids": [
        "ent-side"
      ],
      "closed": true,
      "geometry_type": "rectangle",
      "points_mm": [
        [
          0,
          0
        ],
        [
          18,
          0
        ],
        [
          18,
          400
        ],
        [
          0,
          400
        ]
      ]
    }
  ],
  "evidence": [
    {
      "id": "ev-front",
      "kind": "geometry",
      "source_entity_ids": [
        "ent-front"
      ],
      "description": "Ejemplo sintético: contorno de la vista front; no se ha leído un archivo CAD real."
    },
    {
      "id": "ev-top",
      "kind": "geometry",
      "source_entity_ids": [
        "ent-top"
      ],
      "description": "Ejemplo sintético: contorno de la vista top; no se ha leído un archivo CAD real."
    },
    {
      "id": "ev-side",
      "kind": "geometry",
      "source_entity_ids": [
        "ent-side"
      ],
      "description": "Ejemplo sintético: contorno de la vista side; no se ha leído un archivo CAD real."
    },
    {
      "id": "ev-association",
      "kind": "view_association",
      "source_entity_ids": [
        "ent-front",
        "ent-top",
        "ent-side"
      ],
      "description": "Asociación manual de este ejemplo: tres vistas ortogonales de una sola ocurrencia física del conjunto de ensayo, que contiene únicamente este panel."
    }
  ],
  "measurements": [
    {
      "id": "m-length",
      "kind": "length",
      "value_mm": 600.0,
      "origin": "geometry",
      "status": "verified",
      "frame_id": "frame-panel-001",
      "evidence_ids": [
        "ev-front"
      ],
      "dependency_ids": [],
      "derivation": null
    },
    {
      "id": "m-width",
      "kind": "width",
      "value_mm": 400.0,
      "origin": "geometry",
      "status": "verified",
      "frame_id": "frame-panel-001",
      "evidence_ids": [
        "ev-front"
      ],
      "dependency_ids": [],
      "derivation": null
    },
    {
      "id": "m-thickness",
      "kind": "thickness",
      "value_mm": 18.0,
      "origin": "geometry",
      "status": "verified",
      "frame_id": "frame-panel-001",
      "evidence_ids": [
        "ev-side"
      ],
      "dependency_ids": [],
      "derivation": null
    }
  ],
  "observations": [
    {
      "id": "obs-front",
      "view_id": "view-front",
      "contour_ids": [
        "cont-front"
      ]
    },
    {
      "id": "obs-top",
      "view_id": "view-top",
      "contour_ids": [
        "cont-top"
      ]
    },
    {
      "id": "obs-side",
      "view_id": "view-side",
      "contour_ids": [
        "cont-side"
      ]
    }
  ],
  "candidates": [
    {
      "id": "cand-panel-001",
      "observation_ids": [
        "obs-front",
        "obs-top",
        "obs-side"
      ],
      "entity_level": "part",
      "hypothesis_set_id": null,
      "identity_status": "confirmed",
      "frame_id": "frame-panel-001",
      "identity_evidence_ids": [
        "ev-association"
      ],
      "dimension_options": {
        "length": [
          "m-length"
        ],
        "width": [
          "m-width"
        ],
        "thickness": [
          "m-thickness"
        ]
      },
      "placement": null
    }
  ]
}
```

## Argumentos de la herramienta final

```json
{
  "schema_version": "0.1.0",
  "candidate_revision": "rev-synthetic-panel-001",
  "pieces": [
    {
      "id": "piece-001",
      "name": "Panel rectangular",
      "entity_level": "part",
      "role": "unknown",
      "label_status": "unknown",
      "candidate_ids": [
        "cand-panel-001"
      ],
      "quantity": 1,
      "dimension_refs": {
        "length": "m-length",
        "width": "m-width",
        "thickness": "m-thickness"
      },
      "source_contour_ids": [
        "cont-front",
        "cont-top",
        "cont-side"
      ]
    }
  ],
  "dispositions": []
}
```

El servidor resolvería `length=600`, `width=400`, `thickness=18` desde las referencias; el agente no envía esos números como autoridad. `quantity=1` depende de la asociación manual de la ocurrencia y no del número de vistas. El rol desconocido no equivale a identidad desconocida.

## Variantes que deben comprobar los tests futuros

| Variación | Comportamiento esperado |
|---|---|
| Eliminar evidencia y opción de espesor | `thickness=null`, revisión; no sólido completo |
| Quitar confirmación de asociación | Cantidad desconocida; no contar tres piezas |
| Introducir ID de medida inexistente | Rechazo por referencia inválida |
| Añadir otra ocurrencia realmente distinta y equivalente | Cantidad 2 solo tras evidencia de identidad y agrupación |
| Agotar presupuesto con ledger íntegro | Abstención del servidor y resultado revisable |
| Ledger vacío válido | Listas vacías, R-018 en revisión, nunca `completed` |

Estos ejemplos se pueden parsear como JSON. Eso solo verifica sintaxis: la aprobación del modelo de datos y las pruebas geométricas siguen pendientes.

## Relación con el nuevo corpus descargado

El panel y los mensajes de este documento siguen siendo ejemplos propios y sintéticos; no se han extraído de [PlankAssembly](PLANKASSEMBLY.md). La descarga no convierte estos ejemplos en una ejecución ni aprueba el contrato. Para futuros ejemplos de ese corpus, mantener su programa como referencia privada, excluir la envolvente del recuento y no publicar coordenadas reservadas dentro del contexto del agente. Cualquier cambio del contrato mantiene el acuerdo A/B y aviso C.
