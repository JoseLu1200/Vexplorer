# Reconstrucción funcional propuesta y comparación Idol

Solicitud aprobada: plano pobre sin BOM/3D -> hipótesis de componentes y montaje -> vistas, planos, BOM y 3D; comprobar cuatro variantes A Idol directo, B harness con modelo paramétrico, C render B hacia Idol, D render reservado hacia Idol (control favorable). El usuario solicita revisión visual multimodal de todas las salidas y completar diseños plausibles sin presentar supuestos como hechos.

## Decisión

Representación canónica de cuboides por ocurrencia, dimensiones/posición explícitas, procedencia de cada componente, decisiones de diseño separadas, preguntas y estado `proposed|insufficient_evidence|unsupported`. Pydantic valida todos los datos; generación de GLB, renders, planos y BOM consume exactamente ese mismo modelo. No ejecutar código generado por LLM. Funcionalidad revisada visualmente no significa resistencia certificada. Ningún modelo certifica fabricación ni inventa precios.

Alternativas: Idol como representación principal pierde piezas y escala; reconstruir malla desde splats añade errores. Elegida la representación paramétrica con Idol como comparación opcional, según aprobación del usuario. El alcance inicial es mobiliario ortogonal de paneles; curvas, mecanizados y análisis estructural permanecen explícitamente no soportados.

## Integración

Módulo aditivo con proveedor nativo existente, una propuesta estructurada y una revisión visual acotada. Entrada: imágenes y contexto público del run; nunca referencias privadas. Para datos ausentes se admiten hipótesis de diseño explícitas con justificación y preguntas, nunca estado observado. Unidad desconocida impide declarar precisión métrica. Los artefactos no sustituyen BOM/costes confirmados. El servicio devuelve estado y evidencia, admite abstención y errores conservados.

## Ensayo

Tres controles originales de completitud incierta, más muebles sintéticos propios funcionalmente revisables (mesa apoyada, estantería, mueble con compartimentos). Ocultar interiores, suprimir cotas, degradar vistas sin filtrar IDs/partes al modelo. Referencias físicas separadas; inferencias y hashes congelados antes de puntuación. Diagnóstico, no test ciego industrial. Misma entrada PNG para comparación común; pista DXF diferenciada. Seed inicial 42; repetir seeds 123/456 si recursos permiten, declarando cobertura efectiva. Primer ensayo 32768 gaussianas para todos los casos; la densidad es parte del protocolo.

## Métricas

Vistas suministradas y reservadas: silhouette IoU, error de bordes, dimensiones solo con escala legítima; forma normalizada separada. Componentes/cantidades solo para salida estructurada. No comparar centros de gaussianas como superficie CAD. Evaluación de recuperación/comprensión exploratoria separada y sin interpretar juicio visual como verdad física. Registrar latencia, memoria, fallos y casos sin salida.

## Aceptación

Pruebas independientes de coherencia y exportaciones, separación de referencia, abstención, restricciones dimensionales y límites. Ensayo real A/B/C/D cuando dependencias/accesos lo permitan; reportar bloqueo exacto y conservar resultados parciales si una frontera externa lo impide. Publicar informe con galerías inspeccionadas, versiones y límites. No publicar datos de terceros ni secretos.
