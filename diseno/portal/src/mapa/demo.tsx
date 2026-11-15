// Página de prueba del mapa: /src/mapa/demo.html?foco=<id>&espacio=<clave>&proyeccion=pca3|umap2|tsne2&tema=dark
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles.css";
import { MapaMuebles } from "./MapaMuebles";

const q = new URLSearchParams(location.search);
if (q.get("tema")) document.documentElement.dataset.theme = q.get("tema")!;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <div className="h-full w-full">
      <MapaMuebles focoId={q.get("foco")} espacio={q.get("espacio") ?? undefined} proyeccion={(q.get("proyeccion") as "pca3" | "umap2" | "tsne2" | null) ?? undefined} depuracion />
    </div>
  </StrictMode>,
);
