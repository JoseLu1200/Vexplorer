# Brainstorming: Casos de Uso y Explotación del Sistema de Embeddings en Vexplorer

**Fecha:** 2026-11-14  
**Área:** Semántica, Machine Learning, Visor y CAD-Completion  
**Documento de referencia interna:** `docs/BRAINSTORMING_EMBEDDINGS.md`

---

## 1. Contexto y Ventaja Competitiva de Vexplorer

A diferencia de sistemas genéricos de Retrieval-Augmented Generation (RAG) o búsqueda vectorial textual, Vexplorer combina:
1. **Descriptores Técnicos Estructurados:** Normalización topológica del mueble, relaciones dimensionales ($X, Y, Z$), roles funcionales de piezas (`side_panel`, `shelf`, `top_panel`, `base_panel`, `leg`, etc.) y esquemas de ensamblaje (`top_base_between_sides`, `cap_sides`, etc.).
2. **Representación Vectorial Semántica:** Espacio latente (`OpenAIEmbeddingProvider`) alimentado con representaciones normalizadas ricas y reproducibles.
3. **Huella Digital Invariante a Traslación:** Hashes deterministas que aíslan la geometría de las coordenadas absolutas del dibujo CAD.

Este documento formaliza el brainstorming estratégico para explotar este sistema en 5 verticales de alto impacto.

---

## 2. Cinco Verticales de Explotación

### Eje 1: CAD-Completion y Autocompletado de Planos Incompletos

* **Imputación de incógnitas por vecino más cercano (Nearest-Neighbor Imputation):**
  - **Problema:** En planos 2D esquemáticos es muy frecuente la ausencia de cotas de espesor o profundidades ocultas.
  - **Solución con embeddings:** Proyectar la topología y dimensiones conocidas en el espacio vectorial y recuperar los $k$ muebles análogos más cercanos del histórico.
  - **Comportamiento:** Si el 95% del clúster vecino utiliza tablero de 19 mm con canteado de 1 mm, el sistema sugiere automáticamente el valor con métrica de confianza técnica, acelerando la revisión humana.
* **Inferencia de herrajes y mecanizados ocultos:**
  - Los planos 2D habitualmente omiten mecanizados internos (cremalleras de taladros, tubillones, excéntricas minifix).
  - Al vectorizar un tipo de unión estructural, el modelo puede emparejar el ensamble con su kit de mecanizado y tornillería estándar en taller.

---

### Eje 2: Presupuestación Instantánea por Analogía (Cost Retrieval)

* **Tarificación por analogía en 2 segundos:**
  - En lugar de reconstruir tiempos de seccionadora, canteadora y CNC desde cero cuando se requiere un presupuesto rápido, el embedding rescata los 3 proyectos fabricados más similares en complejidad geométrica y volumen de corte.
  - *Ejemplo de salida:* "Mueble similar al proyecto 'Hotel Bilbao 2025' (Similitud: 0.96). Coste real registrado: 142,50 €. Rango estimado: 140–150 €".
* **Detección temprana de anomalías de coste (Outlier Detection):**
  - Si el cálculo paramétrico arroja un coste que se desvía más de un 35% del promedio de su vecindario latente, se levanta una alerta técnica antes de emitir la oferta (evitando presupuestos a pérdidas o desorbitados por sobredimensionamiento).

---

### Eje 3: Búsqueda Multimodal y Lenguaje Natural (NL to CAD Retrieval)

* **Búsqueda conversacional en el archivo de planos:**
  - Permitir al personal de oficina técnica o compras buscar sobre miles de archivos DXF sin recordar nombres de archivo o códigos internos:
    - *"Estanterías estrechas de más de 2 metros con al menos 4 baldas"*.
    - *"Muebles bajos de televisión con zócalo cerrado y distribución simétrica"*.
  - El prompt en lenguaje natural se mapea al espacio de embeddings compartido con los descriptores de los planos.
* **Búsqueda inversa de soluciones (Reverse CAD Search):**
  - Un cliente o arquitecto aporta un boceto o un plano nuevo; el sistema extrae las proporciones y roles, genera el embedding y localiza en el catálogo de fábrica la solución más próxima para reutilizar programas de mecanizado existentes sin rediseñar.

---

### Eje 4: Optimización de Fabricación en Lote (Clustering & Nesting)

* **Agrupamiento inteligente de órdenes de fabricación (Batching):**
  - Ante lotes heterogéneos de pedidos, los algoritmos de clustering (`/api/v1/library/groups`) agrupan los muebles por familias morfológicas compatibles.
  - Permite coordinar tiradas de corte con espesores y materiales homogéneos, maximizando el aprovechamiento del tablero (*nesting* masivo y reducción de mermas).
* **Deduplicación y modularización de piezas:**
  - Extender la vectorización a nivel de componente individual (pieza aislada).
  - Detectar piezas prácticamente gemelas entre clientes distintos (ej. 800×400×18 mm vs. 802×400×18 mm) y recomendar la unificación hacia piezas modulares de stock.

---

### Eje 5: Control de Calidad y Validación de Diseño Pre-Corte (Design QA)

* **Detección de incongruencias estructurales:**
  - El espacio latente codifica implícitamente las proporciones funcionales y saludables de los muebles.
  - Si un plano plantea una balda de 1300 mm en tablero fino de 16 mm sin montante intermedio, el vector resultante cae fuera de la distribución normal (*out-of-distribution*), alertando de riesgo mecánico por pandeo antes de pasar a producción.

---

## 3. Matriz de Priorización

| Iniciativa | Impacto Técnico / Comercial | Complejidad | Aprovechamiento de Código Actual |
|---|:---:|:---:|:---:|
| **1. Autocompletado de incógnitas por precedentes** | 🟢 Muy Alto | 🟢 Baja/Media | **Directo:** Biblioteca, descriptores y oráculo existentes |
| **2. Búsqueda por lenguaje natural (NL to CAD)** | 🟢 Muy Alto | 🟡 Media | **Directo:** `OpenAIEmbeddingProvider` y `descriptor.py` |
| **3. Presupuestador comparativo instantáneo** | 🟢 Alto | 🟢 Baja | **Directo:** Servicio de costes y comparables ya implementados |
| **4. Agrupamiento para optimización de corte** | 🟡 Medio/Alto | 🟡 Media | **Directo:** Endpoints `/api/v1/library/groups` |
| **5. QA estructural y alertas de pandeo** | 🟡 Medio | 🔴 Alta | Requiere dataset calibrado de resistencia de materiales |

---

## 4. Hoja de Ruta Sugerida

1. **Fase 1 (Inmediata):** Exponer un endpoint de búsqueda semántica abierta (`POST /api/v1/library/search`) que acepte texto libre y devuelva los ítems del histórico ordenados por similitud coseno.
2. **Fase 2:** Integrar en el panel de revisión humana (`Revisar`) una tarjeta de sugerencias: "Precedentes históricos sugieren: espesor 18 mm (similitud 0.94)".
3. **Fase 3:** Incorporar la comparativa de costes histórica directamente en la ficha técnica exportable.
