'use strict';
// Settings view: references, diagnostics and training.
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
  clearTimeout(refreshSetup.timer);
  if(location.hash!=='#setup') return;
  try {
    [references, checkState] = await Promise.all([api('/api/references'), api('/api/check')]);
    renderReferences(); renderCheck();clearTimeout(refreshSetup.timer);if(checkState.status==='running')refreshSetup.timer=setTimeout(refreshSetup,4000);
  } catch(error) { showError(error.message);if(checkState.status==='running')refreshSetup.timer=setTimeout(refreshSetup,4000); }
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
  renderCheck();refreshSetup();
});
function renderLogJobs() {
  if (!jobs.some(job => job.id === logSelection)) logSelection = jobs[0]?.id || '';
  $('log-job').innerHTML = jobs.length ? jobs.map(job => `<option value="${job.id}">${escapeHTML(jobName(job))} · ${date(job.created)}</option>`).join('') : `<option value="">${t('Нет анализов')}</option>`;
  $('log-job').value = logSelection;
  if (!logSelection) $('job-log').textContent = t('Выберите анализ для просмотра журнала.');
}
async function updateLog() {
  if(location.hash!=='#setup') return;
  const version = ++logVersion;
  if (!logSelection) return;
  try {
    const data = await api(`/api/jobs/${logSelection}/log`);
    if (version === logVersion) $('job-log').textContent = data.log || t('Журнал пока пуст.');
  } catch(error) { if (version === logVersion) $('job-log').textContent = translateMessage(error.message); }
}
$('log-job').addEventListener('change', event => { logSelection = event.target.value; updateLog(); });

let trainingState = {status:'idle', epoch:0, epochs:5};
const trainingPanel=document.querySelector('.training-panel');
const mlFlow=document.createElement('div');mlFlow.className='ml-flow';mlFlow.innerHTML=`<div><b>01</b><span><strong>${t('Анализ')}</strong><small>DINOv2 + GPU</small></span></div><i>→</i><div><b>02</b><span><strong>${t('Проверка')}</strong><small>${t('Решения агронома')}</small></span></div><i>→</i><div><b>03</b><span><strong>${t('Обучение')}</strong><small>${t('YOLO на H100')}</small></span></div>`;
trainingPanel.before(mlFlow);
const fullTraining=document.createElement('button');fullTraining.id='start-full-training';fullTraining.className='primary full-training';fullTraining.textContent=t('⚡ Начать полное обучение');
document.querySelector('.training-actions').prepend(fullTraining);
const trainingReadiness=document.createElement('div');trainingReadiness.id='training-readiness';trainingReadiness.className='readiness';document.querySelector('.training-actions').before(trainingReadiness);
const setupView=$('setup');setupView.querySelector('.page-heading h1').textContent=t('Настройки');setupView.querySelector('.page-heading .muted').textContent=t('Эталоны и технические инструменты для администратора.');

const setupGrid=setupView.querySelector('.dashboard-grid'),checkPanel=setupGrid.children[1];
setupView.append(checkPanel);
technicalSection('Диагностика',[checkPanel,document.querySelector('.job-log-panel')]);
const referencePanel=setupGrid.children[0], referenceList=$('reference-body').closest('.panel');
setupView.append(referencePanel);technicalSection('Эталоны',[referencePanel,referenceList],true);setupGrid.remove();
const computePanel=document.createElement('article');computePanel.className='panel';computePanel.append(advancedHint.cloneNode(true),$('analysis-options'));setupView.append(computePanel);
technicalSection('Анализ и вычисления',[computePanel]);
const settingsLink=document.createElement('button');settingsLink.className='secondary';settingsLink.textContent=t('Анализ и вычисления');settingsLink.addEventListener('click',()=>{tab('setup');computePanel.parentElement.open=true;computePanel.scrollIntoView();});advanced.append(settingsLink);
technicalSection('ML / Обучение',[mlFlow,trainingPanel]);

function renderTraining() {
  $('start-training').disabled = trainingState.status === 'running';
  fullTraining.disabled = trainingState.status === 'running' || !trainingState.full_ready;
  $('download-weights').disabled = !trainingState.weights_ready;
  const label = {idle:'Обучение ещё не запускалось.', running:'Обучение выполняется…', done:trainingState.mode==='full'?'Полное GPU-обучение завершено.':'Пробное обучение завершено.', error:'Обучение завершилось с ошибкой.'}[trainingState.status];
  const percent=trainingState.percent ?? Math.round(100*(trainingState.epoch||0)/Math.max(1,trainingState.epochs||1));
  $('training-status').textContent = `${t(label)} ${percent}% · ${number(trainingState.epoch)} / ${number(trainingState.epochs)} ${t('эпох')}`;
  $('training-progress').max = trainingState.epochs || 1;
  $('training-progress').value = trainingState.epoch || 0;
  trainingReadiness.className=`readiness ${trainingState.full_ready?'ready':'waiting'}`;
  trainingReadiness.innerHTML=trainingState.full_ready?`<b>${t('✓ Датасет готов')}</b><span>${t('Train/val проверены · H100 · 150 эпох · AMP')}</span>`:`<b>${t('○ Нужна проверенная разметка')}</b><span>${t('Завершите проверку и создайте')} yolo_dataset/verified/dataset.yaml</span>`;
  $('training-log').hidden = !trainingState.log && !trainingState.error;
  $('training-log').textContent = trainingState.log || translateMessage(trainingState.error || '');
}
async function refreshTraining() {
  clearTimeout(refreshTraining.timer);
  if(location.hash!=='#setup') return;
  try { trainingState = await api('/api/training'); renderTraining();clearTimeout(refreshTraining.timer);if(trainingState.status==='running')refreshTraining.timer=setTimeout(refreshTraining,4000); }
  catch(error) { $('training-status').textContent = translateMessage(error.message);if(trainingState.status==='running')refreshTraining.timer=setTimeout(refreshTraining,4000); }
}
$('start-training').addEventListener('click', async () => {
  trainingState = {status:'running',epoch:0,epochs:5}; renderTraining();
  try { trainingState = await api('/api/training', {method:'POST'}); }
  catch(error) { trainingState = {status:'error',epoch:0,epochs:5,error:error.message}; }
  renderTraining();refreshTraining();
});
fullTraining.addEventListener('click',async()=>{trainingState={status:'running',mode:'full',epoch:0,epochs:150,percent:0,full_ready:true};renderTraining();try{trainingState=await api('/api/training/full',{method:'POST'});}catch(error){trainingState={status:'error',mode:'full',epoch:0,epochs:150,percent:0,full_ready:true,error:error.message};}renderTraining();refreshTraining();});
$('download-weights').addEventListener('click', () => { location.href = '/api/training/weights'; });
