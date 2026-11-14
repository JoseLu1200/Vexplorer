# Mapa Completo de Vectores y Embeddings en Vexplorer

**Fecha:** 2026-11-14  
**Rama:** `embeddings`  
**Propósito:** Radiografía técnica de todos los sistemas vectoriales implementados en el repositorio, su funcionamiento interno exacto y las líneas de trabajo abiertas sobre vectores.

---

## 1. Resumen Ejecutivo

En **Vexplorer** conviven **5 sistemas vectoriales diferenciados** repartidos entre producción, histórico de costes, explorador visual y laboratorio offline:

| Sistema | Tipo de vector | Dimensión / Naturaleza | Módulo principal | Uso actual |
|---|---|---|---|---|
| **A. Embedding Semántico de Producción** | Denso neuronal (OpenAI) | 256 floats (`text-embedding-3-small`) | `backend/app/semantic/` | Similitud semántica y grupos en biblioteca |
| **B. Vector de Características Geométricas** | Estructural determinista | Ratios de medidas, roles y espesores | `backend/app/similarity/` | Similitud offline, grupos y detector de duplicados |
| **C. Vectores del Histórico de Costes** | Híbrido (atributos + coseno) | Pesos explícitos + embeddings históricos | `backend/app/historico/` | Recuperación de proyectos y estimación de costes |
| **D. Vectores del Explorador Semántico** | Matriz L2 + PCA 2D + kNN/LogReg | Cualquier dimensión compatible | `backend/app/semantic_explorer/` | Mapa 2D, vecinos y clasificación supervisada |
| **E. Vectores Multimodales Locales** | Neuronal local + features DXF | Texto, imagen renderizada y mixto | `tools/semantic_lab/` | Experimentación offline (`dinov3`, `embeddinggemma2`, `minilm`) |

Todos los cálculos de producto escalar y normalización L2 de producción comparten un único núcleo vectorizado con `numpy` en `backend/app/similarity/math_utils.py`.

---

## 2. Detalle Técnico de Cada Sistema Vectorial

### A. Vector Semántico de Producción (`OpenAIEmbeddingProvider`)
* **Archivos clave:**
  - `backend/app/semantic/embeddings.py`
  - `backend/app/semantic/descriptor.py`
  - `backend/app/servicios/repository.py`
* **Flujo interno paso a paso:**
  1. A partir de un `Result` se construye un descriptor normalizado (`FurnitureDescriptor` v1, `FurnitureDescriptorV2` o `FurnitureDescriptorV3`) mediante `build_descriptor(result)`.
  2. `semantic_text(descriptor)` convierte el descriptor en una cadena estructurada fija:
     ```text
     descriptor=furniture-v2; family=...; structure=...; dimensions_mm=width:900,depth:300,height:1200; roles=...; unknowns=...
     ```
  3. `embedding_cache_key(descriptor_version, model, dimensions, normalized_text)` genera un hash SHA-256 determinista.
  4. Si no existe en la tabla SQLite `embedding_cache`, se llama a OpenAI (`text-embedding-3-small`, 256 dimensiones, formato `float`), se valida finitud y norma no nula (`validate_embedding`), y se persiste en caché.
  5. Las comparaciones posteriores usan `cosine_similarity` y `cosine_matrix` de `backend/app/similarity/math_utils.py`.

---

### B. Vector de Características Geométricas (`geometric_match`)
* **Archivos clave:**
  - `backend/app/similarity/service.py`
  - `backend/app/similarity/clustering.py`
  - `backend/app/similarity/thresholds.py`
