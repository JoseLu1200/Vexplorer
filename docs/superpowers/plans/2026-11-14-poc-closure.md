# Cierre de abstención, semántica y versión — Implementation Plan

> **For agentic workers:** ejecutar las tareas por dominio con pruebas de comportamiento antes de cambios. El usuario solicita ejecución directa mediante GPT-6.1 Sol y revisión final GPT-6 Astra.

**Goal:** corregir abstenciones evitables y cerrar un ensayo reproducible de despiece semántico y PDF raster, conservando incertidumbre real.

**Architecture:** mantener geometría determinista y medidas referenciadas. Separar revisión geométrica de faltantes económicos, y evaluación semántica offline de runtime. Generar familias de mobiliario con componentes, funciones, montaje y alternativas en referencia privada; entregar solo planos pobres al agente.

**Tech Stack:** Python/Pydantic/ezdxf/FastAPI actuales, frontend JS existente.

**Spec:** solicitudes del usuario de esta sesión y transcripcion-contexto-poc.md; decisiones concretas siguientes.

## Global Constraints
- No convertir abstención en aceptación automática ni desconocidos en cifras inventadas.
- No atribuir validación humana/industrial a un oráculo sintético.
- Separación por familia/proyecto antes de variantes; referencias privadas fuera del runtime y de los bundles públicos.
- Preservar cambios UX/auth existentes; solo raíz integra y crea commits.
- Un escritor de contratos, acuerdo A/B y aviso C antes de modificarlos.

## Review Focus
- Material/acabado desconocidos no deben borrar geometría respaldada.
- Abstención recuperable debe poder solicitar evidencia/reparación acotada; ausencia real se conserva.
- Dimensiones iguales no acreditan función ni montaje; medir semántica y relaciones aparte.
- Casos fallidos permanecen en denominadores; pruebas no reciben claves del oráculo.
- Raster sin escala conserva dimensiones desconocidas, incluso con interpretación visual exitosa.

## Tareas
- [x] Abstención: reproducir causas con trazas de blind20; añadir regresiones independientes; corregir autonomía/contexto en su alcance; verificar contra casos desconocidos/conflictivos.
- [x] Semántica: definir contrato offline compartido con corpus; implementar alineación por rol/relaciones y escenarios alternativos con precisión, recobrado, omisiones y no evaluables; tests adversariales contra matching solo dimensional.
- [x] Montaje estructurado: ampliar salida de propuesta con relaciones/alternativas hipotéticas y referencias cerradas; conservar lectura de snapshots anteriores; coordinar contrato A/B/C y prompt con PDF, propagación con abstención; evaluar desde salida nativa congelada, nunca completar desde referencia.
- [x] Corpus: contrastar fuentes públicas y construir generador sintético propio con al menos tres familias; separar desarrollo/reservado por estructura/proyecto; comprobar hashes, duplicados, alternativas y ausencia de fuga. Congelar antes de inferencia.
- [x] PDF: reproducir provider_response_incomplete del raster instrumentado; corregir la causa con test de frontera y confirmar recorrido raster completo sin inventar escala.
- [x] Release: reconciliar README/estado/producción, incorporar cambios existentes revisados, crear manifiesto reproducible sin secretos/datos; verificar recorridos contra árbol exacto.
- [x] Integración: suite Python/JS, pruebas de corpus/semántica, ensayos live acotados tras pruebas offline, informe con resultados y límites; revisión final Astra sobre diff real y evidencias; corregir hallazgos; commit final identificado.

## Resultado y ajuste de alcance comprobado

La implementación y las comprobaciones están documentadas en `docs/CIERRE_POC_2026-11-14.md`. La causa histórica exacta de `provider_response_incomplete` no se pudo inferir de la telemetría antigua; sí se reprodujo/corrigió la contradicción de referencias raster, se amplió telemetría segura y se completó el recorrido HTTP. No se atribuye una causa no observada.

El banco reservado es sintético por autorización del usuario y está separado por proyecto/topología; las clases de producto existen en ambos splits. Los resultados semánticos siguen siendo insuficientes para aceptación autónoma industrial. La entrega de software no convierte esa limitación en una tarea validada de precisión de montaje.
