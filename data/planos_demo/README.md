# Fixture público de demo

Entradas propias y sintéticas de una estantería rectangular montada. Los DXF contienen solo vistas `FRONT`, `TOP` y `RIGHT`, geometría observable y pocas cotas generales. No contienen nombres de piezas, BOM, cantidades, materiales ni la construcción privada de referencia.

- `estanteria_montada.dxf`: caso de desarrollo con una observación corta visible, pero con montaje ambiguo que requiere confirmación humana.
- `estanteria_incompleta.dxf`: conserva las tres vistas y cotas generales, pero elimina la evidencia de espesor; el sistema debe mantenerlo desconocido.
- `mueble_demo_002.dxf`: misma familia observable, con dimensiones generales distintas.
- `mueble_demo_003.dxf`: mueble bajo con una sola división horizontal observable.
- `mueble_demo_unidades_desconocidas.dxf`: control de preview en coordenadas fuente sin unidad declarada.
- `mueble_demo_trapecio.dxf`: control de preview fuera del subconjunto rectangular, sin inferencia de piezas.
- `fixture_manifest.json`: procedencia y contrato público, sin respuesta de evaluación.

Regeneración desde la raíz:

```powershell
python -m tools.build_demo_fixture
```

Estas entradas prueban el mecanismo en desarrollo. No son un benchmark ciego ni acreditan precisión industrial.

