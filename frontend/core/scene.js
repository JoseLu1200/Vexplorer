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

const IDENTITY_ROTATION = [1, 0, 0, 0, 1, 0, 0, 0, 1];
const SIGNED_AXIS = {
  "+x": [1, 0, 0], "-x": [-1, 0, 0],
  "+y": [0, 1, 0], "-y": [0, -1, 0],
  "+z": [0, 0, 1], "-z": [0, 0, -1],
};

function orientationTransform(orientation) {
  if (orientation == null) return { rotationMatrix: [...IDENTITY_ROTATION], worldOrder: [0, 1, 2] };
  const axes = [orientation.length_axis, orientation.width_axis, orientation.thickness_axis].map((axis) => SIGNED_AXIS[axis]);
  if (axes.some((axis) => !axis)) return null;
  const worldOrder = axes.map((axis) => axis.findIndex((value) => value !== 0));
  if (new Set(worldOrder).size !== 3) return null;
  const [a, b, c] = axes;
  const determinant = a[0] * (b[1] * c[2] - b[2] * c[1]) - b[0] * (a[1] * c[2] - a[2] * c[1]) + c[0] * (a[1] * b[2] - a[2] * b[1]);
  if (determinant !== 1) return null;
  return {
    rotationMatrix: [a[0], b[0], c[0], a[1], b[1], c[1], a[2], b[2], c[2]],
    worldOrder,
  };
}

export function normaliseScene(raw = {}) {
  const warnings = [...(raw.warnings ?? [])];
  const keys = new Set();
  const objects = (raw.objects ?? []).flatMap((item, index) => {
    const position = xyz(item.position_mm);
    const dimensions = xyz(item.dimensions_mm);
    const surface=item.render_kind==="surface";
    if (!position || !dimensions || dimensions.some((value,index) => value <= 0 && !(surface&&index===2&&value===0))) return [];
    const pieceId = item.piece_id ?? item.proposal_id ?? `object-${index}`;
    const key = item.occurrence_id ?? `${pieceId}:${item.occurrence_index ?? index}`;
    if (keys.has(key)) { warnings.push(`Identidad de ocurrencia duplicada: ${key}.`); return []; }
    const transform = orientationTransform(item.orientation);
    if (!transform) { warnings.push(`Transformación ortogonal inválida para ${key}.`); return []; }
    keys.add(key);
    const validatedWorldDimensions=xyz(item.world_dimensions_mm??item.size_mm);
    const worldDimensions = validatedWorldDimensions?.every((value)=>value>0)
      ? validatedWorldDimensions
      : [0, 1, 2].map((worldAxis) => dimensions[transform.worldOrder.indexOf(worldAxis)]);
    return [{
      key,
      pieceId, proposalId: item.proposal_id, role: item.role, label: item.label ?? item.role ?? pieceId,
      position, dimensions, worldDimensions, rotationMatrix: transform.rotationMatrix, orientation: item.orientation ?? null,
      occurrenceId: item.occurrence_id ?? null, occurrenceIndex: item.occurrence_index ?? null,
      occurrenceIds: [...(item.occurrence_ids ?? [])], scenarioOccurrenceIds: [...(item.scenario_occurrence_ids ?? [])],
      renderKind:surface?"surface":"solid", evidenceIds: [...(item.evidence_ids ?? [])], contourIds: [...(item.source_contour_ids ?? item.contour_ids ?? [])],
      placementBasis: item.placement_basis ?? null, partObservationId: item.part_observation_id ?? null,
      placementStatus: item.placement_status ?? "human_selected", placementConstraintIds: [...(item.placement_constraint_ids ?? [])],
    }];
  });
  if (objects.length < (raw.objects ?? []).length && !warnings.some((item) => /dimension|medida|grosor/i.test(item))) warnings.push("No se representan objetos con posición o medidas incompletas.");
  return { state: raw.state ?? raw.status ?? "unavailable", coordinateSystem: raw.coordinate_system, objects, warnings, assumptions: raw.assumptions ?? [], collisionStatus: raw.collision_status ?? "not_evaluated" };
}

