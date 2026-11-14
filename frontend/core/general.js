const list = (value) => Array.isArray(value) ? value : [];

export function generalRunOptions(mode){return{proposal_mode:mode==="live"||mode==="recorded_replay"?"model_generated":"none"};}

export function generalMachineStatusPresentation(workspace){
  if(workspace?.reviewerKind!=="machine")return null;
  const incomplete=workspace.autoReviewStatus!=="accepted"||workspace.status!=="approved";
  return incomplete
    ?{label:"Auto-revisión con incógnitas",message:"La revisión automática terminó con datos desconocidos. Los resultados siguen disponibles y conservan esas incógnitas; la corrección humana es opcional."}
    :{label:"Auto-revisión completada",message:"La revisión automática de coherencia terminó. Puedes consultar resultados, descargas y escenarios sin una aprobación humana obligatoria."};
}

function field(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const range=value.range_mm&&Number.isFinite(Number(value.range_mm.min_mm))&&Number.isFinite(Number(value.range_mm.max_mm))?{min:Number(value.range_mm.min_mm),max:Number(value.range_mm.max_mm)}:null;
    return { value: value.value ?? value.value_mm ?? null, unit: value.unit ?? ("value_mm" in value ? "mm" : null), state: value.state ?? value.origin ?? "unknown", provenance: value.provenance ?? null, formula: value.formula ?? null, range, method:value.method??null, explanation:value.explanation??value.rationale??null, reviewStatus:value.review_status??null, dependencyRefs:list(value.dependency_refs), operandRefs:list(value.operand_refs), sourceRefs:list(value.source_refs), assumptionRefs:list(value.assumption_refs), evidenceIds:list(value.evidence_ids), dimensionIds:list(value.dimension_ids) };
  }
  return { value: value ?? null, unit: null, state: value == null ? "unknown" : "proposed", provenance: null, formula: null };
}

const CONSTRUCTION_STATE_LABELS={observed:"Observada",deduced:"Deducida",estimated:"Estimada",unknown:"Desconocida",conflict:"En conflicto"};

export function presentGeneralConstructionDimension(raw = {}) {
  const reviewStatus=raw.review_status??raw.reviewStatus??null,accepted=reviewStatus===null||reviewStatus==="accepted",numeric=Number(raw.value_mm??raw.value??raw.nominal_mm),value=accepted&&Number.isFinite(numeric)&&numeric>0?numeric:null;
  const rangeValue=raw.range_mm??raw.range,range=rangeValue&&Number.isFinite(Number(rangeValue.min_mm??rangeValue.min))&&Number.isFinite(Number(rangeValue.max_mm??rangeValue.max))
    ?{min:Number(rangeValue.min_mm??rangeValue.min),max:Number(rangeValue.max_mm??rangeValue.max)}:null;
  const state=raw.state??raw.basis??"unknown",approximate=state==="estimated"&&value!==null;
  return {
    value,
    state,
    stateLabel:CONSTRUCTION_STATE_LABELS[state]??"Desconocida",
    reviewStatus:reviewStatus??"accepted",
    approximate,
    display:value===null?"Desconocida":`${approximate?"≈ ":""}${value} mm`,
    range,
    rangeDisplay:range?`${range.min}–${range.max} mm`:null,
    method:raw.method??null,
    formula:raw.formula??null,
    operandRefs:list(raw.operand_refs??raw.operandRefs),
    sourceRefs:list(raw.source_refs??raw.sourceRefs),
    assumptionRefs:list(raw.assumption_refs??raw.assumptionRefs),
    explanation:raw.explanation??raw.rationale??null,
  };
}

export function presentGeneralConstructionQuantity(raw = {}) {
  const reviewStatus=raw.review_status??raw.reviewStatus??null,accepted=reviewStatus===null||reviewStatus==="accepted",numeric=Number(raw.value),value=accepted&&Number.isInteger(numeric)&&numeric>0?numeric:null,state=raw.state??"unknown",approximate=state==="estimated"&&value!==null,minValue=raw.min_value??raw.minValue??null,maxValue=raw.max_value??raw.maxValue??null,hasRange=Number.isInteger(Number(minValue))&&Number.isInteger(Number(maxValue));
  return{...raw,value,state,reviewStatus:reviewStatus??"accepted",approximate,display:value===null?"Desconocida":`${approximate?"≈ ":""}${value} uds.`,minValue:hasRange?Number(minValue):null,maxValue:hasRange?Number(maxValue):null,rangeDisplay:hasRange?`${Number(minValue)}–${Number(maxValue)} uds.`:null,method:raw.method??null,sourceRefs:list(raw.source_refs??raw.sourceRefs),assumptionRefs:list(raw.assumption_refs??raw.assumptionRefs),explanation:raw.explanation??null};
}

