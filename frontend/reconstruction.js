import { createApiClient } from './api/client.js';
const api=createApiClient(),$=(id)=>document.getElementById(id),params=new URLSearchParams(location.search);
let viewer,jobId=params.get('job'),active=true;
const endpoint=(suffix='')=>api.resourceUrl(`/api/v1/reconstruction/${encodeURIComponent(jobId)}${suffix}`);
async function request(url,init){const r=await fetch(url,init);const b=await r.json();if(!r.ok)throw new Error(typeof b.detail==='string'?b.detail:'No se pudo completar la solicitud');return b;}
function lines(id,values){$(id).replaceChildren(...values.map(v=>{const li=document.createElement('li');li.textContent=v;return li;}));}
function link(name,path){const a=document.createElement('a');a.textContent=name;a.href=endpoint(`/artifacts/${path}`);a.setAttribute('download','');return a;}
async function display(state){
  $('source').src=endpoint('/source.png');$('source').hidden=false;
  $('provenance').textContent=`Entrada ${state.run_id} · ${state.source_refs?.length??0} vistas fuente · ${state.unit==='mm'?'Cotas métricas disponibles':'Sin escala absoluta'}`;
  const outcome=state.outcome;if(!outcome){
    if(state.baseline){$('assessment').hidden=false;lines('assumptions',state.baseline.assumptions);lines('missing',state.baseline.missing_information);lines('functional',state.baseline.functional_notes);$('geometry').textContent=`Primera propuesta conservada: ${state.baseline.components.length} piezas. La ejecución falló; esta propuesta parcial no tiene revisión completa ni artefactos publicados.`;const a=document.createElement('a');a.href=endpoint();a.textContent='Descargar estado y propuesta parcial JSON';a.download='partial-proposal.json';$('assessment').append(a);}
    return;
  }
  const proposal=outcome.proposal,checks=outcome.checks;
  $('assessment').hidden=false;$('parts').hidden=!proposal.components.length;
  lines('assumptions',proposal.assumptions);lines('missing',proposal.missing_information);lines('functional',proposal.functional_notes);
  $('geometry').textContent=`${checks.overlaps.length} solapes · ${checks.floating_ids.length} piezas sin conexión al suelo · ${checks.below_ground_ids.length} piezas bajo el suelo. Uso propuesto: ${proposal.intended_use}`;
  $('preview').src=endpoint('/artifacts/view-00.png');$('preview').hidden=false;
  if(proposal.components.length&&proposal.unit==='mm'){
    try{const [{SceneViewer},scene]=await Promise.all([import('./components/SceneViewer.js'),request(endpoint('/artifacts/scene.json'))]);
      viewer?.dispose();viewer=new SceneViewer($('viewer'),{onSelect:item=>{const p=proposal.components.find(p=>p.id===item.pieceId);$('selected').textContent=p?`${p.label}: ${p.size_mm.join(' × ')} mm. ${p.assumptions.join(' ')}`:'';viewer.select(item.pieceId);}});viewer.setScene(scene);$('exploded').disabled=false;$('preview').hidden=true;
    }catch{$('selected').textContent='Vista 3D no disponible en este navegador. Se muestra el render de la propuesta.';}
  }
  $('parts-body').replaceChildren(...proposal.components.map(p=>{const tr=document.createElement('tr');for(const value of [p.label,`${p.size_mm.join(' × ')} ${proposal.unit}`,1]){const td=document.createElement('td');td.textContent=value;tr.append(td);}const td=document.createElement('td');td.append(link('SVG',`parts/${p.id}.svg`));if(state.artifacts.includes(`parts/${p.id}.dxf`))td.append(link('DXF',`parts/${p.id}.dxf`));tr.append(td);return tr;}));
  $('downloads').replaceChildren(...[['BOM CSV','bom.csv'],['Propuesta JSON','proposal.json'],['Montaje GLB','assembly.glb'],['Despiece visual','exploded.png']].filter(([,p])=>state.artifacts.includes(p)).map(([n,p])=>link(n,p)));
}
async function poll(){
  $('generate-button').disabled=true;
  try{while(active){const state=await request(endpoint());const labels={queued:'Propuesta en cola…',running:'Interpretando el plano y revisando el montaje…',needs_review:'Propuesta generada. Revisa las hipótesis y los datos pendientes.',insufficient_evidence:'No hay información suficiente para proponer una construcción.',unsupported:'La geometría excede el tipo de construcción soportado.',interrupted:'La ejecución se interrumpió. Puedes volver a generarla.',failed:'No se pudo generar la propuesta.'};$('status').textContent=labels[state.status]??state.status;if(!['queued','running'].includes(state.status)){await display(state);break;}await new Promise(r=>setTimeout(r,1500));}}
  catch(e){$('status').textContent=e.message;}finally{$('generate-button').disabled=!params.get('run');}
}
$('generate').addEventListener('submit',async e=>{e.preventDefault();if(!params.get('run'))return;$('generate-button').disabled=true;try{const state=await request(api.resourceUrl(`/api/v1/runs/${encodeURIComponent(params.get('run'))}/reconstruction`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({intended_use:$('purpose').value})});jobId=state.job_id;params.set('job',jobId);history.replaceState(null,'',`?${params}`);await poll();}catch(error){$('status').textContent=error.message;$('generate-button').disabled=false;}});
$('exploded').addEventListener('change',e=>viewer?.setExploded(e.target.checked));
window.addEventListener('pagehide',()=>{active=false;viewer?.dispose();});
if(jobId)poll();else if(!params.get('run')){$('status').textContent='Abre un plano de mueble general en Vexplorer y selecciona Construcción propuesta.';$('generate-button').disabled=true;}
