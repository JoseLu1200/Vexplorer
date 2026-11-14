import {filterPoints, mapCoordinates, createRequestGate, overlap, counterpart} from './core/explorer.js';

const $ = id => document.getElementById(id);
const apiRoot = new URL('./api/v1/semantic-explorer/', document.baseURI);
const colors = ['#4667c9','#6e8750','#b17940','#8d6aa5','#447c83','#a55d66','#6d7396','#8b8560'];
const state = {spaces:[],snapshot:null,selected:null,neighbors:[],searchReady:false,reviewAvailable:false,zoom:1,pan:[0,0],comparison:null};
const loadGate = createRequestGate(), selectGate = createRequestGate(), compareGate = createRequestGate();
const node = (tag, text, className) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;};
function message(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
async function api(path,{params,body}={}){
  const url=new URL(path,apiRoot);if(params)url.search=new URLSearchParams(params);
  const response=await fetch(url,{credentials:'same-origin',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
  const value=await response.json();if(!response.ok)throw new Error(`${value.error?.message??'Solicitud no disponible'} (${value.error?.code??response.status})`);return value.data;
}
function spaceTitle(s){return `${s.space.model.split('/').at(-1)} · ${s.space.mode} · ${s.space.dimensions}d · ${s.id.startsWith('corpus:')?s.id.slice(7):s.space.descriptor_version}`;}
function requestFor(point=state.selected){return {space:state.snapshot.space_key,snapshot_id:state.snapshot.snapshot_id,member_id:point.id};}
function imageUrl(point){const url=new URL('image',apiRoot);url.search=new URLSearchParams(requestFor(point));return url;}
function categoryColor(category){const categories=[...new Set(state.snapshot?.points.map(p=>p.category??'Sin categoría')??[])].sort();return colors[categories.indexOf(category??'Sin categoría')%colors.length];}
function visiblePoints(){return filterPoints(state.snapshot?.points??[],$('filter').value,$('category').value);}
function option(value,label){const el=node('option',label);el.value=value;return el;}
function clearSnapshot(){
  state.snapshot=null;state.selected=null;state.neighbors=[];state.searchReady=false;state.comparison=null;state.zoom=1;state.pan=[0,0];
  $('export').disabled=true;$('compare-button').disabled=true;
  $('comparison-result').replaceChildren(node('p','Selecciona un plano y una segunda representación.','empty'));
  $('neighbors').replaceChildren(node('p','Selecciona un plano para recuperar sus vecinos.','empty'));
  $('space-info').textContent='Cada modelo conserva su propio espacio.';$('projection-info').textContent='Proyección pendiente';$('snapshot-label').textContent='Sin snapshot';
  renderCatalog();renderMap();
}

async function loadSpaces(){
  const ticket=loadGate.next();selectGate.next();compareGate.next();message('Consultando catálogos y revisiones…');
  clearSnapshot();$('detail').replaceChildren(node('p','Consultando catálogos…','empty'));$('space').disabled=true;$('reload').disabled=true;
  try{
    const data=await api('spaces');if(!loadGate.current(ticket))return;
    state.spaces=data.spaces;state.reviewAvailable=data.review.available;
    const previous=$('space').value;
    $('space').replaceChildren(...data.spaces.map(s=>option(s.id,spaceTitle(s))));
    $('space').disabled=!data.spaces.length;
    if(data.spaces.some(s=>s.id===previous))$('space').value=previous;
    if(!data.spaces.length){state.snapshot=null;state.selected=null;state.neighbors=[];renderCatalog();renderMap();$('detail').replaceChildren(node('p','Guarda una revisión con embeddings en Biblioteca o publica un corpus con el CLI.','empty'));message(data.errors.length?'Hay un corpus inválido. Revisa los artefactos antes de activarlo.':'No hay embeddings vigentes. El mapa aparecerá al publicar un espacio.',Boolean(data.errors.length));return;}
    await loadSnapshot();
    if(data.errors.length)message('Algunos corpus no se pudieron validar y están excluidos del selector.',true);
  }catch(error){if(loadGate.current(ticket))message(error.message,true);}
  finally{if(loadGate.current(ticket))$('reload').disabled=false;}
}

async function loadSnapshot(){
  const ticket=selectGate.next();compareGate.next();clearSnapshot();
  $('neighbors').replaceChildren(node('p','Selecciona un plano para recuperar sus vecinos.','empty'));
  $('detail').replaceChildren(node('p','Cargando el mapa…','empty'));$('export').disabled=true;$('compare-button').disabled=true;
  message('Preparando la proyección del snapshot…');
  try{
    const snapshot=await api('snapshot',{params:{space:$('space').value}});if(!selectGate.current(ticket))return;
    state.snapshot=snapshot;$('filter').value='';
    $('category').replaceChildren(option('','Todas las categorías'),...[...new Set(snapshot.points.map(p=>p.category).filter(Boolean))].sort().map(x=>option(x,x)));
    $('compare-space').replaceChildren(option('','Elige otro espacio'),...state.spaces.filter(s=>s.id!==snapshot.space_key).map(s=>option(s.id,spaceTitle(s))));
    $('comparison-result').replaceChildren(node('p','Selecciona un plano y una segunda representación.','empty'));
    $('space-info').textContent=`${snapshot.space.mode} · ${snapshot.space.dimensions} dimensiones · revisión ${snapshot.space.revision.slice(0,12)}`;
    $('projection-info').textContent=`${(100*snapshot.projection.explained_variance_ratio.reduce((a,b)=>a+b,0)).toFixed(1)} % de varianza en 2D`;
    $('snapshot-label').textContent=`Snapshot ${snapshot.snapshot_id.slice(0,12)}`;
    $('detail').replaceChildren(node('p','Selecciona un punto o un plano de la lista.','empty'));
    renderCatalog();renderMap();message(`${snapshot.points.length} planos · ${snapshot.synthetic?'incluye planos sintéticos':'procedencia registrada'} · vecinos en el espacio original`);
  }catch(error){if(selectGate.current(ticket)){state.snapshot=null;renderCatalog();renderMap();message(error.message,true);}}
}

function renderCatalog(){
  const points=visiblePoints();$('count').textContent=`${points.length} / ${state.snapshot?.points.length??0}`;
  $('point-list').replaceChildren(...points.map(p=>{const button=node('button',undefined,'point-row');button.type='button';button.setAttribute('aria-pressed',String(state.selected?.id===p.id));const dot=node('span',undefined,'dot');dot.style.setProperty('--dot',categoryColor(p.category));dot.setAttribute('aria-hidden','true');button.append(dot,node('span',p.label));button.title=`${p.label} · ${p.category??'Sin categoría'}`;button.addEventListener('click',()=>selectPoint(p));return button;}));
  if(!points.length)$('point-list').append(node('p','No hay planos que coincidan con este filtro.','empty'));
}
function svg(tag,attrs={}){const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,String(v));return el;}
function renderMap(){
  const all=mapCoordinates(state.snapshot?.points??[]),visible=new Set(visiblePoints().map(p=>p.id)),near=new Set(state.neighbors.map(p=>p.id));
  const plot=$('plot');plot.replaceChildren();plot.setAttribute('transform',`translate(${state.pan[0]} ${state.pan[1]}) translate(400 260) scale(${state.zoom}) translate(-400 -260)`);
  const selected=all.find(p=>p.id===state.selected?.id);
  if(selected)for(const p of all.filter(p=>near.has(p.id)&&visible.has(p.id))){plot.append(svg('line',{x1:selected.position[0],y1:selected.position[1],x2:p.position[0],y2:p.position[1],class:'neighbor-edge'}));}
  const points=all.filter(p=>visible.has(p.id));
  points.forEach((p,index)=>{const circle=svg('circle',{cx:p.position[0],cy:p.position[1],r:state.selected?.id===p.id?7:near.has(p.id)?6:4.5,fill:categoryColor(p.category),class:`map-point${state.selected?.id===p.id?' selected':''}${near.has(p.id)?' neighbor':''}`,tabindex:(state.selected?.id===p.id||(!state.selected&&index===0))?0:-1,role:'button','aria-label':`${p.label}, ${p.category??'sin categoría'}`,'aria-pressed':String(state.selected?.id===p.id)});const title=svg('title');title.textContent=`${p.label} · ${p.category??'Sin categoría'}`;circle.append(title);circle.addEventListener('click',()=>selectPoint(p));circle.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){event.preventDefault();selectPoint(p);}else if(['ArrowRight','ArrowDown','ArrowLeft','ArrowUp'].includes(event.key)){event.preventDefault();const circles=[...plot.querySelectorAll('circle')];const offset=['ArrowRight','ArrowDown'].includes(event.key)?1:-1;circles[(index+offset+circles.length)%circles.length]?.focus();}});plot.append(circle);});
  $('map-empty').hidden=Boolean(all.length);
  $('legend').replaceChildren(...[...new Set(points.map(p=>p.category??'Sin categoría'))].sort().map(category=>{const el=node('span');const dot=node('i',undefined,'dot');dot.style.setProperty('--dot',categoryColor(category));el.append(dot,document.createTextNode(category));return el;}));
}

