# Especificación UX de la demo

## Intención

Una persona técnica debe pasar de un DXF a una ficha revisable de despiece y coste, sin confundir observaciones del plano con cálculos, hipótesis o decisiones humanas. El objetivo principal de cada ejecución es **resolver la siguiente incertidumbre respaldada**, no producir la tabla más llena.

## Dirección visual

Cuaderno técnico industrial claro, con fondo marfil, tinta oscura y un único acento cobalto. Una retícula visible, numeración de pasos y etiquetas monoespaciadas aportan precisión sin imitar software CAD antiguo. La firma visual es una regla vertical que conecta las cinco etapas del trabajo y cambia de estado con la ejecución.

## Recorrido y estructura

1. **Carga**. Estado inicial compuesto con una zona de carga DXF, límite de 20 MiB, modo disponible y explicación breve de privacidad y alcance.
2. **Lectura del plano**. Visor SVG generado solo con puntos seguros del API, selector de vista y panel de evidencia. La unidad queda siempre visible.
3. **Propuestas**. Tabla de componentes vinculada bidireccionalmente al plano. Cantidad, largo, ancho y grosor aceptan ausencia explícita.
4. **Decisión técnica**. Escenarios incompatibles se comparan como alternativas. La persona registra escenario, cantidad, espesor o montaje permitido y motivo. La revisión obsoleta se recarga sin sobrescribir.
5. **Estimación y salida**. Histórico sintético rotulado, diferencias verificables, conceptos con cantidades y tarifas, subtotal provisional, horas, exclusiones y exportación de ficha y traza.

La traza permanece accesible en un cajó lateral y contiene acciones, evidencias y estados, nunca razonamiento interno.

## Copia principal

- Título: «Del plano a una decisión revisable».
- Explicación: «Carga un DXF de una estantería. Vexplorer separa lo medido de lo supuesto, enlaza cada propuesta con el dibujo y prepara una estimación provisional.»
- Acción primaria inicial: «Analizar DXF».
- Señal de confianza: «La geometría funciona sin proveedor. Ningún campo desconocido se rellena automáticamente.»
- Beneficio de continuidad: «Cada cifra conserva su origen. Cada duda termina en una decisión registrada.»

## Jerarquía de datos

| Clase | Etiqueta | Presentación |
|---|---|---|
| Observación | Observado | tinta neutra, enlace directo a evidencia |
| Cálculo | Calculado | cobalto, operación y premisas visibles |
| Hipótesis | Hipótesis | ámbar, escenario y pendiente visible |
| Decisión | Confirmado por persona | verde, revisión y motivo visibles |
| Ausencia | Desconocido | trama suave y texto literal, nunca cero o guión aislado |

## Estados obligatorios

- Carga, análisis, error recuperable, error terminal, vacío y resultado parcial.
- `geometry_only` siempre visible y disponible.
- `live` solo habilitado cuando `capabilities.live_available` sea verdadero.
- `recorded_replay` solo habilitado cuando la API anuncie una grabación real, con ID y fecha de origen.
- Unidad desconocida usa coordenadas fuente y el texto «Unidad sin resolver»; no presenta milímetros.
- Sin propuestas se conserva el plano y se explica qué dato falta.
- Histórico sintético y estimación provisional se rotulan en cabecera y exportación.

## Accesibilidad y seguridad

- Un solo `h1`, landmarks semánticos, enlace de salto, foco visible y controles de al menos 44 píxeles.
- La selección no depende solo del color; usa `aria selected`, contorno y texto.
- Actualizaciones importantes emplean `aria-live` sin narrar cada evento SSE.
- El nombre del archivo y los textos del DXF se insertan con `textContent` o nodos de texto, nunca con `innerHTML`.
- Animaciones limitadas a opacidad y transformación, con reducción de movimiento respetada.

## No objetivos

- Reconstrucción 3D, edición CAD, fabricación certificada o presupuesto aprobado.
- Cálculo de medidas, cantidades o totales que ya pertenezca al backend.
- Datos de demostración incrustados que aparenten una ejecución real.

