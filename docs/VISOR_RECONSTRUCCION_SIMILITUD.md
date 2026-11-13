# Plano, reconstrucción y similitud

Ampliación solicitada el 2026-11-13 sobre la demo integrada `40e5e40`.
Este documento describe el alcance acordado por coordinación. Mientras la verificación figure pendiente, no representa una capacidad comprobada.

## Recorrido previsto

1. Cargar un DXF propio y explorar todas sus vistas, o aislar alzado, planta y lateral.
2. Leer cotas sobre el dibujo, activar capas y navegar con encuadre, desplazamiento y zoom.
3. Seleccionar una propuesta o su evidencia y consultar medidas, unidades, fórmulas, premisas e incógnitas.
4. Registrar la decisión constructiva y obtener una escena de ocurrencias físicas vinculada a esa revisión.
5. Explorar la reconstrucción con órbita y selección, diferenciando geometría esquemática y datos observados.
6. Guardar el mueble en la biblioteca local, crear un descriptor y comparar otras entradas propias.
7. Generar embeddings semánticos con proveedor configurado o usar similitud geométrica explícitamente identificada sin proveedor.
8. Conservar la revisión, ficha, estimación y traza del recorrido anterior.

## Decisiones

- Espacio de trabajo técnico JS/HTML servido por FastAPI, con dibujo como superficie principal.
- Pydantic como autoridad contractual. A/B acuerdan extensiones antes de código y avisan a C/D; B es el único escritor.
- Reconstrucción de la familia rectangular ya admitida. No reconstrucción arbitraria desde cualquier imagen, ni certificación de fabricación.
- Sin espesores típicos, piezas ocultas o materiales añadidos automáticamente. Posición y montaje son premisas trazables.
- Descriptor independiente de handles, posición del plano, nombre del archivo y referencia del evaluador. Las dimensiones desconocidas conservan ese estado.
- Vector geométrico y embedding semántico son representaciones diferentes. La similitud es una ayuda para explorar; no una probabilidad ni una garantía constructiva o económica.
- Embeddings reales mediante la [API oficial](https://developers.openai.com/api/docs/guides/embeddings), con modelo y tamaño identificados, caché y rechazo de vectores incompatibles. Las pruebas simuladas se identifican como pruebas de frontera.
- Entradas y variantes propias para integración. PlankAssembly y sus derivados permanecen fuera de esta entrega.

## Aceptación pendiente

- [ ] Cotas ancladas, unidades y selección bidireccional comprobadas en navegador.
- [ ] Navegación por vistas, zoom, encuadre y capas.
- [ ] Explicaciones con evidencia, fórmulas y desconocidos.
- [ ] Escena por ocurrencias, revisión versionada y abstención ante datos insuficientes.
- [ ] Biblioteca, diferencias, similitud y agrupación sobre variantes propias.
- [ ] Embedding real y persistencia/caché comprobados cuando el proveedor esté disponible.
- [ ] Suite Python/JS y regresiones del recorrido anterior.
- [ ] Revisión final GPT-6 Astra y corrección de hallazgos.

Las cifras, comandos y límites finales se actualizarán con las pruebas efectivamente ejecutadas.
