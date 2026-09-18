'use strict';
const $ = id => document.getElementById(id);
let jobs = [], selected = null, results = [], files = [], busy = false, uploading = false, loading = 0;
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => Number(value || 0).toLocaleString(locale());
const date = value => new Date(value).toLocaleString(locale(), {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
let datasetPreparing = false;
let currentNotice = '';
function showError(details) {
  notice(t('Не удалось выполнить действие.'));
  const disclosure=document.createElement('details'),summary=document.createElement('summary'),body=document.createElement('pre');
  summary.textContent=t('Подробнее');body.textContent=details || '';disclosure.append(summary,body);$('notice').append(disclosure);
}
function notice(message) { currentNotice = message; $('notice').textContent = translateMessage(message); $('notice').hidden = !message; }
function tab(name) {
  if (!['dashboard','analysis','assistant','review','exports','setup'].includes(name)) name = 'dashboard';
  document.querySelectorAll('.view').forEach(el => el.hidden = el.id !== name);
  document.querySelectorAll('[data-tab]').forEach(el => el.classList.toggle('active', el.dataset.tab === name));
  $('crumb').textContent = {dashboard:t('Обзор'),analysis:t('Анализы'),assistant:'AI помощник агроному',review:t('Проверка'),exports:t('Отчёты'),setup:t('Настройки')}[name];
  history.replaceState(null, '', '#'+name);
  if(name==='setup') { refreshSetup();refreshTraining();updateLog(); }
  window.dispatchEvent(new Event('viewchange'));
}
const nav=document.querySelector('nav');
const navLabels={dashboard:t('Обзор'),analysis:t('Анализы'),assistant:'AI помощник',exports:t('Отчёты'),setup:t('Настройки')};
nav.querySelectorAll('[data-tab]').forEach(button=>{const label=navLabels[button.dataset.tab];if(label)button.lastChild.textContent=label;});
const reviewNav=document.createElement('button');reviewNav.dataset.tab='review';reviewNav.innerHTML=`<span>✓</span>${t('Проверка')}`;nav.querySelector('[data-tab="exports"]').before(reviewNav);
const reviewView=document.createElement('section');reviewView.id='review';reviewView.className='view';reviewView.hidden=true;reviewView.innerHTML=`<div class="page-heading"><div><p class="eyebrow">${t('КОНТРОЛЬ КАЧЕСТВА')}</p><h1>${t('Проверка находок')}<span class="green">.</span></h1><p class="muted">${t('Подтвердите или исправьте решения модели.')}</p></div></div><div id="review-queue"></div>`;
$('exports').before(reviewView);
document.querySelectorAll('[data-tab], [data-go]').forEach(el => el.addEventListener('click', () => tab(el.dataset.tab || el.dataset.go)));
window.addEventListener('hashchange', () => tab(location.hash.slice(1)));
function renderToday() { $('today').textContent = new Date().toLocaleDateString(locale(), {day:'numeric',month:'long',year:'numeric'}); }
renderToday();
async function selectJob(id) {
  const version = ++loading;
  selected = id; results = []; renderResults();
  if (!id) return;
  try {
    const data = await api(`/api/jobs/${id}/results`);
    if (version !== loading) return;
    results = data; $('job-select').value = id; renderResults();
  } catch(error) { showError(error.message); }
}
function renderResults() {
  const species = {};
  results.forEach(row => Object.entries(row.counts_by_species || {}).forEach(([name,count]) => species[name] = (species[name] || 0)+count));
  $('stat-images').textContent = number(results.length);
  const {total, reviewed, confirmed, pending, percent:reviewPercent}=reviewMetrics(results);
  const allDetections=results.flatMap(row=>row.detections);
  metricElements[2].querySelector('small').textContent=t(allDetections.some(d=>d.review) ? 'После ручной проверки' : 'Проверка ещё не выполнена');
  $('stat-weeds').textContent = number(allDetections.length);
  $('stat-species').textContent = number(confirmed);
  $('stat-unknown').textContent = `${reviewPercent}%`;
  $('stat-pending').textContent = number(pending);
  $('stat-review-detail').textContent=`${number(reviewed)} ${t('из')} ${number(allDetections.length)} ${t('объектов')}`;
  const entries = Object.entries(species).sort((a,b) => b[1]-a[1]);
  const max = Math.max(1,...entries.map(x => x[1]));
  $('species-chart').innerHTML = entries.length ? entries.map(([name,count]) => `<div><div class="bar-heading"><span>${escapeHTML(name)}</span><span>${number(count)}</span></div><div class="bar-track"><div class="bar-fill" style="width:${count/max*100}%"></div></div></div>`).join('') : t('Пока нет определённых видов. Загрузите снимки или выберите другой анализ.');
  $('image-grid').innerHTML = results.length ? results.map((row,i) => `<button class="image-card" data-image="${i}"><img loading="lazy" src="/api/jobs/${selected}/image/${i}" alt="${escapeHTML(row.image)} — ${t("найденные объекты")}"><div><strong>${escapeHTML(row.image)}</strong><p>${number(row.total_weeds)} ${t("предполагаемых сорняков")} · ${number(row.unknown_count)} ${t("неизвестных")}</p></div></button>`).join('') : `<div class="empty-state"><span>⌖</span><h3>${t("Здесь начинается наблюдение")}</h3><p>${t("Добавьте первый снимок поля — результаты появятся здесь.")}</p><button class="secondary" id="empty-upload">${t("Загрузить снимки")}</button></div>`;
  results.forEach((row,i) => {
    if (row.mode === 'automatic') return;
    const reviewed=row.detections.filter(d=>!isPending(d)).length,total=row.detections.length;
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
  $('preview-body').innerHTML = detections.length ? detections.slice(0,100).map(d => `<tr><td>${escapeHTML(d.image)}</td><td>${escapeHTML(d.species === 'unknown' ? t('Неизвестный вид') : d.species)}</td><td>${escapeHTML(d.stage === 'unknown' ? t('Не определена') : d.stage)}</td><td>${(d.similarity_score == null ? '—' : Number(d.similarity_score).toLocaleString(locale(), {minimumFractionDigits:2, maximumFractionDigits:2}))}</td><td>${['x1','y1','x2','y2'].map(key => escapeHTML(d.bbox[key])).join(', ')}</td></tr>`).join('') : `<tr><td colspan="5" class="empty">${t("Нет обнаружений. После завершения анализа файлы доступны даже при отсутствии объектов.")}</td></tr>`;
  if ($('metric-details') && !$('metric-details').hidden) showMetricDetails($('metric-details').dataset.metric);
  renderReviewQueue(pending,reviewed,allDetections.length);
  renderAutomaticResults();
  document.querySelector('.hero').classList.toggle('compact',jobs.some(job=>job.status==='done'));
}
const metricElements=document.querySelectorAll('.metrics article');
metricElements[0].querySelector('.metric-top').firstChild.textContent=t('Обработано');
metricElements[1].querySelector('.metric-top').firstChild.textContent=t('Обнаружено моделью');metricElements[1].querySelector('small').textContent=t('Все найденные объекты');
metricElements[2].querySelector('.metric-top').firstChild.textContent=t('Подтверждено сорняков');metricElements[2].querySelector('small').textContent=t('После ручной проверки');
metricElements[3].querySelector('.metric-top').firstChild.textContent=t('Проверено');metricElements[3].querySelector('small').id='stat-review-detail';
const pendingCard=document.createElement('article');pendingCard.innerHTML=`<div class="metric-top">${t('Требуют проверки')} <span>⌖</span></div><strong id="stat-pending">0</strong><small>${t('Непроверенные объекты')}</small>`;document.querySelector('.metrics').append(pendingCard);
const dashboardReview=document.createElement('div');dashboardReview.id='dashboard-review-cta';document.querySelector('.metrics').after(dashboardReview);
const metricCards=[...document.querySelectorAll('.metrics article')];
const metricDetails=document.createElement('section');metricDetails.id='metric-details';metricDetails.className='panel metric-details';metricDetails.hidden=true;document.querySelector('.metrics').after(metricDetails);
metricCards.forEach((card,index)=>{card.tabIndex=0;card.setAttribute('role','button');card.setAttribute('aria-expanded','false');card.dataset.metric=['images','detected','confirmed','reviewed','pending'][index];card.addEventListener('click',()=>index===4?continueReview():showMetricDetails(card.dataset.metric));card.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();index===4?continueReview():showMetricDetails(card.dataset.metric);}});});
function showMetricDetails(metric) {
  if (results.length && results.every(row => row.mode === 'automatic')) { metricDetails.hidden = true; tab('exports'); return; }
  const titles={images:t('Обработанные снимки'),detected:t('Объекты, найденные моделью'),confirmed:t('Подтверждённые сорняки'),reviewed:t('Прогресс проверки')};
  metricCards.forEach(card=>{const active=card.dataset.metric===metric;card.classList.toggle('selected',active);card.setAttribute('aria-expanded',String(active));});
  let rows=[];
  rows=results.map((row,index)=>{const detections=row.detections||[],value=metric==='images'?detections.length:metric==='detected'?detections.length:metric==='confirmed'?detections.filter(d=>d.review==='weed').length:detections.filter(d=>!isPending(d)).length;return `<li><span>${escapeHTML(row.image)}<small>${number(value)} ${t('объектов')}</small></span><button class="secondary" data-open-image="${index}">${t('Открыть')} →</button></li>`;});
  metricDetails.dataset.metric=metric;metricDetails.hidden=false;metricDetails.innerHTML=`<div class="metric-detail-head"><div><span class="eyebrow">${t('ДЕТАЛИЗАЦИЯ')}</span><h2>${titles[metric]}</h2></div><button class="metric-close" aria-label="${t('Закрыть')}">✕</button></div><ul>${rows.join('')||`<li class="empty">${t('Данных пока нет')}</li>`}</ul>`;
  metricDetails.querySelector('.metric-close').addEventListener('click',()=>{metricDetails.hidden=true;metricCards.forEach(card=>{card.classList.remove('selected');card.setAttribute('aria-expanded','false');});});
  metricDetails.querySelectorAll('[data-open-image]').forEach(button=>button.addEventListener('click',()=>{const index=Number(button.dataset.openImage);openReview(index);if(button.dataset.findUnknown==='true'){const found=results[index].detections.findIndex(d=>d.kind==='unknown');if(found>=0){reviewDetection=found;renderReview();}}}));
}
function firstPending(){return pendingTarget(results);}
function continueReview(){if(results.length && results.every(row=>row.mode==='automatic')){tab('review');return;}const target=firstPending();if(!target){notice(t('Все объекты этого анализа проверены.'));return;}openReview(target.image);reviewDetection=target.detection;renderReview();}
function renderReviewQueue(pending,reviewed,total){if(!results.length){$('review-queue').textContent=t('Сначала выберите завершённый анализ.');dashboardReview.replaceChildren();return;}const complete=results.length>0&&pending===0;const content=`<article class="panel review-cta ${complete?'complete':''}"><div><span class="eyebrow">${t('ТЕКУЩИЙ АНАЛИЗ')}</span><h2>${complete?t('✓ Проверка завершена'):`${number(pending)} ${t('объектов ждут проверки')}`}</h2><p>${number(reviewed)} ${t('из')} ${number(total)} ${t('объектов уже проверено')}</p>${complete?`<p>${t('Один класс «сорняк». Минимум два разных снимка с подтверждёнными сорняками.')}</p>`:''}</div>${complete?`<button class="primary prepare-dataset" ${selected==='cli'?'disabled':''}>${t('Подготовить датасет для обучения')}</button>`:`<button class="primary continue-review">${t('Продолжить проверку')} →</button>`}</article>`;$('review-queue').innerHTML=content;dashboardReview.innerHTML=results.length?content:'';document.querySelectorAll('.continue-review').forEach(button=>button.addEventListener('click',continueReview));document.querySelectorAll('.prepare-dataset').forEach(button=>{button.disabled=datasetPreparing||selected==='cli';button.addEventListener('click',prepareDataset);});}
function renderJobs() {
    $('history').innerHTML = jobs.length ? jobs.slice(0,5).map(job => `<button class="history-row" data-job="${job.id}"><span class="history-icon">▧</span><span><strong>${escapeHTML(jobName(job))}</strong><small>${date(job.created)}</small></span><span class="badge ${job.status === 'error' ? 'error-badge' : ''}">${{done:t('Готово'),running:t('В работе'),error:t('Ошибка')}[job.status]}</span></button>`).join('') : t('Вы ещё не запускали анализ.');
    document.querySelectorAll('[data-job]').forEach(button => button.addEventListener('click', () => {
      const job = jobs.find(j => j.id === button.dataset.job);
      if (job.status === 'done') { notice(''); selectJob(job.id); }
      else if (job.status === 'error') showError(job.error);
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
    $('analysis-status').textContent = running ? t('Анализ выполняется. Результаты появятся автоматически.') : '';
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
    if (newlyFailed) showError(newlyFailed.error);
    if (newlyDone) { await selectJob(newlyDone.id); tab('dashboard'); }
    else if (!selected && completed.length) await selectJob(completed[0].id);
    else if (selected) $('job-select').value = selected;
    renderStatus();
    if(location.hash==='#setup') await updateLog();
    clearTimeout(refresh.timer);if(running)refresh.timer=setTimeout(refresh,4000);
  } catch(error) { showError(error.message);clearTimeout(refresh.timer);refresh.timer=setTimeout(refresh,4000); }
}
function updateFiles(render = true) {
  if (render) {
    $('file-list').innerHTML = files.map((file,i) => `<div class="file-row"><span>${escapeHTML(file.name)}</span><small>${(file.size/1024/1024).toLocaleString(locale(), {maximumFractionDigits:1})} ${t("МБ")}</small><button data-remove="${i}" aria-label="${t('Удалить')} ${escapeHTML(file.name)}">✕</button></div>`).join('');
    document.querySelectorAll('[data-remove]').forEach(button => button.addEventListener('click', () => { files.splice(Number(button.dataset.remove),1); updateFiles(); }));
  }
  $('file-total').textContent = files.length ? `${files.length} ${t("файлов")} · ${(files.reduce((sum,file) => sum+file.size,0)/1024/1024).toLocaleString(locale(), {maximumFractionDigits:1})} ${t("МБ")}` : t('Файлы не выбраны');
  $('file-input').disabled=uploading;
  document.querySelectorAll('[data-remove]').forEach(button=>button.disabled=uploading);
  $('start-analysis').disabled = busy || uploading || !files.length;
  $('start-analysis').textContent = uploading ? t('Загрузка снимков…') : busy ? t('Анализ выполняется…') : t('Начать анализ ↗');
}
function addFiles(incoming) {
  if(uploading) return;
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
const gpuPreset=document.createElement('button');gpuPreset.type='button';gpuPreset.className='secondary gpu-preset';gpuPreset.textContent=t('⚡ GPU-профиль');$('dropzone').before(gpuPreset);
gpuPreset.addEventListener('click',()=>{const form=$('analysis-options');form.querySelector('[name=device]').value='cuda';form.querySelector('[name=tile_size]').value='1024';form.querySelector('[name=overlap]').value='0.15';form.querySelector('[name=batch_size]').value='64';form.querySelector('[name=debug]').checked=false;notice(t('Включён GPU-профиль: CUDA, batch 64, overlap 0.15.'));});
const advanced=document.querySelector('.analysis-settings');advanced.querySelector('summary').textContent=t('Расширенные настройки');const advancedHint=document.createElement('p');advancedHint.className='muted advanced-hint';advancedHint.textContent=t('Для большинства анализов рекомендуем оставить параметры по умолчанию.');advanced.querySelector('summary').after(advancedHint);advanced.querySelector('.settings-grid').prepend(gpuPreset);
$('start-analysis').addEventListener('click', async () => {
  if (uploading || busy || !files.length) return;
  if (!$('field-crop').reportValidity()) return;
  const options = [...document.querySelectorAll('#analysis-options [name]')];
  if (options.some(input => !input.reportValidity())) return;
  uploading = true; updateFiles(false); notice('');
  const body = new FormData(); body.append('crop', $('field-crop').value); files.forEach(file => body.append('files',file));
  options.forEach(input => body.append(input.name, input.type === 'checkbox' ? String(input.checked) : input.value));
  try { await api('/api/analyze', {method:'POST',body}); files=[]; updateFiles(); await refresh(); }
  catch(error) { showError(error.message); }
  finally { uploading=false; updateFiles(false); }
});
$('job-select').addEventListener('change', event => selectJob(event.target.value));
['json','csv'].forEach(format => $('download-'+format).addEventListener('click', () => { if(selected) location.href=`/api/jobs/${selected}/${format}`; }));
$('close-dialog').addEventListener('click', () => $('image-dialog').close());
document.querySelectorAll('[data-language]').forEach(button => button.addEventListener('click', () => {
  language = button.dataset.language;
  try { localStorage.setItem('olzha-language', language); } catch (_) {}
  location.reload();
}));
['archive','pseudo'].forEach(format => $('download-'+format).addEventListener('click', async () => {
  if (!selected) return;
  const jobId = selected;
  $('download-'+format).disabled = true;
  try {
    const url = URL.createObjectURL(await api(`/api/jobs/${jobId}/${format}`, undefined, 'blob'));
    const link = document.createElement('a');
    link.href = url; link.download = `${format}-${jobId}.zip`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch(error) { showError(error.message); }
  finally { renderResults(); }
}));
const exportGrid=document.querySelector('.export-grid');
const jsonCard=$('download-json').closest('.panel'), csvCard=$('download-csv').closest('.panel'), archive=document.querySelector('.archive-panel');
csvCard.querySelector('.eyebrow').textContent=t('ДАННЫЕ ДЛЯ РАБОТЫ');
csvCard.querySelector('p').textContent=t('Таблица предсказаний и ручных решений для Excel.');
archive.querySelector('h2').textContent=t('Полный архив');
const developerPanel=document.createElement('article');developerPanel.className='panel';
developerPanel.append(jsonCard,$('download-pseudo'),archive.querySelector('.footnote'));
exportGrid.after(developerPanel);exportGrid.append(csvCard,archive);
technicalSection('ДЛЯ РАЗРАБОТЧИКОВ / ML',[developerPanel]);
window.addEventListener('DOMContentLoaded',()=>{tab(location.hash.slice(1));renderResults();refresh();}, {once:true});

window.addEventListener('focus',refresh);

async function prepareDataset() {
  if(datasetPreparing || !selected || selected==='cli') return;
  const job=selected;
  datasetPreparing=true;renderResults();notice(t('Подготовка датасета…'));
  try {
    const summary=await api(`/api/jobs/${job}/dataset`,{method:'POST'});
    tab('setup');
    trainingPanel.parentElement.open=true;
    await refreshTraining();
    notice(`${t('Датасет подготовлен.')} ${t('Обучающие снимки')}: ${summary.train_images}; ${t('Проверочные снимки')}: ${summary.val_images}. ${t('Класс: сорняк. Теперь можно запустить полное обучение.')}`);
    fullTraining.focus();
  } catch(error) { showError(translateMessage(error.message)); }
  finally { datasetPreparing=false;renderResults(); }
}

function renderAutomaticResults() {
  const automatic = results.length && results.every(row => row.mode === 'automatic');
  metricElements[2].querySelector('.metric-top').firstChild.textContent = t(automatic ? 'Предполагаемые сорняки' : 'Подтверждено сорняков');
  metricElements[3].querySelector('.metric-top').firstChild.textContent = t(automatic ? 'Культурные растения' : 'Проверено');
  pendingCard.querySelector('.metric-top').firstChild.textContent = t(automatic ? 'Не определено' : 'Требуют проверки');
  pendingCard.querySelector('small').textContent = t(automatic ? 'Модель воздержалась от ответа' : 'Непроверенные объекты');
  if (!automatic) return;
  const detections = results.flatMap(row => row.detections);
  $('stat-species').textContent = number(detections.filter(d => d.kind === 'weed').length);
  metricElements[2].querySelector('small').textContent = 'Результат модели, без ручного подтверждения';
  $('stat-unknown').textContent = number(detections.filter(d => d.kind === 'crop').length);
  $('stat-review-detail').textContent = results[0].crop;
  $('stat-pending').textContent = number(detections.filter(d => d.kind === 'unknown').length);
  const report = results[0].learning_report;
  const percent = value => value == null ? 'не измерена' : `${(100 * value).toFixed(1)}%`;
  const message = !results[0].crop_supported ? 'В датасете недостаточно фотографий выбранной культуры. Объекты оставлены неопределёнными.' : 'Анализ завершён. Ручная проверка необязательна.';
  dashboardReview.innerHTML = `<article class="panel"><h2>${escapeHTML(message)}</h2><p>Точность обнаружения на поле: не измерена. Цель: 90%.</p>${report ? `<p>Классификация эталонных фото: ${percent(report.accuracy)}; средняя по видам: ${percent(report.balanced_accuracy)}. Тест: ${number(report.count)} фото. Доля принятых ответов на тесте: ${percent(report.coverage)}.</p><p>Это проверка на фотографиях датасета, а не подтверждение 90% на снимках вашего поля.</p>` : ''}<p>Обучение обновляется автоматически при изменении локального датасета.</p></article>`;
  $('download-pseudo').disabled = true;
  $('review-queue').innerHTML = '<article class="panel"><h2>Проверка по желанию</h2><p>Результат уже доступен в обзоре и отчётах. Чтобы исправить отдельный объект, откройте фотографию в обзоре.</p></article>';
}
