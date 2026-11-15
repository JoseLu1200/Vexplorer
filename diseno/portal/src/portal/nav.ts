import { SCREENS, VIEWS, type Screen } from "../router";
import type { PlanRecord } from "../workspace/types";

/** Qué pantallas de un plano se pueden abrir según su estado. Un análisis que se rehace al abrir no bloquea nada. */
export function enabledScreens(plan: PlanRecord | undefined, loaded: boolean, liveOrigin?: string): Set<Screen> {
  if (!plan) return new Set();
  // Muebles procesados y subidas de la vía general: solo las cuatro vistas del lienzo; la mesa enseña su propio estado.
  if (plan.source === "caso" || plan.source === "general") return new Set(VIEWS);
  if ((plan.status === "analyzing" && liveOrigin !== "sync") || plan.status === "error") return new Set(["analisis"]);
  if (plan.source === "library" && !loaded) return new Set(["original", "plano"]);
  return new Set(SCREENS);
}
