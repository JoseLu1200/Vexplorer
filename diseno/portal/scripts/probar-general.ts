// Prueba de la vía general con el código real de src/api/general.ts, src/general y src/casos.
// Se ejecuta con: node scripts/probar-general.mjs [base-backend] [ruta-vexplorer]
import { readFileSync } from "node:fs";
import path from "node:path";
import { createGeneralClient, GeneralApiError, newIdempotencyKey } from "../src/api/general";
import { comprobarEnlaces } from "../src/general/adaptador";
import { abrirRun, aceptarPlantillaMesa, analizarMesa, analizarPlano } from "../src/general/vivo";
import { pasosDeMesa } from "../src/general/proceso";
import { CASOS, RUNS_DEMO, RUNS_PLANK, cargarCaso } from "../src/casos";
import type { MesaTrabajo } from "../src/general/modelo";

const base = process.argv[2] ?? "http://127.0.0.1:8765";
const vexplorer = process.argv[3] ?? "C:/Users/marti/Proyectos/Vexplorer";
let fallos = 0;
const ok = (cond: boolean, texto: string) => {
  if (!cond) fallos++;
  console.log(`${cond ? "  OK " : "  FALLO"} ${texto}`);
};
const resumen = (m: MesaTrabajo) =>
  `${m.estado}; ${m.piezas.length} piezas (${m.piezas.filter((p) => p.inferida).length} inferidas), ` +
  `${m.plano?.contornos.length ?? 0} contornos, ${m.laminas.length} láminas, escena ${m.escena.disposicion} ` +
  `con ${m.escena.cajas.length} cajas y ${m.escena.sinCaja.length} sin caja, ${m.avisos.length} avisos, ${m.pendientes.length} pendientes`;

/** Espera un GeneralApiError con ese código. */
async function falla(trabajo: Promise<unknown>, codigo: string, texto: string, needsModel?: boolean) {
  try {
    await trabajo;
    ok(false, `${texto}: no falló`);
  } catch (error) {
    const e = error as GeneralApiError;
    const coincide = e instanceof GeneralApiError && e.code === codigo && (needsModel === undefined || e.needsModel === needsModel);
    ok(coincide, `${texto} → ${e.status} ${e.code}${e.needsModel ? " [modelo]" : ""}: ${e.message}`);
  }
}

console.log("\n== Casos congelados (src/casos) por el adaptador");
const congelados = new Map<string, MesaTrabajo>();
for (const meta of CASOS) {
  const mesa = await cargarCaso(meta.id);
  congelados.set(meta.id, mesa);
  const enlaces = comprobarEnlaces(mesa);
  ok(enlaces.length === 0, `${meta.id}: ${resumen(mesa)}`);
  enlaces.forEach((f) => console.log(`        ${f}`));
  ok(mesa.piezas.length === meta.piezas, `${meta.id}: ${mesa.piezas.length} piezas, el índice declara ${meta.piezas}`);
  const sinValor = mesa.piezas.flatMap((p) => [p.largo, p.ancho, p.grueso]).filter((m) => m.valor_mm == null);
  ok(sinValor.every((m) => m.texto === "sin medida" && m.estado === "sin_medida"), `${meta.id}: ${sinValor.length} medidas nulas, todas «sin medida»`);
  const estimadas = mesa.piezas.flatMap((p) => [p.largo, p.ancho, p.grueso]).filter((m) => m.estimada);
  ok(estimadas.every((m) => m.texto.startsWith("≈")), `${meta.id}: ${estimadas.length} medidas estimadas, todas con «≈»`);
}

const api = createGeneralClient(base);
console.log(`\n== Backend real en ${base}`);
const config = await api.config();
console.log(`  modos ${config.modes.join(", ")}; vía general disponible ${config.general?.available}; con modelo ${config.general?.live_available}; motivo ${config.unavailableReason}`);

const dxf = path.join(vexplorer, "data/cad_completion_controls/public/F02.dxf");
const archivo = new Blob([readFileSync(dxf)], { type: "application/dxf" });

