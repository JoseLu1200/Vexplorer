function xyz(value) {
  if (Array.isArray(value) && value.length >= 3) return value.slice(0, 3);
  if (value && [value.x, value.y, value.z].every(Number.isFinite)) return [value.x, value.y, value.z];
  return null;
}

const list=(value)=>Array.isArray(value)?value:[];
const fieldValue=(value)=>value&&typeof value==="object"?(value.value_mm??value.value??null):value;
const fieldLabel={length:"largo",width:"ancho",thickness:"grosor",quantity:"cantidad"};
const reviewStatusLabel={accepted:"aceptada",rejected:"rechazada",conflict:"en conflicto",abstained:"abstención",unreviewed:"sin revisar"};

function decisionMap(row){return new Map(list(row?.machineFieldReviews??row?.machine_field_reviews).map((item)=>[item.field,item]));}

export function generalCatalogScene(derived={}, {reviewerKind=null}={}){
  const source=derived.scene??{},rows=new Map(list(derived.bom).map((row)=>[row.componentId??row.component_id,row])),warnings=[...list(source.warnings)],objects=[];
  let cursor=0;
  list(source.items).forEach((item)=>{
    const componentId=item.component_id??item.componentId,row=rows.get(componentId)??{},decisions=decisionMap(row),machine=reviewerKind==="machine";
    const dimension=(name)=>{const value=Number(fieldValue(item[name])),decision=decisions.get(name),accepted=!machine||decision?.status==="accepted";return{value,accepted,decision};};
    const dimensions=[dimension("length"),dimension("width"),dimension("thickness")],invalid=dimensions.findIndex((entry)=>!entry.accepted||!Number.isFinite(entry.value)||entry.value<=0);
    if(invalid>=0){const name=["length","width","thickness"][invalid],entry=dimensions[invalid],detail=list(entry.decision?.checkSummaries??entry.decision?.check_summaries)[0],status=entry.decision?.status;warnings.push(`${componentId}: ${fieldLabel[name]} omitido${status?` (${reviewStatusLabel[status]??status})`:""}${detail?` · ${detail}`:""}; queda desconocido en el catálogo 3D.`);return;}
    const quantityDecision=decisions.get("quantity"),quantityAccepted=!machine||quantityDecision?.status==="accepted",occurrenceStatus=item.occurrence_status??item.occurrenceStatus,occurrenceIds=occurrenceStatus==="confirmed"?list(item.occurrence_ids??item.occurrenceIds):occurrenceStatus==="provisional"&&quantityAccepted?list(item.scenario_occurrence_ids??item.scenarioOccurrenceIds):[];
    if(!occurrenceIds.length){const detail=list(quantityDecision?.checkSummaries??quantityDecision?.check_summaries)[0],status=quantityDecision?.status;warnings.push(`${componentId}: sin ocurrencias físicas o provisionales autorizadas${status&&status!=="accepted"?`; cantidad ${reviewStatusLabel[status]??status}${detail?` · ${detail}`:""}`:""}.`);return;}
    const [length,width,thickness]=dimensions.map((entry)=>entry.value),gap=Math.max(50,thickness*3),evidenceIds=list(row.sourceEvidenceIds??row.source_evidence_ids);
    occurrenceIds.forEach((occurrenceId,index)=>{objects.push({piece_id:occurrenceId,proposal_id:componentId,occurrence_index:index+1,label:row.label??componentId,role:row.role??"unknown",position_mm:{x:cursor,y:0,z:0},dimensions_mm:{x:length,y:width,z:thickness},evidence_ids:evidenceIds,placement_basis:"catalogue_visualisation_not_physical",placement_status:"hypothesis",placement_constraint_ids:[]});cursor+=length+gap;});
  });
  return{state:objects.length?"ready":"unavailable",coordinate_system:"catalogue_schematic_mm",objects,warnings,assumptions:["Catálogo de piezas separadas para visualización; no representa un montaje físico ni posiciones verificadas."],collision_status:"not_evaluated"};
}

export function sceneLoadPlan({runId,resultRevision,generalWorkspace,generalDerived}={}){
  if(generalWorkspace?.isGeneral){
    const proposalRevision=generalWorkspace.proposalRevision,reviewRevision=generalWorkspace.reviewRevision,identity=`${runId}:general:${proposalRevision??"pending"}:${reviewRevision??"pending"}`,exact=generalDerived?.proposalRevision===proposalRevision&&generalDerived?.reviewRevision===reviewRevision;
    const scene=exact?generalCatalogScene(generalDerived,{reviewerKind:generalWorkspace.reviewerKind}):{state:"unavailable",objects:[],warnings:["La escena derivada no corresponde al snapshot general actual."],assumptions:["Catálogo de piezas separadas; no representa un montaje físico."],collision_status:"not_evaluated"};
    return{kind:"general",identity,fetchLegacy:false,scene};
  }
  return{kind:"legacy",identity:`${runId}:legacy:${resultRevision}`,fetchLegacy:true,scene:null};
}

export function generalSceneSelection(workspace,item){return list(workspace?.components).find((component)=>component.id===item?.proposalId)??null;}

export function normaliseScene(raw = {}) {
  const warnings = [...(raw.warnings ?? [])];
  const objects = (raw.objects ?? []).flatMap((item, index) => {
    const position = xyz(item.position_mm);
    const dimensions = xyz(item.dimensions_mm);
    if (!position || !dimensions || dimensions.some((value) => value <= 0)) return [];
    const pieceId = item.piece_id ?? item.proposal_id ?? `object-${index}`;
    return [{
      key: `${pieceId}:${item.occurrence_index ?? index}`,
      pieceId, proposalId: item.proposal_id, role: item.role, label: item.label ?? item.role ?? pieceId,
      position, dimensions, evidenceIds: [...(item.evidence_ids ?? [])], contourIds: [...(item.source_contour_ids ?? item.contour_ids ?? [])],
      placementBasis: item.placement_basis ?? null, partObservationId: item.part_observation_id ?? null,
      placementStatus: item.placement_status ?? "human_selected", placementConstraintIds: [...(item.placement_constraint_ids ?? [])],
    }];
  });
  if (objects.length < (raw.objects ?? []).length && !warnings.some((item) => /dimension|medida|grosor/i.test(item))) warnings.push("No se representan objetos con posición o medidas incompletas.");
  return { state: raw.state ?? "unavailable", coordinateSystem: raw.coordinate_system, objects, warnings, assumptions: raw.assumptions ?? [], collisionStatus: raw.collision_status ?? "not_evaluated" };
}

export function sceneMeshCenter(item) {
  return item.position.map((value, index) => value + item.dimensions[index] / 2);
}

export function cameraZoomPosition(position, target, factor) {
  return position.map((value, index) => target[index] + (value - target[index]) * factor);
}