function detail(point){
  const root=$('detail');root.replaceChildren();
  if(point.has_image){const img=node('img');img.src=imageUrl(point);img.alt=`Render geométrico de ${point.label}`;img.className='preview';root.append(img);}
  root.append(node('h3',point.label,'item-title'),node('p',point.id,'item-id'),node('span',`${point.category??'Sin categoría'} · ${point.category_origin==='editorial_proxy'?'etiqueta editorial':point.category_origin==='reviewed'?'revisada':'sin confirmación'}`,'tag'));
  if(point.classification){const c=point.classification;const box=node('div',undefined,'classification');box.append(node('strong',`Propuesta: ${c.label}`),node('p',`${c.method} · score ${c.score.toFixed(3)} · no calibrado`),node('p','La etiqueta no modifica el ranking ni confirma una familia.'));root.append(box);}
  const attributes=node('dl',undefined,'attributes');for(const[key,value]of Object.entries(point.attributes??{})){const row=node('div');row.append(node('dt',key),node('dd',value??'Desconocido'));attributes.append(row);}root.append(attributes);
  const actions=node('div',undefined,'detail-actions');
  if(point.run_id){const link=node('a','Abrir ejecución y presupuesto');const url=new URL('./',document.baseURI);url.search=new URLSearchParams({run:point.run_id});link.href=url;actions.append(link);root.append(node('p',`Revisión ${point.result_revision} · los importes se calculan en el flujo económico.`, 'caption'));}
  const review=node('button','Pedir segunda opinión · Jev');review.disabled=!state.reviewAvailable||!point.has_image;review.title=review.disabled?'Requiere imagen, clave y presupuesto Jev configurados en servidor.':'Consume un intento del presupuesto de la instancia; reutiliza respuestas idénticas.';review.addEventListener('click',()=>reviewPoint(point,review));actions.append(review);root.append(actions);
  const provenance=node('details');provenance.append(node('summary','Procedencia y versión'),node('p',state.snapshot.provenance,'caption'));root.append(provenance);
}
function renderNeighbors(){
  const root=$('neighbors');root.replaceChildren();
  if(!state.neighbors.length){root.append(node('p','No hay vecinos compatibles con esta selección.','empty'));return;}
  state.neighbors.forEach((p,index)=>{const card=node('article',undefined,'neighbor'),row=node('div',undefined,'neighbor-main');row.append(node('span',String(index+1).padStart(2,'0'),'rank'));
    if(p.has_image){const img=node('img');img.loading='lazy';img.src=imageUrl(p);img.alt='';row.append(img);}
    const button=node('button',p.label);button.addEventListener('click',()=>selectPoint(state.snapshot.points.find(x=>x.id===p.id)));row.append(button,node('span',p.cosine.toFixed(4),'score'));card.append(row,node('p',`${p.category??'Sin categoría'} · coseno, no probabilidad`));
    if(p.differences.length){const details=node('details');details.append(node('summary',`Ver diferencias · ${p.known_field_coverage===null?'sin atributos':Math.round(p.known_field_coverage*100)+' % de campos comparables'}`));const list=node('ul');p.differences.forEach(d=>list.append(node('li',`${d.field}: ${d.query??'desconocido'} → ${d.candidate??'desconocido'}`)));details.append(list);card.append(details);}else card.append(node('p',p.known_field_coverage===null?'Sin datos constructivos comparables.':'Sin diferencias en los atributos conocidos.'));root.append(card);
  });
}
async function selectPoint(point){
  if(!point)return;
  const ticket=selectGate.next();compareGate.next();state.selected=point;state.neighbors=[];state.searchReady=false;state.comparison=null;
  detail(point);renderCatalog();renderMap();$('export').disabled=true;$('compare-button').disabled=true;$('comparison-result').replaceChildren(node('p','Pulsa Comparar vecinos para contrastar esta selección.','empty'));
  $('neighbors').replaceChildren(node('p','Calculando vecinos por coseno…','empty'));
  try{const data=await api('search',{body:{...requestFor(point),limit:Number($('limit').value),category:$('category').value||null,exclude_group:$('exclude-group').checked}});if(!selectGate.current(ticket))return;state.neighbors=data.neighbors;state.searchReady=true;renderNeighbors();renderMap();$('export').disabled=false;$('compare-button').disabled=!$('compare-space').value;message(`Consulta ${point.label}: ${data.neighbors.length} vecinos · ${state.snapshot.space.dimensions} dimensiones originales`);}catch(error){if(selectGate.current(ticket)){$('neighbors').replaceChildren(node('p',error.message,'empty'));message(error.message,true);}}
}
async function compareModels(){
  if(!state.selected||!state.searchReady||!$('compare-space').value)return;
  const ticket=compareGate.next(),point=state.selected;const root=$('comparison-result');root.replaceChildren(node('p','Consultando la otra representación…','empty'));
  try{const other=await api('snapshot',{params:{space:$('compare-space').value}});if(!compareGate.current(ticket))return;const match=counterpart(point,other.points);if(!match){root.replaceChildren(node('p','Este contenido no está presente en el otro espacio. No se comparan IDs que solo coinciden por nombre.','empty'));return;}
    const result=await api('search',{body:{space:other.space_key,snapshot_id:other.snapshot_id,member_id:match.id,limit:Number($('limit').value),category:$('category').value||null,exclude_group:$('exclude-group').checked}});if(!compareGate.current(ticket))return;
    state.comparison={space:other.space,snapshot_id:other.snapshot_id,neighbors:result.neighbors};const shared=overlap(state.neighbors,result.neighbors);root.replaceChildren(node('p',`${shared.shared} contenidos compartidos entre ambos rankings. No es una métrica de calidad.`, 'overlap'));const columns=node('div',undefined,'comparison-results');for(const[title,neighbors]of[[state.snapshot.space.model,state.neighbors],[other.space.model,result.neighbors]]){const col=node('div');col.append(node('h3',title.split('/').at(-1)));const list=node('ol');neighbors.forEach(p=>list.append(node('li',`${p.label} · ${p.cosine.toFixed(4)}`)));col.append(list);columns.append(col);}root.append(columns);
  }catch(error){if(compareGate.current(ticket))root.replaceChildren(node('p',error.message,'empty'));}
}
async function reviewPoint(point,button){
  const snapshot=state.snapshot.snapshot_id;button.disabled=true;const output=node('p','Consultando Jev con imagen y observaciones geométricas…','caption');button.parentElement.after(output);
  try{const result=await api('review',{body:requestFor(point)});if(state.selected?.id!==point.id||state.snapshot?.snapshot_id!==snapshot)return;output.textContent=result.state==='provider_error'?'Jev no devolvió un dictamen válido. Se conserva la búsqueda local.':`${result.label} · score ${result.score.toFixed(3)}, no calibrado · ${result.cache_hit?'respuesta guardada':'una petición'} · propuesta pendiente de revisión.`;}catch(error){output.textContent=error.message;}finally{button.disabled=!state.reviewAvailable;}
}
function resetView(){state.zoom=1;state.pan=[0,0];if(state.snapshot)renderMap();}
$('space').addEventListener('change',loadSnapshot);$('reload').addEventListener('click',loadSpaces);
$('filter').addEventListener('input',()=>{renderCatalog();renderMap();});
$('category').addEventListener('change',()=>{renderCatalog();renderMap();if(state.selected)selectPoint(state.selected);});
for(const id of ['limit','exclude-group'])$(id).addEventListener('change',()=>{if(state.selected)selectPoint(state.selected);});
$('compare-space').addEventListener('change',()=>{compareGate.next();state.comparison=null;$('comparison-result').replaceChildren(node('p','Pulsa Comparar vecinos para contrastar esta selección.','empty'));$('compare-button').disabled=!state.searchReady||!$('compare-space').value;});$('compare-button').addEventListener('click',compareModels);
$('zoom-in').addEventListener('click',()=>{state.zoom=Math.min(5,state.zoom*1.3);renderMap();});$('zoom-out').addEventListener('click',()=>{state.zoom=Math.max(.7,state.zoom/1.3);renderMap();});$('fit').addEventListener('click',()=>{resetView();renderMap();});
let drag=null;$('map').addEventListener('pointerdown',event=>{if(event.target.tagName==='circle')return;drag={x:event.clientX,y:event.clientY,pan:[...state.pan]};$('map').setPointerCapture(event.pointerId);});$('map').addEventListener('pointermove',event=>{if(!drag)return;const scale=800/$('map').getBoundingClientRect().width;state.pan=[drag.pan[0]+(event.clientX-drag.x)*scale,drag.pan[1]+(event.clientY-drag.y)*scale];renderMap();});for(const event of ['pointerup','pointercancel'])$('map').addEventListener(event,()=>{drag=null;});
$('export').addEventListener('click',()=>{if(!state.selected)return;const value={snapshot_id:state.snapshot.snapshot_id,space:state.snapshot.space,projection:state.snapshot.projection,query:state.selected,neighbors:state.neighbors,comparison:state.comparison,notice:'Coseno en espacio original; no equivalencia económica ni medidas inferidas.'};const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const link=node('a');link.href=url;link.download='vexplorer-comparacion.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
loadSpaces();
