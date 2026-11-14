# Brainstorming: casos de uso y explotación del sistema de embeddings en Vexplorer

**Fecha:** 2026-11-14 (revisado el mismo día tras analizar la implementación)
**Área:** semántica, similitud, histórico de costes, revisión y CAD-completion
**Estado:** propuestas. Nada de este documento aprueba contratos nuevos (los cambios en `backend/app/contratos/` siguen requiriendo acuerdo A/B).

---

## 1. Qué hace hoy el embedding

### 1.1 Funcionamiento en una frase

No se embebe el plano: se embebe una **frase de texto que resume el mueble ya analizado**. OpenAI la convierte en una lista de 256 números, y esas listas se comparan con el **coseno** (1 = idénticas, cuanto más bajo, más distintas).

```text
Plano DXF → geometría + agente → despiece → descriptor (semantic/descriptor.py)
   → semantic_text(): "descriptor=furniture-v2; family=...; dimensions_mm=width:900,...; roles=...; unknowns=..."
   ──── ENTRA ────▶ OpenAI text-embedding-3-small (256 dims)  ──── SALE ────▶ [0.12, -0.40, ...]
   → caché SQLite (embedding_cache)
   → usos: similares (coseno), grupos (coseno ≥ umbral), mapa PCA del explorador, clasificador kNN
```

### 1.2 Los tres usos actuales

| Uso | Dónde | Qué hace con el vector |
|---|---|---|
| Biblioteca de muebles | `similarity/service.py`, `POST /runs/{id}/similarity`, `POST /library/groups` | Ordena por coseno; agrupa por *union-find* los pares con coseno ≥ 0,8 |
| Explorador semántico | `semantic_explorer/` | Mapa PCA 2D, vecinos por coseno, clasificación kNN/logística |
| Histórico de costes | `historico/real_service.py`, `POST /history/comparables` | Prefiltra por atributos (1.000 mejores), ordena por coseno. **La estimación final pondera por atributos, no por coseno** |

El vector solo se genera al guardar en biblioteca en modo semántico y queda cacheado por hash de (texto, modelo, dimensiones, versión de descriptor). Dentro de la app es, en la práctica, determinista. No interviene en el análisis del plano ni en las medidas, así que respeta la regla de motor geométrico sin IA. Existe un modo **geométrico** equivalente sin IA (`geometric_match`).

### 1.3 Hallazgos de la revisión del código

| # | Hallazgo | Consecuencia |
|---|---|---|
| H1 | Las medidas viajan como texto (`width:900`) en un modelo de lenguaje, y la plantilla es casi idéntica entre muebles | Lo previsible es que todos los cosenos salgan altos y comprimidos (≈0,9). Un "0,96" puede no significar nada. **Sin medir todavía.** |
| H2 | El texto incluye `unknowns=...` y valores `None` | Dos muebles se parecen por lo que *no* se sabe. Usarlo para imputar incógnitas sería circular. |
| H3 | Umbral de grupos fijo en 0,8 y compartido entre los modos geométrico y semántico (`main.py`, `GroupRequest`) | Las escalas no son comparables; con cosenos comprimidos, todo acaba en un único grupo. |
| H4 | Los grupos se forman por *single-linkage* (componentes conexos) | Se encadenan: si A≈B y B≈C, A y C quedan juntos aunque no se parezcan. |
| H5 | En el histórico, el coseno elige candidatos pero el coste se pondera con `_attribute_score` | El embedding casi no influye en el número final. |
| H6 | No hay abstención: siempre se devuelven vecinos. El `score` del kNN es una proporción de votos | No se puede decir "no hay precedentes suficientes". El laboratorio ya vio etiquetas forzadas sobre planos fuera de dominio. |
| H7 | El coseno está implementado tres veces, en Python puro O(n²), con vectores en JSON en SQLite; el explorador consulta cada run en cada petición | Válido con decenas de elementos; no escala a miles. |
| H8 | Se comprueba el nombre del modelo, no su versión interna | Si el proveedor actualiza el modelo, los vectores nuevos y antiguos pueden dejar de ser comparables sin aviso. |
| H9 | Los vectores de una revisión antigua se excluyen (`stale_revision`) y no se regeneran solos | La biblioteca semántica se vacía en silencio a medida que se revisan resultados. |
| H10 | No existe ninguna métrica de recuperación (P@k, pares relevantes) sobre la biblioteca o el histórico de la app | No se puede afirmar que un cambio mejore los comparables. |

### 1.4 Principio de diseño derivado

> **Números con reglas, semántica con IA.** Las medidas, cantidades y espesores se comparan de forma determinista (ratios, tolerancias). El embedding se reserva para lo que una regla no resuelve: tipo de mueble, material o acabado escritos de formas distintas, texto libre e imágenes. El score final combina ambas partes con pesos explícitos y explicables.

