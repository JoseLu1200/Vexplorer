const list = (value) => Array.isArray(value) ? value : [];
const number = (value) => value === null || value === undefined || (typeof value === "string" && value.trim() === "") ? null : (Number.isFinite(Number(value)) ? Number(value) : null);
const decimal = (value) => new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 }).format(value);
const ORIGIN_LABELS={actual:"Registro empresarial real",published:"Fuente pública publicada",synthetic:"Fixture sintético"};
const COST_BASIS_LABELS={actual:"coste ejecutado",quote:"cotización",budget:"presupuesto"};
const sourceDate=(value)=>{const date=new Date(`${value}T00:00:00Z`);return Number.isNaN(date.valueOf())?String(value):new Intl.DateTimeFormat("es-ES",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}).format(date).replaceAll(".","");};
const uncertaintyLabel=(value,metric)=>({low:`Incertidumbre de ${metric} baja`,medium:`Incertidumbre de ${metric} media`,high:`Incertidumbre de ${metric} alta`,not_estimable:`${metric[0].toUpperCase()}${metric.slice(1)} no estimable`})[value]??`Incertidumbre de ${metric} no publicada`;
const provenanceSummary=(items,prefix)=>{const counts=items.reduce((result,item)=>{result[item.origin]=(result[item.origin]??0)+1;return result;},{}),parts=[["actual","registro empresarial real","registros empresariales reales"],["published","fuente pública publicada","fuentes públicas publicadas"],["synthetic","fixture sintético","fixtures sintéticos"]].flatMap(([key,one,many])=>counts[key]?[`${counts[key]} ${counts[key]===1?one:many}`]:[]);return parts.length?`${prefix}: ${parts.join(" · ")}`:`${prefix}: sin comparables suficientes`;};
const datesSummary=(items,prefix)=>{const dates=[...new Set(items.map((item)=>item.source_date).filter(Boolean))].sort();return dates.length?`${prefix}: ${dates.map(sourceDate).join(" · ")}; no implican actualización a hoy`:`${prefix}: no disponibles`;};
const scopeSummary=(items,key,prefix)=>{const scopes=[...new Set(items.flatMap((item)=>list(item[key])))];return scopes.length?`${prefix}: ${scopes.join(" · ")}`:`${prefix}: no indicado`;};
const costBasisSummary=(items,prefix="Bases de coste")=>{const counts=items.reduce((result,item)=>{const key=item.cost_basis??"unspecified";result[key]=(result[key]??0)+1;return result;},{}),parts=[["actual","coste ejecutado real"],["quote","cotización"],["budget","presupuesto"],["unspecified","base no indicada"]].flatMap(([key,label])=>counts[key]?[`${counts[key]} ${label}${counts[key]===1?"":"s"}`]:[]);return parts.length?`${prefix}: ${parts.join(" · ")}`:`${prefix}: no disponibles`;};
const PROVISIONAL_ASSUMPTIONS={
  provisional_bom:["BOM auto-revisada provisional","La geometría y las cantidades siguen siendo hipótesis revisadas por máquina; no se convierten en hechos confirmados del plano."],
  one_finished_item:["Un mueble terminado condicional","Cada escenario calcula un mueble terminado como condición económica, no como una ocurrencia física inferida del plano."],
  reference_family:["Condición de familia de referencia","El escenario solo aplica si el mueble pertenece a la familia del registro histórico citado."],
  reference_material:["Condición de material de referencia","El escenario adopta de forma condicional el material del registro histórico citado."],
  reference_finish:["Condición de acabado de referencia","El escenario adopta de forma condicional el acabado del registro histórico citado."],
  reference_economic_context:["Contexto económico de referencia","La moneda y los alcances proceden solo del registro citado; el resultado no es una cotización."],
};
const PROVISIONAL_MISSING={
  auto_review_status:"La auto-revisión no produjo un estado utilizable",
  provisional_bom_rows:"La BOM auto-revisada no contiene filas provisionales utilizables",
  provisional_quantity_evidence:"Las cantidades provisionales no tienen evidencia suficiente",
  provisional_geometry_evidence:"La geometría provisional no tiene evidencia suficiente",
  provisional_material_finish_evidence:"Material o acabado provisionales no tienen evidencia suficiente",
  heterogeneous_material_finish:"Los componentes provisionales mezclan materiales o acabados incompatibles",
};
const provisionalAssumption=(item)=>{const translated=PROVISIONAL_ASSUMPTIONS[item.code];return{...item,displayLabel:translated?.[0]??item.label,displayDetail:translated?.[1]??item.detail};};
const provisionalMissing=(code)=>({code,label:PROVISIONAL_MISSING[code]??String(code).replaceAll("_"," ")});

