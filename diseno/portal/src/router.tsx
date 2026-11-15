import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

/**
 * Segmento de pantalla de un plano abierto. Las cuatro vistas del lienzo (original, plano limpio, piezas y 3D) y los
 * paneles que se abren encima de la mesa (revisión, coste, presupuesto y similares). «analisis» es la traza en curso.
 */
export type Screen = "analisis" | "original" | "plano" | "piezas" | "esquema" | "revision" | "compras" | "presupuesto" | "similares";
export const SCREENS: Screen[] = ["analisis", "original", "plano", "piezas", "esquema", "revision", "compras", "presupuesto", "similares"];
export type View = "original" | "plano" | "piezas" | "esquema";
export const VIEWS: View[] = ["original", "plano", "piezas", "esquema"];
export type Sheet = "revision" | "compras" | "presupuesto" | "similares";
export const isView = (screen: Screen): screen is View => (VIEWS as string[]).includes(screen);
export const isSheet = (screen: Screen): screen is Sheet => screen === "revision" || screen === "compras" || screen === "presupuesto" || screen === "similares";

export type Route =
  | { kind: "home"; folderId: string | null }
  | { kind: "plan"; planId: string; screen: Screen };

/** #/ · #/carpetas/<id> · #/planos/<id>/<pantalla> */
export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map((part) => {
    try { return decodeURIComponent(part); } catch { return part; }
  });
  if (parts[0] === "planos" && parts[1]) {
    const screen = SCREENS.includes(parts[2] as Screen) ? (parts[2] as Screen) : "plano";
    return { kind: "plan", planId: parts[1], screen };
  }
  if (parts[0] === "carpetas" && parts[1]) return { kind: "home", folderId: parts[1] };
  return { kind: "home", folderId: null };
}

export function hashOf(route: Route): string {
  if (route.kind === "plan") return `#/planos/${encodeURIComponent(route.planId)}/${route.screen}`;
  return route.folderId ? `#/carpetas/${encodeURIComponent(route.folderId)}` : "#/";
}

interface Router {
  route: Route;
  navigate(route: Route, options?: { replace?: boolean }): void;
}

const Ctx = createContext<Router | null>(null);

export function RouterProvider({ children }: { children: ReactNode }) {
  const [route, setRoute] = useState<Route>(() => parseHash(location.hash));
  useEffect(() => {
    const onHash = () => setRoute(parseHash(location.hash));
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);
  const navigate = useCallback((next: Route, options?: { replace?: boolean }) => {
    const hash = hashOf(next);
    if (location.hash !== hash) {
      try {
        if (options?.replace) history.replaceState(null, "", `${location.pathname}${location.search}${hash}`);
        else history.pushState(null, "", `${location.pathname}${location.search}${hash}`);
      } catch {
        // Algunos marcos bloquean el historial: el hash basta para que la ruta sobreviva a una recarga.
        try { location.hash = hash; } catch { /* la ruta queda solo en memoria */ }
      }
    }
    setRoute(next);
    if (next.kind === "home") scrollTo({ top: 0 });
  }, []);
  useEffect(() => {
    const onPop = () => setRoute(parseHash(location.hash));
    addEventListener("popstate", onPop);
    return () => removeEventListener("popstate", onPop);
  }, []);
  const value = useMemo(() => ({ route, navigate }), [route, navigate]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useRouter() {
  const value = useContext(Ctx);
  if (!value) throw new Error("RouterProvider ausente");
  return value;
}