---

## 2. Ideas ordenadas por complejidad de implementación

Leyenda de origen: **[O]** idea original del brainstorming · **[M]** idea original mejorada · **[N]** idea nueva.
"Contrato" indica si toca `backend/app/contratos/` y, por tanto, si requiere acuerdo A/B.

### Nivel 1 · Complejidad baja (días, sin cambios de contrato o mínimos)

#### 1.1 [N] Medición y calibración de similitudes · *prerrequisito de todo lo demás*
- **Qué:** un script que calcula la distribución de cosenos y de scores geométricos de la biblioteca y del histórico (mínimo, percentiles y separación entre "mismo tipo" y "distinto tipo").
- **Para qué:** confirmar o descartar H1 y fijar umbrales con datos y no a ojo.
- **Implementación:** `tools/` con `numpy`, leyendo `embedding_cache` y `historical_embeddings`. Sin llamadas nuevas a la API.
- **Contrato:** no.

#### 1.2 [N] Umbral calibrado y abstención "sin precedentes"
- **Qué:** sustituir el 0,8 fijo por un umbral por espacio de embedding y modo (por ejemplo, el percentil derivado de 1.1). Si ningún candidato lo supera, se responde explícitamente "sin precedentes suficientes".
- **Resuelve:** H3, H6.
- **Contrato:** no para el umbral; mínimo si se añade un campo de estado de abstención a la respuesta.

#### 1.3 [N] Grupos sin encadenamiento
- **Qué:** sustituir el *single-linkage* por *average* o *complete linkage*, o exigir que cada miembro supere el umbral respecto al centro del grupo.
- **Resuelve:** H4. Es prerrequisito para usar los grupos en fabricación (idea 3.1).
- **Contrato:** no (`SimilarityGroup` no cambia).

#### 1.4 [N] Unificar el cálculo de similitud
- **Qué:** un único módulo de coseno con matriz `numpy` normalizada y cacheada, usado por biblioteca, histórico y explorador.
- **Resuelve:** H7. Hace que el resto de las mejoras se apliquen una sola vez.
- **Contrato:** no.

#### 1.5 [M] "¿Ya hemos fabricado algo así?" *(antes: búsqueda inversa, eje 3)*
- **Qué:** al terminar el análisis de un plano, se lanza automáticamente la búsqueda de similares y, si hay un elemento por encima del umbral de "casi idéntico", se muestra un aviso con enlace a su despiece, coste y programas.
- **Mejora sobre la original:** no requiere un sistema nuevo. Es la búsqueda existente, con disparo automático y umbral calibrado (1.1 + 1.2).
- **Contrato:** no.

#### 1.6 [M] Regla de pandeo en el validador *(antes: QA estructural fuera de distribución, eje 5)*
- **Qué:** reglas deterministas del tipo "balda de más de X mm de luz con espesor ≤ Y mm sin montante intermedio → aviso".
- **Mejora sobre la original:** el pandeo es física, no proximidad en un espacio vectorial; un embedding no lo detecta con fiabilidad. Como regla del validador es explicable, testeable y encaja con la regla 4 de arquitectura (el validador cierra el ciclo).
- **Contrato:** probablemente no (nuevo código de aviso en el validador).
- **Pendiente:** tabla de luces máximas por material y espesor, a validar con técnicos.

#### 1.7 [N] Explicar por qué se parecen dos muebles
- **Qué:** mostrar junto a cada similar las coincidencias y diferencias campo a campo ("mismo espesor; ancho +50 mm; 1 balda menos"). `descriptor_differences` ya calcula las diferencias; falta presentarlas.
- **Para qué:** que el usuario confíe (o no) en un comparable sin interpretar un coseno.
- **Contrato:** no (`SimilarityMatch.differences` ya existe). Principalmente frontend.

### Nivel 2 · Complejidad media (una o dos semanas, cambios de contrato acotados)

#### 2.1 [M] Sugerencias de valores que faltan por precedentes *(eje 1, la de más impacto)*
- **Qué:** si un plano no indica espesor, material, canteado o profundidad, sugerir el valor habitual entre muebles parecidos.
  > "Espesor sugerido: 18 mm. Así lo tienen 7 de 8 muebles similares (rango 16–19 mm)."
- **Mejoras sobre la original:**
  - Los vecinos se buscan **filtrando por familia/estructura y ordenando por medidas conocidas**, no por coseno del texto completo, que incluye las incógnitas (H2).
  - Se muestran el **soporte y la dispersión** (n de N, rango), no un "95 % de confianza" sin respaldo estadístico.
  - Se marca siempre como **hipótesis**, se acepta en **Revisar** con una decisión registrada y nunca se convierte en medida observada.
  - Con la abstención de 1.2: si no hay precedentes suficientes, no se sugiere nada.
