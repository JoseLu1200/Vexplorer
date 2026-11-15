# Martín — diseño de landing y portal

## Identidad y autorización

- Nombre declarado por el usuario: Martín
- Rol: diseño de landing e interfaz, en apoyo de C
- Archivo creado por instrucción explícita del usuario («pushea a main todo») el 2026-11-14
- Última actualización: 2026-11-14

## Tarea de la sesión

- Objetivo: subir los prototipos de diseño (landing, portal y logos) para que el equipo los vea.
- Estado: entregado.

## Alcance y reservas

- Archivos o carpetas que puedo editar: `diseno/**` y este archivo.
- Dependencias que solo leo: `backend/`, `data/`, `docs/`, `frontend/`.
- Solapes: ninguno. No toca `frontend/` (C) ni contratos.

## Hecho en el último bloque

- `diseno/portal`: portal con mesa de trabajo, catálogo con montajes 3D, proceso guiado, Construcción 3D (GLB) y mapa de muebles con embeddings, contra los paquetes de demo de `data/`.
- `diseno/landing` y `diseno/logos`.

## Dependencias / avisos

- El portal consume la API real en modo lectura y los paquetes `data/full_app_demo`, `data/plank_pipeline_demo` y `data/semantic_pipeline_demo`. Necesitaría rutas de listado de documentos y runs, y carpetas, para no depender del navegador.