function reviewedValue(original, rawValue, { numeric=false, humanRef }) {
  const empty=rawValue===null||rawValue===undefined||String(rawValue).trim()==="";
  const value=empty?null:(numeric?Number(rawValue):String(rawValue).trim());
  if(numeric&&value!==null&&(!Number.isFinite(value)||value<=0))throw new TypeError("Las medidas deben ser positivas o quedar desconocidas.");
  const unchanged=original&&value===original.value&&!["unknown","conflict"].includes(original.state);
  if(value===null)return numeric?{value_mm:null,unit:"mm",state:"unknown",dependency_refs:[],evidence_ids:[],dimension_ids:[]}:{value:null,state:"unknown",dependency_refs:[],evidence_ids:[]};
  if(unchanged)return numeric?{value_mm:value,unit:"mm",state:original.state,dependency_refs:list(original.dependencyRefs),evidence_ids:list(original.evidenceIds),dimension_ids:list(original.dimensionIds)}:{value,state:original.state,dependency_refs:list(original.dependencyRefs),evidence_ids:list(original.evidenceIds)};
  return numeric?{value_mm:value,unit:"mm",state:"confirmed",dependency_refs:[humanRef],evidence_ids:[],dimension_ids:[]}:{value,state:"confirmed",dependency_refs:[humanRef],evidence_ids:[]};
}

export function buildGeneralReviewedComponent({ sourceComponents=[], resultId, values={}, reason, humanRef="human:review" }) {
  const sources=list(sourceComponents),primary=sources[0]??{},union=(name)=>[...new Set(sources.flatMap((item)=>list(item[name])))];
  const kind=String(values.kind??"unknown").trim()||"unknown",label=String(values.label??"").trim(),role=String(values.role??"unknown").trim()||"unknown";
  if(!label)throw new TypeError("Cada componente resultante necesita un nombre.");
  if(!["panel","linear_member","hardware","unknown"].includes(kind))throw new TypeError("El tipo debe ser panel, linear_member, hardware o unknown.");
  const quantityRaw=values.quantity,quantityEmpty=quantityRaw===null||quantityRaw===undefined||String(quantityRaw).trim()==="",quantity=quantityEmpty?null:Number(quantityRaw);
  if(quantity!==null&&(!Number.isInteger(quantity)||quantity<1))throw new TypeError("La cantidad debe ser un entero positivo o quedar desconocida.");
  const originalQuantity=primary.quantity,quantityUnchanged=originalQuantity&&quantity===originalQuantity.value&&!["unknown","conflict"].includes(originalQuantity.state);
  const quantityValue=quantity===null?{value:null,state:"unknown",dependency_refs:[],evidence_ids:[]}:quantityUnchanged?{value:quantity,state:originalQuantity.state,dependency_refs:list(originalQuantity.dependencyRefs),evidence_ids:list(originalQuantity.evidenceIds)}:{value:quantity,state:"confirmed",dependency_refs:[humanRef],evidence_ids:[]};
  const length=reviewedValue(primary.dimensions?.length,values.length,{numeric:true,humanRef}),width=reviewedValue(primary.dimensions?.width,values.width,{numeric:true,humanRef}),thickness=reviewedValue(primary.dimensions?.thickness,values.thickness,{numeric:true,humanRef}),material=reviewedValue(primary.material,values.material,{humanRef}),finish=reviewedValue(primary.finish,values.finish,{humanRef});
  const unknownFields=[["length",length.value_mm],["width",width.value_mm],["thickness",thickness.value_mm],["quantity",quantityValue.value],["material",material.value],["finish",finish.value]].filter(([,value])=>value==null).map(([name])=>name);
  return {id:resultId,label,kind,role,length,width,thickness,quantity:quantityValue,material,finish,replaces_component_ids:sources.map((item)=>item.id),source_view_ids:union("viewIds"),source_observation_ids:union("observationIds"),source_contour_ids:union("contourIds"),source_evidence_ids:union("evidenceIds"),source_dimension_ids:union("dimensionIds"),source_document_refs:union("documentRefs"),assumptions:[String(reason??"").trim()].filter(Boolean),unknown_fields:[...unknownFields,"placement"]};
}