export function presentHistoricalRecord(record={}){
  const originLabel=ORIGIN_LABELS[record.origin]??"Procedencia no indicada",costBasisLabel=COST_BASIS_LABELS[record.cost_basis]??null;
  return{...record,originLabel,costBasisLabel,provenanceLabel:[originLabel,costBasisLabel].filter(Boolean).join(" · ")};
}

export function presentHistoryImport(raw = {}) {
  const accepted = Number(raw.accepted ?? raw.accepted_count ?? 0);
  const rejected = Number(raw.rejected ?? raw.rejected_count ?? 0);
  return {
    id: raw.import_id ?? raw.id ?? null,
    accepted,
    rejected,
    summary: `${accepted} registros aceptados · ${rejected} rechazados`,
    errors: list(raw.errors).map((error) => `Fila ${error.row ?? "?"}: ${error.error ?? error.message ?? error.code ?? "Error sin detalle"}`),
  };
}

export function presentHistoricalComparables(raw = {}) {
  const method = raw.retrieval_method ?? "attribute";
  const embeddingSpace=raw.embedding_space??null;
  return {
    method,
    methodLabel: method === "semantic" ? "Similitud semántica real" : "Atributos verificables",
    embeddingSpace,
    embeddingLabel: embeddingSpace ? `${embeddingSpace.model} · ${embeddingSpace.dimensions} dimensiones` : null,
    items: list(raw.comparables ?? raw.items).map((item) => ({
      ...presentHistoricalRecord(item.record),
      score:item.score,
      scoreComponents:item.score_components??{},
      missingFields:list(item.missing_fields),
      differences: list(item.differences),
    })),
  };
}

