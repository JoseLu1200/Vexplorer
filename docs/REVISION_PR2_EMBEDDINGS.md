# Revisión e integración de PR2

El usuario solicitó revisar, mejorar e integrar la PR2 con agentes GPT-6.1 Sol y fusionarla. Autorizó también integrar el commit local `48dac99`, que contiene montaje general, evaluación semántica y similitud técnica. La base de la PR era `e95f6bd`; `main` remoto era `c66f93b`. No había conflicto textual entre esos dos commits, pero sí al incorporar los avances locales.

## Qué aporta

| Bloque | Valor que se conserva | Corrección de integración |
|---|---|---|
| Calibración y abstención | Umbrales separados para búsqueda, grupos y duplicados | El calibrador exporta el formato que realmente consume el servidor; el aviso usa su umbral calibrado |
| Agrupamiento y matemáticas | Enlace completo sin encadenamiento y coseno común estable | Conserva mínimo entre pares; separa versiones de descriptor incompatibles; valida valores no finitos |
| Similitud técnica local | Diferencias por pieza, procedencia, diseños equivalentes y advertencias | Convive con resumen, abstención y explicaciones de la PR; los metadatos de un candidato aislado no prueban coincidencia |
| Precedentes | Hipótesis con soporte y trazabilidad, analogía económica, piezas y lotes | Cantidades desconocidas quedan sin clasificar; candidatos no estimables no agotan el cupo; pesos desbordados se rechazan |
| Mantenimiento semántico | Detección y regeneración, verificación de deriva, huellas históricas | Rotar invalida la caché de biblioteca antes de guardar la huella y comparte exclusión con regeneración |
| Plausibilidad | Advertencias de luz y espesor | Conectadas a explicaciones de resultados; no se inventan apoyos por existir otra pieza vertical; catálogo no confirmado es provisional |
| CAD y montaje | Construcción parametrizada, planos por pieza y montaje general | Unión aditiva de contratos y validadores; conserva límite de 64 componentes, cierres de referencias y distinción de medidas |
| Interfaz | Publicación documentada, comparación técnica, selección de montaje y planos CAD | Limpia avisos antiguos, descarta respuestas obsoletas, usa etiquetas humanas y mantiene las rutas de ambas ramas |

## Decisiones y límites

- Se mantienen los endpoints de precedentes bloqueados en acceso público. La integración no despliega una nueva versión del servicio.
- El híbrido conserva el fallback geométrico documentado y expone pesos efectivos; no significa equivalencia de fabricación.
- MAD cero se comunica como `dispersion_nula`; no se inventa una dispersión para producir alertas.
- Los lotes estiman superficie: las piezas que no caben requieren atención y el resultado no es nesting.
- La rotación invalida la caché de biblioteca; no la caché del histórico económico separado. No detecta automáticamente una deriva antes de verificar/rotar. Los bloqueos son por proceso, acorde al despliegue de un worker documentado.
- Imagen sigue sin proveedor configurado; herrajes y aprendizaje de decisiones siguen siendo mecanismos sin validación empresarial real. Los umbrales empíricos requieren un corpus representativo.
- Los cambios posteriores sin commit del checkout principal se conservan. Esta integración trabaja en `.worktrees/pr2-integration` y no los publica.

## Evidencia

La revisión se dividió entre similitud, precedentes, seguridad e interfaz; la reconciliación añadió revisión de backend y pruebas. Tras agotar la cuota de varios agentes, coordinación completó sus cambios guardados y las verificaciones. Los registros `team/agente_pr2_*.md` conservan sus resultados parciales; el registro de coordinación contiene el cierre consolidado.

- Baseline PR: 1101 pruebas Python aprobadas; un fallo de guard de disco y un error de importación sklearn por falta de paginación local. La prueba de retención de backups se aisló de la capacidad física del disco; la política de espacio libre conserva su prueba específica.
- Frontend integrado final: 260 pruebas aprobadas, cero fallos.
- Navegador real, fixtures offline: carga de revisión, aviso con nombre del precedente, búsqueda con comparación técnica, desglose y miniaturas; cero errores de consola observados.
- `pip check` sin dependencias rotas; compilación Python y construcción de wheel realizadas.
- Regresiones comprobadas en rojo y verde: umbral de duplicado del servidor, rotación/invalidation, cantidades desconocidas, pesos inválidos, calibración y procedencia de coincidencias. Control negativo de pandeo: retirar su integración en memoria hace fallar la prueba del endpoint real.

El resultado final de la suite completa y de la CI se anota en `team/agente_pr2_coordinacion.md` y en la PR; estas pruebas funcionales no acreditan exactitud industrial.

## Incrementos concurrentes

Se incorporó el main posterior con montaje por instancia, contabilidad de evidencia y recuperación durable. Sus cambios de publicación pública y comparación técnica se conservan. Se recuperaron fixes y pruebas PR2 que una reconciliación paralela había descartado. La ingesta incorpora rechazo explícito de DXF 3D y alias ODA; POLYLINE 2D llega a vistas/contornos, y el visor usa warnings reales para DIMLFAC. La revisión final independiente no detectó blockers en frontend ni runner.
