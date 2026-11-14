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

export function tableExportFormat(format) {
  return format === "csv" ? "table_cutlist" : format;
}

const ROLE_QUANTITY = Object.freeze({ tabletop: 1, side_support: 2, corner_support: 4 });
const MEASURE_SOURCE_LABELS = Object.freeze({
  dimension_annotation: "Cota escrita",
  envelope_extent: "Medición CAD · envolvente",
  offset_from_min_x: "Medición CAD · separación desde la izquierda",
  offset_from_max_x: "Medición CAD · separación desde la derecha",
  offset_from_min_y: "Medición CAD · separación inferior",
  offset_from_max_y: "Medición CAD · separación superior",
  opposite_offsets: "Medición CAD · separaciones opuestas",
  profile_required_slot: "Dato requerido por el perfil",
});

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
  const sourceDecisionsById = new Map((result.table_source_review_decisions ?? []).map((item) => [item.warning_id, item]));
  const sourceWarningsById = new Map();
  (evaluatedRaw?.issues ?? []).forEach((issue) => {
    if (!issue.code?.startsWith("source_recovery_") || issue.target_ids?.length < 2) return;
    const id = issue.target_ids[0];
    const code = issue.code === "source_recovery_decision_mismatch" ? issue.target_ids[2] : issue.target_ids[1];
    if (!id || !code) return;
    const decision = sourceDecisionsById.get(id);
    sourceWarningsById.set(id, { id, code, message: issue.message, currentAction: decision?.action ?? null, currentReason: decision?.reason ?? null });
  });
  sourceDecisionsById.forEach((decision, id) => {
    if (!sourceWarningsById.has(id)) sourceWarningsById.set(id, { id, code: decision.warning_code, message: decision.warning_code, currentAction: decision.action, currentReason: decision.reason });
  });
  const measurementDispositions = new Map((evaluatedRaw?.measurement_dispositions ?? []).map((item) => [item.measurement_id, item]));
  const confirmedByTarget = new Map((result.table_confirmed_values ?? []).map((item) => [item.target_id, item]));
  const correctionsByTarget = new Map((result.table_observed_value_corrections ?? []).map((item) => [item.measurement_id, item]));
  const measures = (analysis.measures ?? []).map((measure) => {
    const confirmation = confirmedByTarget.get(measure.id) ?? null;
    const correction = correctionsByTarget.get(measure.id) ?? null;
    const effectiveBinding = evaluatedBindings.find((binding) => binding.operation === "copy" && binding.operandRefs.length === 1 && binding.operandRefs[0].ref_type === "measure" && binding.operandRefs[0].ref_id === measure.id);
    const humanEffective = confirmation !== null || correction !== null;
    return ({
    id: measure.id,
    semantic: measure.semantic ?? "unknown",
    axis: measure.axis ?? "unknown",
    value: Number.isFinite(measure.value_mm) ? measure.value_mm : null,
    state: measure.state ?? "unknown",
    informationClass: measure.state ?? "unknown",
    confirmable: (["unknown", "conflict"].includes(measure.state) || confirmation !== null) && measurementDispositions.get(measure.id)?.blocking !== false,
    correctable: ["observed", "conflict"].includes(measure.state) && (measure.evidence_ids ?? []).length > 0,
    dispositionReason: measurementDispositions.get(measure.id)?.reason ?? null,
    slotOrigin: measure.slot_origin ?? "drawing",
    geometryRelation: measure.geometry_relation ?? (measure.slot_origin === "profile_required_slot" ? "profile_required_slot" : "dimension_annotation"),
    sourceLabel: MEASURE_SOURCE_LABELS[measure.geometry_relation ?? (measure.slot_origin === "profile_required_slot" ? "profile_required_slot" : "dimension_annotation")] ?? "Medición CAD",
    measurementIds: [...(measure.measurement_ids ?? [])],
    viewIds: [...(measure.view_ids ?? [])],
    evidenceIds: [...(measure.evidence_ids ?? [])],
    sourceEntityIds: [...(measure.source_entity_ids ?? [])],
    confirmation,
    correction,
    effectiveValue: confirmation?.value_mm ?? correction?.value_mm ?? effectiveBinding?.result.value ?? null,
    effectiveState: humanEffective ? "confirmed" : effectiveBinding?.result.state ?? null,
    effectivePrefix: humanEffective ? "Vigente" : effectiveBinding ? "Propuesta" : null,
    effectiveLabel: humanEffective ? "Confirmado por persona" : ({ calculated: "Calculado", observed: "Observado", proposed: "Propuesto", unknown: "Desconocido", conflict: "Conflicto" })[effectiveBinding?.result.state] ?? null,
    humanEffective,
  }); });
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
    sourceWarnings: [...sourceWarningsById.values()],
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
    const previous = workspace.measures.find((measure) => measure.id === item.targetId)?.confirmation;
    return [{
      ...(item.confirmationId ? { confirmation_id: item.confirmationId } : {}),
      ...(previous?.confirmation_id ? { supersedes_confirmation_id: previous.confirmation_id } : {}),
      target_kind: "measurement_slot", target_id: item.targetId, value_mm: number, reason: item.reason.trim(), source: "human",
    }];
  });
  const correctable = new Map(workspace.measures.filter((item) => item.correctable).map((item) => [item.id, item]));
  const observedCorrections = (values.observedCorrections ?? []).map((item) => {
    const measure = correctable.get(item.targetId), number = Number(item.valueMm);
    if (!measure || !item.correctionId || !Number.isFinite(number) || number <= 0 || !item.reason?.trim()) throw new TypeError("Cada corrección observada necesita evidencia, valor positivo y motivo.");
    return {
      correction_id: item.correctionId,
      measurement_id: item.targetId,
      value_mm: number,
      reason: item.reason.trim(),
      evidence_ids: [...measure.evidenceIds],
      source: "human",
      ...(measure.correction?.correction_id ? { supersedes_correction_id: measure.correction.correction_id } : {}),
    };
  });
  const sourceWarnings = new Map(workspace.sourceWarnings.map((item) => [item.id, item]));
  const sourceDecisions = (values.sourceDecisions ?? []).map((item) => {
    const warning = sourceWarnings.get(item.warningId);
    if (!warning || warning.code !== item.warningCode || !["accept", "reject"].includes(item.action) || !item.reason?.trim()) throw new TypeError("Cada revisión de fuente necesita incidencia, decisión y motivo.");
    return { warning_id: item.warningId, warning_code: item.warningCode, action: item.action, reason: item.reason.trim() };
  });
  return {
    base_result_revision: revision,
    reviewer_name: values.reviewerName.trim(),
    table_program_id: values.programId,
    table_decisions: tableDecisions,
    table_confirmed_values: tableConfirmedValues,
    ...(observedCorrections.length ? { table_observed_value_corrections: observedCorrections } : {}),
    ...(sourceDecisions.length ? { table_source_review_decisions: sourceDecisions } : {}),
    notes: values.notes.trim(),
  };
}

