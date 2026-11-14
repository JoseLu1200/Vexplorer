const list = (value) => Array.isArray(value) ? value : [];

export function generalRunOptions(mode){return{proposal_mode:mode==="live"||mode==="recorded_replay"?"model_generated":"none"};}

function field(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return { value: value.value ?? value.value_mm ?? null, unit: value.unit ?? ("value_mm" in value ? "mm" : null), state: value.state ?? value.origin ?? "unknown", provenance: value.provenance ?? null, formula: value.formula ?? null, dependencyRefs:list(value.dependency_refs), evidenceIds:list(value.evidence_ids), dimensionIds:list(value.dimension_ids) };
  }
  return { value: value ?? null, unit: null, state: value == null ? "unknown" : "proposed", provenance: null, formula: null };
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

export function normaliseGeneralWorkspace(raw = {}) {
  const effective = raw.review?.components?.length ? raw.review : (raw.draft ?? raw.proposal ?? raw.snapshot ?? raw);
  return {
    isGeneral: Boolean(raw.proposal || raw.draft || raw.review || raw.proposal_revision !== undefined),
    proposalRevision: raw.proposal_revision ?? raw.proposal?.proposal_revision ?? null,
    reviewRevision: raw.review_revision ?? raw.review?.review_revision ?? 0,
    status: raw.status ?? effective.status ?? "unavailable",
    drawingId: raw.draft?.drawing_id ?? raw.proposal?.drawing_id ?? raw.drawing_id ?? null,
    ledgerRevision: raw.draft?.ledger_revision ?? raw.proposal?.ledger_revision ?? raw.ledger_revision ?? null,
    components: list(effective.components).map(component),
    occurrences: list(raw.review?.occurrences ?? effective.occurrences).map((item) => ({ ...item, id: item.id ?? item.occurrence_id, componentId: item.component_id ?? item.componentId, state: item.state ?? "proposed" })),
    premises: list(raw.draft?.premises ?? raw.proposal?.premises),
    assumptions: list(raw.draft?.assumptions ?? raw.proposal?.assumptions),
    warnings: list(raw.warnings ?? effective.warnings),
    furnitureQuantity: field(raw.review?.furniture_quantity),
    currency: raw.review?.currency ?? null,
    requiredCostScope: list(raw.review?.required_cost_scope),
    requiredHoursScope: list(raw.review?.required_hours_scope),
    reviewerKind: raw.review?.reviewer_kind ?? (raw.review ? "human" : null),
    reviewerName: raw.review?.reviewer_name ?? null,
    machineProvenance: raw.review?.machine_provenance ?? null,
    autoChecks: list(raw.review?.machine_checks),
    autoFieldReviews:list(raw.review?.machine_field_reviews),
    autoReviewStatus:raw.review?.auto_review_status??null,
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
  return {
    proposalRevision: packageValue.proposal_revision ?? null,
    reviewRevision: packageValue.review_revision ?? null,
    status: packageValue.status ?? "unavailable",
    bom: list(packageValue.bom_rows ?? packageValue.bom).map((row) => ({ ...row, componentId: row.component_id, occurrenceIds: list(row.occurrence_ids), scenarioOccurrenceIds:list(row.scenario_occurrence_ids), occurrenceStatus:row.occurrence_status??"unknown", quantity: field(row.quantity), length:field(row.length), width:field(row.width), thickness:field(row.thickness), material: field(row.material), finish: field(row.finish) })),
    artifacts: list(packageValue.artifacts).map((artifact) => ({ ...artifact, incompleteReasons: list(artifact.incomplete_reasons), downloads: artifact.downloads ?? {} })),
    scene: packageValue.scene ?? { status: "unavailable" },
    costBasis: { ...(packageValue.cost_basis ?? {}), missingData: list(packageValue.cost_basis?.missing_data), contributors: list(packageValue.cost_basis?.contributors) },
    historicalTarget: raw.historical_target??null,
  };
}

function csv(value) { const text=String(value??""); return /[",\r\n]/.test(text)?`"${text.replaceAll('"','""')}"`:text; }
function fieldValue(value) { return value&&typeof value==="object"&&!Array.isArray(value)?(value.value??value.value_mm??null):value; }
function csvText(value){const text=String(value??"");return /^[=+\-@]/.test(text.trimStart())?`'${text}`:text;}

export function serialiseGeneralBom(bom, format) {
  if(format==="json")return JSON.stringify(list(bom),null,2);
  const rows=list(bom).map((row)=>[row.component_id??row.componentId,csvText(row.label),csvText(row.role),fieldValue(row.quantity),row.quantity?.state??"unknown",row.occurrence_status??row.occurrenceStatus??"unknown",list(row.occurrence_ids??row.occurrenceIds).join("|"),list(row.scenario_occurrence_ids??row.scenarioOccurrenceIds).join("|"),fieldValue(row.dimensions?.length??row.length),fieldValue(row.dimensions?.width??row.width),fieldValue(row.dimensions?.thickness??row.thickness),csvText(fieldValue(row.material)),csvText(fieldValue(row.finish))].map(csv).join(","));
  return ["component_id,label,role,quantity,quantity_state,occurrence_status,physical_occurrence_ids,scenario_occurrence_ids,length_mm,width_mm,thickness_mm,material,finish",...rows].join("\r\n");
}

export function buildManualGeneralProposal({ drawingId, ledgerRevision, label, kind="unknown", role="unknown", reason, idFactory=(value)=>`${value}-${globalThis.crypto?.randomUUID?.()??Date.now()}` }) {
  if(!drawingId||!ledgerRevision)throw new TypeError("Falta la identidad del dibujo o del ledger.");
  if(!String(label??"").trim()||!String(reason??"").trim())throw new TypeError("Nombre y motivo son obligatorios.");
  const proposalId=idFactory("proposal"),componentId=idFactory("component"),premiseId=idFactory("premise"),assumption=String(reason).trim();
  return {schema_version:"0.6.0",id:proposalId,drawing_id:drawingId,ledger_revision:ledgerRevision,proposal_origin:"human",bindings:[],components:[{id:componentId,label:String(label).trim(),kind,role:String(role||"unknown").trim(),length_binding_id:null,width_binding_id:null,thickness_binding_id:null,quantity:{value:null,state:"unknown",dependency_refs:[],evidence_ids:[]},premise_ids:[premiseId],source_view_ids:[],source_observation_ids:[],source_contour_ids:[],source_evidence_ids:[],source_dimension_ids:[],source_document_refs:[],assumptions:[assumption],unknown_fields:["length","width","thickness","quantity","material","finish","placement"]}],premises:[{id:premiseId,description:assumption,required:true,blocking:true}],assumptions:[assumption]};
}
