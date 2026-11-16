'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const storage = {get(key, fallback = null) { try {return JSON.parse(localStorage.getItem(key)) ?? fallback;} catch {return fallback;} }, set(key, value) {try {localStorage.setItem(key, JSON.stringify(value)); return true;} catch {return false;}}, remove(key) {try {localStorage.removeItem(key);} catch {}}};
const state = {records:[], reviews:{}, scope:'required', visible:[], selected:null, result:'', dirty:false, saving:false, playing:false, listLimit:80,frame:0,mediaGeneration:0,frameRequest:0,frameUrls:[]};
const player = new ComparisonPlayer([$('referenceVideo'),$('simulatedVideo')],{
  loop:()=>$('loopVideos').checked,
  onState:(message,playing,loading=false)=>{state.playing=playing;$('playBoth').querySelector('span').textContent=loading?'Cancelar carga':playing?'Pausar ambos':'Reproducir ambos';if($('viewMode').value==='fluid')$('playbackStatus').textContent=message;},
  onTime:(number)=>{state.frame=number;updateFramePosition();},
  onError:message=>{$('playbackStatus').textContent=message;toast(message);},
  onStats:stats=>{$('playbackDiagnostics').textContent=stats.map((s,i)=>`${i?'Simulado':'Referencia'}: ${s.frames} cuadros, ${s.dropped} omitidos`).join(' · ')+` · Desfase: ${Math.round(Math.abs(stats[0].time-stats[1].time)*1000)} ms`;}
});
const resultLabels = {'coincide':'Coincide','no coincide':'No coincide','correcto':'Correcto','caja fija':'Caja fija','no se nota':'No se nota','otro':'Otro'};
const subsetLabels = {test_single:'Test · efecto individual',test_edit:'Test · editados',train_edit:'Train · editados',val_edit:'Val · editados'};
const draftKey = id => `lsp-review-draft-v1:${id}`;
function today() {const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'America/Lima',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()); return ['year','month','day'].map(t=>parts.find(p=>p.type===t).value).join('-');}
function baseRecords() {return state.records.filter(r => state.scope === 'all' || (state.scope === 'listed' ? r.n !== null : r.required));}
function incident(review) {return review && (review.grave || review.duda || ['otro','no coincide','caja fija'].includes(review.resultado));}
function familyMatches(r, filter) {if(!filter)return true; const text = `${r.family} ${r.effect}`.toLowerCase(); return filter==='desenfoque'?/blur|desenfoque/.test(text):filter==='objeto'?text.includes('objeto_mano'):filter==='combinado'?text.includes('combinado')||text.includes(' + '):text.includes(filter);}
function applyFilters(keepSelection = true) {
  const query = $('search').value.trim().toLocaleLowerCase('es');
  const split = $('splitFilter').value, status = $('statusFilter').value, family = $('familyFilter').value;
  state.visible = baseRecords().filter(r => (!query || `${r.original} ${r.n ?? ''} ${r.effect} ${r.family} ${r.file}`.toLocaleLowerCase('es').includes(query)) && (!split || r.split===split) && familyMatches(r,family) && (!status || (status==='pending' ? !state.reviews[r.id] : status==='reviewed' ? !!state.reviews[r.id] : incident(state.reviews[r.id]))));
  if (!keepSelection || !state.visible.some(r=>r.id===state.selected)) state.selected = state.visible[0]?.id ?? null;
  state.listLimit = 80;
  renderList(); renderCase(); renderProgress();
}
function renderList() {
  const list = $('videoList');
  const selectedIndex = state.visible.findIndex(r=>r.id===state.selected);
  $('listCount').textContent = `${state.visible.length} video${state.visible.length===1?'':'s'}`;
  $('listPosition').textContent = state.visible.length ? `${selectedIndex+1} / ${state.visible.length}` : '';
  const records = state.visible.slice(0,state.listLimit);
  if(selectedIndex >= state.listLimit) records.push(state.visible[selectedIndex]);
  list.innerHTML = records.map(r => {
    const review = state.reviews[r.id];
    return `<button class="video-item ${state.selected===r.id?'selected':''} ${review?'reviewed':''}" data-id="${r.id}" aria-current="${state.selected===r.id?'true':'false'}"><span class="item-index">${r.n ?? '·'}</span><span class="item-copy"><strong>${escapeHTML(r.original.replaceAll('_',' '))}</strong><small>${escapeHTML(r.family)} <span>· ${escapeHTML(r.split)}</span></small></span><span class="item-state ${incident(review)?'flagged':''}" title="${review?'Revisado':'Pendiente'}">${review?'✓':'○'}</span></button>`;
  }).join('');
  if(state.visible.length>state.listLimit) list.insertAdjacentHTML('beforeend',`<button id="loadMore" class="load-more">Mostrar más (${state.visible.length-state.listLimit})</button>`);
  list.querySelectorAll('.video-item').forEach(button=>button.addEventListener('click',()=>selectCase(button.dataset.id)));
  $('loadMore')?.addEventListener('click',()=>{state.listLimit+=100;renderList();});
}
function renderProgress() {
  const records = baseRecords(), done = records.filter(r=>state.reviews[r.id]).length;
  const percent = records.length ? Math.round(done/records.length*100) : 0;
  $('progressText').textContent = `${done} de ${records.length} revisados`;
  $('progressPercent').textContent = `${percent}%`;
  $('progressBar').style.width = `${percent}%`;
  $('progressHint').textContent = state.scope==='required'?'Revisión solicitada en el README':state.scope==='listed'?'Registros del CSV original':'Catálogo local de simulaciones';
  $('scopeNotice').hidden = state.scope==='required';
  const count = Object.keys(state.reviews).length;
  $('saveStatus').textContent = count ? `${count} revisión${count===1?'':'es'} guardada${count===1?'':'s'} en tu PC` : 'Sin revisiones todavía';
}
function current() {return state.records.find(r=>r.id===state.selected);}
function formData() {return {resultado:state.result,revisado_por:$('reviewer').value,fecha:$('reviewDate').value,observacion:$('observation').value,duda:$('doubt').checked,grave:$('serious').checked};}
function persistDraft() {
  if(!state.selected || !state.dirty)return;
  const ok = storage.set(draftKey(state.selected),formData());
  $('draftStatus').textContent = ok?'Borrador en este navegador':'Pendiente de guardar';
}
function markDirty() {state.dirty=true;persistDraft();showFormError('');const needed=['no coincide','otro'].includes(state.result)||$('serious').checked;$('observationRequired').hidden=!needed;$('observation').required=needed;}
function selectCase(id) {if(state.selected===id)return;persistDraft();state.selected=id;renderList();renderCase();}
function stopVideos() {player.stop();}
function loadReference() {
  const r = current(); if(!r)return;
  const kind = $('referenceSelect').value;
  const available = kind==='base'?r.baseAvailable:kind==='before'?r.beforeAvailable:r.originalAvailable;
  const v = $('referenceVideo');
  v.pause();
  $('referenceLoading').hidden=!available;
  $('referenceLoading').textContent='Preparando referencia…';
  if(available) v.src=`/media/${r.id}/${kind}?vista=fluida&v=2`; else v.removeAttribute('src');
  v.load();
  $('referenceError').textContent=kind==='base'?'La base del simulador no está disponible.':'No se encontró un original organizado con correspondencia única.';
  $('referenceError').hidden=available;
  $('referenceCaption').textContent=kind==='base'?'Mismo fondo y luz, sin efecto':kind==='before'?'Versión anterior a la corrección':`${r.original}.mp4 · ${r.split}`;
  $('referenceVersion').textContent=kind==='before'?'Antes':kind==='base'?'Sin efecto':'Referencia';
}
function renderCase() {
  stopVideos();
  clearTimeout(state.scrubTimer);
  ++state.mediaGeneration;++state.frameRequest;state.frameAbort?.abort();state.frame=0;
  state.userFocus=null;
  const r = current();
  $('reviewWorkspace').hidden=!r;
  $('emptyState').hidden=!!r || !state.records.length;
  if(!r)return;
  const index=state.visible.findIndex(v=>v.id===r.id);
  $('caseNumber').textContent=r.n!==null?`REGISTRO ${String(r.n).padStart(3,'0')}`:'CATÁLOGO AMPLIADO';
  $('caseSplit').textContent=subsetLabels[r.subset]||r.subset;
  $('caseEffect').textContent=r.family.replaceAll('_',' ');
  $('caseName').textContent=r.original.replaceAll('_',' ');
  $('casePosition').textContent=`${index+1} / ${state.visible.length}`;
  $('previous').disabled=index<=0;
  $('next').disabled=index>=state.visible.length-1;
  $('caseReviewed').hidden=!state.reviews[r.id];
  $('expectationText').textContent=r.expected;
  $('knownText').textContent=r.known;
  $('knownText').hidden=!r.known;
  const related=(r.relatedIds||[r.id]).map(id=>state.records.find(item=>item.id===id)).filter(Boolean);
  $('variantSelect').innerHTML=related.map(item=>`<option value="${item.id}" ${item.id===r.id?'selected':''}>${escapeHTML(item.subset==='test_single'?'Prueba individual · '+item.family+' · '+item.effect:'Editado de '+item.split+' · '+item.family)}</option>`).join('');
  $('variantNotice').textContent=r.subset==='test_single'?'Prueba de un solo efecto. Usa la base del simulador para aislarlo; el editado de test reúne las demás modificaciones.':'Editado de '+r.split+'. Muestra los efectos que se generaron juntos en este archivo.';
  const baseOption=$('referenceSelect').querySelector('[value="base"]');
  baseOption.disabled=!r.baseAvailable;
  $('referenceSelect').querySelector('[value="before"]').disabled=!r.beforeAvailable;
  const preferred=storage.get('lsp-reference-kind');
  $('referenceSelect').value=r.beforeAvailable?'before':preferred==='base'&&r.baseAvailable?'base':r.family==='desenfoque'&&r.baseAvailable?'base':'original';
  if(!r.originalAvailable&&r.baseAvailable)$('referenceSelect').value='base';
  $('correctionNotice').hidden=!r.beforeAvailable;
  loadReference();
  const sim=$('simulatedVideo');
  sim.pause();
  $('simulatedLoading').hidden=!r.available;
  $('simulatedLoading').textContent='Preparando reproducción fluida…';
  if(r.available)sim.src=`/media/${r.id}/simulated?vista=fluida&v=2`;else sim.removeAttribute('src');
  sim.load();
  $('simulatedError').hidden=r.available;
  $('effectCaption').textContent=r.effect.startsWith('combinado_')?'Efectos combinados':r.effect.replaceAll('_',' ');
  $('simulationCaption').textContent=r.effect.startsWith('combinado_')?r.family:r.effect.replaceAll('_',' ');
  $('coverage').textContent=r.pct!==''?`${r.pct}% de fotogramas con efecto`:'';
  const review=state.reviews[r.id];
  const draft=storage.get(draftKey(r.id));
  const data=draft||review||{};
  state.result=data.resultado||'';
  state.dirty=!!draft;
  $('reviewer').value=data.revisado_por||storage.get('lsp-review-name','');
  $('reviewDate').value=data.fecha||today();
  $('observation').value=data.observacion||'';
  $('doubt').checked=!!data.duda;
  $('serious').checked=!!data.grave;
  $('draftStatus').textContent=draft?'Borrador recuperado':review?'Guardado en tu PC':'';
  renderResults();
  $('filePath').textContent=r.file;
  $('warningText').textContent=r.warning||'Sin aviso registrado.';
  $('scopeText').textContent=r.required?'Uno de los 38 registros solicitados para D48.':'Revisión adicional. No se incorpora al Excel de los 38 solicitados; usa la exportación ampliada.';
  showFormError('');
  updatePlaybackSettings();
  player.configure([]);updateFramePosition();applyView(false);refreshTiming();
}
function renderResults() {
  const r=current();if(!r)return;
  $('resultOptions').innerHTML=r.options.map((option,i)=>`<button type="button" data-result="${escapeHTML(option)}" aria-pressed="${state.result===option}" class="result-button ${state.result===option?'chosen':''}"><span>${escapeHTML(resultLabels[option]||option)}</span><kbd>${i+1}</kbd></button>`).join('');
  $('resultOptions').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>chooseResult(b.dataset.result)));
  $('shortcutMax').textContent=String(r.options.length);
  const needed=['no coincide','otro'].includes(state.result)||$('serious').checked;
  $('observationRequired').hidden=!needed;
  $('observation').required=needed;
}
function chooseResult(result) {state.result=result;renderResults();markDirty();}
function showFormError(message) {$('formError').textContent=message;$('formError').hidden=!message;}
async function save(next=false) {
  if(state.saving || !current())return;
  if(!state.result){showFormError('Elige un resultado antes de guardar.');$('resultOptions').scrollIntoView({block:'nearest'});return;}
  if(!$('reviewForm').reportValidity())return;
  const id=state.selected, data=formData();
  data.revisado_por=data.revisado_por.trim();
  data.observacion=data.observacion.trim();
  if(!data.revisado_por || ((['otro','no coincide'].includes(data.resultado)||data.grave)&&!data.observacion)){showFormError('Completa tu nombre y la observación requerida.');return;}
  state.saving=true;
  $('saveNext').disabled=true;$('saveOnly').disabled=true;
  try {
    const response=await fetch(`/api/reviews/${id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result=await response.json();if(!response.ok)throw new Error(result.error||'No se pudo guardar.');
    state.reviews[id]=result.review;
    storage.remove(draftKey(id));
    storage.set('lsp-review-name',data.revisado_por);
    state.dirty=false;
    $('draftStatus').textContent='Guardado en tu PC';
    const before=state.visible.map(r=>r.id), index=before.indexOf(id);
    if(next) {
      const following=[...before.slice(index+1),...before.slice(0,index)].find(other=>!state.reviews[other]);
      if(following)state.selected=following;
    }
    applyFilters(true);
    const scope=baseRecords();const done=scope.filter(r=>state.reviews[r.id]).length;
    toast(done===scope.length?'Terminaste este alcance. Ya puedes exportar tu revisión.':'Revisión guardada.');
    if(next)$('caseName').scrollIntoView({block:'nearest',behavior:'smooth'});
  }catch(error){showFormError(`${error.message} Tu borrador sigue en este navegador.`);persistDraft();}
  finally{state.saving=false;$('saveNext').disabled=false;$('saveOnly').disabled=false;}
}
function navigate(delta) {const i=state.visible.findIndex(r=>r.id===state.selected);const r=state.visible[i+delta];if(r)selectCase(r.id);}
function updatePlaybackSettings() {player.setRate(Number($('playbackRate').value));}
async function togglePlayback() {
  clearTimeout(state.scrubTimer);
  if(player.intent){stopVideos();return;}
  if($('viewMode').value==='exact'){$('viewMode').value='fluid';applyView(false);}
  await player.play(state.frame/player.fps);
}
function updateFramePosition() {
  $('comparisonTimeline').max=String(Math.max(0,player.frames-1));
  $('comparisonTimeline').value=String(state.frame);
  $('framePosition').textContent=`${state.frame+1} / ${player.frames} · ${(state.frame/player.fps).toFixed(2)} s`;
}
async function refreshTiming() {
  const token=++state.mediaGeneration,r=current();if(!r)return;
  const kind=$('referenceSelect').value;
  try {
    const times=await Promise.all([kind,'simulated'].map(async k=>{const response=await fetch(`/timing/${r.id}/${k}`);if(!response.ok)return null;return response.json();}));
    if(token!==state.mediaGeneration)return;
    player.configure(times);state.frame=Math.min(state.openFrame??state.frame,player.frames-1);state.openFrame=null;updateFramePosition();
    if(state.frame)player.seekFrame(state.frame);
    if($('viewMode').value==='exact')renderExactFrame();
  }catch(error){if(token===state.mediaGeneration)$('playbackStatus').textContent='No se pudieron leer los tiempos del video. Vuelve a abrir el registro.';}
}
function applyView(render=true) {
  stopVideos();
  const exact=$('viewMode').value==='exact';
  $('zoomControl').hidden=!exact;
  $('viewHint').textContent=exact?'Píxeles del archivo · Pulsa una zona para ampliarla.':'Full HD · Para movimiento. En efectos suaves usa «Fotograma exacto».';
  for(const side of ['reference','simulated']) {
    $(side+'Video').hidden=exact;
    $(side+'Viewport').hidden=!exact||!$(side+'Frame').getAttribute('src');
    if(!exact){$(side+'Loading').textContent=side==='reference'?'Preparando referencia…':'Preparando reproducción fluida…';$(side+'Loading').hidden=$(side+'Video').readyState>=2||!$(side+'Video').getAttribute('src');}
  }
  state.centerZoom=true;
  if(exact&&render)renderExactFrame();
  else if(!exact){++state.frameRequest;state.frameAbort?.abort();$('playbackStatus').textContent='Vista fluida. Usa Reproducir ambos para comparar.';}
}
async function renderExactFrame() {
  const r=current();if(!r)return;
  const request=++state.frameRequest,number=state.frame;
  state.frameAbort?.abort();const controller=new AbortController();state.frameAbort=controller;
  const sides=['reference','simulated'];
  const pairs=sides.map(side=>({side,kind:side==='reference'?$('referenceSelect').value:'simulated'})).filter(({side})=>$(side+'Video').getAttribute('src'));
  const urls=[];
  $('playbackStatus').textContent=`Leyendo fotograma exacto ${number+1}…`;
  for(const {side} of pairs){$(side+'Loading').textContent=`Leyendo fotograma ${number+1}…`;$(side+'Loading').hidden=false;}
  try {
    const frames=await Promise.all(pairs.map(async ({side,kind})=>{
      const response=await fetch(`/frame/${r.id}/${kind}?n=${number}`,{signal:controller.signal});
      if(!response.ok){const error=await response.json();throw new Error(error.error||'No se pudo leer el fotograma.');}
      const url=URL.createObjectURL(await response.blob());urls.push(url);
      const image=new Image();image.src=url;await image.decode();
      return {side,url,width:image.naturalWidth,height:image.naturalHeight};
    }));
    if(request!==state.frameRequest||$('viewMode').value!=='exact')return;
    const previous=state.frameUrls;state.frameUrls=[...urls];urls.length=0;
    for(const {side,url,width,height} of frames) {
      const image=$(side+'Frame');image.src=url;image.dataset.width=width;image.dataset.height=height;
      $(side+'Viewport').hidden=false;$(side+'Loading').hidden=true;
    }
    previous.forEach(url=>URL.revokeObjectURL(url));applyDetailZoom();
    $('playbackStatus').textContent=`Fotograma exacto ${number+1} de ${player.frames} · ${(number/player.fps).toFixed(2)} s · Usa 100 % o 200 % para revisar el detalle.`;
  }catch(error){if(request===state.frameRequest&&error.name!=='AbortError'){$('playbackStatus').textContent=error.message;for(const {side} of pairs)$(side+'Loading').hidden=true;}}
  finally{urls.forEach(url=>URL.revokeObjectURL(url));}
}
function applyDetailZoom() {
  const zoom=$('detailZoom').value;
  for(const side of ['reference','simulated']) {
    const image=$(side+'Frame'),viewport=$(side+'Viewport');
    image.style.width=zoom==='fit'?'100%':`${Number(image.dataset.width||1920)*Number(zoom)}px`;
    image.style.height=zoom==='fit'?'100%':`${Number(image.dataset.height||1080)*Number(zoom)}px`;
    image.style.objectFit=zoom==='fit'?'contain':'fill';
    if(state.centerZoom&&zoom!=='fit'){
      const focus=state.userFocus||current()?.detailFocus?.[state.frame]||[Number(image.dataset.width||1920)/2,Number(image.dataset.height||1080)*.33];
      viewport.scrollLeft=focus[0]*Number(zoom)-viewport.clientWidth/2;
      viewport.scrollTop=focus[1]*Number(zoom)-viewport.clientHeight/2;
    }
    viewport.dataset.zoomed=String(zoom!=='fit');
  }
  state.centerZoom=false;
}
function seekDetail(number) {
  stopVideos();state.frame=Math.max(0,Math.min(player.frames-1,number));
  $('viewMode').value='exact';applyView(false);updateFramePosition();
  player.seekFrame(state.frame);renderExactFrame();
}
function step(delta) {seekDetail(($('viewMode').value==='exact'?state.frame:player.frame())+delta);}
let toastTimer;
function toast(message) {clearTimeout(toastTimer);$('toast').textContent=message;$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,3500);}
function resetFilters() {for(const id of ['search','splitFilter','statusFilter','familyFilter'])$(id).value='';applyFilters(false);}
function attachEvents() {
  document.querySelectorAll('[data-scope]').forEach(button=>button.addEventListener('click',()=>{persistDraft();state.scope=button.dataset.scope;document.querySelectorAll('[data-scope]').forEach(b=>b.classList.toggle('active',b===button));resetFilters();}));
  for(const id of ['search','splitFilter','statusFilter','familyFilter'])$(id).addEventListener(id==='search'?'input':'change',()=>{persistDraft();applyFilters();});
  for(const id of ['reviewer','reviewDate','observation','doubt','serious'])$(id).addEventListener('input',markDirty);
  $('previous').addEventListener('click',()=>navigate(-1));$('next').addEventListener('click',()=>navigate(1));
  $('reviewForm').addEventListener('submit',e=>{e.preventDefault();save(true);});
  $('saveOnly').addEventListener('click',()=>save(false));
  $('referenceSelect').addEventListener('change',()=>{stopVideos();storage.set('lsp-reference-kind',$('referenceSelect').value);loadReference();refreshTiming();});
  $('variantSelect').addEventListener('change',()=>{persistDraft();const id=$('variantSelect').value;const target=state.records.find(item=>item.id===id);if(!target)return;if(state.scope!=='all'&&!(state.scope==='listed'?target.n!==null:target.required)){state.scope='all';document.querySelectorAll('[data-scope]').forEach(b=>b.classList.toggle('active',b.dataset.scope==='all'));for(const key of ['search','splitFilter','statusFilter','familyFilter'])$(key).value='';}state.selected=id;applyFilters(true);});
  $('playBoth').addEventListener('click',togglePlayback);
  $('restartBoth').addEventListener('click',()=>{state.frame=0;player.seekFrame(0);updateFramePosition();if($('viewMode').value==='exact')renderExactFrame();});
  $('playbackRate').addEventListener('change',updatePlaybackSettings);$('loopVideos').addEventListener('change',updatePlaybackSettings);
  $('stepBack').addEventListener('click',()=>step(-1));$('stepForward').addEventListener('click',()=>step(1));
  $('viewMode').addEventListener('change',()=>applyView());
  $('detailZoom').addEventListener('change',()=>{state.centerZoom=true;applyDetailZoom();});
  $('comparisonTimeline').addEventListener('input',()=>{stopVideos();state.frame=Number($('comparisonTimeline').value);updateFramePosition();clearTimeout(state.scrubTimer);const id=state.selected;state.scrubTimer=setTimeout(()=>{if(id===state.selected)seekDetail(state.frame);},140);});
  for(const side of ['reference','simulated']) {
    const other=side==='reference'?'simulated':'reference';
    $(side+'Viewport').addEventListener('scroll',()=>{const source=$(side+'Viewport'),target=$(other+'Viewport');if(Math.abs(source.scrollLeft-target.scrollLeft)>1)target.scrollLeft=source.scrollLeft;if(Math.abs(source.scrollTop-target.scrollTop)>1)target.scrollTop=source.scrollTop;});
    $(side+'Frame').addEventListener('click',event=>{if($('detailZoom').value!=='fit')return;const image=event.currentTarget,rect=image.getBoundingClientRect();state.userFocus=[(event.clientX-rect.left)/rect.width*Number(image.dataset.width),(event.clientY-rect.top)/rect.height*Number(image.dataset.height)];$('detailZoom').value='1';state.centerZoom=true;applyDetailZoom();});
    $(side+'Video').addEventListener('loadeddata',()=>{if($('viewMode').value==='fluid'){$(side+'Loading').hidden=true;if(player.active().every(v=>v.readyState>=2)&&!player.intent)$('playbackStatus').textContent='Ambos videos listos. Reproduce o revisa un fotograma exacto.';}});
  }
  $('referenceVideo').addEventListener('error',()=>$('referenceError').hidden=false);
  $('simulatedVideo').addEventListener('error',()=>{$('simulatedLoading').hidden=true;$('simulatedError').hidden=false;});
  $('notOpening').addEventListener('click',()=>{chooseResult('otro');$('observation').value=$('observation').value.trim()?`${$('observation').value.trim()}. No abre`:'no abre';$('serious').checked=true;markDirty();});
  $('exportButton').addEventListener('click',()=>{const n=state.records.filter(r=>r.required&&state.reviews[r.id]).length;$('exportSummary').textContent=`${n} de los 38 solicitados guardados. ${38-n} pendientes. Hay ${Object.keys(state.reviews).length} clasificaciones guardadas en total.`;$('exportDialog').showModal();});
  $('helpButton').addEventListener('click',()=>$('helpDialog').showModal());
  $('resetFilters').addEventListener('click',resetFilters);
  $('toggleFilters').addEventListener('click',()=>{const open=document.querySelector('.sidebar').classList.toggle('filters-open');$('toggleFilters').setAttribute('aria-expanded',String(open));});
  document.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}}));
  document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();save(true);return;}if(/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)||document.querySelector('dialog[open]'))return;if(e.code==='Space'){e.preventDefault();togglePlayback();}else if(/^[1-5]$/.test(e.key)){const option=current()?.options[Number(e.key)-1];if(option)chooseResult(option);}else if(e.key==='ArrowRight')navigate(1);else if(e.key==='ArrowLeft')navigate(-1);});
  window.addEventListener('beforeunload',persistDraft);
}
async function init() {
  attachEvents();
  try {
    const response=await fetch('/api/catalog');if(!response.ok)throw new Error('El servidor local no responde.');const data=await response.json();
    state.records=data.records;state.reviews=data.reviews;
    $('localPaths').innerHTML=`<strong>Originales</strong><p>${escapeHTML(data.paths.originals)}</p><strong>Simulados</strong><p>${escapeHTML(data.paths.simulated)}</p><strong>Revisiones guardadas</strong><p>${escapeHTML(data.reviewPath)}</p>`;
    const last=storage.get('lsp-review-last');
    const pending=state.records.find(r=>r.required&&!state.reviews[r.id]);
    state.selected=last&&state.records.some(r=>r.id===last&&r.required)?last:pending?.id||state.records.find(r=>r.required)?.id;
    const query=new URLSearchParams(location.search),target=state.records.find(r=>r.n===Number(query.get('n'))&&r.required);
    if(target){state.selected=target.id;const frame=Number(query.get('frame'));if(Number.isInteger(frame)&&frame>=0)state.openFrame=frame;}
    if(query.get('view')==='exact')$('viewMode').value='exact';
    applyFilters(true);
    document.addEventListener('click',()=>{if(state.selected)storage.set('lsp-review-last',state.selected);});
  } catch(error) {$('loadError').textContent=`No se pudo cargar la revisión: ${error.message} Vuelve a iniciar la aplicación con INICIAR_REVISION_VISUAL.bat.`;$('loadError').hidden=false;$('listCount').textContent='Error al cargar';}
}
init();