export function presentHistoricalEstimate(raw = {}) {
  const hours = raw.hours_range ?? raw.hours ?? {};
  const value = number(raw.manufacturing_hours ?? hours.value ?? raw.estimated_hours);
  const low = number(Array.isArray(hours)?hours[0]:(hours.low ?? hours.min));
  const high = number(Array.isArray(hours)?hours[1]:(hours.high ?? hours.max));
  const total = number(raw.cost_subtotal ?? raw.total_cost ?? raw.total);
  const provenance=list(raw.result_provenance),hasMetricFlags=provenance.some((item)=>typeof item.contributes_cost==="boolean"||typeof item.contributes_hours==="boolean"),costProvenance=hasMetricFlags?provenance.filter((item)=>item.contributes_cost):provenance,hoursProvenance=hasMetricFlags?provenance.filter((item)=>item.contributes_hours):provenance;
  const hoursLabel = value == null ? "Horas desconocidas" : `${decimal(value)} h${low != null && high != null ? ` · rango ${decimal(low)}–${decimal(high)} h` : ""}`;
  return {
    status: raw.status ?? (total == null ? "incomplete" : "complete"),
    provenanceLabel: provenanceSummary(provenance,"Base"),
    provenanceBasisLabel: costBasisSummary(provenance,"Bases económicas"),
    provenanceDateLabel: datesSummary(provenance,"Fechas declaradas por las fuentes"),
    costProvenanceLabel:provenanceSummary(costProvenance,"Base de coste"),
    hoursProvenanceLabel:provenanceSummary(hoursProvenance,"Base de horas"),
    costBasisLabel:costBasisSummary(costProvenance),
    hoursBasisLabel:scopeSummary(hoursProvenance,"hours_scope","Alcance de horas"),
    costScopeLabel:scopeSummary(costProvenance,"cost_scope","Alcance de coste"),
    costDateLabel:datesSummary(costProvenance,"Fechas de coste declaradas por las fuentes"),
    hoursDateLabel:datesSummary(hoursProvenance,"Fechas de horas declaradas por las fuentes"),
    hoursLabel,
    totalLabel: total == null ? "Total desconocido" : `${decimal(total)} ${raw.currency ?? "EUR"}`,
    formula: raw.formula ?? list(raw.contributors)[0]?.formula ?? "Fórmula no publicada",
    factors: list(raw.factors),
    uncertainty: raw.uncertainty ?? "not_estimable",
    uncertaintyLabel: ({low:"Incertidumbre baja",medium:"Incertidumbre media",high:"Incertidumbre alta",not_estimable:"No estimable"})[raw.uncertainty]??"Incertidumbre no publicada",
    costUncertainty:raw.cost_uncertainty??raw.uncertainty??"not_estimable",
    hoursUncertainty:raw.hours_uncertainty??raw.uncertainty??"not_estimable",
    costUncertaintyLabel:uncertaintyLabel(raw.cost_uncertainty??raw.uncertainty??"not_estimable","coste"),
    hoursUncertaintyLabel:uncertaintyLabel(raw.hours_uncertainty??raw.uncertainty??"not_estimable","horas"),
    missingData: list(raw.missing_data),
    lines: list(raw.lines ?? raw.contributors),
  };
}

export function presentProvisionalScenarios(raw={}){
  const rangeLabel=(value,unit)=>Array.isArray(value)&&value.length===2?`${decimal(value[0])}–${decimal(value[1])} ${unit}`:"Rango no estimable";
  const scenarios=list(raw.scenarios).map((item)=>{
    const condition=item.condition??{},provenance=list(item.result_provenance),source=provenance[0]??{},record=presentHistoricalRecord(source),currency=item.currency??condition.currency;
    return{
      ...item,
      labelText:"Escenario condicional provisional · no es una cotización",
      costLabel:number(item.cost_subtotal)==null?"Coste no estimable":`${decimal(number(item.cost_subtotal))} ${currency??"moneda desconocida"}`,
      hoursLabel:number(item.manufacturing_hours)==null?"Horas no estimables":`${decimal(number(item.manufacturing_hours))} h`,
      costRangeLabel:rangeLabel(item.cost_range,currency??"moneda desconocida"),
      hoursRangeLabel:rangeLabel(item.hours_range,"h"),
      costUncertaintyLabel:uncertaintyLabel(item.cost_uncertainty,"coste"),
      hoursUncertaintyLabel:uncertaintyLabel(item.hours_uncertainty,"horas"),
      conditionLabel:`1 mueble · material ${condition.material??"desconocido"} · acabado ${condition.finish??"desconocido"} · moneda ${currency??"desconocida"}`,
      scopeLabel:`Coste: ${list(condition.cost_scope).join(", ")||"sin alcance"} · Horas: ${list(condition.hours_scope).join(", ")||"sin alcance"}`,
      provenanceLabel:[record.provenanceLabel,source.source,source.source_date?sourceDate(source.source_date):null].filter(Boolean).join(" · "),
      assumptions:list(item.assumptions).map(provisionalAssumption),
      missingData:list(item.missing_data).map(provisionalMissing),
      contributors:list(item.contributors),
    };
  });
  return{...raw,statusLabel:raw.status==="provisional"?"Escenarios provisionales":"No estimable",labelText:"Estimaciones condicionales; no son cotizaciones ni hechos confirmados",assumptions:list(raw.assumptions).map(provisionalAssumption),missingData:list(raw.missing_data).map(provisionalMissing),scenarios};
}