* **Flujo interno paso a paso:**
  1. Compara ejes dimensionales (`width_mm`, `depth_mm`, `height_mm`) mediante el ratio `min(a, b) / max(a, b)`.
  2. Compara cantidades por rol de pieza (`side_panel`, `shelf`, `top_panel`, `base_panel`, `tabletop`, etc.).
  3. Combina las componentes con pesos explícitos y deterministas:
     - **`furniture-v1`:** `0.70 * dimensiones + 0.30 * roles`
     - **`furniture-v2` / `furniture-v3`:** `0.60 * dimensiones + 0.25 * roles + 0.15 * espesor`
  4. Permite agrupar muebles mediante enlace completo (*complete-linkage* en `clustering.py`) evitando encadenamientos `A~B, B~C` cuando `A!~C`, y aplicar umbrales calibrados con abstención (`thresholds.py`).

---

### C. Vectores del Histórico Real de Costes (`historical_embeddings`)
* **Archivo clave:** `backend/app/historico/real_service.py`
* **Flujo interno en 2 fases:**
  1. **Prefiltrado por atributos (`_attribute_score`):** Evalúa diferencias numéricas (`width_mm`, `depth_mm`, `height_mm`, `length_mm`, `area_mm2`, `volume_mm3`, `quantity`) y categóricas (`family`, `material`, `finish`) con pesos explícitos (`family: 0.2`, `material: 0.2`, `area_mm2: 0.15`, `finish: 0.1`, etc.) para seleccionar los 1.000 mejores candidatos.
  2. **Ranking semántico:** Ordena los candidatos filtrados aplicando `cosine_similarity` (`math_utils.py`) sobre sus vectores almacenados.
  3. **Estimación:** Escala costes y horas con factores de cantidad y consumo de material a partir de los registros históricos compatibles.

---

### D. Vectores del Explorador Semántico (PCA 2D + kNN / LogReg)
* **Archivos clave:**
  - `backend/app/semantic_explorer/core.py`
  - `backend/app/semantic_explorer/classification.py`
* **Capacidades vectoriales:**
  1. **Normalización unificada (`unit_vectors`):** Convierte las entradas de un `Bundle` en una matriz unitaria L2 vía `normalize_matrix`.
  2. **Proyección PCA 2D (`make_snapshot`):** Centra la matriz (`matrix - matrix.mean(axis=0)`), aplica descomposición `np.linalg.svd` y proyecta en 2 ejes `(x, y)` con orientación determinista de signo y cálculo de varianza explicada (`pca-centered-svd-v1`).
  3. **Búsqueda vecinal (`search`):** Calcula `cosine_matrix` de una consulta contra toda la matriz y devuelve diferencias atributo a atributo.
  4. **Clasificación supervisada sobre artefactos numéricos (`classify`):**
     - **`knn`:** Distancia `1 - cosine`, selección de `k` vecinos y voto ponderado por `1 / distancia`.
     - **`logreg`:** Concatena el vector unitario L2 con `features` numéricas tabulares, estandariza `(x - mean) / scale`, aplica coeficientes lineales y calcula probabilidades vía sigmoide o softmax.

---

### E. Vectores Multimodales Locales (Laboratorio Semántico Offline)
* **Archivos clave:**
  - `tools/semantic_lab/features.py`
  - `tools/semantic_lab/encode.py`
* **Funcionamiento interno:**
  1. **Extracción geométrica y render neutro (`features.py`):** Lee el DXF con `ezdxf`, expande bloques `INSERT`, aplana curvas (`ARC`, `CIRCLE`, `ELLIPSE`, `SPLINE`, `LWPOLYLINE`, `POLYLINE`) y genera simultáneamente:
     - Un diccionario de características numéricas puras (`features: dict[str, float]`).
     - Una firma geométrica (`geometry_signature`) y un render PNG neutro (`render_sha256`).
  2. **Codificación local (`encode.py`):** Ejecuta modelos locales sin enviar etiquetas ni nombres de archivo al encoder en tres modos (`text`, `image`, `mixed`):
     - `dinov3` (`facebook/dinov3-vits16-pretrain-lvd1689m`) — solo imagen.
     - `embeddinggemma2` (`google/embeddinggemma-2`) — texto, imagen o mixto.
     - `minilm` (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) — solo texto.

---

## 3. Líneas de Trabajo Recomendadas sobre Vectores

