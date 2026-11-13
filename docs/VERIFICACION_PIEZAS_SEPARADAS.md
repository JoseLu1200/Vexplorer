# Verificación del recorrido desde piezas separadas

Estado: **integración en curso**. Esta comprobación corresponde al nuevo requisito confirmado el 14/11/2026: DXF 2D de piezas separadas, sin montaje completo ni modelo 3D como entrada. La [auditoría anterior](AUDITORIA_APP_2026-11-14.md) permanece ligada a `dab7ce5`.

## Ya observado en el motor integrado

Se ejecutaron `extract_drawing(..., input_kind="separated_part_views")` y `extract_separated_parts(...)` sobre los DXF públicos propios, sin abrir referencias privadas:

| Caso | Observación |
|---|---|
| `piezas_completo.dxf` | Nueve vistas, tres observaciones K1/K2/K3, cantidad 2 en cada una: seis ejemplares, no nueve |
| Pieza K1 | 1200 × 300 × 18 mm, trazada al plano |
| Piezas K2/K3 | 864 × 300 × 18 mm, trazadas al plano; los identificadores no aportan funciones de montaje |
| Cantidad ausente | K3 conserva cantidad `null`, dimensiones completas y estado parcial |
| Espesor ausente | K3 conserva espesor `null`; siete vistas en la entrada, sin inventar las dos vistas ausentes |
| Sin identificadores | Tres observaciones ambiguas separadas; no se fusionan ni se deduce cantidad de sus vistas |

Pruebas geométricas de integración ejecutadas tras `a646290`: **11 pasan**. Esto verifica extracción y casos cubiertos de candidatas; no acredita todavía el recorrido completo ni todos los montajes producidos. Se está revisando la compatibilidad de baldas con el hueco disponible en cada alternativa.

## Pendiente para aceptación

- API real con el nuevo `input_kind`, revisiones y errores de entrada.
- Navegador: piezas/vistas/cotas/explicación, revisión, escena y conservación de incógnitas.
- Harness live nuevo con herramientas referidas a observaciones/candidatos, sin medidas generadas por el modelo.
- Descriptor v2 y embeddings reales; invariancia a identificadores/traslación y sensibilidad al espesor.
- Exportación y cálculo sintético por ejemplares, sin duplicar vistas.
- Suite integrada final, revisión GPT-6 Astra y guion README reproducible.

Los resultados incompletos, montajes incompatibles y casos no identificables se documentarán expresamente; no se reemplazarán por una respuesta prefijada.