console.log("\n-- POST /documents + POST /jobs geometry_only con Idempotency-Key, seguimiento de GET /jobs/{id}");
const doc = await api.uploadDocument(archivo, "F02.dxf");
const clave = newIdempotencyKey("probar");
const job = await api.submitJob({ document_id: doc.document_id, mode: "geometry_only" }, clave);
const repetido = await api.submitJob({ document_id: doc.document_id, mode: "geometry_only" }, clave);
ok(repetido.id === job.id, `misma Idempotency-Key devuelve el mismo job (${job.id})`);
const estados: string[] = [];
const final = await api.followJob(job.id, { intervalMs: 300, timeoutMs: 60_000, onUpdate: (v) => estados.push((v as { state: string }).state) });
ok(final.state === "succeeded" && !!final.run_id, `job terminado: ${final.state}, run ${final.run_id}, estados vistos ${[...new Set(estados)].join(" → ")}`);
const runId = final.run_id!;
const mesa = await abrirRun(api, runId, { titulo: "F02 geometry_only", job: final });
ok(mesa.estado === "sin_propuesta" && mesa.pendientes.some((p) => p.tipo === "modelo"), `mesa en vivo: ${resumen(mesa)}`);
ok(comprobarEnlaces(mesa).length === 0, "enlaces de la mesa en vivo");
const ids = new Set(mesa.plano?.contornos.map((c) => c.id));
const congeladoF02 = congelados.get("F02")!;
ok(congeladoF02.plano!.contornos.every((c) => ids.has(c.id)) && ids.size === congeladoF02.plano!.contornos.length,
  `los ${ids.size} contornos del servidor coinciden con los del caso congelado F02`);

console.log("\n-- Rutas generales sobre un run sin propuesta");
ok((await api.getGeneral(runId)) === null, "GET general → null (404 general_proposal_not_found)");
await falla(api.getDerived(runId, { proposalRevision: 1, reviewRevision: 1 }), "general_derived_not_found", "GET general/derived");
ok((await api.getAssembly(runId, { proposalRevision: 1, reviewRevision: 1 })) === null, "GET general/assembly → null (404)");
await falla(api.getArtifact(runId, "general-r1-bom_csv", { proposalRevision: 1, reviewRevision: 1 }), "general_artifact_not_found", "GET general/artifacts/{id}");
await falla(api.createProposal(runId, { mode: "live", base_proposal_revision: 0 }), "general_live_requires_durable_job", "POST general/proposals live", true);
await falla(api.createProposal(runId, { mode: "manual", base_proposal_revision: 0 }), "request_validation_failed", "POST general/proposals manual sin propuesta");
await falla(api.autoReview(runId, { base_proposal_revision: 1, base_review_revision: 0 }), "general_auto_review_requires_durable_job", "POST general/auto-review", true);
const escena = await api.getScene(runId, 1);
ok(escena.state === "unavailable", `GET /runs/{id}/scene → ${escena.state} (${escena.warnings.join(", ")})`);
await falla(api.createReview(runId, { base_proposal_revision: 1, base_review_revision: 0, reviewer_name: "probar", reason: "prueba", operations: [], components: [] }),
  "request_validation_failed", "POST general/reviews con cuerpo vacío (el backend valida antes de buscar la propuesta)");

