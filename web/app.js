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
    $('analysis-status').textContent = running ? t('Анализ выполняется. При первом запуске загружается модель — это может занять несколько минут. Результаты появятся автоматически. Вы можете переходить между вкладками.') : '';
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
function renderTraining() {
  $('start-training').disabled = trainingState.status === 'running';
  $('download-weights').disabled = !trainingState.weights_ready;
  const label = {idle:'Обучение ещё не запускалось.', running:'Обучение выполняется…', done:'Пробное обучение завершено.', error:'Обучение завершилось с ошибкой.'}[trainingState.status];
  $('training-status').textContent = `${t(label)} ${number(trainingState.epoch)} / ${number(trainingState.epochs)}`;
  $('training-progress').value = trainingState.epoch || 0;
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
$('download-weights').addEventListener('click', () => { location.href = '/api/training/weights'; });
refreshTraining();
setInterval(refreshTraining, 4000);
refreshSetup();
setInterval(refreshSetup, 4000);
tab(location.hash.slice(1));
renderResults();
refresh();
setInterval(refresh, 4000);
