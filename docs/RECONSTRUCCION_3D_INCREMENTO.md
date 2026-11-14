# Reconstrucción paramétrica: aclaraciones y cotas

Fecha: 2026-11-14. Continuación de la investigación Idol en `feat/reconstruction-3d`.

## Qué añade

El montaje por componentes ya existente puede recibir respuestas a sus preguntas, cambios de uso y cotas generales (anchura, profundidad, altura). Cada actualización crea una versión nueva y conserva la anterior. Las respuestas anteriores siguen editables aunque el modelo deje de preguntar por ellas.

El servidor reutiliza la imagen y el contexto público congelados, comprobando sus hashes antes de inferir. Las cotas del usuario se comprueban contra la envolvente del montaje con tolerancia diagnóstica de 0,5 mm. Si incumple, se solicita reparación; si persiste, el trabajo falla sin publicar artefactos finales. El modelo también puede abstenerse.

Las declaraciones humanas no se reclasifican como observaciones del dibujo. Cada exportación incluye `revision.json`, con fuente, padre, revisión, aclaraciones, cotas y propuesta. `proposal.json` conserva su formato anterior. Se mantienen GLB, BOM y planos SVG/DXF del diseño propuesto.

## Integración con el overhaul existente

Durante la ejecución se probó inicialmente el visor aislado del estudio. El usuario señaló correctamente que ya existía un overhaul posterior. Se corrigió la base de interfaz antes de entregar:

- Se incorporaron, sin modificar el árbol original, los archivos UX del checkout principal: fuentes Geist/Geist Mono, tokens, layout, interacciones, tema, visor y pruebas. Son trabajo anterior, no un rediseño de este incremento.
- La procedencia y hashes de los archivos capturados están en `reconstruction3d-ux-source.json`. El contenido fuente seguía intacto al verificarlo.
- Se conservaron las mejoras semánticas que ya tenía esta rama al combinar `app.js`.
- «Construcción 3D» se abre dentro del espacio de trabajo, con el plano activo conservado, tema compartido y regreso por botón/Escape. Se corrigió un solape detectado por Playwright trasladando la acción a la barra del visor.
- La navegación a versiones anteriores conserva el modo integrado y la identidad del run.

La documentación anterior indicaba localhost:8771 como instancia del overhaul; durante esta comprobación no respondía. Instancia de integración separada: **http://127.0.0.1:8875/**. No se modificó ni se desplegó el VPS ni el árbol principal.

## Verificación

- Suite Python tras correcciones: **737 aprobadas**, 72,13 s.
- Suite frontend tras integración UX: **172 aprobadas**.
- Ruff del módulo y sus pruebas sin errores.
- Revisión independiente del ciclo: dos hallazgos importantes corregidos con RED→GREEN (corregir declaraciones heredadas y exportar procedencia).
- Revisión adicional del alcance UX solicitado: un hallazgo importante corregido con RED→GREEN (historial perdía embedded/run).
- Navegador: carga real de DXF general, abrir/cerrar panel, fuente Geist, tema oscuro, foco al volver, Escape desde iframe, despiece 3D. A 390×844 no se detectó desbordamiento horizontal de página ni iframe.

Dos pruebas reales, distintas del benchmark congelado:

1. Alzado sin escala: el modelo se abstuvo y preguntó uso/montaje. Aclaraciones de prueba redactadas por el agente (no datos del usuario ni referencia privada) pidieron una mesa autoportante de 1200×600×750 mm. Generó cinco componentes con esa envolvente, dejando materiales, cargas y uniones pendientes. Tiempo del hijo: 45,80 s.
2. Desde la UI integrada se cargó `mesa_demo_001.dxf` como mueble general y se pidió una mesa autoportante. El modelo produjo cuatro componentes, sin solapes, desconexiones del suelo ni elementos bajo el suelo según el diagnóstico geométrico, en 42,62 s. Esto no comprueba resistencia ni recupera necesariamente la construcción original.

En ese segundo recorrido se refinó de nuevo desde el formulario con envolvente 1200×700×750 mm: revisión hija completada en 46,50 s, manifiesto de procedencia descargable y padre conservado. Se navegó al padre dentro del iframe y se comprobó embedded=1, run conservado y cierre con Escape devolviendo foco a «Construcción 3D».

Evidencias externas: `D:/Vexplorer-idol-study/refinement-v1/`, con trabajos persistidos, logs, capturas y scripts de arranque locales. Los datos del benchmark anterior no se sobrescribieron.

## Límites

- Se siguen proponiendo cuboides ortogonales; no hay edición CAD de uniones, curvas o mecanizados.
- Los parámetros explícitos de esta UI son cotas generales, no un editor arbitrario de cada pieza ni un solver CAD completo.
- Sin escala original ni cota humana, la salida sigue siendo relativa. Una cota humana no confirma el resto de dimensiones.
- No se amplían contratos compartidos, costes, precios ni tarifas; el nuevo BOM es una propuesta para revisar.
- Diez refinamientos por cadena y 32 respuestas efectivas. Los trabajos antiguos sin contexto congelado se consultan, pero deben regenerarse para refinarlos.
- Detalle menor diferido por revisión: el fallo tras agotar reparaciones de envolvente se informa como fallo genérico de propuesta; todavía no detalla en pantalla el eje incumplido.
- Los hashes detectan cambios accidentales; no son protección contra un atacante que pueda reescribir datos y hashes. Se mantiene el alcance local de un proceso.

Rama conservada aislada; sin merge, push ni publicación.
