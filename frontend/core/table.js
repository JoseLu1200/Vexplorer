const TABLE_PROFILE = "rectangular_table_v1";
const TABLE_TEMPLATES = new Set(["side_supports_v1", "corner_supports_v1"]);
const SHEET_KINDS = new Set(["general", "component", "cut_sheet"]);
const SHEET_FORMATS = new Set(["svg", "dxf"]);

export function tableRunOptions(mode, templateId = null) {
  if (mode === "live") return { table_profile: TABLE_PROFILE, proposal_mode: "model_generated" };
  if (mode === "recorded_replay") return { table_profile: TABLE_PROFILE, proposal_mode: "none" };
  if (!TABLE_TEMPLATES.has(templateId)) throw new TypeError("Selecciona una plantilla de catálogo válida.");
  return { table_profile: TABLE_PROFILE, proposal_mode: "catalog_baseline", table_template_id: templateId };
}

export function artifactRequestIdentity({ runId, revision, programHash, sheetId, format }) {
  return [runId, revision, programHash, sheetId, format].join(":");
}

const ROLE_QUANTITY = Object.freeze({ tabletop: 1, side_support: 2, corner_support: 4 });

function tableField(raw = {}) {
  return {
    value: Number.isFinite(raw.value_mm) ? raw.value_mm : null,
    state: raw.state ?? "unknown",
    dependencyRefs: Array.isArray(raw.dependency_refs) ? [...raw.dependency_refs] : [],
    evidenceIds: Array.isArray(raw.evidence_ids) ? [...raw.evidence_ids] : [],
  };
}

export function normaliseTableWorkspace(snapshot = {}) {
  const result = snapshot.result ?? snapshot;
  if (result.input_semantics !== "mounted_orthographic_views") return { isTable: false, measures: [], programs: [], evaluated: null };
  const analysis = result.table_analysis ?? {};
  const evaluatedRaw = result.evaluated_table_program;
  const evaluatedBindings = (evaluatedRaw?.bindings ?? []).map((binding) => ({ ...binding, operandRefs: [...(binding.operand_refs ?? [])], result: tableField(binding.result) }));
  const measures = (analysis.measures ?? []).map((measure) => ({
    id: measure.id,
    semantic: measure.semantic ?? "unknown",
    axis: measure.axis ?? "unknown",
    value: Number.isFinite(measure.value_mm) ? measure.value_mm : null,
    state: measure.state ?? "unknown",
    informationClass: measure.state ?? "unknown",
    confirmable: ["unknown", "conflict"].includes(measure.state),
    slotOrigin: measure.slot_origin ?? "drawing",
    measurementIds: [...(measure.measurement_ids ?? [])],
    viewIds: [...(measure.view_ids ?? [])],
    evidenceIds: [...(measure.evidence_ids ?? [])],
    sourceEntityIds: [...(measure.source_entity_ids ?? [])],
    effectiveValue: evaluatedBindings.find((binding) => binding.operation === "copy" && binding.operandRefs.length === 1 && binding.operandRefs[0].ref_type === "measure" && binding.operandRefs[0].ref_id === measure.id)?.result.value ?? null,
  }));
  const programs = (result.table_programs ?? []).map((program) => ({
    id: program.id,
    origin: program.proposal_origin,
    originLabel: program.proposal_origin === "model_generated" ? "Propuesta generativa · agente real" : "Baseline de catálogo",
    templateId: program.table_template_id ?? null,
    assumptions: [...(program.assumptions ?? [])],
    premises: (program.premises ?? []).map((premise) => ({ ...premise })),
    bindings: (program.bindings ?? []).map((binding) => ({ ...binding, operandRefs: [...(binding.operand_refs ?? [])] })),
    components: (program.components ?? []).map((component) => ({
      ...component,
      quantity: ROLE_QUANTITY[component.role] ?? null,
      premiseIds: [...(component.premise_ids ?? [])],
      evidenceIds: [...(component.evidence_ids ?? [])],
    })),
    evidenceIds: [...(program.evidence_ids ?? [])],
  }));
  const evaluated = evaluatedRaw ? {
    programId: evaluatedRaw.raw_program?.id ?? result.selected_table_program_id ?? null,
    programHash: evaluatedRaw.program_hash ?? null,
    state: evaluatedRaw.state ?? "needs_review",
    bindings: evaluatedBindings,
    components: (evaluatedRaw.components ?? []).map((component) => ({
      ...component,
      length: tableField(component.length),
      width: tableField(component.width),
      thickness: tableField(component.thickness),
    })),
    occurrences: [...(evaluatedRaw.occurrences ?? [])],
    placements: [...(evaluatedRaw.placements ?? [])],
    overallDimensions: evaluatedRaw.overall_dimensions ?? {},
    issues: [...(evaluatedRaw.issues ?? [])],
    acceptedTargetIds: [...(evaluatedRaw.accepted_target_ids ?? [])],
    rejectedTargetIds: [...(evaluatedRaw.rejected_target_ids ?? [])],
  } : null;
  return {
    isTable: true,
    revision: result.result_revision ?? snapshot.result_revision ?? null,
    analysisState: analysis.state ?? "needs_review",
    ledgerRevision: analysis.ledger_revision ?? null,
    warnings: [...(analysis.warnings ?? [])],
    measures,
    programs,
    selectedProgramId: result.selected_table_program_id ?? null,
    evaluated,
  };
}