export function normaliseTableCostCatalog(raw = {}) {
  const tariff = (item) => ({ id: item.id, label: item.label ?? item.id, rate: item.rate ?? item.rate_eur_per_unit ?? null, rateUnit: item.rate_unit ?? null });
  const tariffs = raw.tariffs ?? [];
  return {
    version: raw.catalog_version ?? null,
    synthetic: raw.synthetic === true,
    source: raw.source ?? null,
    effectiveDate: raw.effective_date ?? null,
    materials: (raw.material_tariffs ?? raw.materials ?? tariffs.filter((item) => item.scope === "material")).map(tariff),
    edges: tariffs.filter((item) => item.scope === "edge").map(tariff),
    operations: (raw.operation_tariffs ?? raw.operations ?? tariffs.filter((item) => item.scope === "operation")).map(tariff),
    labor: tariffs.filter((item) => item.scope === "labor").map(tariff),
    finishing: tariffs.filter((item) => item.scope === "finishing").map(tariff),
  };
}

export function buildTableCostScope(values = {}) {
  const optionalNumber = (value, label) => {
    if (value === "" || value == null) return null;
    const number = Number(value);
    if (!Number.isFinite(number) || number < 0) throw new TypeError(`${label} debe ser un número no negativo.`);
    return number;
  };
  const exclusions = (values.exclusions ?? []).map((item) => {
    const reason = String(item.reason ?? "").trim();
    if (!reason) throw new TypeError("Cada exclusión necesita un motivo.");
    return { scope: item.scope, reason };
  });
  const operations = values.operations ?? [];
  const operationHours = Object.fromEntries(operations.flatMap((item) => {
    const hours = optionalNumber(item.hours, "Las horas de operación");
    return hours == null ? [] : [[item.id, hours]];
  }));
  const margin = optionalNumber(values.marginPercent, "El margen provisional");
  if (margin != null && margin >= 100) throw new TypeError("El margen provisional debe ser menor que 100.");
  const excludedScopes = new Set(exclusions.map((item) => item.scope));
  if (excludedScopes.has("material") && (values.materialTariffId || Object.keys(values.componentMaterialTariffIds ?? {}).length)) throw new TypeError("El material excluido no puede incluir tarifas.");
  if (excludedScopes.has("edge") && (values.edgeScope === "all_exposed" || values.edgeTariffId)) throw new TypeError("El canteado excluido no puede incluir alcance o tarifa.");
  if (excludedScopes.has("operation") && (operations.length || Object.keys(operationHours).length)) throw new TypeError("Las operaciones excluidas no pueden incluir tarifas u horas.");
  if (excludedScopes.has("labor") && (values.laborTariffId || values.laborHours !== "" && values.laborHours != null)) throw new TypeError("La mano de obra excluida no puede incluir tarifa u horas.");
  if (excludedScopes.has("finishing") && (values.finishTariffId || values.finishQuantity !== "" && values.finishQuantity != null)) throw new TypeError("El acabado excluido no puede incluir tarifa o superficie.");
  return {
    material_tariff_id: values.materialTariffId || null,
    component_material_tariff_ids: { ...(values.componentMaterialTariffIds ?? {}) },
    edge_scope: values.edgeScope === "all_exposed" ? "all_exposed" : "none",
    edge_tariff_id: values.edgeTariffId || null,
    operation_tariff_ids: operations.map((item) => item.id),
    operation_hours_by_tariff: operationHours,
    labor_tariff_id: values.laborTariffId || null,
    labor_hours: optionalNumber(values.laborHours, "Las horas de mano de obra"),
    finish_tariff_id: values.finishTariffId || null,
    finish_quantity_m2: optionalNumber(values.finishQuantity, "La superficie de acabado"),
    exclusions,
    provisional_margin_percent: margin,
  };
}

