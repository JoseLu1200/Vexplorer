/** @type {import('tailwindcss').Config} */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      bg: v("bg"), surface: v("surface"), sunken: v("sunken"), line: v("line"), "line-strong": v("line-strong"),
      ink: v("ink"), muted: v("muted"), faint: v("faint"),
      cobalt: v("cobalt"), block: v("block"), "on-block": v("on-block"), "on-block-2": v("on-block-2"),
      wood: v("wood"), "wood-ink": v("wood-ink"),
      calc: v("calc"), hip: v("hip"), conf: v("conf"),
      danger: v("danger"), "danger-soft": v("danger-soft"),
      canvas: v("canvas"), "canvas-line": v("canvas-line"), "canvas-ink": v("canvas-ink"),
      dim: v("dim"), "unknown-bg": v("unknown-bg"), "unknown-ink": v("unknown-ink"), select: v("select"),
    },
    fontFamily: {
      sans: ['"Sofia Sans Semi Condensed"', '"Arial Narrow"', "Arial", "sans-serif"],
      display: ['"Sofia Sans Extra Condensed"', '"Arial Narrow"', "sans-serif"],
      mono: ['"Martian Mono"', "ui-monospace", "Consolas", "monospace"],
      // Solo para el titular de la entrada, como en la landing.
      serif: ['"Instrument Serif"', "Georgia", "serif"],
    },
    fontSize: {
      // Escala tipográfica: 12 / 13 / 14 / 15 / 17 / 22 / 32. La landing no baja de 14 en texto corrido.
      "2xs": ["12px", { lineHeight: "16px" }],
      xs: ["13px", { lineHeight: "18px" }],
      sm: ["14px", { lineHeight: "20px" }],
      base: ["15px", { lineHeight: "22px" }],
      md: ["17px", { lineHeight: "24px" }],
      lg: ["22px", { lineHeight: "26px" }],
      xl: ["32px", { lineHeight: "34px" }],
    },
    // Cantos rectos, como la landing. «full» queda para puntos de estado.
    borderRadius: { none: "0", sm: "0", DEFAULT: "0", md: "0", lg: "0", full: "9999px" },
    extend: {
      // Escala de espacio de la landing: 4 · 8 · 12 · 20 · 32 · 52 · 84 · 136.
      spacing: { s1: "4px", s2: "8px", s3: "12px", s4: "20px", s5: "32px", s6: "52px", s7: "84px", s8: "136px" },
    },
  },
  plugins: [],
};