console.log("\n-- Propuesta humana mínima sin modelo: proposals → reviews → derived → artifacts");
try {
  const drawing = await api.getDrawing(runId);
  const dim = drawing.dimensions.find((d) => d.value_mm != null && d.view_id && d.evidence_ids.length)!;
  const obs = drawing.observations.find((o) => o.dimension_ids.includes(dim.id))!;
  // Campos mínimos; el resto los rellena Pydantic con sus valores por defecto.
  const proposal = {
    id: "proposal-probar-portal", drawing_id: drawing.drawing_id, ledger_revision: drawing.drawing_id, proposal_origin: "human",
    bindings: [{ id: "b-largo", operation: "copy", operand_refs: [`dimension:${dim.id}`] }],
    premises: [{ id: "p1", description: "Prueba automática del portal: un panel con el largo de una cota real del plano." }],
    components: [{
      id: "panel-prueba", label: "Panel de prueba", kind: "panel", role: "unknown",
      length_binding_id: "b-largo", width_binding_id: null, thickness_binding_id: null,
      quantity: { value: null, state: "unknown" }, premise_ids: ["p1"],
      source_view_ids: [dim.view_id], source_observation_ids: [obs.id],
      source_evidence_ids: [...dim.evidence_ids], source_dimension_ids: [dim.id],
      assumptions: ["Prueba, no es un despiece."], unknown_fields: ["width", "thickness", "quantity"],
    }],
    assumptions: ["Prueba automática del portal; no es un despiece."],
  } as unknown as Parameters<typeof api.createProposal>[1]["proposal"];
  const record = await api.createProposal(runId, { mode: "manual", base_proposal_revision: 0, proposal });
  ok(record.proposal_revision === 1 && record.review_revision === 0, `POST general/proposals manual → revisión ${record.proposal_revision}/${record.review_revision}, estado ${record.status}`);
  const enRevision = await abrirRun(api, runId, { titulo: "F02 propuesta humana" });
  const panel = enRevision.piezas[0];
  ok(enRevision.estado === "en_revision" && panel?.largo.valor_mm === dim.value_mm && panel.ancho.texto === "sin medida",
    `mesa con propuesta sin revisar: ${resumen(enRevision)}; largo ${panel?.largo.texto} (${panel?.largo.estadoOrigen}), ancho ${panel?.ancho.texto}`);

  // GeneralComponentReview no admite premise_ids; el resto de campos del borrador sí.
  const { premise_ids: _premisas, ...draft } = record.draft.components[0];
  const reviewed = await api.createReview(runId, {
    base_proposal_revision: 1, base_review_revision: 0, reviewer_name: "probar-general", reason: "Prueba automática del portal.",
    operations: [{ kind: "replace", source_component_ids: [draft.id], result_component_ids: ["panel-revisado"], reason: "Prueba." }],
    components: [{
      ...draft, id: "panel-revisado", replaces_component_ids: [draft.id],
      quantity: { value: 1, state: "confirmed", dependency_refs: [], evidence_ids: [] },
      material: { value: null, state: "unknown", dependency_refs: [], evidence_ids: [] },
      finish: { value: null, state: "unknown", dependency_refs: [], evidence_ids: [] },
    }],
  });
  ok(reviewed.review_revision === 1, `POST general/reviews → revisión ${reviewed.proposal_revision}/${reviewed.review_revision}, estado ${reviewed.status}`);
  const revs = { proposalRevision: reviewed.proposal_revision, reviewRevision: reviewed.review_revision };
  const derived = await api.getDerived(runId, revs);
  const conContenido = derived.package.artifacts.filter((a) => typeof a.content === "string" && a.content.length > 0).length;
  ok(derived.package.artifacts.length > 0, `GET general/derived → paquete ${derived.package.status}, ${derived.package.bom_rows.length} filas BOM, construcción ${derived.package.construction ? "sí" : "no"}, ${derived.package.artifacts.length} artefactos (${conContenido} con contenido), escena ${derived.package.scene.status}`);
  const bom = derived.package.artifacts.find((a) => a.kind === "bom_csv")!;
  const fichero = await api.getArtifact(runId, bom.id, revs);
  ok(fichero.body.length > 0, `GET general/artifacts/${bom.id} → ${fichero.filename}, ${fichero.mediaType}, ${fichero.body.split("\n")[0]}`);
  const conDerivado = await abrirRun(api, runId, { titulo: "F02 revisada" });
  ok(comprobarEnlaces(conDerivado).length === 0 && conDerivado.artefactos.every((a) => a.url !== null),
    `mesa con derivado: ${resumen(conDerivado)}; ${conDerivado.artefactos.length} archivos con URL`);
  ok((await api.getAssembly(runId, revs)) === null, "GET general/assembly tras la revisión → null (sin proveedor de montaje no se intenta)");
} catch (error) {
  const e = error as GeneralApiError;
  ok(false, `propuesta humana: ${e.status ?? ""} ${e.code ?? ""} ${e.message} ${JSON.stringify(e.detail ?? "").slice(0, 400)}`);
}

console.log("\n-- Lo que exige modelo");
const live = await api.submitJob({ document_id: doc.document_id, mode: "live" }, newIdempotencyKey("probar"));
const liveFinal = await api.followJob(live.id, { intervalMs: 300, timeoutMs: 60_000 });
ok(liveFinal.state === "failed" && liveFinal.error?.code === "live_provider_unavailable",
  `job live → ${liveFinal.state} ${liveFinal.error?.code}; recuperación ${liveFinal.recovery?.safe_action}`);
const reintento = await api.retryJob(live.id, newIdempotencyKey("probar"));
ok(reintento.retry_of_job_id === live.id, `POST /jobs/{id}/retry → ${reintento.id} (${reintento.state}), reintento de ${reintento.retry_of_job_id}`);
await api.followJob(reintento.id, { intervalMs: 300, timeoutMs: 60_000 });
await falla(api.resumeJob(live.id), "job_resume_checkpoint_unavailable", "POST /jobs/{id}/resume sin propuesta guardada");
const sinModelo = await analizarPlano(api, archivo, "F02.dxf", "live");
ok(sinModelo.job === null && sinModelo.necesitaModelo && sinModelo.mesa === null, `analizarPlano live se para antes de crear el job: ${sinModelo.mensaje}`);
await falla(api.startReconstruction(runId, { intended_use: "cajonera" }, newIdempotencyKey("probar")), "reconstruction_model_unavailable", "POST /runs/{id}/reconstruction", true);
await falla(api.getReconstruction("0".repeat(32)), "job_not_found", "GET /reconstruction/{job} inexistente");
await falla(api.retryAssembly(runId, { proposalRevision: 1, reviewRevision: 1 }, newIdempotencyKey("probar")), "general_assembly_unavailable", "POST general/assembly/retry sobre la revisión 1/1", true);