function component(raw = {}) {
  const dimensions = raw.dimensions ?? { length: raw.length, width: raw.width, thickness: raw.thickness };
  return {
    id: raw.id ?? raw.component_id ?? "",
    label: raw.label ?? raw.name ?? raw.id ?? "Componente sin nombre",
    kind: raw.kind ?? raw.component_kind ?? "unknown",
    role: raw.role ?? "unknown",
    dimensions: Object.fromEntries(Object.entries(dimensions).map(([key, value]) => [key, field(value)])),
    quantity: field(raw.quantity),
    material: field(raw.material),
    finish: field(raw.finish),
    viewIds: list(raw.source_view_ids),
    observationIds: list(raw.source_observation_ids),
    contourIds: list(raw.source_contour_ids),
    evidenceIds: list(raw.source_evidence_ids),
    dimensionIds: list(raw.source_dimension_ids),
    documentRefs: list(raw.source_document_refs),
    assumptions: list(raw.assumptions),
    unknownFields: list(raw.unknown_fields),
    replacesComponentIds: list(raw.replaces_component_ids),
  };
}

const MACHINE_FIELDS=["length","width","thickness","quantity","material","finish"];

function machineReviewMetadata(componentId,name,reviews,checks){
  const targetRef=`component:${componentId}.${name}`,review=reviews.get(targetRef),status=review?.status??"unreviewed",checkIds=list(review?.check_ids),matched=checkIds.map((id)=>checks.get(id)).filter(Boolean),checkSummaries=matched.map((item)=>item.summary).filter(Boolean),sourceRefs=[...new Set(matched.flatMap((item)=>list(item.source_refs)))],fallback={rejected:"Valor rechazado por la revisión automática.",conflict:"La revisión automática detectó evidencia en conflicto.",abstained:"La revisión automática se abstuvo por falta de respaldo suficiente.",unreviewed:"Sin decisión de campo publicada por la revisión automática."}[status]??"Campo aceptado por la revisión automática.";
  return{targetRef,status,checkIds,checkSummaries,sourceRefs,reason:checkSummaries.join(" · ")||fallback};
}

function maskMachineComponent(rawComponent,reviews,checks){
  const masked={...rawComponent,dimensions:{...rawComponent.dimensions},rawHypothesis:rawComponent},unknown=new Set(rawComponent.unknownFields);
  MACHINE_FIELDS.forEach((name)=>{
    const metadata=machineReviewMetadata(rawComponent.id,name,reviews,checks),source=["length","width","thickness"].includes(name)?rawComponent.dimensions[name]:rawComponent[name],effective=metadata.status==="accepted"?{...source,machineReview:metadata}:{...source,value:null,state:"unknown",machineReview:metadata};
    if(["length","width","thickness"].includes(name))masked.dimensions[name]=effective;else masked[name]=effective;
    if(effective.value==null)unknown.add(name);else unknown.delete(name);
  });
  masked.unknownFields=MACHINE_FIELDS.filter((name)=>unknown.has(name));
  return masked;
}

