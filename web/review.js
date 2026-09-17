'use strict';
let reviewImage = 0, reviewDetection = 0, reviewSaving = false, reviewJob = null;
const kindLabels = {weed:'Сорняк',crop:'Культура',unknown:'Проверить',not_plant:'Не растение'};
const kindColors = {weed:'#ff3fa4',crop:'#00d9ff',unknown:'#ffd600',not_plant:'#ffffff'};
function openReview(index) {
  reviewImage = index; reviewDetection = 0; reviewJob = selected;
  $('dialog-title').textContent = results[index].image;
  $('dialog-image').src = `/api/jobs/${reviewJob}/source/${index}`;
  $('review-zoom').value = 1; $('review-frame').style.width = '100%';
  $('review-gsd').value = results[index].gsd_cm || '';
  $('review-message').textContent = '';
  $('image-dialog').showModal(); renderReview();
}
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
  $('review-name').textContent = d ? detectionLabel(d) : t('Нет обнаружений');
  $('review-details').textContent = d ? `${t('Сходство')}: ${Number(d.similarity_score).toFixed(2)} · ${t('Класс')}: ${d.weed_class || '—'} · ${t({annual:'Малолетний',perennial:'Многолетний'}[d.lifecycle] || 'Не определена')}${d.review ? ' · '+t('Проверено вручную') : ''}` : '';
  $('review-counter').textContent = `${d ? reviewDetection+1 : 0} / ${row.detections.length} · ${t('Проверено')}: ${row.detections.filter(d=>d.review && d.review!=='unknown').length}`;
  document.querySelectorAll('[data-decision]').forEach(button => button.disabled=reviewSaving || !d);
  $('review-prev').disabled=reviewSaving || reviewDetection<=0;
  $('review-next').disabled=reviewSaving || reviewDetection>=row.detections.length-1;
  const a = row.agronomy || {};
  const level = {scale_required:'Нужен масштаб',low:'Слабая засорённость',medium:'Средняя засорённость',high:'Сильная засорённость',critical:'Критическая угроза'};
  const density = a.area_m2 ? `${t('Площадь')}: ${a.area_m2.toFixed(2)} м² · ${t('Малолетние')}: ${a.annual_per_m2.toFixed(2)}/м² · ${t('Многолетние')}: ${a.perennial_per_m2.toFixed(2)}/м²` : t('Для плотности укажите масштаб');
  $('review-agronomy').textContent = `${t('Ряды')}: ${row.rows?.count ?? t('Не определены')} · ${t(level[a.level] || 'Нужен масштаб')} · ${density} · ${t('Культур')}: ${row.crop_count || 0} · ${t('Сорняков без агрокласса')}: ${a.unclassified_weeds || 0}`;
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
    $('review-message').textContent=t('Решение сохранено'); renderResults();
  } catch(error) { $('review-message').textContent=translateMessage(error.message); }
  finally { reviewSaving=false; renderReview(); }
}
document.querySelectorAll('[data-decision]').forEach(button=>button.addEventListener('click',()=>decide(button.dataset.decision)));
$('review-prev').addEventListener('click',()=>{ reviewDetection=Math.max(0,reviewDetection-1);renderReview(); });
$('review-next').addEventListener('click',()=>{ reviewDetection=Math.min(results[reviewImage].detections.length-1,reviewDetection+1);renderReview(); });
$('review-zoom').addEventListener('input',()=>{ $('review-frame').style.width=`${Number($('review-zoom').value)*100}%`; });
$('show-rows').addEventListener('change',renderReview);
$('image-dialog').addEventListener('keydown',event=>{
  if (/INPUT|SELECT|TEXTAREA/.test(event.target.tagName)) return;
  const decision = {'1':'weed','2':'crop','3':'not_plant','4':'unknown'}[event.key];
  if (decision) { event.preventDefault();decide(decision); }
});
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
  try { cropImportState=await api('/api/crop-import');renderCropImport(); }
  catch(error) { $('crop-import-status').textContent=translateMessage(error.message); }
}
$('import-crops').addEventListener('click',async()=>{
  cropImportState={status:'running',log:''};renderCropImport();
  try { cropImportState=await api('/api/crop-import',{method:'POST'});renderCropImport(); }
  catch(error) { cropImportState={status:'error',log:error.message};renderCropImport(); }
});
refreshCropImport();setInterval(refreshCropImport,4000);
