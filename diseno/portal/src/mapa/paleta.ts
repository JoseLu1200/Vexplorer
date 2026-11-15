// Colores de grupo en tonos de material apagados: roble, cobalto, salvia, nogal, óxido oscuro, grafito, arena y pizarra.
// Validador de dataviz sobre papel #ece6da y noche #131a2c. Óxido frente a roble: ΔE 17,2 (claro) y 16,4 (oscuro);
// frente a nogal: 11,6 y 13,7, porque ambos son pardos oscuros. Peor par de toda la lista: grafito y nogal, ΔE 7,5,
// en claro; pizarra y grafito, ΔE 3,5, en oscuro. Son apagados a propósito y quedan por debajo del croma mínimo del
// validador, así que la leyenda filtra por grupo como codificación secundaria. El color va solo en puntos y muestras.
export const NOMBRES_MATERIAL = ["roble", "cobalto", "salvia", "nogal", "óxido", "grafito", "arena", "pizarra"];
export const PALETA_CLARA = ["#a07a48", "#2f4a86", "#8f9a72", "#6b4a34", "#a32b1f", "#4a4f5a", "#c4a46e", "#5d7488"];
export const PALETA_OSCURA = ["#c49a62", "#6f8ccf", "#a9b48c", "#85624a", "#d0503c", "#8e95a3", "#e0c690", "#86a0b6"];

export interface Tema {
  oscuro: boolean;
  paleta: string[];
  /** gris del grupo «otras» y de los puntos fuera del filtro. */
  otras: string;
  bg: string;
  ink: string;
  muted: string;
  line: string;
  raro: string;
}

const rgb = (s: CSSStyleDeclaration, v: string, fb: string) => {
  const t = s.getPropertyValue(v).trim();
  return t ? `rgb(${t.split(/\s+/).join(",")})` : fb;
};

export function leerTema(el: Element = document.documentElement): Tema {
  const s = getComputedStyle(el);
  const bg = s.getPropertyValue("--bg").trim().split(/\s+/).map(Number);
  const oscuro = bg.length === 3 && 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2] < 110;
  return {
    oscuro,
    paleta: oscuro ? PALETA_OSCURA : PALETA_CLARA,
    otras: oscuro ? "#5b6275" : "#b3ab9c",
    bg: rgb(s, "--bg", "#ece6da"),
    ink: rgb(s, "--ink", "#1c2541"),
    muted: rgb(s, "--muted", "#4c5570"),
    line: rgb(s, "--line", "#d0cac0"),
    // Anillo de los raros: madera oscura sobre papel, madera clara sobre noche.
    raro: oscuro ? "#e0b884" : "#7a4c1e",
  };
}

export const colorGrupo = (t: Tema, g: number, otras: number) => (g === otras ? t.otras : t.paleta[g % t.paleta.length]);