export function normaliseGeneralWorkspace(raw = {}) {
  const effective = raw.review?.components?.length ? raw.review : (raw.draft ?? raw.proposal ?? raw.snapshot ?? raw);
  const reviewerKind=raw.review?.reviewer_kind ?? (raw.review ? "human" : null),rawComponents=list(effective.components).map(component),checks=new Map(list(raw.review?.machine_checks).map((item)=>[item.id,item])),reviews=new Map(list(raw.review?.machine_field_reviews).map((item)=>[item.target_ref,item])),components=reviewerKind==="machine"?rawComponents.map((item)=>maskMachineComponent(item,reviews,checks)):rawComponents;
  return {
    isGeneral: Boolean(raw.proposal || raw.draft || raw.review || raw.proposal_revision !== undefined),
    proposalRevision: raw.proposal_revision ?? raw.proposal?.proposal_revision ?? null,
    reviewRevision: raw.review_revision ?? raw.review?.review_revision ?? 0,
    status: raw.status ?? effective.status ?? "unavailable",
    drawingId: raw.draft?.drawing_id ?? raw.proposal?.drawing_id ?? raw.drawing_id ?? null,
    ledgerRevision: raw.draft?.ledger_revision ?? raw.proposal?.ledger_revision ?? raw.ledger_revision ?? null,
    components,
    rawComponents,
    occurrences: list(raw.review?.occurrences ?? effective.occurrences).map((item) => ({ ...item, id: item.id ?? item.occurrence_id, componentId: item.component_id ?? item.componentId, state: item.state ?? "proposed" })),
    premises: list(raw.draft?.premises ?? raw.proposal?.premises),
    assumptions: list(raw.draft?.assumptions ?? raw.proposal?.assumptions),
    warnings: list(raw.warnings ?? effective.warnings),
    furnitureQuantity: field(raw.review?.furniture_quantity),
    currency: raw.review?.currency ?? null,
    requiredCostScope: list(raw.review?.required_cost_scope),
    requiredHoursScope: list(raw.review?.required_hours_scope),
    reviewerKind,
    reviewerName: raw.review?.reviewer_name ?? null,
    machineProvenance: raw.review?.machine_provenance ?? null,
    autoChecks: list(raw.review?.machine_checks),
    autoFieldReviews:list(raw.review?.machine_field_reviews),
    autoReviewStatus:raw.review?.auto_review_status??null,
    constructionScenarioId: effective.construction_scenario_id??raw.proposal?.construction_scenario_id??null,
    constructionParameters:list(effective.construction_parameters??raw.proposal?.construction_parameters).map((item)=>({id:item.id,label:item.label,...presentGeneralConstructionDimension(item),bindingId:item.binding_id??null})),
    constructionDetails:list(effective.construction_details??raw.proposal?.construction_details).map((item)=>({...item,componentIds:list(item.component_ids),parameterRefs:list(item.parameter_refs),sourceRefs:list(item.source_refs),assumptionRefs:list(item.assumption_refs)})),
    constructionDecisions:list(effective.construction_decisions??raw.proposal?.construction_decisions).map((item)=>({...item,targetRefs:list(item.target_refs),basisRefs:list(item.basis_refs),alternatives:list(item.alternatives)})),
  };
}

export function buildGeneralReviewPayload(workspace, values = {}) {
  if (!Number.isInteger(workspace?.proposalRevision)) throw new TypeError("La propuesta general no tiene una revisión válida.");
  const reason = String(values.reason ?? "").trim();
  if (!reason) throw new TypeError("Explica el motivo técnico de la revisión.");
  const operations = list(values.operations).map((operation) => ({
    kind: operation.kind,
    source_component_ids: list(operation.sourceComponentIds ?? operation.source_component_ids),
    result_component_ids: list(operation.resultComponentIds ?? operation.result_component_ids),
    reason: String(operation.reason ?? reason).trim(),
  }));
  if (!operations.length) throw new TypeError("Añade al menos una operación de revisión.");
  const currency=String(values.currency??"").trim().toUpperCase();
  if(currency&&!/^[A-Z]{3}$/.test(currency))throw new TypeError("La moneda debe tener tres letras ISO.");
  const scope=(items,label)=>{const values=[...new Set(list(items).map((item)=>String(item).trim()).filter(Boolean))];if(values.some((item)=>!/^[A-Za-z0-9_-]{1,100}$/.test(item)))throw new TypeError(`El alcance de ${label} solo admite letras, números, guion y guion bajo.`);return values;};
  return {
    base_proposal_revision: workspace.proposalRevision,
    base_review_revision: Number.isInteger(workspace.reviewRevision) ? workspace.reviewRevision : 0,
    reviewer_name: String(values.reviewerName ?? values.reviewer ?? "").trim(),
    reason,
    operations,
    components: list(values.components),
    furniture_quantity: values.furnitureQuantity == null || String(values.furnitureQuantity).trim()==="" ? {value:null,state:"unknown",dependency_refs:[],evidence_ids:[]} : (()=>{const quantity=Number(values.furnitureQuantity);if(!Number.isInteger(quantity)||quantity<1)throw new TypeError("Las unidades de mueble terminado deben ser un entero positivo o quedar desconocidas.");return{value:quantity,state:"confirmed",dependency_refs:[values.humanRef??"human:review"],evidence_ids:[]};})(),
    currency: currency||null,
    required_cost_scope: scope(values.requiredCostScope,"coste"),
    required_hours_scope: scope(values.requiredHoursScope,"horas"),
  };
}

