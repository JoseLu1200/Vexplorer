# Agente UX layout — legibilidad y desplazamiento

## Identidad y autorización

- Identidad: agente de IA de interfaz; no representa a una persona.
- Rol: corregir jerarquía visual, densidad, radios y acceso al contenido en Vexplorer.
- Autorización: delegación explícita del coordinador del 2026-11-14 dentro del swarm autorizado por el usuario.

## Alcance y reservas

- Propiedad exclusiva: `frontend/styles.css`, `frontend/index.html` y este registro.
- Solo lectura: `frontend/app.js`, componentes, backend, contratos y registros ajenos.
- Se preservan los cambios locales previos y todos los IDs, `data-*`, estados, unidades y procedencia consumidos por la aplicación.
- Sin commit, push ni despliegue.

## Objetivo y estrategia

- Mantener el recorrido plano → piezas → revisión → biblioteca → coste, con la procedencia siempre visible.
- Hacer accesible el contenido en escritorio, móvil, baja altura y zoom de 200 %, evitando alturas incompatibles y contenedores con `overflow` bloqueado.
- Reducir texto estructural y apelotonamiento mediante jerarquía, aire y plegados nativos solo si no alteran hooks funcionales.
- Aplicar una estética técnica sobria: shell de 10–12 px, controles de 6–8 px y píldoras reservadas a estados o etiquetas.

## Estado y verificación

- Estado: implementación UX terminada y suite compartida verde.
- `frontend/styles.css`: cascarón 12 px, tarjetas 8–10 px, controles 6–8 px; jerarquía y contraste reforzados; toolbar en dos filas con scroll interno por grupo; tabla y panel con scroll independiente en escritorio; reflow de documento en móvil/zoom; fallback desplazable para menos de 520 px de alto.
- `frontend/index.html`: se conservaron IDs y `data-*`; fuentes locales precargadas, estado de sesión rotulado para el raíl contraído y tabs estáticas con semántica accesible. Coste mantiene procedencia y tarifa principal visibles, agrupa material/canteado y operaciones/alcance en dos detalles, y deja visible el aviso que impide interpretar un subtotal incompleto como total.
- `frontend/assets/fonts/*`: Geist Variable y Geist Mono Variable 5.3.0, subconjunto latino local de Fontsource, con licencia OFL incluida; sin CDN.
- Verificación compartida final: `npm test --prefix frontend` → 161/161 correctas en 248 ms.
- `git diff --check -- frontend/index.html frontend/styles.css frontend/assets/fonts team/agente_ux_layout.md` → correcto.
- Playwright CLI sobre Edge y servidor aislado: Geist/Mono cargadas; ancho documento/viewport 390/390, 720/720, 980/980 y 1440/1440; sin scroll horizontal global. En 390×844, tabla `scrollWidth=511`, `clientWidth=374` con scroll local y panel tras el dock. En 1100×500, cabecera de piezas conserva 92/91 px y la tabla ocupa los 58 px restantes con scroll. En 1440, toolbar `scrollWidth=clientWidth`, vistas con scroll interno y controles de capas visibles en segunda fila.
- Capturas finales: `.runtime/ui-review-maisa/layout-mobile-final.png`, `layout-short-final.png`, `layout-zoom200-final.png`, `layout-toolbar-desktop.png`, `layout-toolbar-collapsed.png` y `layout-cost-mobile.png`.
- Comprobación Coste en 390×844: documento 390/390, ambos `details` cerrados inicialmente, procedencia sintética y tarifa principal visibles, y aviso de campos desconocidos fuera de los plegados.

## Dependencias y avisos

- `frontend/app.js` está reservado por el agente funcional. No se renombran IDs ni atributos usados por sus selectores.
- El coordinador mantiene el servidor de revisión aislado en `http://127.0.0.1:8771`; no se usará su superficie Playwright/Chrome sin coordinación.
- El `404` de `table-costs` observado en la ejecución restaurada indica que esa revisión no tiene estimación guardada; la interfaz lo trata como estado aditivo ausente y no como un fallo de layout.