export function sceneMeshCenter(item) {
  return item.position.map((value, index) => value + (item.worldDimensions ?? item.dimensions)[index] / 2);
}

export function sceneMeshTransform(item) {
  return { center: sceneMeshCenter(item), rotationMatrix: [...(item.rotationMatrix ?? IDENTITY_ROTATION)] };
}

const DISPLAY_UP_ROTATION={
  y:IDENTITY_ROTATION,
  z:[1,0,0,0,0,1,0,-1,0],
  x:[0,-1,0,1,0,0,0,0,1],
};

function multiplyRotation(left,right){
  return [0,1,2].flatMap((row)=>[0,1,2].map((column)=>[0,1,2].reduce((sum,index)=>sum+left[row*3+index]*right[index*3+column],0)));
}

export function sceneForDisplayUp(model, upAxis="y") {
  const globalRotation=DISPLAY_UP_ROTATION[upAxis]??DISPLAY_UP_ROTATION.y;
  if(globalRotation===IDENTITY_ROTATION)return model;
  const objects=(model.objects??[]).map((item)=>{
    const sourceSize=item.worldDimensions??item.dimensions,position=[0,1,2].map((displayAxis)=>{
      const row=globalRotation.slice(displayAxis*3,displayAxis*3+3),sourceAxis=row.findIndex((value)=>value!==0),sign=row[sourceAxis];
      return sign>0?item.position[sourceAxis]:-(item.position[sourceAxis]+sourceSize[sourceAxis]);
    }),worldDimensions=[0,1,2].map((displayAxis)=>{
      const row=globalRotation.slice(displayAxis*3,displayAxis*3+3),sourceAxis=row.findIndex((value)=>value!==0);return sourceSize[sourceAxis];
    });
    return {...item,position,worldDimensions,rotationMatrix:multiplyRotation(globalRotation,item.rotationMatrix??IDENTITY_ROTATION)};
  });
  return {...model,objects,displayUpAxis:upAxis};
}

export function normaliseGeneralAssemblyResponse(raw = null) {
  const wrapped=raw&&("current" in raw||Array.isArray(raw.accepted_alternatives)||Array.isArray(raw.acceptedAlternatives));
  const current=wrapped?raw.current??null:raw;
  const acceptedAlternatives=wrapped
    ? [...(raw.accepted_alternatives??raw.acceptedAlternatives??[])]
    : current?.report?.status==="accepted"?[current]:[];
  const identities=new Set(acceptedAlternatives.map((attempt)=>attempt?.candidate?.alternative_id??`assembly:${attempt?.assembly_revision}`).filter(Boolean));
  return {current,acceptedAlternatives,ambiguous:Boolean(wrapped&&raw.ambiguous)||identities.size>1,status:wrapped?raw.status??null:current?.report?.status??null};
}

export function generalAssemblyScene(value, fallback = {}) {
  const {current}=normaliseGeneralAssemblyResponse(value);
  return current?.report?.status==="accepted"&&current.report.scene?current.report.scene:fallback;
}

export function generalAssemblyDiagnosticScene(value, bomScene = {}) {
  const {current}=normaliseGeneralAssemblyResponse(value),report=current?.report,placements=report?.placements??[];
  if(!["rejected","incomplete"].includes(report?.status)||!current?.candidate||!placements.length)return null;
  const components=new Map((bomScene.items??[]).map((item)=>[item.component_id,item]));
  const items=placements.map((placement)=>{
    const component=components.get(placement.component_id),dimensions=[component?.length?.value_mm,component?.width?.value_mm,component?.thickness?.value_mm];
    if(!component||!dimensions.every((number)=>Number.isFinite(number)&&number>0))return null;
    const confirmed=(component.occurrence_ids??[]).includes(placement.occurrence_id),provisional=(component.scenario_occurrence_ids??[]).includes(placement.occurrence_id)||String(placement.occurrence_id).startsWith("provisional:");
    return {id:`diagnostic:${placement.occurrence_id}`,component_id:placement.component_id,occurrence_id:placement.occurrence_id,occurrence_index:placement.occurrence_index,
      occurrence_ids:confirmed?[placement.occurrence_id]:[],scenario_occurrence_ids:provisional?[placement.occurrence_id]:[],occurrence_status:confirmed?"confirmed":provisional?"provisional":"unknown",
      length:component.length,width:component.width,thickness:component.thickness,position_mm:placement.position_mm,size_mm:placement.size_mm,orientation:placement.orientation,
      source_refs:[...(placement.source_refs??[])],status:"placed_hypothesis"};
  });
  if(items.some((item)=>item===null))return null;
  return {status:"mounted_hypothesis",items,warnings:["Candidato rechazado · no validado · solo inspección; no usar para fabricar."],diagnostic_rejected:true,diagnostic_issues:[...(report.issues??[])],assembly_revision:current.assembly_revision};
}

