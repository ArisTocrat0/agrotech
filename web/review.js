'use strict';
const classLabels = {A:'A · Двудольные (широколистные)', B:'B · Злаковые (узколистные)'};
const stageLabels = {base_minimum:'Идеальное окно: базовая/минимальная норма по регламенту препарата', review_increase_15_20:'4–6 листьев: по заданному правилу +15–20%; требуется проверка регламента препарата', warn_ineffective_crop_risk:'Поздняя фаза: возможна неэффективность обработки и повреждение культуры', review_stage:'Фаза не определена: требуется проверка'};
let reviewImage = 0, reviewDetection = 0, reviewSaving = false, reviewJob = null;
const kindLabels = {weed:'Сорняк',crop:'Культура',unknown:'Проверить',not_plant:'Не растение'};
const kindColors = {weed:'#ff3fa4',crop:'#00d9ff',unknown:'#ffd600',not_plant:'#ffffff'};
function openReview(index) {
  if(reviewSaving || !results[index]) return;
  reviewImage = index; reviewDetection = 0; reviewJob = selected;
  $('dialog-title').textContent = results[index].image;
  $('dialog-image').src = `/api/jobs/${reviewJob}/source/${index}`;
  $('review-zoom').value = 1; $('review-frame').style.width = '100%';
  $('review-gsd').value = results[index].gsd_cm || '';
  $('review-message').textContent = ''; ensureReviewControls();
  $('image-dialog').showModal(); renderReview();
}
function ensureReviewControls() {
  if (!$('review-progress')) { const box=document.createElement('div');box.className='review-progress';box.innerHTML=`<div><span>${t('Прогресс проверки')}</span><strong id="review-progress-label">0%</strong></div><progress id="review-progress" max="100" value="0"></progress>`;document.querySelector('.review-layout').before(box); }
  if (!$('review-next-pending')) { const button=document.createElement('button');button.id='review-next-pending';button.className='secondary';button.textContent=t('Следующий непроверенный')+' ⇥';button.addEventListener('click',nextPending);document.querySelector('.review-navigation').append(button); }
  if (!$('show-all-boxes')) { const label=document.createElement('label');label.className='show-all-boxes';label.innerHTML='<input id="show-all-boxes" type="checkbox"> '+t('Показать все рамки');label.querySelector('input').addEventListener('change',renderReview);document.querySelector('.review-toolbar').append(label); }
  if (!$('review-crop')) { const heading=document.createElement('span');heading.className='crop-label';heading.textContent=t('Сейчас вы проверяете');const canvas=document.createElement('canvas');canvas.id='review-crop';canvas.width=320;canvas.height=220;document.querySelector('.review-inspector').prepend(canvas);document.querySelector('.review-inspector').prepend(heading); }
}
function renderSelectedCrop(row,d) { const canvas=$('review-crop'),image=$('dialog-image');if(!canvas||!d||(!image.complete || !image.naturalWidth))return;const context=canvas.getContext('2d'),b=d.bbox,pad=Math.max(12,Math.round(Math.max(b.x2-b.x1,b.y2-b.y1)*.35));const x=Math.max(0,b.x1-pad),y=Math.max(0,b.y1-pad),w=Math.min(row.width-x,b.x2-b.x1+pad*2),h=Math.min(row.height-y,b.y2-b.y1+pad*2);context.fillStyle='#101512';context.fillRect(0,0,canvas.width,canvas.height);const scale=Math.min(canvas.width/w,canvas.height/h),dw=w*scale,dh=h*scale,dx=(canvas.width-dw)/2,dy=(canvas.height-dh)/2;context.drawImage(image,x,y,w,h,dx,dy,dw,dh);context.strokeStyle=kindColors[d.kind]||kindColors.unknown;context.lineWidth=4;context.strokeRect(dx+(b.x1-x)*scale,dy+(b.y1-y)*scale,(b.x2-b.x1)*scale,(b.y2-b.y1)*scale); }
function detectionLabel(d) {
  const species = d.species === 'unknown' ? t('Неизвестный вид') : d.species;
  return `${t(kindLabels[d.kind] || 'Проверить')} · ${species} · ${d.stage === 'unknown' ? t('Не определена') : d.stage}`;
}
function renderReview() {
  const row = results[reviewImage];
  if (!row || selected !== reviewJob) return;
  const overlay = $('review-overlay'); overlay.replaceChildren();
  overlay.setAttribute('viewBox',`0 0 ${row.width} ${row.height}`);
  overlay.setAttribute('preserveAspectRatio','none');
  const svg = name => document.createElementNS('http://www.w3.org/2000/svg',name);
  if ($('show-rows').checked) (row.rows?.lines || []).forEach(line => {
    const el = svg('line');
    for (const [key,value] of Object.entries(line)) el.setAttribute(key,value);
    el.setAttribute('stroke','#ffffff'); el.setAttribute('stroke-width','2');
    el.setAttribute('stroke-dasharray','10 8'); el.setAttribute('vector-effect','non-scaling-stroke');
    el.style.pointerEvents='none'; overlay.append(el);
  });
  row.detections.forEach((d,index) => {
    if (!$('show-all-boxes')?.checked && index !== reviewDetection) return;
    const rect = svg('rect'), b = d.bbox;
    for (const [key,value] of Object.entries({x:b.x1,y:b.y1,width:b.x2-b.x1,height:b.y2-b.y1})) rect.setAttribute(key,value);
    rect.setAttribute('stroke',kindColors[d.kind] || kindColors.unknown);
    rect.setAttribute('stroke-width',index === reviewDetection ? '4' : '2');
    rect.setAttribute('vector-effect','non-scaling-stroke');
    rect.setAttribute('fill',index === reviewDetection ? '#ffffff33' : '#ffffff01');
    rect.setAttribute('tabindex','0'); rect.setAttribute('role','button');
    rect.setAttribute('aria-label',detectionLabel(d));
    if (d.kind === 'unknown') rect.setAttribute('stroke-dasharray','5 3');
    const title = svg('title'); title.textContent = `${detectionLabel(d)} · ${t('Сходство')}: ${Number(d.similarity_score).toFixed(2)}`;
    rect.append(title);
    rect.addEventListener('click',() => { reviewDetection=index; renderReview(); });
    rect.addEventListener('keydown',event => { if (event.key==='Enter' || event.key===' ') { event.preventDefault();reviewDetection=index;renderReview(); } });
    overlay.append(rect);
  });
  const d = row.detections[reviewDetection];
  renderSelectedCrop(row,d);
  $('review-name').textContent = d ? detectionLabel(d) : t('Нет обнаружений');
  $('review-details').textContent = d ? `${t('Сходство')}: ${Number(d.similarity_score).toFixed(2)} · ${t('Класс')}: ${t(classLabels[d.weed_class] || 'Не определена')} · ${t({annual:'Малолетний',perennial:'Многолетний'}[d.lifecycle] || 'Не определена')}${d.review ? ' · '+t('Проверено вручную') : ''}` : '';
  $('review-stage').textContent = d?.stage_advice ? `${d.priority === 'high' ? t('Приоритет: многолетник') + ' · ' : ''}${t(stageLabels[d.stage_advice.action])}` : '';
  const reviewed=row.detections.filter(d=>!isPending(d)).length;
  const percent=row.detections.length ? Math.round(reviewed/row.detections.length*100) : 100;
  $('review-counter').textContent = `${d ? reviewDetection+1 : 0} / ${row.detections.length} · ${t('Проверено')}: ${reviewed}`;
  if ($('review-progress')) { $('review-progress').value=percent;$('review-progress-label').textContent=`${percent}%`; }
  document.querySelectorAll('[data-decision]').forEach(button => button.disabled=reviewSaving || !d);
  if($('review-next-pending')) $('review-next-pending').disabled=reviewSaving;
  $('review-prev').disabled=reviewSaving || reviewDetection<=0;
  $('review-next').disabled=reviewSaving || reviewDetection>=row.detections.length-1;
  const a = row.agronomy || {};
  const level = {scale_required:'Нужен масштаб',low:'Слабая засорённость',medium:'Средняя засорённость',high:'Сильная засорённость',critical:'Критическая угроза'};
  const density = a.area_m2 ? `${t('Площадь')}: ${a.area_m2.toFixed(2)} м² · ${t('Малолетние')}: ${a.annual_per_m2.toFixed(2)}/м² · ${t('Многолетние')}: ${a.perennial_per_m2.toFixed(2)}/м²` : t('Для плотности укажите масштаб');
  $('review-agronomy').textContent = `${t('Ряды')}: ${row.rows?.count ?? t('Не определены')} · ${t(level[a.level] || 'Нужен масштаб')} · ${density} · ${t('Культур')}: ${row.crop_count || 0} · ${t('Сорняков без агрокласса')}: ${a.unclassified_weeds || 0}`;
  const classes = $('review-classes'); classes.replaceChildren();
  for (const group of ['A','B']) {
    const stats = a.classes?.[group]; if (!stats) continue;
    const line = document.createElement('p');
    const densityText = key => stats[key] == null ? '—' : Number(stats[key]).toFixed(2);
    line.textContent = `${t(classLabels[group])}: ${t('Малолетние')} ${stats.annual_count} (${densityText('annual_per_m2')}/м²), ${t('Многолетние')} ${stats.perennial_count} (${densityText('perennial_per_m2')}/м²)`;
    if (stats.priority === 'high') line.textContent += ` · ${t('Приоритет: многолетник')}`;
    classes.append(line);
  }
  const actions = {measure_scale:'Нужен масштаб', do_not_spray:'Не опрыскивать: ниже экономического порога', standard_rate:'Стандартная норма по регламенту препарата', maximum_label_rate:'Максимальная разрешённая норма по регламенту препарата', urgent_treatment:'Критическая угроза: срочно оценить обработку', agronomist_review:'Требуется проверка агрономом'};
  $('review-action').textContent = a.threshold_action ? `${t('По заданным порогам')}: ${t(actions[a.threshold_action])}. ${t('Решение')}: ${t(actions[a.recommendation])}.` : '';
  const reasons = {scale_required:'Нужен масштаб', uncertain_classification:'Есть объекты с неопределённым классом', late_stage_crop_risk:'Поздняя фаза: возможна неэффективность обработки и повреждение культуры', unknown_stage:'Фаза не определена: требуется проверка', perennials_below_threshold:'Есть многолетники ниже критического порога: требуется отдельная оценка'};
  $('review-reasons').textContent = (a.review_reasons || []).map(reason => t(reasons[reason] || reason)).join(' · ');
  const perf = row.performance;
  $('review-performance').textContent = perf ? `${t('Обработка кадра')}: ${Number(row.processing_seconds).toFixed(3)} ${t('с')} · ${Number(perf.fps).toFixed(2)} FPS · ${t('Путь за обработку при 20 км/ч')}: ${Number(perf.motion_at_20_kmh.processing_distance_m).toFixed(2)} ${t('м')}` : '';

}
function nextPending() {
  if(reviewSaving || selected!==reviewJob) return;
  const target=pendingTarget(results,reviewImage,reviewDetection);
  if(target){
    if(target.image!==reviewImage){$('dialog-image').src=`/api/jobs/${reviewJob}/source/${target.image}`;$('review-zoom').value=1;$('review-frame').style.width='100%';}
    reviewImage=target.image;reviewDetection=target.detection;
    $('dialog-title').textContent=results[reviewImage].image;$('review-gsd').value=results[reviewImage].gsd_cm||'';
    $('review-message').textContent='';renderReview();return;
  }
  $('review-message').textContent=t('Все объекты этого анализа проверены.');
}
async function decide(decision) {
  if (reviewSaving || selected !== reviewJob) return;
  const d = results[reviewImage]?.detections[reviewDetection]; if (!d) return;
  reviewSaving=true; renderReview();
  const job = reviewJob;
  try {
    const updated = await api(`/api/jobs/${job}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:reviewImage,detection:d.id,decision})});
    if (selected !== job) return;
    results=updated;
    reviewDetection=Math.min(reviewDetection+1,results[reviewImage].detections.length-1);
    $('review-message').textContent='✓ '+t('Решение сохранено'); renderResults();
  } catch(error) { $('review-message').textContent=translateMessage(error.message); }
  finally { reviewSaving=false; renderReview(); }
}
document.querySelectorAll('[data-decision]').forEach(button=>button.addEventListener('click',()=>decide(button.dataset.decision)));
$('review-prev').addEventListener('click',()=>{ reviewDetection=Math.max(0,reviewDetection-1);renderReview(); });
$('review-next').addEventListener('click',()=>{ reviewDetection=Math.min(results[reviewImage].detections.length-1,reviewDetection+1);renderReview(); });
$('review-zoom').addEventListener('input',()=>{ $('review-frame').style.width=`${Number($('review-zoom').value)*100}%`; });
$('show-rows').addEventListener('change',renderReview);
$('dialog-image').addEventListener('load',renderReview);
$('image-dialog').addEventListener('keydown',event=>{
  if (reviewSaving || event.defaultPrevented || /INPUT|SELECT|TEXTAREA/.test(event.target.tagName)) return;
  const decision = {'1':'weed','2':'crop','3':'not_plant','4':'unknown'}[event.key];
  if (decision) { event.preventDefault();decide(decision); }
  else if(event.key==='ArrowLeft'){event.preventDefault();reviewDetection=Math.max(0,reviewDetection-1);renderReview();}
  else if(event.key==='ArrowRight'){event.preventDefault();reviewDetection=Math.min(results[reviewImage].detections.length-1,reviewDetection+1);renderReview();}
  else if(event.key==='Enter' && event.target.tagName!=='BUTTON'){event.preventDefault();nextPending();}
});
// TODO: add undo when the API supports restoring an unreviewed state.
// Undo is intentionally not emulated: the current API can replace a decision but
// cannot restore the pristine "unreviewed" state without losing audit semantics.
$('review-geometry').addEventListener('click',async()=>{
  if (!$('review-gsd').reportValidity()) return;
  const job=reviewJob;
  $('review-geometry').disabled=true;
  try {
    const updated=await api(`/api/jobs/${job}/geometry`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:reviewImage,gsd_cm:$('review-gsd').value})});
    if (selected===job) { results=updated;renderReview();renderResults(); }
  } catch(error) { $('review-message').textContent=translateMessage(error.message); }
  finally { $('review-geometry').disabled=false; }
});

let cropImportState = {status:'idle',log:''};
function renderCropImport() {
  $('import-crops').disabled=cropImportState.status==='running';
  $('crop-import-status').textContent=t({idle:'Фотографии ещё не загружены',running:'Загрузка фотографий…',done:'Фотографии загружены',error:'Не удалось загрузить все фотографии'}[cropImportState.status]);
  $('crop-import-log').hidden=!cropImportState.log;
  $('crop-import-log').textContent=cropImportState.log;
}
async function refreshCropImport() {
  clearTimeout(refreshCropImport.timer);
  if(location.hash!=='#setup') return;
  try { const previous=cropImportState.status;cropImportState=await api('/api/crop-import');renderCropImport();if(previous==='running'&&cropImportState.status!=='running')refreshSetup();clearTimeout(refreshCropImport.timer);if(cropImportState.status==='running')refreshCropImport.timer=setTimeout(refreshCropImport,4000); }
  catch(error) { $('crop-import-status').textContent=translateMessage(error.message);if(cropImportState.status==='running')refreshCropImport.timer=setTimeout(refreshCropImport,4000); }
}
$('import-crops').addEventListener('click',async()=>{
  cropImportState={status:'running',log:''};renderCropImport();
  try { cropImportState=await api('/api/crop-import',{method:'POST'});renderCropImport();refreshCropImport(); }
  catch(error) { cropImportState={status:'error',log:error.message};renderCropImport(); }
});
refreshCropImport();

window.addEventListener('viewchange',()=>{if(location.hash==='#setup')refreshCropImport();});
