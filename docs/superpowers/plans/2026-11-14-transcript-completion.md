# Transcript Completion Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. User selected GPT-6.1 Sol implementation swarm and GPT-6 Astra reviewer.

**Goal:** completar el software de interpretación revisable, entrada multiformato, histórico económico y evaluación descrito en la transcripción.

**Architecture:** módulos aditivos con Pydantic, routers montados en FastAPI y frontend existente. Geometría determinista antes de propuestas; revisión y evidencia persistidas.

**Tech Stack:** Python, FastAPI, Pydantic, ezdxf, PyMuPDF, JavaScript, Three.js.

**Spec:** `docs/superpowers/specs/2026-11-14-transcript-completion-design.md` y `docs/CASO_DE_USO_Y_EVALUACION.md`.

## Global Constraints

- No datos reales inventados, cifras geométricas arbitrarias ni medidas desde píxeles sin escala confirmada.
- A/B acuerdan contratos; backend general es escritor único y avisa a interfaz/integración.
- Nuevas rutas conservan autenticación privada, actor, límites y prefijo.
- No acceso del runtime a referencias de evaluación.

## Review Focus

- PDF sin escala o raster no puede producir cotas métricas confirmadas.
- Vistas duplicadas y alternativas no incrementan cantidad física.
- Material/acabado/moneda incompatibles impiden estimación aparentemente completa.
- Revisiones concurrentes o IDs ajenos no sobrescriben ni mezclan evidencias.
- Un resultado sintético o sin referencia no demuestra precisión o ahorro real.

## Tasks

- [x] Ingesta: crear adaptadores en `backend/app/ingesta/`, pruebas de PDF vector/raster/escala y frontera ODA; comunicar firmas a integración.
- [x] Descomposición general: modelos aditivos, herramientas estrictas, propuestas desde documento sin gate de mesa, revisión con reemplazos, BOM/planos/escena y pruebas de fuentes inválidas/incógnitas/concurrencia.
- [x] Histórico: modelos y store, import JSON/CSV atómico, recuperación e inferencia de coste/horas por concepto; pruebas de fórmula fija+variable y rechazo de incompatibles.
- [x] Evaluación: `evaluation/metrics.py`, `tools/evaluate_cases.py`, tests de métricas con predicción congelada/referencia separada y documentación de uso.
- [x] Interfaz: upload multiformato, recorrido general revisable, derivados e histórico; tests JS y recorrido navegador.
- [x] Integración: routers/config/uploads en `main.py`, límites y procedencia, pruebas HTTP en local/producción.
- [ ] Verificación: pytest completo, npm test, compileall/diff check, smoke HTTP/navegador y revisión Astra; corregir hallazgos y registrar límites empíricos.
- [x] Revisión multimodal autónoma: imágenes reales de CAD/PDF, crítica separada, reparación acotada, estados factuales conservados y despiece provisional sin aprobación humana obligatoria. Ciclo HTTP real y dos casos diagnósticos v5 completados; las incógnitas permanecen explícitas.
- [x] Asociación de proyecciones: candidatos geométricos explícitos para ayudar al proponente y al crítico; ambigüedad y duplicados visibles.
- [ ] Evaluación pareada nueva: congelar propuesta inicial y salida corregida de veinte entradas nuevas antes de puntuar referencias privadas; registrar mejoras y regresiones.

Cada implementador escribe pruebas de comportamiento antes del código y comunica resultados observados. El coordinador verifica conjuntamente; ningún conteo de pruebas equivale a cumplimiento industrial.
