import re,sys
# Ejecutar desde la raíz del worktree después de `npm run build`: empaqueta dist/index.html en build.html.
src='dist/index.html'; dst='build.html'
s=open(src,encoding='utf8').read()
s=re.sub(r'<!doctype html>\s*','',s,flags=re.I)
s=re.sub(r'</?html[^>]*>','',s); s=re.sub(r'</?head>','',s); s=re.sub(r'</?body>','',s)
s=re.sub(r'<meta charset="UTF-8" />\s*','',s)
s=re.sub(r'<meta name="viewport"[^>]*>\s*','',s)
head='<!-- Vexplorer, landing cobalto, variante Ensamble (sale de la ronda 12). Componentes de terceros: React Bits (MIT + Commons Clause, David Haz): Topography y Crosshair. Demo en cinco pasos con la cajonera F02 de los controles CAD de Vexplorer (DXF y despiece revisado reales; precios con las tarifas de ejemplo del backend). Fuentes: Instrument Serif, Sofia Sans y Martian Mono (OFL) desde Google Fonts. Fotos: Carpentry_workshop_full_of_machines_and_wood.jpg de Shixart1985 (CC BY 2.0, crédito en el pie); Wood_texture,_light.jpg de Kurt Kaiser, Wikimedia Commons, CC0, en duotono cobalto. -->\n'
open(dst,'w',encoding='utf8').write(head+s.strip()+'\n')
