Sí, pero **uno ligero**. Para un hackathon no usaría LangChain ni frameworks pesados: añaden capas que depurar a las 3 de la mañana. Os basta con el *tool use* nativo de la API (Claude, OpenAI o la que tengáis) y un bucle de unas 50 líneas que vosotros controláis del todo. Si queréis algo hecho, el Agents SDK de OpenAI o el de Anthropic valen, pero el bucle propio es más fácil de depurar y de enseñar.

**Arquitectura**

```
[Frontend]  subir plano · traza del agente en vivo · tabla de despiece · visor 3D
     │ (HTTP + SSE para ir mostrando los pasos)
[Backend FastAPI]
     │
     ├─ 1. Ingesta        DWG → DXF (ODA), unidades, limpieza
     ├─ 2. Motor geométrico (determinista, sin IA)
     │      vistas · contornos · cotas · alineación entre vistas
     │      → genera piezas CANDIDATAS
     ├─ 3. Capa de herramientas   funciones + esquemas JSON
     ├─ 4. Agente LLM     revisa candidatas, resuelve dudas,
     │                     nombra piezas, agrupa iguales
     │                     → termina llamando a entregar_despiece()
     ├─ 5. Validador (determinista)
     │      ¿las piezas cuadran con las cotas generales?
     │      ¿hay piezas solapadas? → si falla, vuelve al agente
     └─ 6. Salida   JSON → tabla/CSV + cajas 3D
```

**Decisiones clave**

1. **El motor geométrico trabaja antes que el agente.** El agente no empieza de cero: recibe un primer borrador con las piezas candidatas y lo corrige. Así hace menos llamadas, tarda menos y se equivoca menos.
2. **La salida es una herramienta.** El agente termina llamando a `entregar_despiece(piezas)` con un esquema estricto (nombre, cantidad, largo, ancho, grosor, ids de contornos de origen). Nada de parsear texto libre.
3. **Trazabilidad:** cada pieza guarda los contornos de los que sale. En el frontend, al pasar por encima de una pieza de la tabla, se resalta en el plano. Es el detalle que enamora a los jueces.
4. **El validador cierra el ciclo.** Si algo no cuadra, el error vuelve al agente como mensaje ("las piezas suman 1250 mm y la cota general es 1200") y lo corrige. Así hay autocorrección real, no de adorno.
5. **Tened un plan B para la demo.** Si la API falla o tarda, se muestra el resultado del motor geométrico solo. Guardad también en caché las respuestas de los planos de la demo.
6. **Límites del bucle:** un máximo de unas 15 iteraciones, un tiempo máximo y registro de todo (os sirve para depurar y para la traza en pantalla).

**Extra para el pitch (opcional):** exponer las herramientas como **servidor MCP**. Con muy poco trabajo extra, cualquier asistente compatible (Claude Desktop, por ejemplo) podría usar vuestro "delineante". Queda muy bien como "plataforma", pero solo si os sobra tiempo.

**Reparto para un equipo de 3 o 4 personas**
- **Persona A:** ingesta y motor geométrico. Es la parte más crítica, que empiece ya.
- **Persona B:** herramientas, agente y validador.
- **Persona C:** frontend (tabla, traza en vivo, visor three.js).
- **Persona D, si la hay:** conseguir planos de prueba, pitch y plan B de la demo.

Lo que A y B tienen que acordar en la primera hora es **el formato JSON de las piezas y los contornos**. Ese contrato es lo que permite trabajar en paralelo.

¿Os escribo el esqueleto del backend (FastAPI con el bucle del agente y las herramientas definidas con datos falsos) para que cada uno pueda empezar ya a rellenar su parte?