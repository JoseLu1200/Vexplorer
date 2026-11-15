import { useEffect, useMemo, useRef, useState } from "react";
import { Destacados } from "../portal/Destacados";
import { api } from "../api";
import type { RunMode } from "../api/types";
import { COPY } from "../copy";
import { PlanThumb } from "../components/PlanThumb";
import { Relief } from "../components/Relief";
import { Menu, Modal, Skel, StatusBadge, shortError, type MenuItem } from "../components/system";
import { fmtDate } from "../lib/domain";
import { useRouter } from "../router";
import { useStore } from "../state";
import { useWorkspace } from "../workspace/store";
import type { Folder, PlanRecord, PlanStatus } from "../workspace/types";

type Sort = "date" | "status" | "name";
type Target = { type: "plan" | "folder"; id: string };
type Dialog =
  | { kind: "name"; title: string; initial: string; submit: (name: string) => void }
  | { kind: "move"; target: Target }
  | { kind: "delete"; target: Target };

const STATUS_ORDER: Record<PlanStatus, number> = { analyzing: 0, error: 1, needs_review: 2, reviewed: 3 };
const norm = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function readSort(): Sort {
  try {
    const value = localStorage.getItem("vx-sort");
    if (value === "date" || value === "status" || value === "name") return value;
  } catch { /* sin almacenamiento */ }
  return "date";
}

export const DRAG_PLAN = "application/x-vexplorer-plan";
export const DRAG_FOLDER = "application/x-vexplorer-folder";

