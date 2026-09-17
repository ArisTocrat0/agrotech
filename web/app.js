'use strict';
const $ = id => document.getElementById(id);
let jobs = [], selected = null, results = [], files = [], busy = false, uploading = false, loading = 0;
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => Number(value || 0).toLocaleString(locale());
const date = value => new Date(value).toLocaleString(locale(), {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
let currentNotice = '';
function notice(message) { currentNotice = message; $('notice').textContent = translateMessage(message); $('notice').hidden = !message; }
function tab(name) {
  if (!['dashboard','analysis','exports','setup'].includes(name)) name = 'dashboard';
  document.querySelectorAll('.view').forEach(el => el.hidden = el.id !== name);
  document.querySelectorAll('[data-tab]').forEach(el => el.classList.toggle('active', el.dataset.tab === name));
  $('crumb').textContent = {dashboard:t('Обзор полей'),analysis:t('Новый анализ'),exports:t('Выгрузка данных'),setup:t('Подготовка')}[name];
  history.replaceState(null, '', '#'+name);
}
document.querySelectorAll('[data-tab], [data-go]').forEach(el => el.addEventListener('click', () => tab(el.dataset.tab || el.dataset.go)));
window.addEventListener('hashchange', () => tab(location.hash.slice(1)));
function renderToday() { $('today').textContent = new Date().toLocaleDateString(locale(), {day:'numeric',month:'long',year:'numeric'}); }
renderToday();
async function api(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || t('Ошибка запроса'));
  return body;
}
async function selectJob(id) {
  const version = ++loading;
  selected = id; results = []; renderResults();
  if (!id) return;
  try {
    const data = await api(`/api/jobs/${id}/results`);
    if (version !== loading) return;
    results = data; $('job-select').value = id; renderResults();
  } catch(error) { notice(error.message); }
}
function renderResults() {
  const species = {};
  results.forEach(row => Object.entries(row.counts_by_species || {}).forEach(([name,count]) => species[name] = (species[name] || 0)+count));
  $('stat-images').textContent = number(results.length);
  $('stat-weeds').textContent = number(results.reduce((sum,row) => sum+row.total_weeds,0));
  $('stat-species').textContent = number(Object.keys(species).length);
  $('stat-unknown').textContent = number(results.reduce((sum,row) => sum+(row.unknown_count || 0),0));
  const entries = Object.entries(species).sort((a,b) => b[1]-a[1]);
  const max = Math.max(1,...entries.map(x => x[1]));
  $('species-chart').innerHTML = entries.length ? entries.map(([name,count]) => `<div><div class="bar-heading"><span>${escapeHTML(name)}</span><span>${number(count)}</span></div><div class="bar-track"><div class="bar-fill" style="width:${count/max*100}%"></div></div></div>`).join('') : t('Пока нет определённых видов. Загрузите снимки или выберите другой анализ.');
  $('image-grid').innerHTML = results.length ? results.map((row,i) => `<button class="image-card" data-image="${i}"><img loading="lazy" src="/api/jobs/${selected}/image/${i}" alt="${escapeHTML(row.image)} — ${t("найденные объекты")}"><div><strong>${escapeHTML(row.image)}</strong><p>${number(row.total_weeds)} ${t("предполагаемых сорняков")} · ${number(row.unknown_count)} ${t("неизвестных")}</p></div></button>`).join('') : `<div class="empty-state"><span>⌖</span><h3>${t("Здесь начинается наблюдение")}</h3><p>${t("Добавьте первый снимок поля — результаты появятся здесь.")}</p><button class="secondary" id="empty-upload">${t("Загрузить снимки")}</button></div>`;
  results.forEach((row,i) => {
    const reviewed=row.detections.filter(d=>d.review).length,total=row.detections.length;
    const percent=total ? Math.round(reviewed/total*100) : 100;
    const content=document.querySelector(`[data-image="${i}"] div`); if (!content) return;
    const progress=document.createElement('span'); progress.className='card-progress';
    progress.innerHTML=`<i style="width:${percent}%"></i>`; content.append(progress);
    const label=document.createElement('small');label.textContent=`${t('Проверено')}: ${reviewed}/${total} · ${percent}%`;content.append(label);
  });
  $('empty-upload')?.addEventListener('click', () => tab('analysis'));
  document.querySelectorAll('[data-image]').forEach(button => button.addEventListener('click', () => {
    openReview(Number(button.dataset.image));
  }));
  const job = jobs.find(job => job.id === selected);
  $('export-description').textContent = results.length ? `${(job ? jobName(job) : t('Анализ'))} · ${number(results.length)} ${t("снимков")} · ${job ? date(job.created) : ''}` : t('Сначала запустите анализ или выберите готовый на странице обзора.');
  ['json','csv','archive'].forEach(format => $('download-'+format).disabled = !results.length);
  $('download-pseudo').disabled = !results.length || selected === 'cli';
  const detections = results.flatMap(row => row.detections.map(d => ({...d,image:row.image})));
  $('preview-count').textContent = `${number(detections.length)} ${t("объектов")}`;
  $('preview-body').innerHTML = detections.length ? detections.slice(0,100).map(d => `<tr><td>${escapeHTML(d.image)}</td><td>${escapeHTML(d.species === 'unknown' ? t('Неизвестный вид') : d.species)}</td><td>${escapeHTML(d.stage === 'unknown' ? t('Не определена') : d.stage)}</td><td>${Number(d.similarity_score).toLocaleString(locale(), {minimumFractionDigits:2, maximumFractionDigits:2})}</td><td>${['x1','y1','x2','y2'].map(key => escapeHTML(d.bbox[key])).join(', ')}</td></tr>`).join('') : `<tr><td colspan="5" class="empty">${t("Нет обнаружений. После завершения анализа файлы доступны даже при отсутствии объектов.")}</td></tr>`;
  if ($('metric-details') && !$('metric-details').hidden) showMetricDetails($('metric-details').dataset.metric);
}
const metricCards=[...document.querySelectorAll('.metrics article')];
const metricDetails=document.createElement('section');metricDetails.id='metric-details';metricDetails.className='panel metric-details';metricDetails.hidden=true;document.querySelector('.metrics').after(metricDetails);
metricCards.forEach((card,index)=>{card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-expanded','false');card.dataset.metric=['images','weeds','species','unknown'][index];card.addEventListener('click',()=>showMetricDetails(card.dataset.metric));card.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();showMetricDetails(card.dataset.metric);}});});
function showMetricDetails(metric) {
  const titles={images:'Обработанные снимки',weeds:'Предполагаемые сорняки',species:'Найденные виды',unknown:'Объекты, которые нужно проверить'};
  metricCards.forEach(card=>{const active=card.dataset.metric===metric;card.classList.toggle('selected',active);card.setAttribute('aria-expanded',String(active));});
  let rows=[];
  if(metric==='species'||metric==='weeds'){const counts={};results.flatMap(row=>row.detections).filter(d=>d.kind==='weed'&&d.species!=='unknown').forEach(d=>counts[d.species]=(counts[d.species]||0)+1);rows=Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([name,count])=>`<li><span>${escapeHTML(name)}</span><strong>${number(count)}</strong></li>`);}
  else rows=results.map((row,index)=>{const value=metric==='unknown'?(row.unknown_count||0):metric==='images'?(row.detections?.length||0):(row.total_weeds||0);const suffix=metric==='images'?'объектов':metric==='unknown'?'на проверку':'сорняков';return `<li><span>${escapeHTML(row.image)}<small>${number(value)} ${suffix}</small></span><button class="secondary" data-open-image="${index}" data-find-unknown="${metric==='unknown'}">Открыть →</button></li>`;});
  metricDetails.dataset.metric=metric;metricDetails.hidden=false;metricDetails.innerHTML=`<div class="metric-detail-head"><div><span class="eyebrow">ДЕТАЛИЗАЦИЯ</span><h2>${titles[metric]}</h2></div><button class="metric-close" aria-label="Закрыть">✕</button></div><ul>${rows.join('')||'<li class="empty">Данных пока нет</li>'}</ul>`;
  metricDetails.querySelector('.metric-close').addEventListener('click',()=>{metricDetails.hidden=true;metricCards.forEach(card=>{card.classList.remove('selected');card.setAttribute('aria-expanded','false');});});
  metricDetails.querySelectorAll('[data-open-image]').forEach(button=>button.addEventListener('click',()=>{const index=Number(button.dataset.openImage);openReview(index);if(button.dataset.findUnknown==='true'){const found=results[index].detections.findIndex(d=>d.kind==='unknown');if(found>=0){reviewDetection=found;renderReview();}}}));
}
function renderJobs() {
    $('history').innerHTML = jobs.length ? jobs.slice(0,5).map(job => `<button class="history-row" data-job="${job.id}"><span class="history-icon">▧</span><span><strong>${escapeHTML(jobName(job))}</strong><small>${date(job.created)}</small></span><span class="badge ${job.status === 'error' ? 'error-badge' : ''}">${{done:t('Готово'),running:t('В работе'),error:t('Ошибка')}[job.status]}</span></button>`).join('') : t('Вы ещё не запускали анализ.');
    document.querySelectorAll('[data-job]').forEach(button => button.addEventListener('click', () => {
      const job = jobs.find(j => j.id === button.dataset.job);
      if (job.status === 'done') { notice(''); selectJob(job.id); }
      else if (job.status === 'error') notice(job.error || t('Анализ завершился с ошибкой.'));
      else tab('analysis');
    }));
    const completed = jobs.filter(job => job.status === 'done');
    $('job-select').innerHTML = completed.length ? completed.map(job => `<option value="${job.id}">${escapeHTML(jobName(job))} · ${date(job.created)}</option>`).join('') : `<option value="">${t("Нет завершённых анализов")}</option>`;
    if (selected) $('job-select').value = selected;
    renderLogJobs();
}
function renderStatus() {
  const running = jobs.some(job => job.status === 'running');
    $('analysis-status').hidden = !running;
    $('analysis-status').textContent = running ? t('Анализ выполняется локально. Загрузка модели из интернета возможна только при включённом разрешении. Результаты появятся автоматически.') : '';
}
async function refresh() {
  try {
    const previous = jobs;
    jobs = await api('/api/jobs');
    const running = jobs.find(job => job.status === 'running');
    busy = Boolean(running);
    updateFiles(false);
    renderJobs();
    const completed = jobs.filter(job => job.status === 'done');
    const newlyDone = jobs.find(job => job.status === 'done' && previous.some(old => old.id === job.id && old.status === 'running'));
    const newlyFailed = jobs.find(job => job.status === 'error' && previous.some(old => old.id === job.id && old.status === 'running'));
    if (newlyFailed) notice(newlyFailed.error || t('Анализ завершился с ошибкой.'));
    if (newlyDone) { await selectJob(newlyDone.id); tab('dashboard'); }
    else if (!selected && completed.length) await selectJob(completed[0].id);
    else if (selected) $('job-select').value = selected;
    renderStatus();
    await updateLog();
  } catch(error) { notice(t('Не удалось связаться с сервером.')+' '+error.message); }
}
function updateFiles(render = true) {
  if (render) {
    $('file-list').innerHTML = files.map((file,i) => `<div class="file-row"><span>${escapeHTML(file.name)}</span><small>${(file.size/1024/1024).toLocaleString(locale(), {maximumFractionDigits:1})} ${t("МБ")}</small><button data-remove="${i}" aria-label="${t('Удалить')} ${escapeHTML(file.name)}">✕</button></div>`).join('');
    document.querySelectorAll('[data-remove]').forEach(button => button.addEventListener('click', () => { files.splice(Number(button.dataset.remove),1); updateFiles(); }));
  }
  $('file-total').textContent = files.length ? `${files.length} ${t("файлов")} · ${(files.reduce((sum,file) => sum+file.size,0)/1024/1024).toLocaleString(locale(), {maximumFractionDigits:1})} ${t("МБ")}` : t('Файлы не выбраны');
  $('start-analysis').disabled = busy || uploading || !files.length;
  $('start-analysis').textContent = uploading ? t('Загрузка снимков…') : busy ? t('Анализ выполняется…') : t('Начать анализ ↗');
}
function addFiles(incoming) {
  const accepted = [...incoming];
  if (accepted.some(file => !/\.(jpe?g|png)$/i.test(file.name))) return notice(t('Выберите только JPG, JPEG или PNG.'));
  const combined = [...files, ...accepted];
  if (combined.length > 20 || combined.reduce((sum,file) => sum+file.size,0) > 99*1024*1024) return notice(t('За один анализ можно загрузить до 20 файлов общим размером до 99 МБ.'));
  files = combined; notice(''); updateFiles();
}
$('file-input').addEventListener('change', event => { addFiles(event.target.files); event.target.value=''; });
['dragenter','dragover'].forEach(type => $('dropzone').addEventListener(type, event => {event.preventDefault();$('dropzone').classList.add('drag');}));
['dragleave','drop'].forEach(type => $('dropzone').addEventListener(type, event => {event.preventDefault();$('dropzone').classList.remove('drag');}));
$('dropzone').addEventListener('drop', event => addFiles(event.dataTransfer.files));
const gpuPreset=document.createElement('button');gpuPreset.type='button';gpuPreset.className='secondary gpu-preset';gpuPreset.textContent='⚡ GPU-профиль';$('dropzone').before(gpuPreset);
gpuPreset.addEventListener('click',()=>{const form=$('analysis-options');form.querySelector('[name=device]').value='cuda';form.querySelector('[name=tile_size]').value='1024';form.querySelector('[name=overlap]').value='0.15';form.querySelector('[name=batch_size]').value='64';form.querySelector('[name=debug]').checked=false;notice('Включён GPU-профиль: CUDA, batch 64, overlap 0.15.');});
$('start-analysis').addEventListener('click', async () => {
  const options = [...document.querySelectorAll('#analysis-options [name]')];
  if (options.some(input => !input.reportValidity())) return;
  uploading = true; updateFiles(false); notice('');
  const body = new FormData(); files.forEach(file => body.append('files',file));
  options.forEach(input => body.append(input.name, input.type === 'checkbox' ? String(input.checked) : input.value));
  try { await api('/api/analyze', {method:'POST',body}); files=[]; updateFiles(); await refresh(); }
  catch(error) { notice(error.message); }
  finally { uploading=false; updateFiles(false); }
});
$('job-select').addEventListener('change', event => selectJob(event.target.value));
['json','csv'].forEach(format => $('download-'+format).addEventListener('click', () => { if(selected) location.href=`/api/jobs/${selected}/${format}`; }));
$('close-dialog').addEventListener('click', () => $('image-dialog').close());
document.querySelectorAll('[data-language]').forEach(button => button.addEventListener('click', () => {
  language = button.dataset.language;
  try { localStorage.setItem('olzha-language', language); } catch (_) {}
  translatePage();
  renderToday();
  tab(location.hash.slice(1));
  renderJobs();
  renderResults();
  updateFiles();
  renderStatus();
  notice(currentNotice);
  renderReferences();
  renderCheck();
  renderReferenceStatus();
  renderTraining();
  if ($('image-dialog').open) renderReview();
  renderCropImport();
}));
let references = [], checkState = {status:'idle', log:''}, referenceMessage = '', logSelection = '', logVersion = 0;
function renderReferences() {
  $('reference-body').innerHTML = references.length ? references.map(row => `<tr><td>${escapeHTML(row.species)}</td><td>${escapeHTML(row.stage)}</td><td>${t(row.kind === 'crop' ? 'Культура' : 'Сорняк')}</td><td>${number(row.count)}</td></tr>`).join('') : `<tr><td colspan="3">${t('Пока нет эталонов. Добавьте фотографии выше.')}</td></tr>`;
}
function renderReferenceStatus() { $('reference-status').textContent = translateMessage(referenceMessage); }
function renderCheck() {
  $('run-check').disabled = checkState.status === 'running';
  $('check-status').textContent = t({idle:'Проверка ещё не запускалась.', running:'Проверка выполняется…', done:'Проверка пройдена.', error:'Проверка выявила ошибки. Подробности ниже.'}[checkState.status]);
  $('check-log').hidden = !checkState.log;
  $('check-log').textContent = checkState.log;
}
async function refreshSetup() {
  try {
    [references, checkState] = await Promise.all([api('/api/references'), api('/api/check')]);
    renderReferences(); renderCheck();
  } catch(error) { notice(error.message); }
}
$('reference-form').addEventListener('submit', async event => {
  event.preventDefault();
  const body = new FormData(event.currentTarget), photos = body.getAll('files');
  if (photos.length > 20 || photos.reduce((sum,file) => sum + file.size, 0) > 99*1024*1024) {
    referenceMessage = 'За один анализ можно загрузить до 20 файлов общим размером до 99 МБ.';
    renderReferenceStatus(); return;
  }
  $('save-references').disabled = true;
  referenceMessage = 'Сохранение…'; renderReferenceStatus();
  try {
    references = await api('/api/references', {method:'POST', body});
    $('reference-form').reset();
    referenceMessage = 'Эталоны сохранены. Можно запускать анализ.';
    renderReferences();
  } catch(error) { referenceMessage = error.message; }
  finally { $('save-references').disabled = false; renderReferenceStatus(); }
});
$('run-check').addEventListener('click', async () => {
  checkState = {status:'running',log:''}; renderCheck();
  try { checkState = await api('/api/check', {method:'POST'}); }
  catch(error) { checkState = {status:'error',log:error.message}; }
  renderCheck();
});
function renderLogJobs() {
  if (!jobs.some(job => job.id === logSelection)) logSelection = jobs[0]?.id || '';
  $('log-job').innerHTML = jobs.length ? jobs.map(job => `<option value="${job.id}">${escapeHTML(jobName(job))} · ${date(job.created)}</option>`).join('') : `<option value="">${t('Нет анализов')}</option>`;
  $('log-job').value = logSelection;
  if (!logSelection) $('job-log').textContent = t('Выберите анализ для просмотра журнала.');
}
async function updateLog() {
  const version = ++logVersion;
  if (!logSelection) return;
  try {
    const data = await api(`/api/jobs/${logSelection}/log`);
    if (version === logVersion) $('job-log').textContent = data.log || t('Журнал пока пуст.');
  } catch(error) { if (version === logVersion) $('job-log').textContent = translateMessage(error.message); }
}
$('log-job').addEventListener('change', event => { logSelection = event.target.value; updateLog(); });
['archive','pseudo'].forEach(format => $('download-'+format).addEventListener('click', async () => {
  if (!selected) return;
  const jobId = selected;
  $('download-'+format).disabled = true;
  try {
    const response = await fetch(`/api/jobs/${jobId}/${format}`);
    if (!response.ok) { const data = await response.json(); throw new Error(data.error); }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url; link.download = `${format}-${jobId}.zip`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch(error) { notice(error.message); }
  finally { renderResults(); }
}));
let trainingState = {status:'idle', epoch:0, epochs:5};
const trainingPanel=document.querySelector('.training-panel');
const mlFlow=document.createElement('div');mlFlow.className='ml-flow';mlFlow.innerHTML='<div><b>01</b><span><strong>Анализ</strong><small>DINOv2 + GPU</small></span></div><i>→</i><div><b>02</b><span><strong>Проверка</strong><small>Решения агронома</small></span></div><i>→</i><div><b>03</b><span><strong>Обучение</strong><small>YOLO на H100</small></span></div>';
trainingPanel.before(mlFlow);
const fullTraining=document.createElement('button');fullTraining.id='start-full-training';fullTraining.className='primary full-training';fullTraining.textContent='⚡ Начать полное обучение';
document.querySelector('.training-actions').prepend(fullTraining);
const trainingReadiness=document.createElement('div');trainingReadiness.id='training-readiness';trainingReadiness.className='readiness';document.querySelector('.training-actions').before(trainingReadiness);
function renderTraining() {
  $('start-training').disabled = trainingState.status === 'running';
  fullTraining.disabled = trainingState.status === 'running' || !trainingState.full_ready;
  $('download-weights').disabled = !trainingState.weights_ready;
  const label = {idle:'Обучение ещё не запускалось.', running:'Обучение выполняется…', done:trainingState.mode==='full'?'Полное GPU-обучение завершено.':'Пробное обучение завершено.', error:'Обучение завершилось с ошибкой.'}[trainingState.status];
  const percent=trainingState.percent ?? Math.round(100*(trainingState.epoch||0)/Math.max(1,trainingState.epochs||1));
  $('training-status').textContent = `${t(label)} ${percent}% · ${number(trainingState.epoch)} / ${number(trainingState.epochs)} эпох`;
  $('training-progress').max = trainingState.epochs || 1;
  $('training-progress').value = trainingState.epoch || 0;
  trainingReadiness.className=`readiness ${trainingState.full_ready?'ready':'waiting'}`;
  trainingReadiness.innerHTML=trainingState.full_ready?'<b>✓ Датасет готов</b><span>Train/val проверены · H100 · 150 эпох · AMP</span>':'<b>○ Нужна проверенная разметка</b><span>Завершите проверку и создайте yolo_dataset/verified/dataset.yaml</span>';
  $('training-log').hidden = !trainingState.log && !trainingState.error;
  $('training-log').textContent = trainingState.log || translateMessage(trainingState.error || '');
}
async function refreshTraining() {
  try { trainingState = await api('/api/training'); renderTraining(); }
  catch(error) { $('training-status').textContent = translateMessage(error.message); }
}
$('start-training').addEventListener('click', async () => {
  trainingState = {status:'running',epoch:0,epochs:5}; renderTraining();
  try { trainingState = await api('/api/training', {method:'POST'}); }
  catch(error) { trainingState = {status:'error',epoch:0,epochs:5,error:error.message}; }
  renderTraining();
});
fullTraining.addEventListener('click',async()=>{trainingState={status:'running',mode:'full',epoch:0,epochs:150,percent:0,full_ready:true};renderTraining();try{trainingState=await api('/api/training/full',{method:'POST'});}catch(error){trainingState={status:'error',mode:'full',epoch:0,epochs:150,percent:0,full_ready:true,error:error.message};}renderTraining();});
$('download-weights').addEventListener('click', () => { location.href = '/api/training/weights'; });
refreshTraining();
setInterval(refreshTraining, 4000);
refreshSetup();
setInterval(refreshSetup, 4000);
tab(location.hash.slice(1));
renderResults();
refresh();
setInterval(refresh, 4000);
