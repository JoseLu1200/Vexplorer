import { COPY } from "../copy";
import { PlanThumb } from "../components/PlanThumb";
import { useRouter } from "../router";
import { useWorkspace } from "../workspace/store";
import type { PlanRecord } from "../workspace/types";

/** Construcción 3D destacada en la entrada: el estudio 01 en grande y después los estudios 02-06 y la mesa v1 → v2. */
const ORDEN = ["recon_caso01", "recon_caso02", "recon_caso03", "recon_caso04", "recon_caso05", "recon_caso06", "recon_mesa"];

/** Abre el mueble con «Ver el proceso» en marcha. */
export function abrirConProceso(planId: string, navigate: ReturnType<typeof useRouter>["navigate"]) {
  try { sessionStorage.setItem(`vx-proceso-${planId}`, "1"); } catch { /* sin almacenamiento: se abre sin proceso */ }
  navigate({ kind: "plan", planId, screen: "esquema" });
}

export function Destacados() {
  const ws = useWorkspace();
  const { navigate } = useRouter();
  const planes = ORDEN.map((id) => ws.plans.find((plan) => plan.source === "caso" && plan.asset === id)).filter((plan): plan is PlanRecord => !!plan);
  if (!planes.length) return null;
  const [principal, ...resto] = planes;
  return (
    <section aria-label={COPY.portal.destacados.title} className="grid grid-cols-1 gap-s3 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]" data-testid="destacados">
      <Tarjeta plan={principal} grande onOpen={() => abrirConProceso(principal.id, navigate)} />
      <ul className="grid grid-cols-2 gap-s3 sm:grid-cols-3">
        {resto.map((plan) => <li key={plan.id}><Tarjeta plan={plan} onOpen={() => abrirConProceso(plan.id, navigate)} /></li>)}
      </ul>
    </section>
  );
}

function Tarjeta({ plan, grande = false, onOpen }: { plan: PlanRecord; grande?: boolean; onOpen: () => void }) {
  const thumb = plan.thumb?.map((c) => ({ id: c.id, points_mm: c.points, points_source: c.points, closed: c.closed })) ?? [];
  return (
    <button className="group flex h-full w-full flex-col border border-line bg-surface text-left hover:border-ink" onClick={onOpen} data-destacado={plan.asset}>
      <span className={`block w-full ${grande ? "h-[260px]" : "h-[110px]"} border-b border-line`}>
        {thumb.length ? <PlanThumb contours={thumb} className="h-full w-full p-s3" label="" /> : null}
      </span>
      <span className="flex items-center justify-between gap-s2 px-s3 py-s2">
        <span className={`min-w-0 truncate ${grande ? "text-md font-semibold" : "text-sm"} text-ink`}>{plan.name}</span>
        <span className="inline-flex shrink-0 items-center gap-s1 text-2xs font-semibold text-ink lg:text-sm">
          <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 2.5v7l6-3.5z" fill="currentColor" /></svg>
          {grande ? COPY.portal.proceso.open : COPY.portal.proceso.title}
        </span>
      </span>
    </button>
  );
}
