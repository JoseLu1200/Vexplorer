import { useState } from "react";
import { useStore } from "../state";
import Topography from "./rb/Topography";

/**
 * Curvas de nivel de la landing (Topography de React Bits) solo en estados vacíos, donde no hay datos.
 * Muy tenues, quietas con movimiento reducido y sin reacción al puntero. Sin WebGL2 no se dibuja nada.
 */
export function Relief() {
  const { theme } = useStore();
  const [ok] = useState(() => {
    try {
      return !!document.createElement("canvas").getContext("webgl2");
    } catch {
      return false;
    }
  });
  if (!ok) return null;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const light = theme === "light";
  return (
    <div className="pointer-events-none absolute inset-0 [mask-image:radial-gradient(closest-side,#000_35%,transparent)]" aria-hidden="true">
      <Topography
        color={light ? "#9a6a3c" : "#cfa477"}
        lightMode={light}
        lineCount={14}
        lineWidth={1.1}
        majorLines
        tilt={90}
        elevation={1.2}
        scale={0.8}
        detail={0.3}
        speed={reduced ? 0 : 0.03}
        morph={reduced ? 0 : 0.2}
        glow={0}
        depthOfField={0}
        fog={0}
        opacity={light ? 0.4 : 0.32}
        mouseInteraction={false}
        clickEffect="none"
        parallax={0}
        intro={false}
      />
    </div>
  );
}
