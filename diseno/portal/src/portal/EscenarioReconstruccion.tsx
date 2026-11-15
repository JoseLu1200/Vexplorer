import { COPY } from "../copy";
import type { ReconstruccionVista } from "../general";

export type Escenario = "revision" | "bom";

/**
 * Archivos reales de un trabajo de Construcción 3D para «Ver el proceso»: en la revisión, el plano original frente al
 * render de la propuesta que el modelo compara con él; y el BOM.
 */
export function EscenarioReconstruccion({ r, plano, escenario, insetTop, insetBottom }: { r: ReconstruccionVista; plano: string | null; escenario: Escenario; insetTop: number; insetBottom: number }) {
  return (
    <div className="plan-grid scroll-thin absolute inset-0 z-10 overflow-y-auto" style={{ paddingTop: insetTop + 8, paddingBottom: insetBottom + 64 }} data-testid={`escenario-${escenario}`}>
      <div className="mx-auto w-full max-w-[1100px] px-s4 lg:pl-[380px] lg:pr-s5">
        {escenario === "revision" && (
          <div className="grid grid-cols-1 gap-s3 sm:grid-cols-2" data-testid="revision">
            <figure className="flex flex-col gap-s1">
              <div className="aspect-[4/3] border border-line bg-white">{plano && <img src={plano} alt={COPY.portal.proceso.planoOriginal} className="h-full w-full object-contain" />}</div>
              <figcaption className="text-2xs text-muted">{COPY.portal.proceso.planoOriginal}</figcaption>
            </figure>
            <figure className="flex flex-col gap-s1">
              <div className="aspect-[4/3] border border-line bg-white">{r.render && <img src={r.render} alt={COPY.portal.proceso.render} className="h-full w-full object-contain" />}</div>
              <figcaption className="text-2xs text-muted">{COPY.portal.proceso.render}</figcaption>
            </figure>
          </div>
        )}
        {escenario === "bom" && (
          <table className="w-full border-collapse bg-surface text-sm" data-testid="bom">
            <caption className="sr-only">BOM</caption>
            <thead>
              <tr className="border-b border-line-strong text-left text-2xs text-muted">
                <th scope="col" className="px-s3 py-s2 font-normal">{COPY.portal.pieces}</th>
                <th scope="col" className="px-s3 py-s2 text-right font-normal">mm</th>
                <th scope="col" className="px-s3 py-s2 text-right font-normal">{COPY.cols.quantity}</th>
              </tr>
            </thead>
            <tbody>
              {r.bom.map((fila) => (
                <tr key={fila.id} className="border-b border-line">
                  <td className="px-s3 py-s2 text-ink">{fila.nombre}</td>
                  <td className="num whitespace-nowrap px-s3 py-s2 text-right font-mono text-2xs text-ink">{fila.x} × {fila.y} × {fila.z}</td>
                  <td className="num px-s3 py-s2 text-right font-mono text-2xs text-ink">{fila.cantidad}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