- **Contrato:** sí (nuevo tipo de sugerencia con procedencia de los vecinos).

#### 2.2 [M] Presupuesto por analogía con alerta de desviación *(eje 2)*
- **Qué:** junto al coste calculado, mostrar los 3 proyectos más parecidos y su coste real, y avisar si el cálculo se desvía del rango del vecindario.
  > "Tu cálculo: 210 €. Proyectos similares: 140–155 €. Desviación +40 %: revisar."
- **Mejoras sobre la original:**
  - El umbral de alerta se expresa en función de la dispersión del vecindario, no como un 35 % fijo.
  - Se exige moneda, fecha y alcance compatibles (el histórico ya lo hace) y se declara si los vecinos son sintéticos o publicados.
  - Se resuelve H5: decidir explícitamente si la ponderación usa atributos, coseno o score híbrido (2.3).
- **Limitación:** sin histórico real de la empresa, solo funciona con datos sintéticos o publicados. Se puede construir ya y alimentar después.
- **Contrato:** poco (campos de alerta en la estimación).

#### 2.3 [N] Score híbrido: medidas deterministas + semántica
- **Qué:** sacar las medidas del texto embebido (nueva `descriptor_version`) y calcular `score = w₁·geométrico + w₂·semántico`, con ambos componentes visibles en `score_components`.
- **Resuelve:** H1, H2, H5. Aplica el principio 1.4.
- **Contrato:** sí (`score_kind` nuevo y nueva versión de descriptor). Requiere volver a embeber la biblioteca.

#### 2.4 [N] Piezas casi idénticas y estandarización *(antes: deduplicación por embeddings, eje 4)*
- **Qué:** detectar piezas de distintos proyectos que casi coinciden (800×400×18 frente a 802×400×18, mismo material) y proponer una medida estándar.
- **Mejora sobre la original:** se resuelve con **tolerancia numérica por dimensión**, no con embeddings: es más exacto, explicable y gratis.
- **Contrato:** sí (modelo nuevo de propuesta de unificación).

#### 2.5 [N] Regeneración automática de embeddings al revisar
- **Qué:** cuando una revisión cambia el descriptor de un elemento de la biblioteca, se regenera su vector (en segundo plano, con caché) en lugar de excluirlo como obsoleto.
- **Resuelve:** H9.
- **Contrato:** no o mínimo (estado del embedding).

#### 2.6 [N] Versionado del espacio de embedding
- **Qué:** registrar una huella del modelo (por ejemplo, el vector de un conjunto fijo de frases de control) y comprobarla periódicamente. Si cambia, se marca el espacio como nuevo y se planifica volver a embeber.
- **Resuelve:** H8.
- **Contrato:** sí (`EmbeddingMetadata` con identificador de espacio).

#### 2.7 [N] Conjunto de evaluación de recuperación
- **Qué:** una lista pequeña de pares "estos dos muebles son comparables / no lo son", revisada por el equipo, y una métrica P@k y nDCG reproducible.
- **Resuelve:** H10. Permite demostrar que 2.3 o cualquier cambio mejora de verdad.
- **Contrato:** no (vive en `evaluation/`). Coste principal: anotar los pares.

### Nivel 3 · Complejidad alta (varias semanas, dependencias externas)

#### 3.1 [M] Agrupar pedidos para corte en lote *(eje 4)*
- **Qué:** agrupar un lote de pedidos por espesor y material compatibles para cortarlos juntos.
- **Mejoras sobre la original:**
  - La agrupación primaria es por **claves exactas** (espesor, material, acabado) y no por similitud de mueble completo: dos muebles distintos pueden compartir tablero.
  - Depende de 1.3 (sin encadenamiento).
  - El *nesting* real (colocar piezas en el tablero) es un proyecto aparte; aquí solo se prepara el lote.
- **Contrato:** sí. Requiere el concepto de "pedido/lote", hoy inexistente.

#### 3.2 [M] Búsqueda en lenguaje natural *(eje 3, "Fase 1" original)*
- **Qué:** buscar "estanterías de más de 2 m con al menos 4 baldas" o "muebles bajos de TV con zócalo cerrado".
- **Mejora sobre la original:** en lugar de embeber la frase y compararla por coseno con la plantilla del descriptor (formas muy distintas, mala coincidencia), un LLM **traduce la frase a filtros estructurados** (`alto > 2000`, `baldas ≥ 4`, `familia = estantería`) mediante una herramienta con esquema estricto. Después se filtra de forma determinista, se ordena con el score híbrido y se **muestran los filtros entendidos** para que el usuario los corrija. El embedding se usa solo para los términos sin campo estructurado ("zócalo cerrado").
- **Complejidad:** el descriptor actual no contiene conceptos como "zócalo" o "simetría"; ampliarlo es la parte cara.
- **Contrato:** sí (endpoint nuevo y herramienta del agente).