| Prioridad | Línea de trabajo | Qué problema resuelve | Módulos implicados |
|:---:|---|---|---|
| **1** | **Score Híbrido Real** *(separar números del texto embebido)* | Evita que `width:900` en texto comprima los cosenos de OpenAI; combina exactitud matemática en medidas + IA en semántica. | `descriptor.py`, `service.py`, `math_utils.py` |
| **2** | **Imputación de Incógnitas por Precedentes (`kNN`)** | Sugiere espesores, materiales o acabados faltantes en planos pobres mostrando soporte y rango (`"7 de 8 similares usan 18 mm"`). | `similarity/`, `classification.py`, `frontend/` |
| **3** | **Vectorización Temprana desde DXF (`features.py` -> Producción)** | Permite buscar muebles similares **nada más subir el DXF**, antes de esperar al despiece del agente o del revisor. | `tools/semantic_lab/features.py`, `backend/app/geometria/` |
| **4** | **Conectar Embeddings Locales (`embeddinggemma2` / `dinov3`) al Explorador** | Habilita búsqueda semántica y visual 100% local y gratuita sin depender de llamadas a OpenAI. | `tools/semantic_lab/encode.py`, `semantic_explorer/` |

---

## 4. Núcleo Matemático Compartido (`math_utils.py`)

Toda similitud coseno en producción y explorador pasa por `backend/app/similarity/math_utils.py`:
- `normalize_vector` y `normalize_matrix` escalan previamente por el valor absoluto máximo para evitar *overflow*/*underflow* numérico en `float64`.
- `cosine_similarity` y `cosine_matrix` garantizan contratos de error estrictos:
  - `ValueError("embedding_space_incompatible")` si los vectores están vacíos o difieren en dimensión.
  - `ValueError("invalid_embedding")` si contienen `NaN`/`Inf` o tienen norma cero.

---

## 5. Estado tras la fusión de `precedentes` (ideas 2.1–3.5)

El paquete `backend/app/precedentes/` (detalle en [PRECEDENTES](PRECEDENTES.md)) consume los sistemas anteriores sin crear un espacio vectorial nuevo, salvo el mecanismo de imagen (3.3):

| Pieza | Sistemas que usa | Relación con las líneas de trabajo de la sección 3 |
|---|---|---|
| 2.1 Sugerencias de valores que faltan | B (`geometric_match`, umbral calibrado de `thresholds.py`) | **Línea 2 implementada en backend:** moda o mediana, soporte n/N, rango e ids de vecinos; estado `hipotesis` y abstención. Score relativo al techo alcanzable por la consulta. Falta la interfaz en Revisar. |
| 2.3 Score híbrido | A + B, coseno de `math_utils.py`, umbrales de `thresholds.py` | **Línea 1 a medias:** combina geométrico y coseno con pesos explícitos y abstención, pero el texto embebido sigue incluyendo medidas. Separarlas exige una nueva `descriptor_version` y volver a embeber. |
| 2.5 / 2.6 Regeneración y versionado del espacio | A | Mantenimiento del espacio de producción: obsoletos, deriva del modelo y rotación de la referencia. |
| 2.2 Presupuesto por analogía · 3.5 Herrajes | C (`find_comparables`, `estimate`) | Alerta por dispersión robusta del vecindario; herrajes en almacén propio. |
| 3.2 Búsqueda en lenguaje natural | B (filtros deterministas sobre descriptores) | LLM → filtros estructurados; no embebe la consulta. |
| 3.3 Embeddings de imagen | Nuevo espacio por `espacio_id`, coseno de `math_utils.py` | **Punto de enganche para las líneas 3 y 4:** protocolo `ProveedorEmbeddingImagen` y almacén listos; falta conectar `dinov3` o `embeddinggemma2` como proveedor. |
| 3.4 Decisiones de revisión · 2.7 Evaluación | Componentes de B y A | Recomendación de pesos por AUC y métricas P@k / nDCG con juicios de relevancia. |