export function buildTableReviewPayload(snapshot, workspace, values = {}) {
  const revision = snapshot?.result_revision ?? snapshot?.result?.result_revision;
  if (!Number.isInteger(revision) || revision < 1) throw new TypeError("La revisión base no es válida.");
  if (!values.reviewerName?.trim() || !values.notes?.trim() || !values.programId) throw new TypeError("Indica programa, persona revisora y motivo técnico.");
  const program = workspace.programs.find((item) => item.id === values.programId);
  if (!program) throw new TypeError("El programa seleccionado no pertenece a esta revisión.");
  const allowedTargets = new Set([
    `program:${program.id}`,
    ...program.components.map((item) => `component:${item.id}`),
    ...program.premises.map((item) => `premise:${item.id}`),
  ]);
  const tableDecisions = (values.decisions ?? []).map((decision) => {
    if (!allowedTargets.has(`${decision.targetKind}:${decision.targetId}`) || !["accept", "reject"].includes(decision.action) || !decision.reason?.trim()) {
      throw new TypeError("Cada decisión debe referir un objetivo válido y tener motivo.");
    }
    return { target_kind: decision.targetKind, target_id: decision.targetId, action: decision.action, reason: decision.reason.trim() };
  });
  const confirmable = new Set(workspace.measures.filter((item) => item.confirmable).map((item) => item.id));
  const tableConfirmedValues = (values.confirmedValues ?? []).flatMap((item) => {
    if (!confirmable.has(item.targetId)) return [];
    const number = Number(item.valueMm);
    if (!Number.isFinite(number) || number <= 0 || !item.reason?.trim()) throw new TypeError("Cada medida confirmada necesita un valor positivo y motivo.");
    return [{ target_kind: "measurement_slot", target_id: item.targetId, value_mm: number, reason: item.reason.trim(), source: "human" }];
  });
  return {
    base_result_revision: revision,
    reviewer_name: values.reviewerName.trim(),
    table_program_id: values.programId,
    table_decisions: tableDecisions,
    table_confirmed_values: tableConfirmedValues,
    notes: values.notes.trim(),
  };
}

