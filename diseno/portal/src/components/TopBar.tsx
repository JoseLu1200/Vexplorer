import { useEffect } from "react";
import { api } from "../api";
import { COPY } from "../copy";
import { useRouter } from "../router";
import { useStore } from "../state";
import { useWorkspace } from "../workspace/store";
import { Logo } from "./Logo";

/**
 * Franja superior de la entrada y de los estados de un plano que no son la mesa (análisis en curso, error, carga).
 * Sin fondo propio ni borde: el logo arriba a la izquierda y las acciones compactas a la derecha.
 */
export function PortalBar() {
  const { route, navigate } = useRouter();
  const { theme, toggleTheme } = useStore();
  const ws = useWorkspace();
  const plan = route.kind === "plan" ? ws.plans.find((item) => item.id === route.planId) : undefined;
  const folderId = route.kind === "plan" ? plan?.folderId ?? null : route.folderId;
  const path = ws.folderPath(folderId);

  useEffect(() => { document.documentElement.removeAttribute("data-plan"); }, []);

  const crumbs: { label: string; onClick?: () => void; mono?: boolean }[] = [
    { label: COPY.nav.home, onClick: () => navigate({ kind: "home", folderId: null }) },
    ...path.map((folder) => ({ label: folder.name, onClick: () => navigate({ kind: "home", folderId: folder.id }) })),
  ];
  if (plan) crumbs.push({ label: plan.name, mono: true });

  return (
    <header className="relative z-30 flex h-[var(--bar-h)] items-center gap-s4 pl-[max(16px,env(safe-area-inset-left,0px))] pr-[max(16px,env(safe-area-inset-right,0px))]">
      <a href="#/" onClick={(event) => { event.preventDefault(); navigate({ kind: "home", folderId: null }); }} className="shrink-0" aria-label="Vexplorer, ir a Planos">
        <Logo />
      </a>
      {crumbs.length > 1 && (
        <nav aria-label="Migas de pan" className="hidden min-w-0 flex-1 items-center md:flex">
          <ol className="flex min-w-0 items-center gap-s2 text-sm">
            {crumbs.map((crumb, index) => {
              const last = index === crumbs.length - 1;
              return (
                <li key={`${crumb.label}-${index}`} className={`flex min-w-0 items-center gap-s2 ${crumb.mono ? "shrink" : "shrink-0"}`}>
                  {index > 0 && <span className="text-muted" aria-hidden="true">›</span>}
                  {last || !crumb.onClick ? (
                    <span aria-current={last ? "page" : undefined} className={`truncate ${crumb.mono ? "num font-mono text-2xs" : ""} ${last ? "font-semibold text-ink" : "text-muted"}`}>{crumb.label}</span>
                  ) : (
                    <a href="#" onClick={(event) => { event.preventDefault(); crumb.onClick!(); }} className={`truncate text-muted hover:text-ink hover:underline ${crumb.mono ? "num font-mono text-2xs" : ""}`}>{crumb.label}</a>
                  )}
                </li>
              );
            })}
          </ol>
        </nav>
      )}
      <div className="ml-auto flex shrink-0 items-center gap-s2">
        {api.isMock && (
          <span className="inline-flex h-7 items-center whitespace-nowrap border border-line-strong px-s2 text-xs font-semibold text-ink" title="Respuestas grabadas del backend sobre planos públicos de ejemplo">
            {COPY.mockBadge}
          </span>
        )}
        <button className="btn btn-ghost btn-icon max-lg:!hidden" onClick={() => dispatchEvent(new CustomEvent("vx-shortcuts"))} aria-label={COPY.shortcuts.open} title={`${COPY.shortcuts.open} (?)`}>
          <span className="font-mono text-sm" aria-hidden="true">?</span>
        </button>
        <button className="btn btn-ghost btn-icon" onClick={toggleTheme} aria-label={theme === "dark" ? COPY.theme.light : COPY.theme.dark} title={theme === "dark" ? COPY.theme.light : COPY.theme.dark}>
          <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
            <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <path d="M10 3 A7 7 0 0 1 10 17 Z" fill="currentColor" />
          </svg>
        </button>
      </div>
    </header>
  );
}
