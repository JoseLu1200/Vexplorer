# Plano, reconstrucción y similitud

Ampliación solicitada el 2026-11-13 sobre la demo integrada `40e5e40`.
Implementación integrada y comprobada localmente el 2026-11-14. La revisión final y el merge se registran en el archivo del coordinador.

## Recorrido implementado

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

## Aceptación

- [x] Cotas ancladas, unidades y selección bidireccional comprobadas en navegador.
- [x] Navegación por vistas, zoom, encuadre y capas.
- [x] Explicaciones con evidencia, fórmulas y desconocidos.
- [x] Escena por ocurrencias, revisión versionada y abstención ante datos insuficientes.
- [x] Biblioteca, diferencias, similitud y agrupación sobre variantes propias.
- [x] Embedding real y persistencia/caché comprobados con proveedor configurado.
- [x] Suite Python/JS y regresiones del recorrido anterior.
- [x] Revisión final GPT-6 Astra: SHIP, tras corrección de hallazgos.

## Evidencia observada

- Instalación: `python -m pip install -e '.[test]'` dentro del entorno virtual y `npm ci --prefix frontend`; Three.js 0.187.0 servido localmente y Pillow 12.3.0 declarado. Backend/frontend arrancados con el comando del README en puerto 8765.
- Navegador: carga real del DXF propio, cuatro cotas legibles, tres vistas, selección de baldas y evidencia; revisión 2 con espesor 18, largos derivados 864 mm; CAD original SVG cargado; reconstrucción WebGL de seis tableros y conservación de sesión tras recarga. Se corrigieron módulo Three.js ausente, coordenadas mínimo/centro, bloqueo de redimensionado y respuestas asíncronas obsoletas.
- Aceptación independiente: escena con volumen manual de 31.622.400 mm³; unidades desconocidas, plano no rectangular visible sin inferencia, referencia privada aislada, descriptor invariante al desplazamiento y exportación completa.
- Proveedor real: tres embeddings generados con `text-embedding-3-small`, 256 dimensiones. El control trasladado reutilizó la caché del original; repetir el guardado también devolvió caché. No se usó replay ni respuestas prefijadas.
- Similitud real: original/control trasladado 1.0; variante 002 aproximadamente 0.999049; estantería baja 003 aproximadamente 0.998864. Con umbral semántico 0.97, los cuatro casos forman un grupo de la misma familia. El ranking geométrico fue 1.0, 0.944135 y 0.817315. Son comprobaciones de mecanismo, no evaluación de relevancia empresarial.
- Interfaz de biblioteca: consultas geométricas y semánticas, agrupación con miembros/etiquetas y umbral explícito. Una puntuación alta no confirma construcción, cantidad ni precio.
- La subida de archivos del conector Chrome rechazó la ruta local por su configuración de raíces. Para el ensayo se pasaron los bytes del DXF propio a un `File` del navegador y se ejecutó el formulario normal; no se sustituyó la API ni su resultado.

La suite final y la aceptación de Astra se anotan en [el cierre del coordinador](../team/agente_coordinador.md). Se conserva el aviso conocido de deprecación TestClient/httpx; los DXF generados mantienen el whitespace propio del formato.
