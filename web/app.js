'use strict';
const $ = id => document.getElementById(id);
let jobs = [], selected = null, results = [], files = [], busy = false, uploading = false, loading = 0;
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => Number(value || 0).toLocaleString('ru-RU');
const date = value => new Date(value).toLocaleString('ru-RU', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
function notice(message) { $('notice').textContent = message; $('notice').hidden = !message; }
function tab(name) {
  if (!['dashboard','analysis','exports'].includes(name)) name = 'dashboard';
  document.querySelectorAll('.view').forEach(el => el.hidden = el.id !== name);
  document.querySelectorAll('[data-tab]').forEach(el => el.classList.toggle('active', el.dataset.tab === name));
  $('crumb').textContent = {dashboard:'Обзор полей',analysis:'Новый анализ',exports:'Выгрузка данных'}[name];
  history.replaceState(null, '', '#'+name);
}
document.querySelectorAll('[data-tab], [data-go]').forEach(el => el.addEventListener('click', () => tab(el.dataset.tab || el.dataset.go)));
window.addEventListener('hashchange', () => tab(location.hash.slice(1)));
$('today').textContent = new Date().toLocaleDateString('ru-RU', {day:'numeric',month:'long',year:'numeric'});
async function api(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Ошибка запроса');
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
  $('species-chart').innerHTML = entries.length ? entries.map(([name,count]) => `<div><div class="bar-heading"><span>${escapeHTML(name)}</span><span>${number(count)}</span></div><div class="bar-track"><div class="bar-fill" style="width:${count/max*100}%"></div></div></div>`).join('') : 'Пока нет определённых видов. Загрузите снимки или выберите другой анализ.';
  $('image-grid').innerHTML = results.length ? results.map((row,i) => `<button class="image-card" data-image="${i}"><img loading="lazy" src="/api/jobs/${selected}/image/${i}" alt="${escapeHTML(row.image)} — найденные объекты"><div><strong>${escapeHTML(row.image)}</strong><p>${number(row.total_weeds)} предполагаемых сорняков · ${number(row.unknown_count)} неизвестных</p></div></button>`).join('') : '<div class="empty-state"><span>⌖</span><h3>Здесь начинается наблюдение</h3><p>Добавьте первый снимок поля — результаты появятся здесь.</p><button class="secondary" id="empty-upload">Загрузить снимки</button></div>';
  $('empty-upload')?.addEventListener('click', () => tab('analysis'));
  document.querySelectorAll('[data-image]').forEach(button => button.addEventListener('click', () => {
    const i = Number(button.dataset.image);
    $('dialog-title').textContent = results[i].image;
    $('dialog-image').src = `/api/jobs/${selected}/image/${i}`;
    $('image-dialog').showModal();
  }));
  const job = jobs.find(job => job.id === selected);
  $('export-description').textContent = results.length ? `${job?.name || 'Анализ'} · ${number(results.length)} снимков · ${job ? date(job.created) : ''}` : 'Сначала запустите анализ или выберите готовый на странице обзора.';
  ['json','csv'].forEach(format => $('download-'+format).disabled = !results.length);
  const detections = results.flatMap(row => row.detections.map(d => ({...d,image:row.image})));
  $('preview-count').textContent = `${number(detections.length)} объектов`;
  $('preview-body').innerHTML = detections.length ? detections.slice(0,100).map(d => `<tr><td>${escapeHTML(d.image)}</td><td>${escapeHTML(d.species === 'unknown' ? 'Неизвестный вид' : d.species)}</td><td>${escapeHTML(d.stage === 'unknown' ? 'Не определена' : d.stage)}</td><td>${Number(d.similarity_score).toFixed(2)}</td><td>${['x1','y1','x2','y2'].map(key => escapeHTML(d.bbox[key])).join(', ')}</td></tr>`).join('') : '<tr><td colspan="5" class="empty">Нет обнаружений. После завершения анализа файлы доступны даже при отсутствии объектов.</td></tr>';
}
async function refresh() {
  try {
    const previous = jobs;
    jobs = await api('/api/jobs');
    const running = jobs.find(job => job.status === 'running');
    busy = Boolean(running);
    updateFiles(false);
    $('history').innerHTML = jobs.length ? jobs.slice(0,5).map(job => `<button class="history-row" data-job="${job.id}"><span class="history-icon">▧</span><span><strong>${escapeHTML(job.name)}</strong><small>${date(job.created)}</small></span><span class="badge ${job.status === 'error' ? 'error-badge' : ''}">${{done:'Готово',running:'В работе',error:'Ошибка'}[job.status]}</span></button>`).join('') : 'Вы ещё не запускали анализ.';
    document.querySelectorAll('[data-job]').forEach(button => button.addEventListener('click', () => {
      const job = jobs.find(j => j.id === button.dataset.job);
      if (job.status === 'done') { notice(''); selectJob(job.id); }
      else if (job.status === 'error') notice(job.error || 'Анализ завершился с ошибкой.');
      else tab('analysis');
    }));
    const completed = jobs.filter(job => job.status === 'done');
    $('job-select').innerHTML = completed.length ? completed.map(job => `<option value="${job.id}">${escapeHTML(job.name)} · ${date(job.created)}</option>`).join('') : '<option value="">Нет завершённых анализов</option>';
    const newlyDone = jobs.find(job => job.status === 'done' && previous.some(old => old.id === job.id && old.status === 'running'));
    const newlyFailed = jobs.find(job => job.status === 'error' && previous.some(old => old.id === job.id && old.status === 'running'));
    if (newlyFailed) notice(newlyFailed.error || 'Анализ завершился с ошибкой.');
    if (newlyDone) { await selectJob(newlyDone.id); tab('dashboard'); }
    else if (!selected && completed.length) await selectJob(completed[0].id);
    else if (selected) $('job-select').value = selected;
    $('analysis-status').hidden = !running;
    $('analysis-status').textContent = running ? 'Анализ выполняется. При первом запуске загружается модель — это может занять несколько минут. Результаты появятся автоматически. Вы можете переходить между вкладками.' : '';
  } catch(error) { notice('Не удалось связаться с сервером. '+error.message); }
}
function updateFiles(render = true) {
  if (render) {
    $('file-list').innerHTML = files.map((file,i) => `<div class="file-row"><span>${escapeHTML(file.name)}</span><small>${(file.size/1024/1024).toFixed(1)} МБ</small><button data-remove="${i}" aria-label="Удалить ${escapeHTML(file.name)}">✕</button></div>`).join('');
    document.querySelectorAll('[data-remove]').forEach(button => button.addEventListener('click', () => { files.splice(Number(button.dataset.remove),1); updateFiles(); }));
  }
  $('file-total').textContent = files.length ? `${files.length} файлов · ${(files.reduce((sum,file) => sum+file.size,0)/1024/1024).toFixed(1)} МБ` : 'Файлы не выбраны';
  $('start-analysis').disabled = busy || uploading || !files.length;
  $('start-analysis').textContent = uploading ? 'Загрузка снимков…' : busy ? 'Анализ выполняется…' : 'Начать анализ ↗';
}
function addFiles(incoming) {
  const accepted = [...incoming];
  if (accepted.some(file => !/\.(jpe?g|png)$/i.test(file.name))) return notice('Выберите только JPG, JPEG или PNG.');
  const combined = [...files, ...accepted];
  if (combined.length > 20 || combined.reduce((sum,file) => sum+file.size,0) > 99*1024*1024) return notice('За один анализ можно загрузить до 20 файлов общим размером до 99 МБ.');
  files = combined; notice(''); updateFiles();
}
$('file-input').addEventListener('change', event => { addFiles(event.target.files); event.target.value=''; });
['dragenter','dragover'].forEach(type => $('dropzone').addEventListener(type, event => {event.preventDefault();$('dropzone').classList.add('drag');}));
['dragleave','drop'].forEach(type => $('dropzone').addEventListener(type, event => {event.preventDefault();$('dropzone').classList.remove('drag');}));
$('dropzone').addEventListener('drop', event => addFiles(event.dataTransfer.files));
$('start-analysis').addEventListener('click', async () => {
  uploading = true; updateFiles(false); notice('');
  const body = new FormData(); files.forEach(file => body.append('files',file));
  try { await api('/api/analyze', {method:'POST',body}); files=[]; updateFiles(); await refresh(); }
  catch(error) { notice(error.message); }
  finally { uploading=false; updateFiles(false); }
});
$('job-select').addEventListener('change', event => selectJob(event.target.value));
['json','csv'].forEach(format => $('download-'+format).addEventListener('click', () => { if(selected) location.href=`/api/jobs/${selected}/${format}`; }));
$('close-dialog').addEventListener('click', () => $('image-dialog').close());
tab(location.hash.slice(1));
refresh();
setInterval(refresh, 4000);
