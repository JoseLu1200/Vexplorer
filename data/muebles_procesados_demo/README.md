# Muebles ya procesados para la web app

Restaurar `demo-runtime.zip` con `python -m tools.backup restore`. Es un backup nativo v2, no un ZIP de entrada para «Cargar plano». Contiene cuatro ejecuciones, originales, evidencias, revisiones, tres muebles de ensayo en la biblioteca geométrica y 19 registros económicos publicados. No necesita API de IA, embeddings nuevos ni reprocesamiento.

La [guía de demo](../../docs/DEMO_DATOS_PROCESADOS.md) incluye arranque, enlaces de cada ejecución y uso en el host productivo. El [catálogo de descargas](../../docs/DATASETS_DESCARGA_DIRECTA.md) ofrece los paquetes completos sin HF.

Cada carpeta conserva `fuente.dxf`, `drawing.json`, `ledger.json`, `revision_inicial.json`, `resultado.json` y `despiece.csv`. Los casos completos añaden `revision_ensayo.json` y `similitud_geometrica.json`. `resultado.json` incluye despiece, escena 3D esquemática, explicaciones, descriptor, comparables, estimación y eventos. Las fechas e IDs pertenecen a esta instantánea y no se deben confundir con IDs del servicio público.

Los cuatro planos son fixtures propios **sintéticos**. Las revisiones y tarifas son decisiones de ensayo. El caso incompleto conserva `needs_review` y no inventa piezas. Los 19 registros publicados tienen su atribución y limitaciones en `data/datasets/`: presupuestos y coeficientes publicados, no órdenes reales cerradas. PlankAssembly se distribuye aparte y no forma parte de estos resultados.

Regenerar, solo si se necesitan resultados nuevos, desde la raíz del repo:

```console
python -m tools.build_processed_demo --output .runtime/demo-nueva
```

El destino debe ser nuevo. La generación usa almacenamiento temporal y proveedor desactivado; no toca la base operativa. No se necesita ejecutar este comando para mostrar la instantánea incluida.