export function completeGeneralReviewSnapshot(workspace, { operations=[], components=[], reason, humanRef="human:review" } = {}) {
  const covered=new Set(list(operations).flatMap((item)=>list(item.sourceComponentIds??item.source_component_ids))),allOperations=[...operations],allComponents=[...components];
  list(workspace?.components).filter((source)=>!covered.has(source.id)).forEach((source)=>{
    const resultId=`${source.id}-carry-r${(workspace.reviewRevision??0)+1}`;
    const values={label:source.label,kind:source.kind,role:source.role,quantity:source.quantity?.value,length:source.dimensions?.length?.value,width:source.dimensions?.width?.value,thickness:source.dimensions?.thickness?.value,material:source.material?.value,finish:source.finish?.value};
    allOperations.push({kind:"replace",sourceComponentIds:[source.id],resultComponentIds:[resultId],reason:`${reason} Componente conservado sin cambios.`.trim()});
    allComponents.push(buildGeneralReviewedComponent({sourceComponents:[source],resultId,values,reason,humanRef}));
  });
  return {operations:allOperations,components:allComponents};
}

export function presentGeneralDerived(raw = {}) {
  const packageValue=raw.package??raw;
  const constructionRaw=packageValue.construction,construction=constructionRaw?(()=>{const decisions=list(constructionRaw.decisions).map((item)=>({...item,targetRefs:list(item.target_refs),basisRefs:list(item.basis_refs),alternatives:list(item.alternatives)})),decisionById=new Map(decisions.map((item)=>[item.id,item]));return{
    runId:constructionRaw.run_id,proposalRevision:constructionRaw.proposal_revision,reviewRevision:constructionRaw.review_revision,basisRevision:constructionRaw.basis_revision,scenarioId:constructionRaw.scenario_id,authority:constructionRaw.authority,
    summary:{...(constructionRaw.summary??{}),componentCount:constructionRaw.summary?.component_count??0,occurrenceCount:constructionRaw.summary?.occurrence_count??0,sourceRefs:list(constructionRaw.summary?.source_refs),topDecisionIds:list(constructionRaw.summary?.top_decision_ids),warnings:list(constructionRaw.summary?.warnings)},
    pieces:list(constructionRaw.pieces).map((item)=>({...item,pieceId:item.piece_id,componentId:item.component_id,scenarioId:item.scenario_id,occurrenceIds:list(item.occurrence_ids),scenarioOccurrenceIds:list(item.scenario_occurrence_ids),detailIds:list(item.detail_ids),sourceRefs:list(item.source_refs),sheetIds:list(item.sheet_ids),length:presentGeneralConstructionDimension(item.length),width:presentGeneralConstructionDimension(item.width),thickness:presentGeneralConstructionDimension(item.thickness),quantity:presentGeneralConstructionQuantity(item.quantity)})),
    placements:list(constructionRaw.placements),details:list(constructionRaw.details).map((item)=>({...item,componentIds:list(item.component_ids),parameterRefs:list(item.parameter_refs),sourceRefs:list(item.source_refs),assumptionRefs:list(item.assumption_refs)})),decisions,topDecisions:list(constructionRaw.summary?.top_decision_ids).map((id)=>decisionById.get(id)).filter(Boolean),warnings:list(constructionRaw.warnings),sheets:list(constructionRaw.sheets).map((item)=>({...item,sheetId:item.sheet_id,pieceId:item.piece_id??null,primitives:list(item.primitives),warnings:list(item.warnings)})),
  };})():null;
  return {
    proposalRevision: packageValue.proposal_revision ?? null,
    reviewRevision: packageValue.review_revision ?? null,
    status: packageValue.status ?? "unavailable",
    bom: list(packageValue.bom_rows ?? packageValue.bom).map((row) => ({ ...row, componentId: row.component_id, occurrenceIds: list(row.occurrence_ids), scenarioOccurrenceIds:list(row.scenario_occurrence_ids), occurrenceStatus:row.occurrence_status??"unknown", quantity: field(row.quantity), length:field(row.length), width:field(row.width), thickness:field(row.thickness), material: field(row.material), finish: field(row.finish), machineFieldReviews:list(row.machine_field_reviews).map((item)=>({...item,targetRef:item.target_ref,checkIds:list(item.check_ids),checkSummaries:list(item.check_summaries),sourceRefs:list(item.source_refs)})) })),
    artifacts: list(packageValue.artifacts).map((artifact) => ({ ...artifact, sheetId:artifact.sheet_id??null,componentId:artifact.component_id??null,incompleteReasons: list(artifact.incomplete_reasons), downloads: artifact.downloads ?? {} })),
    scene: packageValue.scene ?? { status: "unavailable" },
    costBasis: { ...(packageValue.cost_basis ?? {}), missingData: list(packageValue.cost_basis?.missing_data), contributors: list(packageValue.cost_basis?.contributors) },
    historicalTarget: raw.historical_target??null,
    construction,
  };
}

