import { useId } from "react";

/** Los dos tableros del logo de la landing cobalto, en un viewBox de 100. */
export const LOGO_A = "4,24 20,24 50,80 34,80";
export const LOGO_B = "28,24 44,24 74,80 58,80";

/**
 * Logo de Vexplorer, copiado del componente `Logo` de la landing (landing-cobalto-b, src/App.tsx): dos tableros de borde
 * fino y una flecha de cota de (34,80) a (74,24) con la punta en ángulo recto, que pasa por detrás de los tableros con una
 * máscara. El favicon de index.html y public/favicon.svg es el de la landing.
 */
export function LogoMark({ size = 30, stroke = 5, className = "" }: { size?: number; stroke?: number; className?: string }) {
  const id = `lm${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} className={`text-ink ${className}`} aria-hidden="true" focusable="false" style={{ overflow: "visible" }}>
      <defs>
        <mask id={id} maskUnits="userSpaceOnUse" x="-10" y="-10" width="120" height="120">
          <rect x="-10" y="-10" width="120" height="120" fill="white" />
          <polygon points={LOGO_A} fill="black" />
          <polygon points={LOGO_B} fill="black" />
        </mask>
      </defs>
      <g mask={`url(#${id})`} stroke="currentColor" strokeWidth={stroke + 1.5} fill="none">
        <path d="M34 80 L74 24" />
        <path d="M60 24 L74 24 L74 38" strokeLinecap="square" strokeLinejoin="miter" />
      </g>
      <polygon points={LOGO_A} fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinejoin="miter" />
      <polygon points={LOGO_B} fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinejoin="miter" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="inline-flex items-center gap-s2" aria-label="Vexplorer">
      <LogoMark />
      <span className="translate-y-px text-[21px] font-bold leading-none tracking-[0.005em] text-ink" aria-hidden="true">Vexplorer</span>
    </span>
  );
}
