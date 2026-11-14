// Ruta #mapa del portal: el mapa a pantalla completa con el logo de esquina y «Volver».
import { LogoMark } from "../components/Logo";
import { MapaMuebles } from "./MapaMuebles";

// «Volver» lleva a la última ruta del portal que no era el mapa, aunque dentro del mapa se haya cambiado el foco varias veces.
let origen = "#/";
addEventListener("hashchange", (e) => {
  const previo = new URL(e.oldURL).hash;
  if (!previo.startsWith("#mapa")) origen = previo || "#/";
});
const volver = () => {
  location.hash = origen;
};

export function PaginaMapa() {
  // Admite #mapa?foco=<id> (enlaces del portal) y ?foco=<id> en la URL.
  const h = location.hash;
  const q = new URLSearchParams(h.includes("?") ? h.slice(h.indexOf("?") + 1) : location.search);
  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-bg text-ink">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-line px-s3">
        <a href="#/" className="flex items-center gap-s2 text-ink" aria-label="Vexplorer, inicio">
          <LogoMark size={26} />
          <span className="font-display text-lg font-bold leading-none">Vexplorer</span>
        </a>
        <button type="button" onClick={volver} className="h-8 px-s2 text-sm text-ink hover:bg-sunken">
          Volver
        </button>
      </header>
      <div className="relative min-h-0 flex-1">
        <MapaMuebles focoId={q.get("foco")} />
      </div>
    </div>
  );
}
