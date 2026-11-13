# Primera demo ejecutable: alcance e integración

Fecha: 2026-11-13. Base: main c09a6f9, actualizado con `git pull --ff-only`.
Este documento registra decisiones del coordinador autorizado. Los registros de cada agente y VERIFICACION_DEMO distinguen implementación y comprobación.

## Diseño elegido

Una estantería rectangular de tableros y un fixture propio de desarrollo. El dibujo representa el conjunto montado con vistas 2D y pocas cotas. La revisión resuelve una unión constructiva que el plano no determina. Una variante conserva dimensiones desconocidas. La referencia de evaluación está separada del runtime.

El frontend JS/HTML se sirve desde FastAPI para reproducir el recorrido con un proceso. La geometría usa ezdxf y cálculos deterministas; los modelos Pydantic son la única autoridad contractual. El modelo live inspecciona evidencia y entrega referencias mediante herramientas nativas, sin autoridad para escribir mediciones.

Se descarta generar ahora un corpus PlankAssembly: su adaptación y condiciones de uso no son dependencias de la demo. Un visor 3D tampoco aporta aceptación al recorrido solicitado.

## Contratos y propiedad

A y B registran su acuerdo explícito antes de implementar contratos; B es su único escritor y avisa a C. Cada agente tiene rama, worktree y registro autorizado. Ver [coordinación](../team/agente_coordinador.md).

| Trabajo | Propietario | Entrega |
|---|---|---|
| Ingesta y geometría | A, agente_geometria | Vistas, medidas, evidencia y candidatas |
| API, contratos, validación, harness y economía | B, agente_backend | Resultado versionado y cálculo reproducible |
| Interfaz | C, agente_frontend | Selección, revisión, comparables, ficha y traza |
| Fixture y evaluación | D, agente_evaluacion | Entradas propias y referencia reservada |
| Integración y aceptación | Agente coordinador | Suite, navegador, documentación y commits |
| Revisión final | GPT-6 Astra, solo lectura | Hallazgos sobre código integrado y evidencia |

## Secuencia de ejecución

- [x] Actualizar main y comprobar baseline: 13 pruebas pasan.
- [x] Crear rama de integración y cuatro worktrees.
- [x] Registrar acuerdo A/B y aviso C.
- [x] Integrar contratos, fixture, geometría, backend y frontend.
- [x] Ejecutar pruebas de unidades, cardinalidad, abstención, aislamiento, revisión y cálculo.
- [x] Instalar y arrancar con comandos comprobados.
- [x] Recorrer en navegador carga → evidencia → decisión humana → comparable → estimación → exportación.
- [x] Comprobar variante incompleta y modos disponibles.
- [ ] Revisión final GPT-6 Astra y corrección de hallazgos.
- [ ] Actualizar README, resultados y límites con evidencia observada.

## Criterios de aceptación

El usuario debe poder localizar en el plano la evidencia de una propuesta, distinguir observaciones/cálculos/hipótesis, conservar nulos y revisar la ambigüedad con autor y motivo. La revisión anterior permanece recuperable. El histórico y las tarifas se identifican como sintéticos. La estimación muestra conceptos, unidades, cantidades, tarifas, exclusiones y revisión fuente, sin sumar alternativas ni duplicar costes.

`geometry_only` debe funcionar sin proveedor. `live` necesita un proveedor real configurado; su ausencia se informa. `recorded_replay` se rechaza si no hay ejecución real grabada. Las pruebas con proveedor simulado son pruebas de frontera, no ejecuciones live.

El aislamiento se verifica en las capacidades y contexto de las herramientas: solo el documento actual y su evidencia. No basta con separar carpetas. La referencia no forma parte del prompt, endpoints ni archivos estáticos.

## Riesgos a comprobar

- Cotas en unidades distintas o desconocidas, sin normalización implícita.
- Cantidades físicas independientes del número de vistas.
- Espesor y profundidad ausentes, sin valores típicos.
- Referencias caducadas o de otra ejecución y revisiones concurrentes.
- Estimación parcial o rechazada cuando faltan premisas; tarifas y costes fijos usados una sola vez.
- Mensajes de error y trazas sin secretos ni razonamiento interno.

## Límites deliberados

Fixture de desarrollo sintético, una familia y un subconjunto DXF declarado. No acredita generalización, ahorro humano, aptitud de fabricación ni precisión económica empresarial. DWG/PDF, adaptación PlankAssembly, embeddings y comparación estadística de métodos requieren trabajo posterior. No se despliega ni se publica ningún dataset.