export function normaliseTableCostCatalog(raw = {}) {
  const tariff = (item) => ({ id: item.id, label: item.label ?? item.id, rate: item.rate ?? item.rate_eur_per_unit ?? null, rateUnit: item.rate_unit ?? null });
  const tariffs = raw.tariffs ?? [];
  return {
    version: raw.catalog_version ?? null,
    synthetic: raw.synthetic === true,
    materials: (raw.material_tariffs ?? raw.materials ?? tariffs.filter((item) => item.scope === "material")).map(tariff),
    operations: (raw.operation_tariffs ?? raw.operations ?? tariffs.filter((item) => item.scope === "operation")).map(tariff),
  };
}

export function presentTableCosts(raw = {}) {
  const euros = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: 2 });
  const number = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 3 });
  const items = (raw.concepts ?? []).map((concept) => ({
    ...concept,
    quantityLabel: Number.isFinite(concept.quantity) ? `${number.format(concept.quantity)} ${concept.quantity_unit}` : "Cantidad pendiente",
    rateLabel: Number.isFinite(concept.rate_eur_per_unit) ? `${euros.format(concept.rate_eur_per_unit)} por ${concept.rate_unit.replace("EUR/", "")}` : "Tarifa pendiente",
    amountLabel: Number.isFinite(concept.amount_eur) ? euros.format(concept.amount_eur) : "Pendiente",
  }));
  const resolved = items.filter((item) => Number.isFinite(item.amount_eur));
  const largestContribution = resolved.reduce((largest, item) => !largest || item.amount_eur > largest.amount_eur ? item : largest, null);
  const complete = raw.total_state === "complete" && Number.isFinite(raw.grand_total_eur);
  return {
    revision: raw.result_revision ?? null,
    programHash: raw.program_hash ?? null,
    catalogVersion: raw.catalog_version ?? null,
    complete,
    totalLabel: complete ? euros.format(raw.grand_total_eur) : `Subtotal conocido ${euros.format(raw.known_subtotal_eur ?? 0)}`,
    items,
    largestContribution,
    warnings: [...(raw.warnings ?? [])],
  };
}

export function normaliseTableDrawingManifest(raw = {}) {
  const revision = Number.isInteger(raw.result_revision) ? raw.result_revision : null;
  const programHash = typeof raw.program_hash === "string" ? raw.program_hash : null;
  const sheets = (raw.sheets ?? raw.items ?? []).flatMap((sheet) => {
    if (!sheet || typeof sheet.sheet_id !== "string" || !SHEET_KINDS.has(sheet.kind)) return [];
    const sheetRevision = Number.isInteger(sheet.result_revision) ? sheet.result_revision : revision;
    const sheetHash = typeof sheet.program_hash === "string" ? sheet.program_hash : programHash;
    if (sheetRevision !== revision || sheetHash !== programHash) return [];
    const formatRecords = sheet.formats ?? [];
    const formats = [...new Set(formatRecords.map((format) => typeof format === "string" ? format : format.format).filter((format) => SHEET_FORMATS.has(format)))];
    const formatLinks = Object.fromEntries(formatRecords.flatMap((format) => {
      if (typeof format === "string" || !SHEET_FORMATS.has(format.format) || typeof format.url !== "string" || !format.url.startsWith("/api/v1/")) return [];
      return [[format.format, format.url]];
    }));
    return [{
      id: sheet.sheet_id,
      kind: sheet.kind,
      title: sheet.title || "Lámina sin título",
      componentId: sheet.component_id ?? null,
      page: Number.isInteger(sheet.page) ? sheet.page : null,
      revision: sheetRevision,
      programHash: sheetHash,
      status: sheet.status === "ready" ? "ready" : "incomplete",
      warnings: Array.isArray(sheet.warnings) ? sheet.warnings.map(String) : [],
      formats,
      formatLinks,
    }];
  });
  return {
    revision,
    programHash,
    sheets,
    byKind: {
      general: sheets.filter((sheet) => sheet.kind === "general"),
      components: sheets.filter((sheet) => sheet.kind === "component"),
      cut_sheet: sheets.filter((sheet) => sheet.kind === "cut_sheet"),
    },
  };
}
