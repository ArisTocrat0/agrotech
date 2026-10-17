'use strict';
// Deterministic checks; no network, model, browser dependency or generated detections.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ui = require('../web/environment.js');
const values = {confidence: '0.35', latitude: '', longitude: '', geodata: ''};
const limits = {max_files: 10, max_upload_bytes: 100 * 1024 * 1024};
const photo = {name: 'DJI_001.JPG', size: 1000};
const event = {class_name: 'fire', location: {latitude: 0, longitude: 0, source: 'operator_capture_position', precision: 'capture_position_not_object'}};
const path = '/api/environment/files/' + 'a'.repeat(32) + '/evidence/00_00000000_annotated.jpg';
assert.equal(ui.mediaKind('DJI_001.JPG'), 'image');
for (const name of ['file.mp4', 'file.mov', 'file.webp', 'file.jpg.exe', 'file.svg']) assert.equal(ui.mediaKind(name), null);
assert.throws(() => ui.validateUpload([], values, limits), /Выберите/);
assert.throws(() => ui.validateUpload([photo], values, null), /Лимиты/);
assert.throws(() => ui.validateUpload(Array.from({length: 11}, (_, n) => ({name: n + '.jpg', size: 1})), values, limits), /не более 10/);
assert.throws(() => ui.validateUpload([{...photo, size: limits.max_upload_bytes + 1}], values, limits), /размер/);
assert.throws(() => ui.validateUpload([{...photo, size: 0}], values, limits), /пуст/);
assert.throws(() => ui.validateUpload([photo, photo], values, limits), /Повторяется/);
assert.throws(() => ui.validateUpload([{name: 'x.mp4', size: 1}], values, limits), /Неподдерживаемый/);
for (const confidence of ['', 'NaN', 'Infinity', '0', '-1', '1.1']) assert.throws(() => ui.validateUpload([photo], {...values, confidence}, limits), /Порог/);
assert.deepEqual(ui.validateUpload([photo], values, limits), {confidence: 0.35, latitude: null, longitude: null, geodata: ''});
assert.deepEqual(ui.validateUpload([photo], {...values, latitude: '0', longitude: '0'}, limits), {confidence: 0.35, latitude: 0, longitude: 0, geodata: ''});
assert.throws(() => ui.validateUpload([photo], {...values, latitude: '0'}, limits), /обе координаты/);
assert.throws(() => ui.validateUpload([photo], {...values, latitude: '91', longitude: '10'}, limits), /широту/);
assert.throws(() => ui.validateUpload([photo], {...values, geodata: '{'}, limits), /корректным JSON/);
assert.throws(() => ui.validateUpload([photo], {...values, geodata: '[]'}, limits), /ожидается объект/);
assert.throws(() => ui.validateUpload([photo], {...values, geodata: '{"missing.jpg":{}}'}, limits), /невыбранный/);
const geodata = JSON.stringify({[photo.name]: {latitude: 0, longitude: 0, source: 'operator_capture_position'}});
assert.equal(ui.validateUpload([photo], {...values, geodata}, limits).geodata, geodata);
assert.throws(() => ui.validateUpload([photo], {...values, geodata, latitude: '0', longitude: '0'}, limits), /либо/);
for (const location of [{latitude: true, longitude: 0, source: 'operator_capture_position'}, {latitude: 0, longitude: 0}, {latitude: 0, longitude: 0, source: 'operator_capture_position', frames: []}]) {
  assert.throws(() => ui.validateUpload([photo], {...values, geodata: JSON.stringify({[photo.name]: location})}, limits), /Для фото/);
}
assert.equal(ui.captureLocation(event), event.location);
assert.equal(ui.captureLocation({location: {...event.location, source: 'embedded_gps_capture_position'}}).latitude, 0);
assert.equal(ui.captureLocation({location: {...event.location, precision: 'object'}}), null);
assert.equal(ui.captureLocation({location: {...event.location, source: 'invented'}}), null);
assert.equal(ui.captureLocation({location: {...event.location, latitude: NaN}}), null);
assert.deepEqual(ui.summarize([event, {class_name: 'trash', location: null}, {class_name: 'smoke'}]), {trash: 1, fire: 1, smoke: 1, located: 1});
assert.deepEqual(ui.projectLocations([{location: null}]), {points: []});
const locations = ui.projectLocations([event, event]);
assert.equal(locations.points.length, 2);
assert.equal(locations.points[0].x, locations.points[1].x, 'Co-located observations must never be jittered into fake positions');
assert.equal(locations.points[0].y, locations.points[1].y);
assert.ok(Number.isFinite(ui.projectLocations([{location: {...event.location, latitude: 90, longitude: 180}}]).points[0].x));
assert.equal(ui.safeAssetURL(path, 'http://localhost:8000'), 'http://localhost:8000' + path);
for (const value of ['https://evil.example/a.jpg', '//evil.example/a.jpg', '/api/environment/assistant', path + '?leak=1', '/api/environment/files/' + 'a'.repeat(32) + '/../secret.jpg', 'javascript:alert(1)']) assert.equal(ui.safeAssetURL(value, 'http://localhost:8000'), null);
assert.equal(ui.safeAssetURL('/api/environment/files/' + 'a'.repeat(32) + '/events.geojson', 'http://localhost:8000'), 'http://localhost:8000/api/environment/files/' + 'a'.repeat(32) + '/events.geojson');
const html = fs.readFileSync('web/environment.html', 'utf8');
const js = fs.readFileSync('web/environment.js', 'utf8');
assert.match(html, /lang="ru"/);
assert.match(html, /absence-does-not-prove-safety|отсутствие находок не доказывает безопасность/);
assert.match(html, /accept="\.jpg,\.jpeg,\.png"/);
assert.doesNotMatch(html, /\s(?:onclick|onload|style)=|<script(?![^>]*src=)/i);
assert.doesNotMatch(html, /https?:\/\/|видео|sample-interval|telemetry/i);
assert.doesNotMatch(js, /innerHTML|insertAdjacentHTML|eval\(/);
assert.match(js, /state\.submitting \|\| state\.uncertainSubmission/);
assert.match(js, /version !== state\.selectionVersion/);
assert.match(js, /MAX_READ_FAILURES = 3/);
assert.match(js, /POLL_WINDOW_MS = 10 \* 60 \* 1000/);
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
assert.equal(new Set(ids).size, ids.length, 'HTML IDs must be unique');
for (const match of js.matchAll(/\$\('([^']+)'\)/g)) assert.ok(ids.includes(match[1]), `JS references missing HTML id ${match[1]}`);
assert.equal((fs.readFileSync('web/index.html', 'utf8').match(/href="\/environment\.html"/g) || []).length, 1);
console.log('PASS: photos-only upload validation, limits, original names, geodata provenance, true zero coordinates, no fabricated positions, same-origin evidence allowlist, CSP/static contracts, bounded polling and markup references');

// Exercise the actual controller against a minimal deterministic DOM and transport.
class Element {
  constructor(tagName = 'div') {
    this.tagName = tagName; this.children = []; this.attributes = {}; this.listeners = {};
    this.dataset = {}; this.value = ''; this.hidden = false; this.disabled = false; this.open = false;
    this.classList = {add() {}, remove() {}};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  removeAttribute(key) { delete this.attributes[key]; }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  dispatch(name, event = {}) { for (const callback of this.listeners[name] || []) callback(event); }
  closest(selector) { return this.parents[selector]; }
  showModal() { this.open = true; }
  close() { this.open = false; this.dispatch('close'); }
}
const flush = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return {promise, resolve, reject}; };
function harness() {
  const nodes = new Map(ids.map(id => [id, new Element()]));
  nodes.get('confidence').value = '0.35'; nodes.get('event-filter').value = 'all';
  nodes.get('media-files').parents = {'.dropzone': new Element()};
  nodes.get('model-heading').parents = {'.model-card': new Element()};
  const calls = [], timers = new Map(), handlers = {};
  let timerId = 0;
  const win = {document: {getElementById: id => nodes.get(id), createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag)},
    location: {origin: 'http://localhost:8000'}, AbortController,
    FormData: class {constructor() { this.entries = []; } append(...args) { this.entries.push(args); }},
    addEventListener(name, callback) { handlers[name] = callback; },
    setTimeout(callback, delay) { timers.set(++timerId, {callback, delay}); return timerId; },
    clearTimeout(id) { timers.delete(id); },
    fetch: async (url, options) => {
      calls.push({url, options});
      const data = await h.respond(url, options);
      return {ok: true, status: 200, json: async () => data};
    }};
  const h = {nodes, calls, timers, handlers, win,
    status: 'model_not_configured', jobs: [], detail: {},
    respond: async url => {
      if (url.endsWith('/status')) return {status: h.status, message: 'Test status', classes: ['trash', 'fire', 'smoke'], limits};
      if (url.endsWith('/jobs')) return {jobs: h.jobs};
      if (url.startsWith('/api/environment/jobs/')) return h.detail[url.split('/').pop()];
      throw Error('Unexpected request: ' + url);
    },
    async poll() { const timer = [...timers.entries()].find(([, value]) => value.delay < 15000); assert.ok(timer, 'Expected scheduled poll'); timers.delete(timer[0]); timer[1].callback(); await flush(); }};
  h.app = ui.createApp(win);
  return h;
}
function result(events = []) {return {schema_version: 1, mode: 'environment', status: 'complete', events, media: [{source_name: 'DJI.JPG', kind: 'image', frames_analyzed: 1}], warnings: []};}
(async () => {
  const h = harness(); await flush();
  h.app.setFiles([photo]);
  await h.app.submit({preventDefault() {}});
  assert.equal(h.nodes.get('start-analysis').disabled, true);
  assert.equal(h.calls.some(call => call.options.method === 'POST'), false, 'Missing model must block programmatic submit');
  h.status = 'configured'; await h.app.refreshStatus();
  assert.equal(h.nodes.get('start-analysis').disabled, false);
  const posted = deferred(); const originalRespond = h.respond;
  h.respond = (url, options) => options.method === 'POST' ? posted.promise : originalRespond(url, options);
  const first = h.app.submit({preventDefault() {}});
  const second = h.app.submit({preventDefault() {}});
  assert.equal(h.calls.filter(call => call.options.method === 'POST').length, 1);
  assert.equal(h.nodes.get('upload-fields').disabled, true);
  h.detail.jobA = {id: 'jobA', name: 'First', status: 'running'};
  h.jobs = [{id: 'jobA', name: 'First', status: 'running'}];
  posted.resolve({id: 'jobA'}); await Promise.all([first, second]); await flush();
  assert.equal(h.app.state.selected, 'jobA');
  assert.equal(h.nodes.get('start-analysis').disabled, true, 'A running job prevents accidental second launch');
  h.detail.jobA = {id: 'jobA', name: 'First', status: 'done', result: result([{...event, location: null, source_name: '<img src=x onerror=alert(1)>', evidence_url: path}])};
  await h.poll();
  assert.equal(h.nodes.get('count-fire').textContent, '1');
  assert.equal(h.nodes.get('location-map').children[0].tagName, 'div', 'No map SVG when no coordinates');
  assert.match(h.nodes.get('map-caption').textContent, /0 из 1/);
  const stale = deferred();
  h.respond = (url, options) => url.endsWith('/jobA') ? stale.promise : originalRespond(url, options);
  h.detail.jobB = {id: 'jobB', name: 'Newest selection', status: 'done', result: result([{...event, location: {...event.location, source: 'embedded_gps_capture_position'}, evidence_url: path}])};
  const oldRead = h.app.selectJob('jobA'); await h.app.selectJob('jobB');
  stale.resolve(h.detail.jobA); await oldRead;
  assert.equal(h.app.state.selected, 'jobB');
  assert.match(h.nodes.get('selected-job').textContent, /Newest selection/);
  assert.equal(h.nodes.get('location-map').children[0].tagName, 'svg', 'Real EXIF position including zero must render');
  assert.equal(h.nodes.get('count-located').textContent, '1');
  h.respond = originalRespond;
  h.detail.jobA = {id: 'jobA', name: 'First', status: 'running'};
  await h.app.selectJob('jobA');
  h.app.state.pollStarted = Date.now() - 600001;
  await h.poll();
  assert.equal(h.nodes.get('resume-polling').hidden, false);
  assert.match(h.nodes.get('job-progress-text').textContent, /приостановлено после 10 минут/);
  h.respond = (url, options) => url.includes('/jobs/jobA') ? Promise.reject(Error('offline')) : originalRespond(url, options);
  await h.app.selectJob('jobA'); await h.poll(); await h.poll();
  assert.equal(h.app.state.readFailures, 3);
  assert.equal(h.nodes.get('resume-polling').hidden, false);
  assert.match(h.nodes.get('job-progress-text').textContent, /не означает отмену/);
  assert.equal([...h.timers.values()].filter(timer => timer.delay < 15000).length, 0, 'Read retries are bounded');
  h.app.stopPolling();
  const uncertain = harness(); await flush(); uncertain.status = 'configured'; await uncertain.app.refreshStatus(); uncertain.app.setFiles([photo]);
  const recoverRespond = uncertain.respond;
  uncertain.respond = (url, options) => options.method === 'POST' || url.endsWith('/jobs') ? Promise.reject(new TypeError('network')) : recoverRespond(url, options);
  await uncertain.app.submit({preventDefault() {}}); await flush();
  assert.equal(uncertain.app.state.uncertainSubmission, true);
  assert.equal(uncertain.nodes.get('start-analysis').disabled, true);
  await uncertain.app.submit({preventDefault() {}});
  assert.equal(uncertain.calls.filter(call => call.options.method === 'POST').length, 1, 'Uncertain transport must not automatically resend');
  uncertain.respond = recoverRespond; await uncertain.app.refreshJobs();
  assert.equal(uncertain.app.state.uncertainSubmission, false);
  assert.equal(uncertain.nodes.get('start-analysis').disabled, false);
  const assistant = harness(); await flush();
  assistant.app.state.selected = 'photoJob';
  let assistantHost = 'agromind.example', assistantPostCount = 0, assistantBody;
  let answerDeferred = deferred();
  const baseAssistantRespond = assistant.respond;
  assistant.respond = async (url, options) => {
    if (url === '/api/environment/assistant/status') return {status: 'configured', endpoint_host: assistantHost, message: 'Configured, not verified'};
    if (url === '/api/environment/assistant') { assistantPostCount++; assistantBody = JSON.parse(options.body); return answerDeferred.promise; }
    return baseAssistantRespond(url, options);
  };
  await assistant.app.prepareAssistant({...event, id: 'chosenEvent'});
  assert.equal(assistant.nodes.get('assistant-consent').checked, false);
  assert.equal(assistant.nodes.get('assistant-image').checked, false);
  assistant.nodes.get('assistant-question').value = 'Что проверить?';
  await assistant.app.askAssistant({preventDefault() {}});
  assert.equal(assistantPostCount, 0, 'No consent means no outgoing assistant message');
  assistant.nodes.get('assistant-consent').checked = true;
  const answerOne = assistant.app.askAssistant({preventDefault() {}});
  const answerTwo = assistant.app.askAssistant({preventDefault() {}});
  await flush();
  assert.equal(assistantPostCount, 1, 'Duplicate assistant click must not transmit twice');
  assert.deepEqual(assistantBody, {job_id: 'photoJob', event_id: 'chosenEvent', message: 'Что проверить?', consent: true, include_image: false, expected_endpoint_host: 'agromind.example'});
  answerDeferred.resolve({response: '<img src=x onerror=alert(1)> Проверьте исходное фото.'});
  await Promise.all([answerOne, answerTwo]);
  assert.match(assistant.nodes.get('assistant-answer').textContent, /<img/);
  assert.equal(assistant.nodes.get('assistant-answer').children.length, 0, 'Assistant HTML remains inert plain text');
  assert.equal(assistant.nodes.get('assistant-consent').checked, false, 'Consent is one-shot');
  await assistant.app.prepareAssistant({...event, id: 'chosenEvent'});
  assistant.nodes.get('assistant-question').value = 'Проверьте фото';
  assistant.nodes.get('assistant-consent').checked = true;
  assistant.nodes.get('assistant-image').checked = true;
  assistantHost = 'changed.example';
  await assistant.app.askAssistant({preventDefault() {}});
  assert.equal(assistantPostCount, 1, 'Changed recipient requires fresh consent and no transmission');
  assert.equal(assistant.nodes.get('assistant-consent').checked, false);
  assert.match(assistant.nodes.get('assistant-feedback').textContent, /Получатель изменился/);
  assistant.handlers.pagehide();
  console.log('PASS: AgroMind explicit one-shot consent, separate image opt-in default, selected-event payload, recipient pin, duplicate request prevention, changed-recipient refusal and untrusted reply escaping');
  h.handlers.pagehide(); uncertain.handlers.pagehide();
  console.log('PASS: actual UI controller missing-model gate, double-submit guard, pending-job lock, zero/missing geodata rendering, stale navigation, 10-minute pause/resume, three-failure bound, uncertain POST lock and explicit history recovery');
})().catch(error => { console.error(error); process.exitCode = 1; });