const ASSEMBLY_ISSUE_LABELS={
  aabb_penetration:"Interferencias entre piezas",
  contour_box_fit_residual:"Contornos no rectangulares",
  shared_evidence_identity:"Evidencia reutilizada entre piezas",
  shared_contour_identity:"Contornos reutilizados entre piezas",
  missing_occurrence:"Piezas sin colocación",
  unknown_occurrence:"Colocaciones de piezas desconocidas",
  occurrence_identity_mismatch:"Identidades de pieza incoherentes",
  stale_revision:"Montaje basado en una revisión obsoleta",
  unknown_frame:"Marcos de proyección desconocidos",
  unknown_contour:"Contornos de origen desconocidos",
  unknown_evidence:"Evidencia de origen desconocida",
  frame_contour_mismatch:"Proyecciones incompatibles con su vista",
  evidence_contour_mismatch:"Evidencia incompatible con el contorno",
  incomplete_axis_coverage:"Cobertura espacial incompleta",
  reprojection_mismatch:"Proyecciones incoherentes entre vistas",
  dimension_mismatch:"Dimensiones incompatibles con el despiece",
  assembly_metric_scale_required:"Falta una escala métrica confirmada",
  assembly_reviewed_dimensions_required:"Faltan dimensiones revisadas",
  assembly_confirmed_quantity_required:"Faltan cantidades confirmadas",
  assembly_unsupported_component_kind:"Hay componentes no compatibles con este montaje",
};

export function groupAssemblyIssues(issues = []) {
  const groups=new Map();
  issues.forEach((raw,index)=>{
    const code=raw?.code??"assembly_issue",entry={code,message:raw?.message??code,occurrenceIds:[...(raw?.occurrence_ids??[])],sourceRefs:[...(raw?.source_refs??[])],index};
    if(!groups.has(code))groups.set(code,{code,label:ASSEMBLY_ISSUE_LABELS[code]??`Incidencia técnica: ${code}`,count:0,occurrenceIds:[],sourceRefs:[],entries:[]});
    const group=groups.get(code);group.count+=1;group.entries.push(entry);group.occurrenceIds.push(...entry.occurrenceIds);group.sourceRefs.push(...entry.sourceRefs);
  });
  return [...groups.values()].map((group)=>({...group,occurrenceIds:[...new Set(group.occurrenceIds)],sourceRefs:[...new Set(group.sourceRefs)]}));
}

export function presentGeneralAssembly(value = null) {
  const bundle=normaliseGeneralAssemblyResponse(value),attempt=bundle.current;
  const status = attempt?.report?.status ?? "unavailable";
  const placements = attempt?.report?.placements?.length ?? 0;
  const revision = attempt?.assembly_revision;
  const issueGroups=groupAssemblyIssues(attempt?.report?.issues??[]),warnings=issueGroups.map((group)=>`${group.label} (${group.count})`);
  if(bundle.ambiguous)warnings.unshift("Ambigüedad de montaje sin resolver: se conservan varias alternativas aceptadas.");
  const alternative=attempt?.candidate?.alternative_id;
  const alternatives=bundle.acceptedAlternatives.length?` · ${bundle.acceptedAlternatives.length} ${bundle.acceptedAlternatives.length===1?"alternativa aceptada":"alternativas aceptadas"}`:"";
  if (status === "accepted") return { label: "Montaje validado · hipótesis", detail: `${placements} instancias colocadas · revisión ${revision}${alternative?` · alternativa ${alternative} (actual)`:""}${alternatives}`, warnings, issueGroups, canRetry: false, ...bundle };
  if (status === "rejected") return { label: "Montaje rechazado", detail: `Revisión ${revision} · las colocaciones rechazadas no se muestran${alternatives}`, warnings, issueGroups, canRetry: true, ...bundle };
  if (status === "incomplete") return { label: "Montaje incompleto", detail: `Revisión ${revision} · sin colocaciones aceptadas${alternatives}`, warnings, issueGroups, canRetry: true, ...bundle };
  return { label: "Montaje no disponible", detail: `La BOM sigue disponible; consultar el 3D no inicia ningún modelo.${alternatives}`, warnings, issueGroups, canRetry: true, ...bundle };
}