#### 3.3 [N] Embeddings de imagen del plano
- **Qué:** incorporar el método del laboratorio (EmbeddingGemma 2, imagen + geometría) para comparar planos **antes** de tener un despiece revisado o cuando el descriptor es pobre.
- **Evidencia previa:** en el laboratorio, macro-F1 0,83 en clasificación de 4 categorías editoriales; transferencia más débil fuera de dominio y sin rechazo. Ver `docs/semantic-lab/`.
- **Complejidad:** modelo local o servicio adicional, versión del espacio y necesidad de abstención.
- **Contrato:** sí.

#### 3.4 [N] Aprendizaje a partir de las decisiones de revisión
- **Qué:** cuando el usuario acepta o descarta un comparable o una sugerencia, se registra. Con suficientes decisiones, se ajustan los pesos del score híbrido o se entrena un reordenador.
- **Dependencias:** 2.3, 2.7 y un volumen real de uso.
- **Contrato:** sí (registro de feedback).

#### 3.5 [O] Inferencia de herrajes y mecanizados ocultos *(eje 1)*
- **Qué:** emparejar el tipo de unión con su kit de mecanizado y tornillería habitual.
- **Bloqueo:** requiere un histórico que contenga herrajes y mecanizados por mueble, que hoy no existe. Se aplaza hasta tener esos datos; se podría reutilizar la lógica de 2.1 sobre ese nuevo campo.

---

## 3. Matriz resumen

| Nivel | Idea | Origen | Impacto | Contrato | Usa embedding |
|---|---|---|:---:|:---:|:---:|
| 1 | 1.1 Medición y calibración | N | Habilitador | No | Mide |
| 1 | 1.2 Umbral calibrado y abstención | N | Alto | Mínimo | Sí |
| 1 | 1.3 Grupos sin encadenamiento | N | Medio | No | Sí |
| 1 | 1.4 Similitud unificada | N | Habilitador | No | Sí |
| 1 | 1.5 "¿Ya hemos fabricado algo así?" | M | Alto | No | Sí |
| 1 | 1.6 Regla de pandeo | M | Medio | No | No |
| 1 | 1.7 Explicar similitudes | N | Medio | No | No |
| 2 | 2.1 Sugerencias de valores que faltan | M | Muy alto | Sí | Parcial |
| 2 | 2.2 Presupuesto por analogía y alerta | M | Alto | Poco | Parcial |
| 2 | 2.3 Score híbrido | N | Alto | Sí | Sí |
| 2 | 2.4 Piezas casi idénticas | M | Medio/alto | Sí | No |
| 2 | 2.5 Regeneración al revisar | N | Medio | Mínimo | Sí |
| 2 | 2.6 Versionado del espacio | N | Medio | Sí | Sí |
| 2 | 2.7 Evaluación de recuperación | N | Habilitador | No | Mide |
| 3 | 3.1 Lotes de corte | M | Medio/alto | Sí | No |
| 3 | 3.2 Búsqueda en lenguaje natural | M | Muy alto | Sí | Parcial |
| 3 | 3.3 Embeddings de imagen | N | Alto | Sí | Sí |
| 3 | 3.4 Aprendizaje de decisiones | N | Alto | Sí | Sí |
| 3 | 3.5 Herrajes y mecanizados | O | Alto | Sí | Parcial |

---

## 4. Hoja de ruta sugerida

1. **Base medible (nivel 1):** 1.1 → 1.4 → 1.2 → 1.3. Sin cambios de contrato; deja umbrales con datos y un único punto donde mejorar.
2. **Primeras funcionalidades visibles:** 1.5 y 1.7 (solo umbral e interfaz) y 1.6 en el validador.
3. **Acuerdo A/B y nivel 2:** 2.3 (score híbrido) y 2.7 (evaluación) primero, porque son la base de calidad; después 2.1 (sugerencias en Revisar) y 2.2 (presupuesto por analogía).
4. **Nivel 3** cuando haya datos reales: histórico de la empresa, decisiones de revisión acumuladas y herrajes.

## 5. Límites que se mantienen

- Toda sugerencia derivada de precedentes es **hipótesis** y se registra como decisión al aceptarla; nunca sustituye una medida observada.
- Similitud no implica intercambiabilidad ni equivalencia de coste. Un comparable sintético o publicado no es un coste empresarial.
- Ningún score de este documento es una probabilidad salvo que se calibre y se evalúe explícitamente (1.1, 2.7).
