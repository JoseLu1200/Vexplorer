# Reutilización e inspiración open source

Consulta de repositorios y documentación oficiales: 2026-11-13. Decisiones para la ampliación del visor, no una comparación exhaustiva de productos. La aceptación de integración se registra en [VISOR_RECONSTRUCCION_SIMILITUD](VISOR_RECONSTRUCCION_SIMILITUD.md).

| Proyecto | Licencia consultada | Uso decidido |
|---|---|---|
| [ezdxf](https://github.com/mozman/ezdxf) | [MIT](https://github.com/mozman/ezdxf/blob/master/LICENSE) | Reutilizar `drawing.SVGBackend` para representar el CAD original. La extracción determinista sigue siendo independiente. |
| [Three.js](https://github.com/mrdoob/three.js) | [MIT](https://github.com/mrdoob/three.js/blob/dev/LICENSE) | Dependencia local del visor 3D: cajas, cámara, `OrbitControls` y selección `Raycaster`. |
| [vagran/dxf-viewer](https://github.com/vagran/dxf-viewer) | [MPL-2.0](https://github.com/vagran/dxf-viewer/blob/master/LICENSE) | Inspiración para encuadre, capas, coordenadas de cursor y eventos. No incorporar su código ni un segundo parser DXF. |
| [three-dxf](https://github.com/gdsestimating/three-dxf) y [dxf-parser](https://github.com/gdsestimating/dxf-parser) | [MIT](https://github.com/gdsestimating/three-dxf/blob/master/LICENSE), [MIT](https://github.com/gdsestimating/dxf-parser/blob/master/LICENSE) | Evaluados, no incorporados: duplicarían el parseo de ezdxf y su asociación de entidades. |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | [MIT](https://github.com/openai/openai-agents-python/blob/main/LICENSE) | Referencia para validación de herramientas, presupuestos y errores controlados. Se mantiene el bucle propio. |
| [PydanticAI](https://github.com/pydantic/pydantic-ai) | [MIT](https://github.com/pydantic/pydantic-ai/blob/main/LICENSE) | Referencia para límites de uso y reparaciones acotadas. No añadir framework. |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) | [MIT](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-MIT) / [Apache-2.0](https://github.com/asg017/sqlite-vec/blob/main/LICENSE-APACHE) | Posible índice futuro si crece la biblioteca; no necesario para la demo local. |
| [scikit-learn](https://github.com/scikit-learn/scikit-learn) | [BSD-3-Clause](https://github.com/scikit-learn/scikit-learn/blob/main/COPYING) | Referencia de similitud coseno, sin añadir dependencia para un agrupado por umbral. |

## Qué aporta cada elección

La [representación SVG nativa de ezdxf](https://ezdxf.readthedocs.io/en/stable/addons/drawing.html) conserva más grafismo del CAD que el subconjunto admitido para inferir piezas: textos, bloques, curvas y representación de cotas. El SVG usa coordenadas de página transformadas; no sirve como evidencia métrica ni comparte automáticamente los identificadores del ledger. Se muestra como imagen separada, sin superponer selecciones no registradas. Se omiten imágenes adjuntas, proxies y rellenos de tramas; el render tiene límites de expansión y tamaño. El presupuesto temporal se comprueba entre entidades, no interrumpe un cálculo individual.

Aunque el backend SVG se describe como nativo, la versión instalada de `ezdxf.addons.drawing` importa `PIL.Image`: se declaró Pillow para hacer reproducible el arranque. No se usa el backend PyMuPDF para esta representación.

El [visor DXF de vagran](https://github.com/vagran/dxf-viewer/blob/master/docs/api.md) aporta referencias útiles de interacción (`FitView`, visibilidad por capas, eventos y conversión de coordenadas). Su propia lista de límites incluye cotas parciales y ausencia de layouts. Elegirlo como segundo parser crearía dos interpretaciones del mismo dibujo; por ello se conservan los datos normalizados de Pydantic.

Los patrones de [herramientas de Agents SDK](https://github.com/openai/openai-agents-python/blob/main/src/agents/tool.py) y [límites de PydanticAI](https://github.com/pydantic/pydantic-ai/blob/main/docs/agent.md) sirven de referencia para validar argumentos y referencias antes de ejecutar, devolver errores corregibles y limitar reparaciones. Las trazas del producto contienen acciones, referencias y resúmenes; no requieren exportar prompts, respuestas completas o razonamiento interno a una plataforma externa.

La similitud usa [coseno](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.cosine_similarity.html) y una biblioteca pequeña. Se versionan descriptor, modelo y dimensiones; no se comparan espacios incompatibles. Una coincidencia ayuda a recuperar muebles, pero no confirma identidad de piezas, cantidades, intercambiabilidad ni precio. Los embeddings se solicitan a la [API oficial](https://developers.openai.com/api/docs/guides/embeddings) únicamente cuando se pide el modo semántico con un proveedor configurado.

No se han importado datasets de estos proyectos. PlankAssembly conserva su tratamiento y condiciones independientes.
