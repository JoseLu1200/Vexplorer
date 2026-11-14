# Montaje general razonado desde planos

Estado: diseño propuesto para aprobación, no implementación terminada.

## Objetivo solicitado

Usar el harness existente para inferir un montaje espacial por instancia a partir del plano y del despiece, comprobarlo, corregirlo y mostrarlo en 3D. El objetivo no se satisface con una cuadrícula de piezas ni con un grafo semántico sin posiciones.

## Diagnóstico comprobado

`general_furniture/live.py` prohíbe colocaciones y describe las relaciones de montaje como no numéricas. `derivations.py` asigna `position_mm=None` a todos los tipos. `GeneralSceneItem` solo admite schematic_unplaced/unavailable; ni representa orientación ni una transformación por instancia. El visor general distribuye los tipos en una cuadrícula local. Las plantillas de mesa sí producen posiciones mediante reglas específicas. El corpus complejo ya contiene evidencia vectorial, regiones espaciales, medidas y correspondencias candidatas aprovechables.

## Alternativas consideradas

1. Más plantillas de muebles: rápidas para familias acotadas, no cumplen la inferencia general pedida.
2. Pedir coordenadas libres al LLM: flexible, pero permite posiciones inventadas y montajes visualmente plausibles que contradicen el plano.
3. Recomendación: agente que selecciona correspondencias y restricciones geométricas; servidor que calcula posiciones, comprueba proyecciones y colisiones y devuelve errores para reparación. Es una elección propuesta del implementador, pendiente de aprobación, no una decisión atribuida al usuario.

## Flujo propuesto

1. Geometría determinista existente produce ledger métrico, contornos y regiones. Se añaden intervalos de coordenadas y candidatos de caras por región, con IDs y procedencia. No se consulta ninguna referencia privada.
2. El agente recibe el despiece de una revisión concreta, imágenes del plano y el contexto geométrico. Herramienta estricta Pydantic para proponer marcos de proyección (región, ejes del mundo, sentidos) y correspondencias por instancia. Puede inspeccionar contexto y solicitar una vista de su montaje candidato.
3. Cada instancia identifica componente, índice dentro de cantidad, orientación y referencias geométricas para sus intervalos X/Y/Z. Las posiciones se calculan desde coordenadas/operaciones respaldadas, no de números libres del LLM. Los desplazamientos entre vistas se separan de distancias físicas; las reflexiones se explicitan.
4. El validador comprueba cobertura de cantidades, IDs únicos, dimensiones preservadas bajo rotación, unidades y escala, referencias existentes, consistencia entre proyecciones y extensión global. Calcula penetraciones de cajas con tolerancia numérica separada de la tolerancia de fabricación. Contacto no equivale a colisión; colisión de cajas no demuestra colisión de geometría mecanizada.
5. Errores concretos por instancia/vista vuelven al agente: discrepancia de intervalo, dimensión incompatible, instancia duplicada, penetración o evidencia insuficiente. Bucle acotado con límite de llamadas, tiempo y tamaño. Se conservan candidato, resumen público, pruebas y errores; no razonamiento interno.
6. Se acepta solo una hipótesis que satisfaga las comprobaciones declaradas. Si varias soluciones compatibles sobreviven, se conservan como alternativas y se muestra la ambigüedad. Fallar el montaje no elimina la BOM ni el plano.
7. Se persiste por run/proposal_revision/review_revision con política/modelo y fuentes. Nunca se sirve un montaje anterior para una revisión nueva. La escena lleva una caja por instancia y posiciones/orientaciones reales; el despiece separado queda como vista alternativa claramente rotulada.

## Alcance inicial honesto

Muebles de paneles rectangulares con vistas ortográficas métricas y posiciones identificables. No promete reconstrucción exacta de curvas, herrajes ocultos, taladros o uniones no representadas. La ambigüedad de proyecciones no se resuelve con valores típicos. PDF sin escala no genera colocaciones métricas. Una hipótesis validada geométricamente no se convierte en aprobación humana para fabricar.

## Integración y compatibilidad

Preferencia por ampliación aditiva del contrato central, manteniendo lectura de escenas antiguas, diferenciando tipos de piezas de instancias y separando el montaje de los costes. Requiere el acuerdo contractual A/B y aviso C exigidos por CLAUDE.md antes de tocar contratos/. No se creará un formato JSON sin esquema para eludir ese requisito.

