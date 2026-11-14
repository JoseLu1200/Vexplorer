export function formatSimilarityScore(value, locale="es-ES") {
  if(!Number.isFinite(value)) return "sin puntuación";
  return `${(value*100).toLocaleString(locale,{minimumFractionDigits:2,maximumFractionDigits:4})} % (${value.toLocaleString(locale,{minimumFractionDigits:4,maximumFractionDigits:6})}); no implica identidad`;
}

export function similarityScoreLabel(item,mode) {
  if(!Number.isFinite(item?.score)) return "";
  const kind=String(item.score_kind??"").toLowerCase();
  const metric=kind.includes("cosine")||kind.includes("semantic")||(!kind&&mode==="semantic")?"similitud coseno":"similitud geométrica";
  return `${metric} ${formatSimilarityScore(item.score)}`;
}

export function libraryCounts(raw={},items=[]) {
  return {
    designs:Number.isInteger(raw.design_count)?raw.design_count:items.length,
    records:Number.isInteger(raw.record_count)?raw.record_count:items.length,
    duplicates:Number.isInteger(raw.duplicate_record_count)?raw.duplicate_record_count:Math.max(0,(raw.record_count??items.length)-(raw.design_count??items.length)),
  };
}

export function presentPieceDifferences(differences) {
  const pieces=(Array.isArray(differences)?differences:[]).filter((item)=>/^(part_features\[\d+\]|components\.)/.test(item.field??""));
  return pieces.map((difference)=>{
    const field=difference.field??"",role=field.match(/^components\.([^.]+)/)?.[1],index=field.match(/^part_features\[(\d+)\]/)?.[1],leaf=field.split(".").at(-1),query=Number(difference.query_value),candidate=Number(difference.candidate_value),ratio=query>0&&candidate>0?Math.max(query,candidate)/Math.min(query,candidate):NaN,fieldLabel=({length_mm:"Largo",width_mm:"Ancho",thickness_mm:"Grosor",quantity:"Cantidad",material_tariff_id:"Material"})[leaf]??leaf??"Campo",unit=/_mm$/.test(leaf)?" mm":"",roleMatch=role?.match(/^(.+?)\[(\d+)\]$/),roleName=roleMatch?.[1]??role,roleIndex=roleMatch?Number(roleMatch[2])+1:null,humanRole=({side_support:"Soporte lateral",tabletop:"Tapa",leg:"Pata"})[roleName]??roleName;
    return {label:difference.label??(humanRole?`${humanRole}${roleIndex??""}`:null)??(index!=null?`Pieza ${Number(index)+1}`:"Pieza sin identificar"),fieldLabel,summary:difference.summary??`${difference.query_value??"desconocido"} ↔ ${difference.candidate_value??"desconocido"}${unit}`,ratioLabel:leaf==="thickness_mm"&&Number.isFinite(ratio)?`×${ratio.toLocaleString("es-ES",{maximumFractionDigits:3})}`:""};
  });
}

export function libraryEmptyMessage(recordCount) {
  return recordCount===0?"Biblioteca pública vacía: guarda una revisión de mobiliario real para iniciar las comparaciones. Los fixtures de demo no se publican.":"No hay diseños que alcancen el criterio seleccionado.";
}