export function presentTableCosts(raw = {}) {
  const euros = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: 2 });
  const number = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 3 });
  const items = (raw.concepts ?? []).map((concept) => ({
    ...concept,
    quantityLabel: Number.isFinite(concept.quantity) ? `${number.format(concept.quantity)} ${concept.quantity_unit}` : "Cantidad pendiente",
    rateLabel: Number.isFinite(concept.rate_eur_per_unit) ? `${euros.format(concept.rate_eur_per_unit)} por ${String(concept.rate_unit ?? "unidad").replace("EUR/", "")}` : concept.state === "not_applicable" ? "No aplica" : "Tarifa pendiente",
    amountLabel: Number.isFinite(concept.amount_eur) ? euros.format(concept.amount_eur) : concept.state === "not_applicable" ? "No aplica" : "Pendiente",
    stateLabel: concept.state === "resolved" ? "Resuelto" : concept.state === "not_applicable" ? "No aplica" : "Desconocido",
  }));
  const resolved = items.filter((item) => Number.isFinite(item.amount_eur));
  const largestContribution = raw.principal_cost_contributor_id ? resolved.find((item) => item.id === raw.principal_cost_contributor_id) ?? null : resolved.reduce((largest, item) => !largest || item.amount_eur > largest.amount_eur ? item : largest, null);
  const complete = raw.total_state === "complete" && Number.isFinite(raw.grand_total_eur);
  const snapshot = raw.catalog_snapshot ?? {};
  return {
    revision: raw.result_revision ?? null,
    programHash: raw.program_hash ?? null,
    catalogVersion: raw.catalog_version ?? null,
    synthetic: raw.synthetic !== false,
    catalogLabel: `${raw.synthetic === false ? "Tarifa real" : "Tarifa demo"}${snapshot.source ? ` · ${snapshot.source}` : ""}${snapshot.effective_date ? ` · ${snapshot.effective_date}` : ""}`,
    complete,
    totalLabel: complete ? euros.format(raw.grand_total_eur) : `Subtotal conocido ${euros.format(raw.known_subtotal_eur ?? 0)}`,
    hoursLabel: Number.isFinite(raw.total_hours) ? `${number.format(raw.total_hours)} h` : "Desconocidas",
    marginLabel: Number.isFinite(raw.provisional_margin_percent) ? `${number.format(raw.provisional_margin_percent)} %` : "Sin margen",
    salePriceLabel: Number.isFinite(raw.provisional_sale_price_eur) ? euros.format(raw.provisional_sale_price_eur) : "No disponible",
    items,
    largestContribution,
    warnings: [...(raw.warnings ?? [])],
  };
}

export function presentTableComponentExplanation(bundle = {}, componentId) {
  bundle = bundle ?? {};
  const raw = (bundle.pieces ?? []).find((item) => [item.piece_id, item.proposal_id].includes(componentId)) ?? {};
  const labels = { quantity: "Cantidad", length_mm: "Largo", width_mm: "Ancho", thickness_mm: "Grosor" };
  return {
    formulas: (raw.formulas ?? []).map((formula) => ({
      fieldLabel: labels[formula.field] ?? formula.field,
      expression: formula.expression,
      operandsLabel: Object.entries(formula.operands_mm ?? {}).map(([id, value]) => `${id} = ${value} mm`).join(" · "),
      resultLabel: Number.isFinite(formula.result_mm) ? `${formula.result_mm} mm` : "Desconocido",
    })),
    premises: [...(raw.premises ?? [])],
    unknownLabels: (raw.unknown_fields ?? []).map((field) => labels[field] ?? field),
    fieldStates: { ...(raw.field_states ?? {}) },
    warnings: [...(bundle.warnings ?? [])],
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
      if (typeof format === "string" || !SHEET_FORMATS.has(format.format) || typeof format.url !== "string" || !format.url.startsWith("/") || format.url.startsWith("//")) return [];
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