Los cambios existentes en el repositorio se preservan. El registro `team/agente_semantica_v2_montaje.md` conserva una reserva sobre semántica de relaciones; la nueva implementación no debe sobrescribir ese trabajo. La integración con `live.py`/`autonomous.py` se realizará con cambios pequeños después de comprobar el estado de esas reservas. El usuario ya autorizó crear los registros necesarios de equipo.

## Pruebas y criterio de aceptación

- Unitarias sin red del esquema y herramientas: referencias falsas, falta de escala, cantidades desconocidas, orientación, duplicados, incompatibilidad entre vistas, contactos y penetraciones.
- Bucle con proveedor simulado: candidato incorrecto, mensaje de error accionable, corrección posterior; agotamiento de presupuesto sin inventar solución; persistencia y revisión obsoleta.
- Prueba real en production local del armario plank-030, usando únicamente DXF y resultados extraídos como entrada. Congelar salida antes de evaluarla contra referencia privada.
- Comparar por instancia dimensiones, orientación y posición, permitiendo una única transformación global coherente entre marcos. No basta ordenar medidas ni alinear cada pieza por separado. Informar cobertura, error de posiciones, orientación y penetraciones. Mostrar el ensamblaje en navegador y contrastar sus proyecciones.
- Probar otro mueble del conjunto que aún no se haya utilizado para ajustar el sistema, y un control con datos insuficientes. Este último debe conservar ambigüedad o abstención.
- Regresión de mesa y de la vista general: cargar, 3D, orbit/zoom, selección bidireccional tabla/pieza, despiece, recarga y errores de consola.
- Entrega con enlaces locales, reporte reproducible y límites observados. Si el montaje no supera las métricas, reportar el fallo y continuar depuración; no presentarlo como resuelto porque renderiza.

## Decisiones técnicas propuestas del implementador

- Primer alcance: orientación ortogonal de tableros; permutaciones de ejes con signos, sin rotación continua arbitraria. Ejes de escena coherentes con el visor existente (X ancho, Y alto, Z fondo).
- Herramientas: inspeccionar contexto de montaje; evaluar candidato (incluye proyecciones/render cuando disponible); entregar candidato final. Todas con esquema generado desde Pydantic y referencias limitadas al run.
- Se ejecuta como fase del trabajo durable, después de la revisión del despiece, con estado visible propio. Una propuesta fallida conserva la revisión y se puede reintentar sin repetir toda la inferencia. Consultar el 3D no dispara gasto de modelo silenciosamente.
- Presupuesto inicial configurable: máximo 5 llamadas y 180 segundos por fase de montaje, 100 instancias y 512 contornos relevantes. La cola existente mantiene el control de concurrencia y cancelación. Alcanzar un límite se presenta como incompleto y conserva el último candidato únicamente como candidato rechazado, no como montaje validado.
- Criterio del caso complejo: cobertura 16/16, dimensiones y posiciones a menos de 1 mm tras una sola alineación global ortogonal, orientaciones de los planos concordantes con referencia, y ausencia de penetraciones no explicadas mayores de 1 mm. No se admite una alineación distinta para cada pieza. En piezas simétricas se evalúa equivalencia geométrica de la caja, no un giro local indistinguible.
- Sin añadir frameworks de agentes ni dependencias geométricas pesadas. Se separan hipótesis, informe determinista y transformación renderizable.

## Revisión independiente incorporada

El builder check confirma que el cambio contractual es necesario y que no quedan decisiones de producto adicionales. Se concreta:

- Cada ocurrencia conserva sus propios contornos/regiones por vista; compartir evidencia a nivel de tipo no basta para ubicar baldas repetidas. Las duplicidades se comprueban por identidad física, permitiendo evidencia ocluida compartida solo con hipótesis explícita.
- Cada intento persistido incluye assembly_revision, candidato, alternativa elegida, modelo/política, fuentes y resultado determinista; no sobrescribe la revisión de BOM.
- El visor normaliza y aplica la transformación ortogonal por ocurrencia, permite selección de instancia y agrupa su selección con el tipo de la tabla. No interpreta una simple permutación de dimensiones como evidencia de orientación.
- La evaluación registra error de centros y caras, también normalizado por diagonal, y reproyección contra todas las vistas utilizadas. La alineación global debe preservar la mano del sistema; cualquier reflexión de una vista se resuelve en su marco de proyección.
