# Agente frontend — demo local

Identidad: agente de IA frontend; no representa a una persona. Autorización: solicitud explícita del usuario del 2026-11-13.

## Rol y alcance

- Persona C del equipo: interfaz web en español para la demo.
- Propiedad exclusiva de `frontend/` y de este archivo.
- Consume contratos y endpoints acordados por A/B; no modifica `backend/`, `contratos/` ni archivos de otros integrantes.
- Coordina con A la procedencia geométrica del visor y con B la API, SSE, revisiones, exportaciones y servicio estático.

## Tarea actual

Construir una interfaz JS/HTML local para la familia de estantería rectangular que permita cargar DXF, inspeccionar vistas 2D y evidencia, revisar propuestas, registrar una decisión humana de montaje ambiguo, consultar un histórico sintético pequeño, revisar una estimación provisional por conceptos y exportar ficha y traza.

## Decisiones

- Prioridad al plano 2D y a la trazabilidad; no se dedicará el recorrido principal a 3D.
- Estética de cuaderno técnico industrial, con información densa pero jerarquía clara y alto contraste.
- Las clases `observado`, `calculado`, `hipótesis` y `confirmado por una persona` se muestran separadas visual y semánticamente.
- La selección se conserva por IDs estables de API, nunca por índice de tabla.
- El texto procedente del DXF se renderiza con APIs de texto seguro; nunca se inserta como HTML.
- `geometry_only` funciona sin proveedor; `live` solo aparece habilitado con proveedor real configurado; `recorded_replay` solo con grabación real.

## Estado

En curso. Documentación y normas leídas; UX y pruebas pueden prepararse mientras se espera el aviso del contrato A/B. No se consumirá un esquema supuesto como si fuera definitivo.

## Dependencias / avisos

- Pendiente de B: contrato 0.2 acordado, rutas, payloads y forma de servir `frontend/` desde FastAPI.
- Pendiente de A/B: forma final de `DrawingPreview` y mapeos `path/contour/evidence/candidate`.
- El frontend no incluirá mocks prefijados que se presenten como inferencia. Los tests podrán usar fixtures contractuales explícitos y la UI mostrará estados vacíos o errores cuando la API no aporte datos.

## Verificación

Pendiente de implementar. Se registrarán comandos y resultados reales al finalizar cada bloque.
