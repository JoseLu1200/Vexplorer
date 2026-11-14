import type { CSSProperties } from "react";
import { COPY } from "../copy";
import { fmt, type Cell, type DataClass } from "../lib/domain";

const TONE: Record<DataClass, string> = {
  observed: "text-ink",
  calculated: "text-calc",
  hypothesis: "text-hip",
  confirmed: "text-conf",
  unknown: "text-muted",
};
const VAR: Record<DataClass, string> = {
  observed: "var(--ink)",
  calculated: "var(--calc)",
  hypothesis: "var(--hip)",
  confirmed: "var(--conf)",
  unknown: "var(--muted)",
};

/** Muestra de la landing: tablero con borde del color de la clase y relleno al 30 %; Desconocido lleva trama. */
export function Swatch({ cls, size = "sm" }: { cls: DataClass; size?: "sm" | "md" }) {
  const box = size === "md" ? "h-[14px] w-[18px]" : "h-[10px] w-[13px] [border-width:1.5px]";
  return <span className={`swatch ${box} ${cls === "unknown" ? "swatch-unknown" : ""}`} style={{ "--c": VAR[cls] } as CSSProperties} aria-hidden="true" />;
}

/** Marca en las celdas. Lo observado es el caso por defecto y va sin muestra; Desconocido se escribe con la palabra. */
export function ClassMarker({ cls }: { cls: DataClass }) {
  return cls === "observed" || cls === "unknown" ? null : <Swatch cls={cls} />;
}

export function ClassChip({ cls, label }: { cls: DataClass; label?: string }) {
  return (
    <span className={`inline-flex items-center gap-s2 text-sm ${TONE[cls]}`}>
      <Swatch cls={cls} />
      <span>{label ?? COPY.classes[cls]}</span>
    </span>
  );
}

/** Celda de valor. Observado sin marca; desconocido escrito; en conflicto, con el aviso escrito. */
export function ValueCell({ cell, unit, align = "right" }: { cell: Cell; unit?: string; align?: "left" | "right" }) {
  const label = cell.conflict ? "En conflicto" : COPY.classes[cell.cls];
  const justify = align === "right" ? "justify-end" : "";
  if (cell.value === null || cell.value === undefined) {
    return (
      <span className={`inline-flex items-center whitespace-nowrap text-sm text-muted ${justify}`}>
        {cell.note ? `desconocido · ${cell.note.toLowerCase()}` : "desconocido"}
      </span>
    );
  }
  const text = typeof cell.value === "number" ? fmt(cell.value) : cell.value;
  // Toda cifra (también los importes ya formateados) va en la mono tabular.
  const numeric = typeof cell.value === "number" || /^[\d.,\s€×-]+$/.test(String(cell.value));
  if (cell.conflict) {
    return (
      <span className={`inline-flex items-center gap-s2 ${justify}`} title={label}>
        <span className="num font-mono text-[13px] text-danger line-through decoration-danger/60">{text}</span>
        {unit && typeof cell.value === "number" && <span className="text-2xs text-muted">{unit}</span>}
        <span className="text-2xs font-semibold text-danger">en conflicto</span>
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-s2 ${justify}`} title={label}>
      <ClassMarker cls={cell.cls} />
      <span className={`${numeric ? "num font-mono text-[13px]" : "text-sm"} ${TONE[cell.cls]}`}>{text}</span>
      {unit && typeof cell.value === "number" && <span className="text-2xs text-muted">{unit}</span>}
      {cell.cls !== "observed" && <span className="sr-only">{label}</span>}
    </span>
  );
}

const ORDER: DataClass[] = ["observed", "calculated", "hypothesis", "confirmed", "unknown"];

/** Las cinco clases con la muestra y la palabra de la landing. La definición va en el título. */
export function Legend({ showChange = false }: { showChange?: boolean }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-s4 gap-y-s2 text-sm text-ink" aria-label={COPY.workspace.legend}>
      {ORDER.map((cls) => (
        <li key={cls} className="inline-flex items-center gap-s2" title={COPY.classDefs[cls]}>
          <Swatch cls={cls} size="md" />
          {COPY.classes[cls]}
        </li>
      ))}
      {showChange && (
        <li className="inline-flex items-center gap-s2">
          <span className="inline-block h-[14px] w-[3px] bg-cobalt" aria-hidden="true" />
          {COPY.changed}
        </li>
      )}
    </ul>
  );
}