export function generalBomArtifact(derived,format){const kind=({csv:"bom_csv",json:"bom_json"})[format];return kind?list(derived?.artifacts).find((item)=>item.kind===kind)??null:null;}

export function generalDerivedLoadFailure(error){if(error?.status!==409)return null;return{label:"Snapshot desactualizado",message:`La propuesta cambió mientras se cargaban sus derivados. Recarga la ejecución para consultar el snapshot exacto.${error.message?` ${error.message}`:""}`};}

function csv(value) { const text=String(value??""); return /[",\r\n]/.test(text)?`"${text.replaceAll('"','""')}"`:text; }
function fieldValue(value) { return value&&typeof value==="object"&&!Array.isArray(value)?(value.value??value.value_mm??null):value; }
function csvText(value){const text=String(value??"");return /^[=+\-@]/.test(text.trimStart())?`'${text}`:text;}
function dimensionCsvCells(value){const item=value&&typeof value==="object"?value:{value:value??null};return[fieldValue(item),item.state??"unknown",item.range?.min??item.range_mm?.min_mm??null,item.range?.max??item.range_mm?.max_mm??null,csvText(item.method),list(item.sourceRefs??item.source_refs).join("|"),list(item.assumptionRefs??item.assumption_refs).join("|")];}

export function serialiseGeneralBom(bom, format) {
  if(format==="json")return JSON.stringify(list(bom),null,2);
  const rows=list(bom).map((row)=>[row.component_id??row.componentId,csvText(row.label),csvText(row.role),fieldValue(row.quantity),row.quantity?.state??"unknown",row.occurrence_status??row.occurrenceStatus??"unknown",list(row.occurrence_ids??row.occurrenceIds).join("|"),list(row.scenario_occurrence_ids??row.scenarioOccurrenceIds).join("|"),...dimensionCsvCells(row.dimensions?.length??row.length),...dimensionCsvCells(row.dimensions?.width??row.width),...dimensionCsvCells(row.dimensions?.thickness??row.thickness),csvText(fieldValue(row.material)),csvText(fieldValue(row.finish))].map(csv).join(","));
  const dimensionHeaders=(name)=>[`${name}_mm`,`${name}_state`,`${name}_range_min_mm`,`${name}_range_max_mm`,`${name}_method`,`${name}_source_refs`,`${name}_assumption_refs`];
  return [["component_id","label","role","quantity","quantity_state","occurrence_status","physical_occurrence_ids","scenario_occurrence_ids",...dimensionHeaders("length"),...dimensionHeaders("width"),...dimensionHeaders("thickness"),"material","finish"].join(","),...rows].join("\r\n");
}

export function buildManualGeneralProposal({ drawingId, ledgerRevision, label, kind="unknown", role="unknown", reason, idFactory=(value)=>`${value}-${globalThis.crypto?.randomUUID?.()??Date.now()}` }) {
  if(!drawingId||!ledgerRevision)throw new TypeError("Falta la identidad del dibujo o del ledger.");
  if(!String(label??"").trim()||!String(reason??"").trim())throw new TypeError("Nombre y motivo son obligatorios.");
  const proposalId=idFactory("proposal"),componentId=idFactory("component"),premiseId=idFactory("premise"),assumption=String(reason).trim();
  return {schema_version:"0.6.0",id:proposalId,drawing_id:drawingId,ledger_revision:ledgerRevision,proposal_origin:"human",bindings:[],components:[{id:componentId,label:String(label).trim(),kind,role:String(role||"unknown").trim(),length_binding_id:null,width_binding_id:null,thickness_binding_id:null,quantity:{value:null,state:"unknown",dependency_refs:[],evidence_ids:[]},premise_ids:[premiseId],source_view_ids:[],source_observation_ids:[],source_contour_ids:[],source_evidence_ids:[],source_dimension_ids:[],source_document_refs:[],assumptions:[assumption],unknown_fields:["length","width","thickness","quantity","material","finish","placement"]}],premises:[{id:premiseId,description:assumption,required:true,blocking:true}],assumptions:[assumption]};
}