export function generalSceneForViewer(scene = {}, draftComponents = []) {
  const provisional = !scene.items && draftComponents.length > 0;
  if (provisional) scene = {items: draftComponents.map((component) => ({
    component_id: component.id,
    ...Object.fromEntries(["length", "width", "thickness"].map((key) => [key, {value_mm: component.dimensions?.[key]?.value}])),
  }))};
  const items=scene.items??[], objects=[];
  const mounted=scene.status==="mounted_hypothesis"||items.some((item)=>item.status==="placed_hypothesis");
  if(mounted){
    items.forEach((item,index)=>objects.push({
      piece_id:item.component_id,proposal_id:item.component_id,label:item.label??item.component_id,
      occurrence_id:item.occurrence_id??null,occurrence_index:item.occurrence_index??index,
      occurrence_ids:item.occurrence_ids??[],scenario_occurrence_ids:item.scenario_occurrence_ids??[],
      dimensions_mm:{x:item.length?.value_mm,y:item.width?.value_mm,z:item.thickness?.value_mm},
      world_dimensions_mm:item.size_mm,position_mm:item.position_mm,orientation:item.orientation,
      placement_basis:item.placement_basis??"validated_general_assembly",placement_status:item.status??"placed_hypothesis",
      evidence_ids:item.evidence_ids??item.source_evidence_ids??[],source_contour_ids:item.source_contour_ids??[],
    }));
    return {state:"mounted_hypothesis",objects,collision_status:scene.collision_status??"not_evaluated",display_layout:false,
      warnings:[...(scene.warnings??[])], assumptions:[...(scene.assumptions??["Montaje por ocurrencia validado geométricamente; sigue siendo una hipótesis revisable."])]};
  }
  const columns=Math.max(1,Math.ceil(Math.sqrt(items.length)));
  const known=items.filter((item)=>[item.length?.value_mm,item.width?.value_mm].every((value)=>Number.isFinite(value)&&value>0));
  const cell=Math.max(1,...known.flatMap((item)=>[item.length.value_mm,item.width.value_mm]))*1.15;
  known.forEach((item,index)=>{
    const thickness=item.thickness?.value_mm, solid=Number.isFinite(thickness)&&thickness>0;
    objects.push({piece_id:item.component_id,proposal_id:item.component_id,label:item.component_id,
      dimensions_mm:{x:item.length.value_mm,y:item.width.value_mm,z:solid?thickness:0},
      position_mm:{x:(index%columns)*cell,y:Math.floor(index/columns)*cell,z:0},
      render_kind:solid?"solid":"surface",placement_basis:"display_layout_not_assembly",placement_status:"hypothesis"});
  });
  const missing=items.length-known.length;
  return {state:objects.length?"ready":"unavailable",objects,collision_status:"not_applicable",display_layout:true,
    warnings:[...(scene.warnings??[]), ...(provisional?["Vista provisional de la propuesta: revisión pendiente."]:[]), ...(missing?[`${missing} componentes sin largo o ancho suficiente para representarlos.`]:[])],
    assumptions:["Una representación por tipo de componente; las cantidades están en la tabla.",
      "Distribución para inspección visual, no posiciones de montaje ni uniones inferidas.",
      "Las superficies sin volumen conservan el grosor desconocido; no se ha rellenado con un valor supuesto."]};
}

export function cameraZoomPosition(position, target, factor) {
  return position.map((value, index) => target[index] + (value - target[index]) * factor);
}
