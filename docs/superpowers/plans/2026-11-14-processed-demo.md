# Datos procesados para demo

Solicitud: subir al repositorio muebles de prueba procesados y documentar su uso en producción.

Se empaquetan cuatro fixtures propios ya versionados: tres revisiones sintéticas de estantería y un control incompleto. Se usa el extractor y la API real con `geometry_only`, sin proveedor, en almacenamiento temporal. Los resultados JSON/CSV y un manifiesto identifican origen, revisión de ensayo y hashes. No se copia ninguna base de datos operativa ni se publican fixtures en la Biblioteca real.

1. Registrar continuidad en el archivo de coordinación autorizado.
2. Añadir prueba del generador: resultados con piezas, nulos del caso incompleto y rechazo de sobrescritura.
3. Implementar `tools/build_processed_demo.py` y generar `data/muebles_procesados_demo/`.
4. Documentar el recorrido en producción con los DXF originales y los exports de referencia; enlazar desde README.
5. Validar fixtures, comprobar diff, publicar la rama/PR y verificar CI antes de integrar.

Aclaraciones del usuario: solo datasets de muebles y PlankAssembly; resultados completos para la web app existente, sin visor HTML nuevo ni nuevas llamadas a una API de IA. La entrega usa backup nativo v2 restaurable, no una nueva ruta de importación. Los 19 registros públicos normalizados se precargan en history.sqlite3 y los tres muebles propios en biblioteca offline. El original PlankAssembly se ofrece aparte, sin modificar y con licencia/atribución.
