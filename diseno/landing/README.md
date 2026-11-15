# Vexplorer, diseño

Prototipos de diseño de Vexplorer fuera del repositorio principal, porque el `CLAUDE.md` de Vexplorer exige un archivo de equipo en `team/` antes de editar código y todavía no existe uno para este trabajo.

Cada línea de trabajo vive en su propia rama:

| Rama | Contenido | Carpeta |
|---|---|---|
| `app-producto` | Interfaz de producto (Vite + React + TS) con cliente de la API real y mock | `app-producto/` |
| `landing-editorial` | Landing completa, dirección editorial | `.wt/landing-editorial/` (worktree) |
| `landing-cobalto` | Landing completa, dirección cobalto | `.wt/landing-cobalto/` (worktree) |
| `landing-cobalto-b` | Variante Ensamble de la línea cobalto, sobre la ronda 12 | `.wt/landing-cobalto-b/` (worktree) |

`main` solo contiene este README. Nada se ha subido a ningún remoto.

## Ronda 12

La rama `landing-cobalto-r12` sale de la v11 congelada y recorta la landing a tres bloques y el pie: el tramo del plano vivo, el esquema 3D y el formulario de demo.

- **Titular:** «Vexplorer» a todo el ancho en Sofia Sans, con el peso animado letra a letra entre 700 y 860 por BreathingText de Fancy Components. Con movimiento reducido se queda a 700.
- **Plano:** con el titular a todo el ancho no cabe en la primera pantalla a un tamaño legible, así que entra cuando el hero ya ha salido (P 0,07, unos 126 px de scroll a 1440) y se dibuja pieza a pieza en ese momento.
- **Forma orgánica:** Topography de React Bits detrás del titular y del plano, con las curvas en vista cenital cruzando la retícula y las cotas.
- **Foto:** `wood-texture-light.webp` (Kurt Kaiser, CC0) a todo el ancho, recortada a la fila de nudos y en duotono cobalto sobre papel con niveles ajustados a su rango de luminancia. Baja y sale cuando el plano se abre.
- **Componentes:** Topography, DecryptedText y Crosshair de React Bits, BreathingText de Fancy Components y TextMorph de Torph. StrokeText y MarqueeAlongSvgPath quedan en `src/components/` sin usar.
- **Fuera:** la ficha exportada, el histórico de muebles parecidos, el precio, el teléfono, la pregunta de planos, la leyenda de asteriscos, la nota de privacidad sin destino y los párrafos de apoyo.

| Medida | v11 a 1440 | v11 a 390 | r12 a 1440 | r12 a 390 |
|---|---|---|---|---|
| Palabras con `words.mjs` (scroll 0) | 527 | 486 | 91 | 91 |
| Palabras con todos los estados del tramo visibles | 741 | 700 | 198 | 215 |
| `<section>` más el tramo | 4 + 1 | 4 + 1 | 2 + 1 | 2 + 1 |
| Alto | 7.153 px | 8.222 px | 4.140 px | 4.114 px |
 Capturas en `capturas/r12` y estados del tramo en `capturas/r12/estados`. `build.html` se genera con `npm run build` y `python strip.py` desde la raíz del worktree.

## Variante Ensamble

La rama `landing-cobalto-b` sale de la ronda 12 y mantiene su esqueleto y su copy, pero cambia dos elementos con el eje puesto en componentes e interacción, y antes corrige la regla del fondo.

- **Regla del fondo:** las curvas de nivel solo están en el hero y se apagan entre P 0,03 y 0,07, antes de que la caja del plano empiece a entrar en P 0,07, así que ni la caja con sus piezas, cotas y rótulos, ni la tabla de 390, ni los filtros, ni el formulario tienen nada orgánico, fotográfico o texturizado detrás en ningún tema. La caja es papel liso y opaco, sin la retícula que llevaba la ronda 12.
- **Esquema 3D:** el bloque cobalto pasa a ser un tramo fijo de 280svh donde la estantería entra explosionada, con cada pieza fuera por su propio eje, y el scroll la cierra pieza a pieza en el orden de montaje con la pieza que se mueve en ámbar. Las cotas de 1800, 900 y 400 mm salen con el mueble cerrado y la de 1800 va girada como en el plano. Con movimiento reducido es un bloque normal con el mueble montado, sin WebGL el isométrico de respaldo también se cierra con el scroll, y la retícula de suelo desaparece.
- **Filtros de clase de dato:** TrueFocus de React Bits sustituye a los botones con DecryptedText, y su marco de cuatro esquinas va a la clase que el plano está enseñando, sigue el avance del scroll y salta a la que se pulse. Las inactivas van en tinta secundaria, con 5,95:1 en claro y 7,82:1 en oscuro.
- **Componentes en uso:** Topography, Crosshair y TrueFocus de React Bits (MIT + Commons Clause), con TrueFocus adaptado a índice controlado y botones con `aria-pressed`, BreathingText de Fancy Components (MIT) y TextMorph de Torph (MIT). DecryptedText, ScrollReveal, StrokeText y MarqueeAlongSvgPath quedan en `src/components/` sin usar.

Capturas en `capturas/ensamble` y estados del plano y del esquema en `capturas/ensamble/estados`. `build.html` se genera con `npm run build` y `python -I strip.py` desde la raíz del worktree.