/** Pantalla de entrada: carpetas y planos del espacio de trabajo. */
export function ProjectsScreen({ folderId }: { folderId: string | null }) {
  const ws = useWorkspace();
  const { navigate } = useRouter();
  const [query, setQuery] = useState("");
  const [sort, setSortState] = useState<Sort>(readSort);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const folder = folderId ? ws.folders.find((item) => item.id === folderId) ?? null : null;
  const setSort = (value: Sort) => { setSortState(value); try { localStorage.setItem("vx-sort", value); } catch { /* sin almacenamiento */ } };

  useEffect(() => {
    const onFocus = () => search.current?.focus();
    addEventListener("vx-focus-search", onFocus);
    return () => removeEventListener("vx-focus-search", onFocus);
  }, []);

  const folderName = (id: string | null) => (id ? ws.folders.find((item) => item.id === id)?.name ?? COPY.folders.root : COPY.folders.root);
  const plans = useMemo(() => {
    const q = norm(query.trim());
    const list = q ? ws.plans.filter((plan) => norm(plan.name).includes(q) || norm(plan.filename).includes(q)) : folderId ? ws.plans.filter((plan) => plan.folderId === folderId) : ws.plans;
    const sorted = [...list];
    if (sort === "date") sorted.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt) || a.name.localeCompare(b.name, "es", { numeric: true }));
    if (sort === "status") sorted.sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || b.updatedAt.localeCompare(a.updatedAt));
    if (sort === "name") sorted.sort((a, b) => a.name.localeCompare(b.name, "es", { numeric: true }));
    return sorted;
  }, [ws.plans, query, folderId, sort]);
  const subfolders = folderId && !query ? ws.folders.filter((item) => item.parentId === folderId).sort((a, b) => a.name.localeCompare(b.name, "es", { numeric: true })) : [];

  const newFolder = (parentId: string | null) => setDialog({
    kind: "name", title: parentId ? COPY.folders.createSub : COPY.folders.create, initial: COPY.folders.untitled,
    submit: (name) => { const id = ws.createFolder(name, parentId); navigate({ kind: "home", folderId: id }); },
  });
  const folderItems = (item: Folder): MenuItem[] => [
    { label: COPY.folders.rename, onSelect: () => setDialog({ kind: "name", title: COPY.folders.rename, initial: item.name, submit: (name) => ws.renameFolder(item.id, name) }) },
    { label: COPY.folders.createSub, onSelect: () => newFolder(item.id) },
    { label: COPY.folders.move, onSelect: () => setDialog({ kind: "move", target: { type: "folder", id: item.id } }) },
    { label: COPY.folders.remove, danger: true, onSelect: () => setDialog({ kind: "delete", target: { type: "folder", id: item.id } }) },
  ];
  const planItems = (plan: PlanRecord): MenuItem[] => [
    ...(plan.status === "error" ? [] : [
      { label: COPY.plans.open, onSelect: () => navigate({ kind: "plan", planId: plan.id, screen: plan.status === "analyzing" ? "analisis" : "plano" }) },
      { label: COPY.plans.openAnalysis, onSelect: () => navigate({ kind: "plan", planId: plan.id, screen: "analisis" }), disabled: plan.source === "library" || plan.source === "caso" || plan.source === "general" },
      { label: COPY.cad.open, hint: plan.source === "caso" ? COPY.portal.general.noFile : COPY.cad.originalHint, disabled: plan.source === "caso", onSelect: () => { ws.downloadDxf(plan.id); } },
    ]),
    ...(plan.status === "error" && plan.error?.code !== "unsupported_format" ? [{ label: COPY.plans.retry, onSelect: () => ws.retry(plan.id) }] : []),
    { label: COPY.folders.rename, onSelect: () => setDialog({ kind: "name", title: COPY.folders.rename, initial: plan.name, submit: (name) => ws.renamePlan(plan.id, name) }) },
    { label: COPY.folders.move, onSelect: () => setDialog({ kind: "move", target: { type: "plan", id: plan.id } }) },
    { label: COPY.folders.remove, danger: true, onSelect: () => setDialog({ kind: "delete", target: { type: "plan", id: plan.id } }) },
  ];

  const title = query ? COPY.home.search : folder ? folder.name : COPY.home.all;
  const topLevel = ws.folders.filter((item) => item.parentId === null).sort((a, b) => a.name.localeCompare(b.name, "es", { numeric: true }));
  const activeTop = folderId ? ws.folderPath(folderId)[0]?.id ?? null : null;

  return (
    <div className="flex min-h-[calc(100vh-var(--bar-h))]">
      <aside aria-label={COPY.home.folders} className="hidden w-[264px] shrink-0 flex-col gap-s2 border-r border-line py-s4 lg:flex">
        <div className="flex items-center justify-between px-s4">
          <h2 className="eyebrow">{COPY.home.folders}</h2>
          <button className="inline-flex h-8 items-center gap-s1 px-s2 text-sm font-semibold text-ink hover:bg-sunken" onClick={() => newFolder(null)} title={COPY.folders.create}>
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1.5v9M1.5 6h9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
            {COPY.folders.create}
          </button>
        </div>
        <nav className="flex flex-col">
          <SidebarItem label={COPY.home.all} active={!folderId} dropId="root" depth={0} onOpen={() => navigate({ kind: "home", folderId: null })} icon="all" />
          {ws.ready ? <FolderTree parentId={null} depth={0} activeId={folderId} items={folderItems} /> : <div className="flex flex-col gap-s2 px-s4 pt-s2">{[0, 1, 2].map((i) => <Skel key={i} className="h-5 w-3/4" />)}</div>}
        </nav>
      </aside>

      <div className="min-w-0 flex-1">
        <div className="page flex flex-col gap-s4 py-s4 lg:max-w-none lg:px-s5 lg:py-s5">
          <div className="flex min-h-[40px] items-center justify-between gap-s3">
            <div className="flex min-w-0 items-center gap-s2">
              <h1 className="truncate font-serif text-[30px] font-normal leading-[34px] sm:text-[40px] sm:leading-[44px] tracking-[-0.01em] text-ink">{title}</h1>
              {folder && !query && <Menu label={COPY.folders.actions(folder.name)} items={folderItems(folder)} align="left" />}
            </div>
            <UploadButton onPick={() => fileInput.current?.click()} />
            <input
              ref={fileInput}
              id="dxf-files"
              type="file"
              multiple
              accept=".dxf,application/dxf,image/vnd.dxf,.png,image/png"
              className="sr-only"
              tabIndex={-1}
              onChange={(event) => {
                const files = [...(event.target.files ?? [])];
                if (files.length) ws.addFiles(files, folderId);
                event.target.value = "";
              }}
            />
          </div>

          {/* Carpetas en móvil */}
          <div className="-mx-4 overflow-x-auto px-4 lg:hidden">
            <div className="flex w-max gap-s2" role="list" aria-label={COPY.home.folders}>
              <Chip active={!folderId} onClick={() => navigate({ kind: "home", folderId: null })} dropId="root">{COPY.home.all}</Chip>
              {topLevel.map((item) => <Chip key={item.id} active={activeTop === item.id} onClick={() => navigate({ kind: "home", folderId: item.id })} dropId={item.id}>{item.name}</Chip>)}
              <button className="inline-flex h-9 items-center gap-s1 border border-dashed border-line-strong px-s3 text-sm font-semibold text-ink" onClick={() => newFolder(null)}>
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1.5v9M1.5 6h9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
                {COPY.folders.create}
              </button>
            </div>
          </div>

          <Toolbar query={query} setQuery={setQuery} sort={sort} setSort={setSort} searchRef={search} />
          {ws.ready && !query && (!folder || folder.name === COPY.portal.general.folder) && <Destacados />}
          {!ws.persistent && ws.ready && <p className="border-l-2 border-hip pl-s3 text-sm text-muted">{COPY.home.storageOff}</p>}

          {!ws.ready ? (
            <PlanGridSkeleton />
          ) : (
            <>
              {subfolders.length > 0 && (
                <section aria-label={COPY.home.subfolders} className="grid grid-cols-1 gap-s2 sm:grid-cols-[repeat(auto-fill,minmax(220px,1fr))]">
                  {subfolders.map((item) => (
                    <div key={item.id} data-drop-folder={item.id} className="group flex h-12 items-center border border-line bg-surface pr-s1 hover:border-ink" draggable onDragStart={(event) => { event.dataTransfer.setData(DRAG_FOLDER, item.id); event.dataTransfer.effectAllowed = "move"; }}>
                      <button className="flex h-full min-w-0 flex-1 items-center gap-s3 px-s3 text-left" onClick={() => navigate({ kind: "home", folderId: item.id })}>
                        <FolderIcon />
                        <span className="truncate text-base font-semibold text-ink">{item.name}</span>
                      </button>
                      <Menu label={COPY.folders.actions(item.name)} items={folderItems(item)} />
                    </div>
                  ))}
                </section>
              )}
              {plans.length === 0 ? (
                query ? (
                  <div className="flex flex-col items-start gap-s3 py-s5">
                    <p className="text-md text-ink">{COPY.home.noResults(query.trim())}</p>
                    <button className="btn btn-sm" onClick={() => setQuery("")}>{COPY.home.clearSearch}</button>
                  </div>
                ) : subfolders.length ? null : (
                  <EmptyDrop title={folder ? COPY.home.emptyFolder : COPY.home.emptyAll} onPick={() => fileInput.current?.click()} />
                )
              ) : (
                <ul className="grid grid-cols-1 gap-px border border-line bg-line sm:gap-s3 sm:border-0 sm:bg-transparent sm:[grid-template-columns:repeat(auto-fill,minmax(228px,1fr))]" aria-label={COPY.home.plans} data-testid="plan-grid">
                  {plans.map((plan) => (
                    <PlanCard key={plan.id} plan={plan} folderLabel={!folderId || query ? folderName(plan.folderId) : null} items={planItems(plan)} stage={ws.live[plan.id]?.stage} />
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </div>

      {dialog?.kind === "name" && <NameDialog dialog={dialog} onClose={() => setDialog(null)} />}
      {dialog?.kind === "move" && <MoveDialog target={dialog.target} onClose={() => setDialog(null)} />}
      {dialog?.kind === "delete" && <DeleteDialog target={dialog.target} onClose={() => setDialog(null)} onDeleted={(type, id) => { if (type === "folder" && folderId && ws.descendants(id).has(folderId)) navigate({ kind: "home", folderId: null }); }} />}
    </div>
  );
}

function Toolbar({ query, setQuery, sort, setSort, searchRef }: { query: string; setQuery: (v: string) => void; sort: Sort; setSort: (v: Sort) => void; searchRef: React.RefObject<HTMLInputElement> }) {
  return (
    <div className="flex flex-wrap items-center gap-s3">
      <label className="relative min-w-0 flex-1 basis-[220px]">
        <span className="sr-only">{COPY.home.search}</span>
        <svg width="14" height="14" viewBox="0 0 16 16" className="pointer-events-none absolute left-s3 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="m10.5 10.5 3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
        <input ref={searchRef} type="search" id="plan-search" className="input" style={{ paddingLeft: 34, paddingRight: 34 }} placeholder={COPY.home.search} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") { setQuery(""); (event.target as HTMLInputElement).blur(); } }} />
        <kbd className="pointer-events-none absolute right-s3 top-1/2 hidden -translate-y-1/2 border border-line-strong px-1 font-mono text-2xs text-muted sm:block" aria-hidden="true">/</kbd>
      </label>
      <a href="#mapa" className="btn h-10" data-testid="abrir-mapa">{COPY.portal.mapa.button}</a>
      <label className="flex items-center gap-s2">
        <span className="whitespace-nowrap text-sm text-muted">{COPY.home.sort}</span>
        <select id="plan-sort" className="input h-10 w-auto pr-s5" value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
          <option value="date">{COPY.home.sortDate}</option>
          <option value="status">{COPY.home.sortStatus}</option>
          <option value="name">{COPY.home.sortName}</option>
        </select>
      </label>
    </div>
  );
}

/** Subir DXF con el modo de análisis plegado en su desplegable: se cambia pocas veces. */
function UploadButton({ onPick }: { onPick: () => void }) {
  const ws = useWorkspace();
  const { config } = useStore();
  const modes: RunMode[] = ["geometry_only", "live"];
  return (
    <div className="flex shrink-0 items-stretch">
      <button className="btn btn-primary px-s3 sm:px-s4" onClick={onPick} title={COPY.upload.modes[ws.mode]?.label} aria-label={COPY.home.upload}>
        <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 10.5V2.5M5 5.5l3-3 3 3M2.5 10.5v3h11v-3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        <span className="hidden sm:inline">{COPY.home.upload}</span>
        <span className="sm:hidden">{COPY.home.uploadShort}</span>
      </button>
      <Menu
        label={COPY.upload.mode}
        className="-ml-px border border-wood bg-wood text-wood-ink"
        triggerClassName="h-[38px] w-9 !text-wood-ink hover:!bg-transparent"
        trigger={<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>}
        items={[
          // Sin proveedor de modelo no se ofrece el modo con asistente: ningún botón intenta «live».
          ...modes.filter((value) => value === "geometry_only" || Boolean(config?.live_available)).map((value) => {
            const enabled = true;
            return {
              group: COPY.upload.mode,
              label: `${ws.uploadKind === "parts" && ws.mode === value ? "✓ " : ""}${COPY.home.modeShort[value]}`,
              hint: enabled ? COPY.upload.modes[value].label : COPY.upload.modes[value].off,
              disabled: !enabled,
              onSelect: () => { ws.setUploadKind("parts"); ws.setMode(value); },
            };
          }),
          // La vía de muebles generales solo existe con el backend real.
          ...(api.isMock ? [] : [{
            group: COPY.portal.general.uploadGeneral,
            label: `${ws.uploadKind === "general" ? "✓ " : ""}${COPY.portal.general.uploadGeneral}`,
            hint: COPY.portal.general.uploadGeneralHint,
            onSelect: () => ws.setUploadKind("general"),
          }, {
            group: COPY.portal.general.uploadGeneral,
            label: `${ws.uploadKind === "mesa" ? "✓ " : ""}${COPY.portal.general.uploadMesa}`,
            hint: COPY.portal.general.uploadMesaHint,
            onSelect: () => ws.setUploadKind("mesa"),
          }]),
        ]}
      />
    </div>
  );
}

function SidebarItem({ label, active, dropId, depth, onOpen, icon, menu, draggableId }: { label: string; active: boolean; dropId: string; depth: number; onOpen: () => void; icon: "all" | "folder"; menu?: MenuItem[]; draggableId?: string }) {
  return (
    <div
      data-drop-folder={dropId}
      className={`group flex h-9 items-center pr-s2 ${active ? "bg-sunken" : "hover:bg-sunken"}`}
      style={{ paddingLeft: 16 + depth * 16 }}
      draggable={Boolean(draggableId)}
      onDragStart={draggableId ? (event) => { event.dataTransfer.setData(DRAG_FOLDER, draggableId); event.dataTransfer.effectAllowed = "move"; } : undefined}
    >
      <button className={`flex h-full min-w-0 flex-1 items-center gap-s2 text-left text-base ${active ? "font-semibold text-ink" : "text-ink"}`} onClick={onOpen} aria-current={active ? "page" : undefined}>
        {icon === "all" ? (
          <svg width="16" height="16" viewBox="0 0 16 16" className="shrink-0 text-muted" aria-hidden="true"><rect x="2.5" y="2.5" width="4.5" height="4.5" fill="none" stroke="currentColor" strokeWidth="1.2" /><rect x="9" y="2.5" width="4.5" height="4.5" fill="none" stroke="currentColor" strokeWidth="1.2" /><rect x="2.5" y="9" width="4.5" height="4.5" fill="none" stroke="currentColor" strokeWidth="1.2" /><rect x="9" y="9" width="4.5" height="4.5" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
        ) : <FolderIcon />}
        <span className="truncate">{label}</span>
      </button>
      {menu && <Menu label={COPY.folders.actions(label)} items={menu} className="opacity-100 lg:opacity-0 lg:focus-within:opacity-100 lg:group-hover:opacity-100" />}
    </div>
  );
}

function FolderTree({ parentId, depth, activeId, items }: { parentId: string | null; depth: number; activeId: string | null; items: (folder: Folder) => MenuItem[] }) {
  const ws = useWorkspace();
  const { navigate } = useRouter();
  const children = ws.folders.filter((folder) => folder.parentId === parentId).sort((a, b) => a.name.localeCompare(b.name, "es", { numeric: true }));
  return (
    <>
      {children.map((folder) => (
        <div key={folder.id}>
          <SidebarItem label={folder.name} active={activeId === folder.id} dropId={folder.id} depth={depth} onOpen={() => navigate({ kind: "home", folderId: folder.id })} icon="folder" menu={items(folder)} draggableId={folder.id} />
          <FolderTree parentId={folder.id} depth={depth + 1} activeId={activeId} items={items} />
        </div>
      ))}
    </>
  );
}

function Chip({ active, onClick, dropId, children }: { active: boolean; onClick: () => void; dropId: string; children: React.ReactNode }) {
  return (
    <button role="listitem" data-drop-folder={dropId} onClick={onClick} aria-current={active ? "page" : undefined} className={`inline-flex h-9 items-center whitespace-nowrap border px-s3 text-sm font-semibold ${active ? "border-ink bg-ink text-surface" : "border-line-strong text-ink"}`}>
      {children}
    </button>
  );
}

function FolderIcon() {
  return <svg width="16" height="16" viewBox="0 0 16 16" className="shrink-0 text-muted" aria-hidden="true"><path d="M1.8 3.5h4.4l1.4 1.6h6.6v7.4H1.8Z" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" /></svg>;
}

function PlanCard({ plan, folderLabel, items, stage }: { plan: PlanRecord; folderLabel: string | null; items: MenuItem[]; stage?: string }) {
  const { navigate } = useRouter();
  const open = () => navigate({ kind: "plan", planId: plan.id, screen: plan.status === "analyzing" || plan.status === "error" ? "analisis" : "plano" });
  const thumb = plan.thumb?.map((c) => ({ id: c.id, points_mm: c.points, points_source: c.points, closed: c.closed })) ?? null;
  return (
    <li
      className="group relative flex bg-surface sm:flex-col sm:border sm:border-line sm:hover:border-ink"
      draggable
      onDragStart={(event) => { event.dataTransfer.setData(DRAG_PLAN, plan.id); event.dataTransfer.effectAllowed = "move"; }}
      data-plan={plan.id}
      data-status={plan.status}
    >
      <button className="flex min-w-0 flex-1 items-center gap-s3 p-s3 text-left sm:flex-col sm:items-stretch sm:gap-0 sm:p-0" onClick={open} aria-label={`${plan.name}, ${COPY.status[plan.status]}`}>
        <span className="relative flex h-[60px] w-[80px] shrink-0 items-center justify-center border border-line sm:h-[148px] sm:w-full sm:border-0 sm:border-b">
          {thumb && thumb.length ? (
            <PlanThumb contours={thumb} className={`h-full w-full p-s2 sm:p-s4 ${plan.status === "analyzing" ? "thumb-draw" : ""}`} label="" />
          ) : plan.status === "error" ? (
            <svg width="22" height="22" viewBox="0 0 16 16" className="text-danger" aria-hidden="true"><path d="M8 1.5 15 14H1Z" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" /><path d="M8 6v3.6M8 11.4v.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
          ) : (
            <span className="flex h-full w-full flex-col justify-center gap-s2 p-s3 sm:p-s5" aria-hidden="true"><Skel className="h-3 w-3/5" /><Skel className="h-3 w-2/5" /><Skel className="h-3 w-4/5" /></span>
          )}
          {plan.status === "analyzing" && stage && (
            <span className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-line" aria-hidden="true"><span className="anim-bar absolute inset-y-0 left-0 w-2/5 bg-ink" /></span>
          )}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-s1 sm:p-s3">
          <span className="num line-clamp-2 font-mono text-[13px] font-medium text-ink [overflow-wrap:anywhere]" title={plan.name}><Breakable text={plan.name} /></span>
          {folderLabel && <span className="truncate text-sm text-muted">{folderLabel}</span>}
          <span className="flex flex-wrap items-center justify-between gap-x-s3 gap-y-s1">
            <StatusBadge status={plan.status} />
            <span className="num font-mono text-2xs text-muted">{fmtDate(plan.updatedAt)}</span>
          </span>
          {plan.status === "error" && plan.error && <span className="text-sm text-danger">{shortError(plan.error.code, plan.error.message)}</span>}
        </span>
      </button>
      <Menu label={COPY.folders.actions(plan.name)} items={items} className="self-center pr-s2 sm:absolute sm:right-s2 sm:top-s2 sm:pr-0 sm:[&>button]:border sm:[&>button]:border-line sm:[&>button]:bg-surface" />
    </li>
  );
}

function PlanGridSkeleton() {
  return (
    <ul className="grid grid-cols-1 gap-s3 sm:[grid-template-columns:repeat(auto-fill,minmax(228px,1fr))]" aria-busy="true" aria-label={COPY.home.plans}>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <li key={i} className="flex gap-s3 border border-line bg-surface p-s3 sm:flex-col sm:p-0">
          <Skel className="h-[60px] w-[80px] sm:h-[148px] sm:w-full" />
          <span className="flex flex-1 flex-col gap-s2 sm:p-s3"><Skel className="h-4 w-4/5" /><Skel className="h-3 w-1/2" /></span>
        </li>
      ))}
    </ul>
  );
}

/** Estado vacío: el único sitio de esta pantalla con curvas de nivel, muy tenues. */
function EmptyDrop({ title, onPick }: { title: string; onPick: () => void }) {
  const [wide] = useState(() => matchMedia("(min-width: 1024px)").matches);
  return (
    <div className="relative flex min-h-[360px] flex-col items-center justify-center overflow-hidden border border-dashed border-line-strong px-s4 py-s6 text-center">
      {wide && <Relief />}
      <div className="relative flex flex-col items-center gap-s3 bg-bg px-s4 py-s3">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        <p className="max-w-[42ch] text-base text-muted">{COPY.home.emptyHint}</p>
        <button className="btn btn-sm" onClick={onPick}>{COPY.home.upload}</button>
      </div>
    </div>
  );
}

function NameDialog({ dialog, onClose }: { dialog: Extract<Dialog, { kind: "name" }>; onClose: () => void }) {
  const [name, setName] = useState(dialog.initial);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { setTimeout(() => input.current?.select(), 10); }, []);
  const submit = () => { if (!name.trim()) return; dialog.submit(name.trim()); onClose(); };
  return (
    <Modal title={dialog.title} onClose={onClose} footer={<><button className="btn btn-sm" onClick={onClose}>{COPY.folders.cancel}</button><button className="btn btn-primary btn-sm" onClick={submit} disabled={!name.trim()}>{COPY.folders.save}</button></>}>
      <label htmlFor="name-field" className="text-sm font-semibold text-ink">{COPY.folders.name}</label>
      <input ref={input} id="name-field" className="input" value={name} onChange={(event) => setName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") submit(); }} />
    </Modal>
  );
}

function MoveDialog({ target, onClose }: { target: Target; onClose: () => void }) {
  const ws = useWorkspace();
  const plan = target.type === "plan" ? ws.plans.find((item) => item.id === target.id) : null;
  const folder = target.type === "folder" ? ws.folders.find((item) => item.id === target.id) : null;
  const currentParent = plan ? plan.folderId : folder?.parentId ?? null;
  const [choice, setChoice] = useState<string>(currentParent ?? "root");
  const blocked = folder ? ws.descendants(folder.id) : new Set<string>();
  const name = plan?.name ?? folder?.name ?? "";
  const rows: { id: string; label: string; depth: number }[] = [{ id: "root", label: COPY.folders.root, depth: 0 }];
  const walk = (parentId: string | null, depth: number) => {
    ws.folders.filter((item) => item.parentId === parentId).sort((a, b) => a.name.localeCompare(b.name, "es", { numeric: true })).forEach((item) => { rows.push({ id: item.id, label: item.name, depth }); walk(item.id, depth + 1); });
  };
  walk(null, 1);
  const submit = () => {
    const destination = choice === "root" ? null : choice;
    if (plan) ws.movePlan(plan.id, destination);
    if (folder && !ws.moveFolder(folder.id, destination)) { ws.toast(COPY.folders.cycle, { tone: "error" }); return; }
    ws.toast(COPY.folders.moved(name, destination ? ws.folders.find((item) => item.id === destination)?.name ?? "" : COPY.folders.root));
    onClose();
  };
  return (
    <Modal title={COPY.folders.moveTitle(name)} onClose={onClose} footer={<><button className="btn btn-sm" onClick={onClose}>{COPY.folders.cancel}</button><button className="btn btn-primary btn-sm" onClick={submit} disabled={choice === (currentParent ?? "root")}>{COPY.folders.moveSubmit}</button></>}>
      <fieldset className="flex flex-col border border-line">
        <legend className="sr-only">{COPY.home.folders}</legend>
        {rows.map((row) => {
          const disabled = blocked.has(row.id);
          return (
            <label key={row.id} className={`flex h-10 items-center gap-s2 border-b border-line pr-s3 last:border-b-0 ${disabled ? "cursor-not-allowed text-muted" : "cursor-pointer text-ink hover:bg-sunken"} ${choice === row.id ? "bg-sunken font-semibold" : ""}`} style={{ paddingLeft: 12 + row.depth * 16 }}>
              <input type="radio" name="move-target" value={row.id} checked={choice === row.id} disabled={disabled} onChange={() => setChoice(row.id)} className="accent-[rgb(var(--ink))]" />
              {row.id !== "root" && <FolderIcon />}
              <span className="truncate text-base">{row.label}</span>
            </label>
          );
        })}
      </fieldset>
    </Modal>
  );
}

function DeleteDialog({ target, onClose, onDeleted }: { target: Target; onClose: () => void; onDeleted: (type: Target["type"], id: string) => void }) {
  const ws = useWorkspace();
  const name = target.type === "plan" ? ws.plans.find((item) => item.id === target.id)?.name ?? "" : ws.folders.find((item) => item.id === target.id)?.name ?? "";
  const submit = () => {
    onDeleted(target.type, target.id);
    if (target.type === "plan") ws.deletePlan(target.id); else ws.deleteFolder(target.id);
    onClose();
  };
  return (
    <Modal title={COPY.folders.removeTitle(name)} onClose={onClose} footer={<><button className="btn btn-sm" onClick={onClose}>{COPY.folders.cancel}</button><button className="btn btn-sm border-danger bg-danger text-surface hover:!bg-danger" onClick={submit}>{COPY.folders.removeConfirm}</button></>}>
      <p className="text-base text-ink">{target.type === "plan" ? COPY.folders.removePlanBody : COPY.folders.removeFolderBody}</p>
    </Modal>
  );
}

/** Nombre de archivo que puede partirse tras «_», «.» o «-» en vez de a mitad de palabra. */
function Breakable({ text }: { text: string }) {
  const parts = text.split(/(?<=[_.-])/);
  return <>{parts.map((part, index) => <span key={index}>{part}{index < parts.length - 1 && <wbr />}</span>)}</>;
}