console.log("\n-- Flujo completo analizarPlano geometry_only");
const flujo = await analizarPlano(api, archivo, "F02.dxf", "geometry_only", { intervalMs: 300, timeoutMs: 60_000 });
ok(flujo.job.state === "succeeded" && flujo.mesa?.estado === "sin_propuesta" && flujo.necesitaModelo, `analizarPlano → ${flujo.mensaje}`);

console.log("\n-- Runs de la demo procesada (RUNS_DEMO) contra el backend");
for (const demo of RUNS_DEMO) {
  try {
    const vivo = await abrirRun(api, demo.runId, { titulo: demo.casoId, sintetico: true });
    const congelado = congelados.get(demo.casoId)!;
    ok(comprobarEnlaces(vivo).length === 0 && vivo.piezas.length === congelado.piezas.length && vivo.escena.cajas.length === congelado.escena.cajas.length,
      `${demo.casoId}: en vivo ${resumen(vivo)}`);
  } catch (error) {
    ok(false, `${demo.casoId}: ${(error as Error).message}`);
  }
}

console.log("\n-- Casos congelados del pipeline guardado: montaje, traza, artefactos y DXF original");
{
  const p030 = congelados.get("plank_030")!;
  const v = p030.escena.validacion;
  ok(p030.escena.disposicion === "montaje" && p030.escena.cajas.length === 16 && v?.estado === "rejected" && p030.escena.ejeVertical === "z",
    `plank_030: montaje ${v?.estado} con ${p030.escena.cajas.length} cajas, ${p030.escena.cajas.filter((c) => c.conflicto).length} en penetración, máx ${v?.penetracionMax_mm.toFixed(2)} mm, eje ${p030.escena.ejeVertical}`);
  ok(v?.incidencias.map((i) => `${i.codigo}×${i.veces}`).join(", ") === "aabb_penetration×19, shared_evidence_identity×16, contour_box_fit_residual×11, shared_contour_identity×1",
    `plank_030: incidencias ${v?.incidencias.map((i) => `${i.etiqueta} ×${i.veces}`).join(" · ")}`);
  ok(p030.escena.alternativa?.disposicion === "piezas_separadas", `plank_030: alternativa por tipos con ${p030.escena.alternativa?.cajas.length} cajas`);
  ok(p030.traza.length > 0, `plank_030: traza ${p030.traza.map((t) => `${t.hora} ${t.etiqueta}${t.modelo ? ` [${t.modelo}]` : ""} ${t.resultados.map((r) => `${r.resultado}${r.veces > 1 ? `×${r.veces}` : ""}`).join("/")}`).join(" | ")}`);
  ok(p030.artefactos.filter((a) => a.contenido).length === 4 && p030.original?.contenido?.startsWith("  0") === true && p030.atribucion !== null,
    `plank_030: ${p030.artefactos.filter((a) => a.contenido).length} artefactos con contenido, DXF original ${p030.original?.nombre}, atribución ${p030.atribucion}`);
  const mesa = congelados.get("mesa_coste")!;
  ok(mesa.escena.disposicion === "montaje" && mesa.laminas.filter((l) => l.svg).length === 4 && mesa.coste?.total != null,
    `mesa_coste: ${mesa.piezas.length} piezas, montaje con ${mesa.escena.cajas.length} cajas, ${mesa.laminas.length} láminas SVG, coste ${mesa.coste?.total} ${mesa.coste?.moneda} (${mesa.coste?.estadoTotal})`);
}

const plankBase = process.env.PLANK_BASE ?? "http://127.0.0.1:18864";
const plankApi = createGeneralClient(plankBase);
const plankVivo = await plankApi.config().then(() => true).catch(() => false);
console.log(`\n-- RUNS_PLANK contra ${plankBase}${plankVivo ? "" : " (no responde, se omite)"}`);
if (plankVivo) {
  for (const run of RUNS_PLANK) {
    try {
      const vivo = await abrirRun(plankApi, run.runId, { titulo: run.casoId, atribucion: run.atribucion ?? null });
      const congelado = congelados.get(run.casoId)!;
      // Los exports de piezas separadas y del PDF no traen eventos ni derivado: ahí solo se comparan piezas y cajas.
      const completo = congelado.traza.length > 0;
      const igual = vivo.piezas.length === congelado.piezas.length && vivo.escena.cajas.length === congelado.escena.cajas.length
        && (!completo || (vivo.laminas.length === congelado.laminas.length && vivo.traza.length === congelado.traza.length));
      ok(comprobarEnlaces(vivo).length === 0 && igual,
        `${run.casoId}: en vivo ${resumen(vivo)}, traza ${vivo.traza.length} pasos, original ${vivo.original?.nombre ?? "sin original"}, coste ${vivo.coste?.total ?? "sin coste"}`);
    } catch (error) {
      ok(false, `${run.casoId}: ${(error as Error).message}`);
    }
  }
}

if (plankVivo) {
  console.log(`\n-- Subida de mesa sin modelo en ${plankBase}: plantilla, aceptación humana, láminas, coste y montaje`);
  try {
    const mesaDxf = new Blob([readFileSync(path.join(vexplorer, "data/planos_demo/mesa_demo_001.dxf"))]);
    const fases: string[] = [];
    const { job, runId } = await analizarMesa(plankApi, mesaDxf, "mesa_demo_001.dxf", (f) => fases.push(f));
    ok(job.state === "succeeded" && !!runId, `analizarMesa → ${job.state}, run ${runId}, fases ${fases.join(" → ")}`);
    const r1 = await abrirRun(plankApi, runId!, { titulo: "mesa r1" });
    const p1 = pasosDeMesa(r1, { geometria: "vivo", resto: "vivo" });
    ok(r1.piezas.length === 2 && p1.find((p) => p.id === "revision")?.estado === "requiere_revision",
      `revisión 1: ${resumen(r1)}; pasos ${p1.map((p) => `${p.id}:${p.estado}`).join(" ")}`);
    const rev = await aceptarPlantillaMesa(plankApi, runId!, "probar-general");
    const r2 = await abrirRun(plankApi, runId!, { titulo: "mesa r2" });
    const p2 = pasosDeMesa(r2, { geometria: "vivo", resto: "vivo" });
    ok(rev === 2 && r2.escena.disposicion === "montaje" && r2.coste?.total != null && r2.laminas.length === 4,
      `aceptada → revisión ${rev}: ${resumen(r2)}, coste ${r2.coste?.total} ${r2.coste?.moneda}; pasos ${p2.map((p) => `${p.id}:${p.estado}`).join(" ")}`);
  } catch (error) {
    ok(false, `mesa: ${(error as Error).message} ${JSON.stringify((error as GeneralApiError).detail ?? "").slice(0, 300)}`);
  }
  const replay = await plankApi.replayAvailability((await plankApi.uploadDocument(new Blob([readFileSync(path.join(vexplorer, "data/planos_demo/mesa_demo_001.dxf"))]), "mesa_demo_001.dxf")).document_id);
  console.log(`  INFO replay-availability mesa_demo_001: ${JSON.stringify(replay)}`);
  for (const job of ["3894284a17bb46dbbcc0766766f4195a", "a174a6e50eab4111858b22f3b800d0f9", "07f54e99bbf44b4ea75f4577f6fc5aba"]) {
    try {
      const estado = await plankApi.getReconstruction(job);
      const glb = await fetch(plankApi.reconstructionArtifactUrl(job, "assembly.glb"));
      ok(estado.job_id === job && (glb.ok || estado.status === "insufficient_evidence"),
        `GET /reconstruction/${job.slice(0, 8)} → ${estado.status}, revisión ${estado.revision}, ${estado.outcome?.proposal?.components?.length ?? 0} componentes, assembly.glb ${glb.status}`);
    } catch (error) {
      ok(false, `reconstrucción ${job}: ${(error as Error).message}`);
    }
  }
  const p030 = congelados.get("plank_030")!;
  console.log(`  INFO pasos plank_030 guardado: ${pasosDeMesa(p030, { geometria: "guardado", resto: "guardado" }).map((p) => `${p.titulo} [${p.estado}] ${p.hora ?? ""} ${p.modelo ?? ""} ${p.linea}`).join(" | ")}`);
}

console.log(`\n${fallos === 0 ? "Todo correcto." : `${fallos} comprobaciones fallidas.`}`);
process.exit(fallos === 0 ? 0 : 1);
