/* Separate environmental workflow. No plant-model fallback, remote tiles or demo data. */
(function (root) {
  'use strict';
  const CLASS_NAMES = Object.freeze({trash: 'Мусор', fire: 'Огонь', smoke: 'Дым'});
  const PHOTO_EXTENSIONS = new Set(['jpg', 'jpeg', 'png']);
  const POLL_INTERVAL_MS = 2000;
  const POLL_WINDOW_MS = 10 * 60 * 1000;
  const MAX_READ_FAILURES = 3;
  const PAGE_SIZE = 30;
  const SVG_NS = 'http://www.w3.org/2000/svg';

  function mediaKind(name) {
    const extension = String(name).split('.').pop().toLowerCase();
    if (PHOTO_EXTENSIONS.has(extension)) return 'image';
    return null;
  }
  function finiteNumber(value) { return typeof value === 'number' && Number.isFinite(value); }
  function validCoordinates(value) {
    return Boolean(value && finiteNumber(value.latitude) && finiteNumber(value.longitude)
      && Math.abs(value.latitude) <= 90 && Math.abs(value.longitude) <= 180);
  }
  function captureLocation(event) {
    const location = event && event.location;
    return validCoordinates(location) && location.precision === 'capture_position_not_object'
      && ['operator_capture_position', 'embedded_gps_capture_position'].includes(location.source)
      ? location : null;
  }
  function safeAssetURL(value, origin) {
    if (typeof value !== 'string' || !value.startsWith('/api/environment/') || value.startsWith('//')) return null;
    try {
      const url = new URL(value, origin);
      return url.origin === origin && !url.username && !url.password && (/^\/api\/environment\/files\/[a-f0-9]{32}\/(?:events\.geojson|evidence\/[0-9]{2}_[0-9]{8}(?:_annotated)?\.jpg)$/).test(url.pathname) && !url.search && !url.hash ? url.href : null;
    } catch (_) { return null; }
  }
  function errorText(data, fallback) {
    if (typeof data === 'string' && data.trim()) return data;
    if (data && typeof data.error === 'string') return data.error;
    if (data && typeof data.message === 'string') return data.message;
    if (data && data.error && typeof data.error.message === 'string') return data.error.message;
    return fallback;
  }
  function validateUpload(files, values, limits) {
    if (!files.length) throw Error('Выберите хотя бы один файл.');
    if (!limits || !Number.isInteger(limits.max_files) || !finiteNumber(limits.max_upload_bytes)) {
      throw Error('Лимиты сервера недоступны. Повторите проверку готовности модели.');
    }
    if (files.length > limits.max_files) throw Error(`Допустимо не более ${limits.max_files} файлов за запуск.`);
    if (files.reduce((sum, file) => sum + file.size, 0) > limits.max_upload_bytes) throw Error('Общий размер файлов превышает лимит сервера.');
    const names = new Set();
    for (const file of files) {
      if (!mediaKind(file.name)) throw Error(`Неподдерживаемый формат: ${file.name}`);
      if (file.size <= 0) throw Error(`Файл пуст: ${file.name}`);
      if (names.has(file.name)) throw Error(`Повторяется имя файла «${file.name}». Переименуйте один файл, чтобы не перепутать геоданные.`);
      names.add(file.name);
    }
    const confidence = Number(values.confidence);
    if (!String(values.confidence).trim() || !finiteNumber(confidence) || confidence < 0.01 || confidence > 1) throw Error('Порог оценки должен быть от 0,01 до 1.');
    const latitudeText = String(values.latitude || '').trim();
    const longitudeText = String(values.longitude || '').trim();
    const geodataText = String(values.geodata || '').trim();
    const coordinate = {latitude: Number(latitudeText), longitude: Number(longitudeText)};
    if (Boolean(latitudeText) !== Boolean(longitudeText)) throw Error('Укажите обе координаты съёмки или оставьте обе пустыми.');
    if (latitudeText && !validCoordinates(coordinate)) throw Error('Проверьте широту (−90…90) и долготу (−180…180).');
    if (latitudeText && geodataText) throw Error('Используйте либо общие координаты фото, либо геоданные JSON.');
    if (geodataText) {
      if (geodataText.length > 1048576) throw Error('Геоданные JSON слишком велики (предел: 1 МиБ текста).');
      let data;
      try { data = JSON.parse(geodataText); } catch (_) { throw Error('Геоданные должны быть корректным JSON.'); }
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw Error('Геоданные JSON: ожидается объект с именами исходных файлов.');
      for (const [name, location] of Object.entries(data)) {
        if (!names.has(name)) throw Error(`Геоданные ссылаются на невыбранный файл: ${name}`);
        if (!validCoordinates(location) || location.source !== 'operator_capture_position' || Object.hasOwn(location, 'frames')) {
          throw Error(`Для фото «${name}» нужны реальные latitude, longitude и source: operator_capture_position.`);
        }
      }
    }
    return {confidence, latitude: latitudeText ? coordinate.latitude : null,
      longitude: longitudeText ? coordinate.longitude : null, geodata: geodataText};
  }
  function summarize(events) {
    const counts = {trash: 0, fire: 0, smoke: 0, located: 0};
    for (const event of events) {
      if (Object.prototype.hasOwnProperty.call(CLASS_NAMES, event.class_name)) counts[event.class_name] += 1;
      if (captureLocation(event)) counts.located += 1;
    }
    return counts;
  }
  function projectLocations(events) {
    const points = events.map((event, index) => ({event, index, location: captureLocation(event)})).filter(point => point.location);
    if (!points.length) return {points: []};
    let minLon = Math.min(...points.map(point => point.location.longitude));
    let maxLon = Math.max(...points.map(point => point.location.longitude));
    let minLat = Math.min(...points.map(point => point.location.latitude));
    let maxLat = Math.max(...points.map(point => point.location.latitude));
    const lonPadding = Math.max((maxLon - minLon) * 0.12, 0.0001);
    const latPadding = Math.max((maxLat - minLat) * 0.12, 0.0001);
    minLon = Math.max(-180, minLon - lonPadding); maxLon = Math.min(180, maxLon + lonPadding);
    minLat = Math.max(-90, minLat - latPadding); maxLat = Math.min(90, maxLat + latPadding);
    for (const point of points) {
      point.x = 68 + ((point.location.longitude - minLon) / (maxLon - minLon)) * 464;
      point.y = 24 + ((maxLat - point.location.latitude) / (maxLat - minLat)) * 216;
    }
    return {points, minLon, maxLon, minLat, maxLat};
  }
  function formatTime(value) {
    if (!finiteNumber(value) || value < 0) return 'время не указано';
    const minutes = Math.floor(value / 60);
    return `${minutes}:${(value % 60).toFixed(1).padStart(4, '0')}`;
  }
  function createApp(win) {
    const doc = win.document;
    const $ = id => doc.getElementById(id);
    const state = {status: null, files: [], submitting: false, jobs: [], selected: null, result: null,
      selectionVersion: 0, statusVersion: 0, refreshBusy: false, pollTimer: null, pollStarted: 0, readFailures: 0,
      pageLimit: PAGE_SIZE, disposed: false, controllers: new Set(), detailController: null, uncertainSubmission: false, assistantVersion: 0, assistantStatus: null, assistantEvent: null, assistantJob: null, assistantBusy: false};
    function node(tag, className, text) {
      const item = doc.createElement(tag);
      if (className) item.className = className;
      if (text !== undefined) item.textContent = String(text);
      return item;
    }
    function svgNode(tag, attributes, text) {
      const item = doc.createElementNS(SVG_NS, tag);
      for (const [key, value] of Object.entries(attributes || {})) item.setAttribute(key, String(value));
      if (text !== undefined) item.textContent = String(text);
      return item;
    }
    function notice(message, error = false) {
      $('notice').textContent = message;
      $('notice').hidden = !message;
      $('notice').className = error ? 'notice error' : 'notice';
    }
    async function api(path, options = {}, timeoutMs = 15000, controller = new win.AbortController()) {
      state.controllers.add(controller);
      const timeout = win.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await win.fetch(path, {...options, credentials: 'same-origin', signal: controller.signal,
          headers: {Accept: 'application/json', ...options.headers}});
        let data;
        try { data = await response.json(); } catch (_) { throw Error(`Сервер вернул непонятный ответ (HTTP ${response.status}).`); }
        if (!response.ok) { const error = Error(errorText(data, `Ошибка сервера (HTTP ${response.status}).`)); error.httpStatus = response.status; throw error; }
        return data;
      } finally { win.clearTimeout(timeout); state.controllers.delete(controller); }
    }
    function uploadValues() {
      return {confidence: $('confidence').value,
        latitude: $('latitude').value, longitude: $('longitude').value, geodata: $('geodata').value};
    }
    function updateControls() {
      const configured = state.status && state.status.status === 'configured';
      const running = state.jobs.some(job => job.status === 'running');
      $('upload-fields').disabled = state.submitting;
      $('latitude').disabled = state.submitting;
      $('longitude').disabled = state.submitting;
      $('clear-files').disabled = state.submitting || !state.files.length;
      $('start-analysis').disabled = !configured || state.submitting || state.uncertainSubmission || running || !state.files.length;
      $('start-analysis').textContent = state.submitting ? 'Отправляем материалы…' : 'Начать анализ ↗';
      $('analysis-form').setAttribute('aria-busy', String(state.submitting));
      $('start-hint').textContent = state.submitting ? 'Не отправляйте файлы повторно. Дождитесь ответа сервера.'
        : state.uncertainSubmission ? 'Сначала обновите историю: предыдущая отправка могла быть принята.'
        : !configured ? 'Для запуска нужна настроенная экологическая модель.'
        : running ? 'Есть выполняющийся запуск. Дождитесь его завершения или обновите историю.'
        : !state.files.length ? 'Выберите исходные файлы для анализа.' : 'Предполагаемые находки потребуют проверки человеком.';
    }
    function setFiles(files) {
      if (state.submitting) return;
      state.files = Array.from(files);
      const list = $('file-list'); list.replaceChildren();
      for (const file of state.files) {
        const item = node('li'); item.append(node('span', '', file.name), node('small', '', `${(file.size / 1048576).toFixed(2)} МБ`)); list.append(item);
      }
      const total = state.files.reduce((sum, file) => sum + file.size, 0);
      $('file-total').textContent = state.files.length ? `${state.files.length} файлов · ${(total / 1048576).toFixed(2)} МБ` : 'Файлы не выбраны';
      updateControls();
    }
    async function refreshStatus() {
      const version = ++state.statusVersion;
      $('refresh-status').disabled = true;
      try {
        const data = await api('/api/environment/status');
        if (version !== state.statusVersion || state.disposed) return;
        state.status = data;
        const titles = {configured: 'Модель настроена', model_not_configured: 'Экологическая модель не подключена', configuration_error: 'Ошибка конфигурации модели'};
        $('model-heading').textContent = titles[data.status] || 'Неизвестное состояние модели';
        $('model-message').textContent = typeof data.message === 'string' ? data.message : 'Проверьте конфигурацию экологической модели на сервере.';
        $('model-heading').closest('.model-card').dataset.state = data.status;
        $('model-classes').textContent = Array.isArray(data.classes) && data.classes.length
          ? `Классы модели: ${data.classes.map(value => CLASS_NAMES[value] || String(value)).join(', ')}. Настройка не подтверждает качество обнаружения.` : '';
        const limits = data.limits;
        $('upload-limits').textContent = limits && finiteNumber(limits.max_upload_bytes)
          ? `До ${limits.max_files} файлов · ${(limits.max_upload_bytes / 1048576).toFixed(0)} МБ суммарно · JPG, JPEG, PNG`
          : 'Лимиты сервера не получены';
      } catch (error) {
        if (version !== state.statusVersion || state.disposed) return;
        state.status = null;
        $('model-heading').textContent = 'Не удалось проверить модель';
        $('model-message').textContent = error.name === 'AbortError' ? 'Сервер не ответил вовремя. Повторите проверку.' : error.message;
        $('model-classes').textContent = '';
      } finally { if (version === state.statusVersion) { $('refresh-status').disabled = false; updateControls(); } }
    }
    function displayDate(created) {
      if (!created) return 'Дата не указана';
      const date = new Date(created);
      return Number.isNaN(date.getTime()) ? String(created) : date.toLocaleString('ru-RU', {dateStyle: 'short', timeStyle: 'short'});
    }
    function renderJobs() {
      const list = $('job-list'); list.replaceChildren();
      const titles = {running: 'Выполняется', done: 'Завершён', error: 'Ошибка'};
      for (const job of state.jobs) {
        const item = node('li'); const button = node('button'); button.type = 'button';
        button.setAttribute('aria-pressed', String(state.selected === job.id));
        button.append(node('span', 'job-name', job.name || job.id));
        const meta = node('span', 'job-meta'); meta.append(node('span', '', displayDate(job.created)), node('span', `job-state ${job.status === 'error' ? 'error' : ''}`, titles[job.status] || 'Статус неизвестен'));
        button.append(meta); button.addEventListener('click', () => selectJob(job.id)); item.append(button); list.append(item);
      }
      updateControls();
    }
    async function refreshJobs(autoSelect = false) {
      if (state.refreshBusy) return;
      state.refreshBusy = true; $('refresh-jobs').disabled = true;
      try {
        const data = await api('/api/environment/jobs');
        if (state.disposed) return;
        if (!data || !Array.isArray(data.jobs)) throw Error('Сервер вернул неверный формат истории.');
        const incoming = data.jobs.filter(job => job && typeof job.id === 'string');
        state.jobs = incoming.map(job => {
          const previous = state.jobs.find(item => item.id === job.id);
          return previous && ['done', 'error'].includes(previous.status) && job.status === 'running' ? previous : job;
        }).concat(state.jobs.filter(job => job.locallyAccepted && !incoming.some(item => item.id === job.id)));
        state.uncertainSubmission = false;
        renderJobs();
        $('history-status').textContent = state.jobs.length ? `${state.jobs.length} запусков. Выберите, чтобы открыть.` : 'Вы ещё не запускали экологический анализ.';
        if (autoSelect && !state.selected && state.jobs.length) selectJob(state.jobs[0].id);
      } catch (error) {
        if (!state.disposed) $('history-status').textContent = error.name === 'AbortError' ? 'История не ответила вовремя. Нажмите «Обновить».' : `Не удалось обновить историю: ${error.message}`;
      } finally { state.refreshBusy = false; $('refresh-jobs').disabled = false; }
    }
    function stopPolling() {
      if (state.pollTimer !== null) win.clearTimeout(state.pollTimer);
      state.pollTimer = null;
      if (state.detailController) state.detailController.abort();
      state.detailController = null;
    }
    function progress(message, allowResume = false) {
      $('job-progress').hidden = !message;
      $('job-progress-text').textContent = message;
      $('resume-polling').hidden = !allowResume;
    }
    function clearResult() {
      state.result = null; state.pageLimit = PAGE_SIZE;
      for (const key of ['trash', 'fire', 'smoke', 'located']) $(`count-${key}`).textContent = '—';
      $('download-geojson').hidden = true; $('download-geojson').removeAttribute('href');
      $('result-warnings').hidden = true; $('result-warnings').replaceChildren();
      $('media-coverage').replaceChildren(node('li', 'muted', 'Результаты этого запуска ещё не получены.'));
      $('location-map').replaceChildren(emptyState('⌖', 'Нет полученных геоданных', 'Точки не строятся без известных координат.'));
      $('map-caption').textContent = 'Только координаты из выбранного запуска. Точное положение объектов не рассчитано.';
      $('evidence-summary').textContent = '';
      $('evidence-list').replaceChildren(emptyState('▧', 'Ожидаем результат', 'Кадры появятся после завершения выбранного анализа.'));
      $('show-more').hidden = true;
      if ($('evidence-dialog').open) $('evidence-dialog').close();
    }
    function emptyState(symbol, title, message) {
      const box = node('div', 'empty-state'); box.append(node('span', '', symbol), node('h3', '', title), node('p', '', message)); return box;
    }
    async function selectJob(id) {
      stopPolling();
      state.selected = id; const version = ++state.selectionVersion;
      state.pollStarted = Date.now(); state.readFailures = 0;
      clearResult(); renderJobs(); $('selected-job').textContent = `Запуск ${id}`;
      progress('Загружаем выбранный запуск…');
      await readJob(id, version);
    }
    async function readJob(id, version) {
      if (state.disposed || version !== state.selectionVersion) return;
      state.detailController = new win.AbortController();
      try {
        const job = await api(`/api/environment/jobs/${encodeURIComponent(id)}`, {}, 15000, state.detailController);
        if (state.disposed || version !== state.selectionVersion) return;
        state.readFailures = 0;
        $('selected-job').textContent = `${job.name || id} · ${displayDate(job.created)}`;
        const oldIndex = state.jobs.findIndex(item => item.id === id);
        if (oldIndex >= 0) state.jobs[oldIndex] = {...state.jobs[oldIndex], ...job, result: undefined};
        else state.jobs.unshift({...job, id, result: undefined});
        renderJobs();
        if (job.status === 'running') {
          if (Date.now() - state.pollStarted >= POLL_WINDOW_MS) {
            progress('Автообновление приостановлено после 10 минут. Запуск на сервере может продолжаться; проверьте результат вручную.', true);
          } else {
            progress('Сервер обрабатывает материалы. Можно открыть другой запуск; закрытие страницы не отменяет обработку.');
            state.pollTimer = win.setTimeout(() => readJob(id, version), POLL_INTERVAL_MS);
          }
        } else if (job.status === 'done') {
          if (!job.result || job.result.mode !== 'environment' || job.result.schema_version !== 1 || !Array.isArray(job.result.events) || !Array.isArray(job.result.media)) throw Error('Не удалось прочитать результат этого запуска: неподдерживаемый формат.');
          state.result = job.result; progress(''); renderResult();
        } else if (job.status === 'error') {
          progress(`Анализ завершился ошибкой: ${errorText(job.error, 'подробности не предоставлены сервером')}`);
          $('evidence-list').replaceChildren(emptyState('!', 'Анализ не завершён', 'Нет подтверждённого результата. Исправьте причину ошибки перед новым запуском.'));
        } else {
          progress('Неизвестный статус запуска. Автообновление остановлено; проверьте результат вручную.', true);
        }
      } catch (error) {
        if (state.disposed || version !== state.selectionVersion) return;
        state.readFailures += 1;
        const message = error.name === 'AbortError' ? 'Сервер не ответил вовремя.' : error.message;
        if (state.readFailures >= MAX_READ_FAILURES || Date.now() - state.pollStarted >= POLL_WINDOW_MS) {
          progress(`Не удалось получить результат: ${message} Автообновление остановлено. Это не означает отмену анализа.`, true);
        } else {
          progress(`Не удалось обновить результат: ${message} Повторим чтение (${state.readFailures}/${MAX_READ_FAILURES}).`);
          state.pollTimer = win.setTimeout(() => readJob(id, version), POLL_INTERVAL_MS * state.readFailures);
        }
      }
    }
    async function submit(event) {
      event.preventDefault();
      if (state.submitting || state.uncertainSubmission || !state.status || state.status.status !== 'configured' || state.jobs.some(job => job.status === 'running')) return;
      let values;
      try { values = validateUpload(state.files, uploadValues(), state.status.limits); }
      catch (error) { notice(error.message, true); return; }
      state.submitting = true; notice(''); updateControls();
      const form = new win.FormData();
      for (const file of state.files) form.append('files', file, file.name);
      form.append('confidence', String(values.confidence));
      if (values.latitude !== null) { form.append('latitude', String(values.latitude)); form.append('longitude', String(values.longitude)); }
      if (values.geodata) form.append('geodata', values.geodata);
      const selectedBeforeUpload = state.selectionVersion;
      try {
        const job = await api('/api/environment/analyze', {method: 'POST', body: form}, 90000);
        if (state.disposed) return;
        if (!job || typeof job.id !== 'string' || !job.id) throw Error('Сервер не вернул идентификатор запуска. Обновите историю перед повторной отправкой.');
        state.jobs.unshift({id: job.id, name: state.files.map(file => file.name).join(', '), status: 'running', locallyAccepted: true, created: new Date().toISOString()});
        renderJobs();
        notice('Материалы приняты. Предполагаемые находки появятся после обработки.');
        if (selectedBeforeUpload === state.selectionVersion) selectJob(job.id);
        else notice('Новый запуск принят и добавлен в историю. Открытый вами результат сохранён.');
        refreshJobs();
      } catch (error) {
        if (!state.disposed) {
          const uncertain = !error.httpStatus;
          state.uncertainSubmission = uncertain;
          notice(uncertain ? 'Ответ на отправку не получен. Запуск мог начаться: сначала обновите историю, чтобы не отправить файлы повторно.' : error.message, true);
          refreshJobs();
        }
      } finally { state.submitting = false; if (!state.disposed) updateControls(); }
    }
    function renderResult() {
      const result = state.result; if (!result) return;
      const counts = summarize(result.events);
      for (const key of ['trash', 'fire', 'smoke', 'located']) $(`count-${key}`).textContent = String(counts[key]);
      const url = safeAssetURL(result.geojson_url, win.location.origin);
      $('download-geojson').hidden = !url;
      if (url) $('download-geojson').href = url;
      const warnings = [];
      if (result.status === 'partial') warnings.push('Результат частичный: часть материалов могла быть пропущена или ограничена.');
      if (!result.events.length) warnings.push('Модель не нашла подходящих признаков на проверенных кадрах. Это не доказывает отсутствие мусора, огня или дыма.');
      warnings.push('Все обнаружения предварительные и требуют проверки человеком. Количество находок не равно количеству уникальных объектов.');
      if (Array.isArray(result.warnings)) warnings.push(...result.warnings.map(String));
      const warningBox = $('result-warnings'); warningBox.replaceChildren(node('h3', '', 'Важно при проверке'));
      const warningList = node('ul'); for (const text of new Set(warnings)) warningList.append(node('li', '', text));
      warningBox.append(warningList); warningBox.hidden = false;
      const mediaList = $('media-coverage'); mediaList.replaceChildren();
      for (const media of result.media) {
        const item = node('li'); item.append(node('strong', '', media.source_name || 'Без имени'));
        const frames = Number.isInteger(media.frames_analyzed) ? media.frames_analyzed : 'неизвестно';
        item.append(node('p', '', `Фото · проверено кадров: ${frames}`));
        if (Array.isArray(media.warnings)) for (const warning of media.warnings) item.append(node('p', 'coverage-warning', String(warning)));
        mediaList.append(item);
      }
      if (!result.media.length) mediaList.append(node('li', 'muted', 'Сервер не предоставил перечень обработанных материалов.'));
      renderMap(); renderEvidence();
    }
    function filteredEvents() {
      const filter = $('event-filter').value;
      return (state.result ? state.result.events : []).map((event, index) => ({event, index})).filter(item => filter === 'all' || item.event.class_name === filter);
    }
    function renderMap() {
      const events = state.result ? state.result.events : [];
      const projected = projectLocations(events); const map = $('location-map'); map.replaceChildren();
      $('map-caption').textContent = `${projected.points.length} из ${events.length} находок имеют известные координаты съёмки. Остальные не нанесены на схему.`;
      if (!projected.points.length) { map.append(emptyState('⌖', 'Нет координат съёмки', 'Без EXIF GPS или геоданных оператора находки остаются только в списке.')); return; }
      const svg = svgNode('svg', {viewBox: '0 0 600 285', role: 'group', 'aria-label': 'Схема реальных координат съёмки. Точки не являются точным положением объектов.'});
      svg.append(svgNode('rect', {x: 68, y: 24, width: 464, height: 216, class: 'map-frame'}));
      for (let i = 1; i < 4; i += 1) {
        svg.append(svgNode('line', {x1: 68 + 116 * i, y1: 24, x2: 68 + 116 * i, y2: 240, class: 'map-grid'}));
        svg.append(svgNode('line', {x1: 68, y1: 24 + 54 * i, x2: 532, y2: 24 + 54 * i, class: 'map-grid'}));
      }
      svg.append(svgNode('text', {x: 68, y: 261, class: 'map-label'}, projected.minLon.toFixed(5)),
        svgNode('text', {x: 532, y: 261, 'text-anchor': 'end', class: 'map-label'}, projected.maxLon.toFixed(5)),
        svgNode('text', {x: 300, y: 280, 'text-anchor': 'middle', class: 'map-label'}, 'Долгота →'),
        svgNode('text', {x: 3, y: 28, class: 'map-label'}, projected.maxLat.toFixed(4)),
        svgNode('text', {x: 3, y: 240, class: 'map-label'}, projected.minLat.toFixed(4)),
        svgNode('text', {x: 3, y: 14, class: 'map-label'}, 'Широта ↑'));
      for (const point of projected.points) {
        const circle = svgNode('circle', {cx: point.x, cy: point.y, r: 10, class: `map-point ${Object.prototype.hasOwnProperty.call(CLASS_NAMES, point.event.class_name) ? point.event.class_name : ''}`,
          tabindex: 0, role: 'button', 'aria-label': `Открыть находку ${point.index + 1}: ${CLASS_NAMES[point.event.class_name] || 'Наблюдение'}, координаты съёмки ${point.location.latitude}, ${point.location.longitude}`});
        circle.append(svgNode('title', {}, `${CLASS_NAMES[point.event.class_name] || 'Наблюдение'} · ${point.location.latitude}, ${point.location.longitude} · положение съёмки`));
        circle.addEventListener('click', () => openEvidence(point.event, point.index));
        circle.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openEvidence(point.event, point.index); } });
        svg.append(circle, svgNode('text', {x: point.x, y: point.y + 3.5, class: 'map-number', 'aria-hidden': 'true'}, point.index + 1));
      }
      map.append(svg);
    }
    function evidenceImage(event, eager = false) {
      const frame = node('div', 'evidence-frame'); const url = safeAssetURL(event.source_evidence_url || event.evidence_url, win.location.origin);
      if (!url) { frame.append(node('span', 'image-error', 'Снимок недоступен: безопасная ссылка не получена.')); return frame; }
      const image = node('img'); image.alt = `Кадр для проверки: ${CLASS_NAMES[event.class_name] || 'наблюдение'} — ${event.source_name || 'источник'}`;
      image.loading = eager ? 'eager' : 'lazy'; image.decoding = 'async';
      const overlay = svgNode('svg', {'aria-hidden': 'true', preserveAspectRatio: 'xMidYMid meet'});
      image.addEventListener('load', () => {
        if (!image.naturalWidth || !image.naturalHeight) return;
        overlay.setAttribute('viewBox', `0 0 ${image.naturalWidth} ${image.naturalHeight}`);
        const box = event.bbox;
        if (!Array.isArray(box) || box.length !== 4 || !box.every(finiteNumber)) return;
        const [x1, y1, x2, y2] = box;
        if (x1 < 0 || y1 < 0 || x2 <= x1 || y2 <= y1 || x2 > image.naturalWidth || y2 > image.naturalHeight) return;
        overlay.replaceChildren(svgNode('rect', {x: x1, y: y1, width: x2 - x1, height: y2 - y1}));
      });
      image.addEventListener('error', () => frame.replaceChildren(node('span', 'image-error', 'Не удалось загрузить исходный кадр. Проверьте доступность материалов на сервере.')), {once: true});
      frame.append(image, overlay); image.src = url; return frame;
    }
    function eventDescription(event) {
      const parts = [];
      if (Number.isInteger(event.frame_index)) parts.push(`кадр ${event.frame_index}`);
      if (finiteNumber(event.timestamp_seconds)) parts.push(formatTime(event.timestamp_seconds));
      return parts.length ? parts.join(' · ') : 'Фотография';
    }
    function locationDescription(event) {
      const location = captureLocation(event);
      if (!location) return 'Геопривязка отсутствует';
      const sources = {operator_capture_position: 'оператор', embedded_gps_capture_position: 'EXIF GPS'};
      return `Съёмка: ${location.latitude.toFixed(6)}, ${location.longitude.toFixed(6)} · ${sources[location.source]}`;
    }
    function openEvidence(event, index) {
      const dialog = $('evidence-dialog');
      $('dialog-title').textContent = `${index + 1}. ${CLASS_NAMES[event.class_name] || 'Наблюдение'} · ${event.source_name || 'исходный кадр'}`;
      $('dialog-evidence').replaceChildren(evidenceImage(event, true));
      $('dialog-details').textContent = `${eventDescription(event)}. ${locationDescription(event)}. Требует проверки человеком.`;
      prepareAssistant(event);
      if (!dialog.open) dialog.showModal();
    }
    function updateAssistantControls() {
      const configured = state.assistantStatus && state.assistantStatus.status === 'configured' && state.assistantStatus.endpoint_host;
      $('assistant-send').disabled = state.assistantBusy || !configured || !$('assistant-consent').checked || !$('assistant-question').value.trim() || !state.assistantEvent;
      $('assistant-send').textContent = state.assistantBusy ? 'Ожидаем ответ…' : 'Отправить вопрос ↗';
      $('assistant-question').disabled = state.assistantBusy;
      $('assistant-consent').disabled = state.assistantBusy || !configured;
      $('assistant-image').disabled = state.assistantBusy || !configured;
      $('assistant-form').setAttribute('aria-busy', String(state.assistantBusy));
    }
    function showAssistantStatus(status) {
      state.assistantStatus = status;
      $('assistant-status').textContent = status && typeof status.message === 'string' ? status.message : 'Настройка Экокинеу недоступна.';
      const host = status && status.status === 'configured' && typeof status.endpoint_host === 'string' ? status.endpoint_host : null;
      $('assistant-consent-text').textContent = host
        ? `Разрешаю отправить в Экокинеу на ${host} мой вопрос, данные выбранной находки (тип, оценку, рамку, статус проверки) и реальные координаты съёмки, если они есть, для ответа на вопрос.`
        : 'Для отправки данных нужен настроенный получатель Экокинеу.';
      updateAssistantControls();
    }
    async function prepareAssistant(event) {
      const version = ++state.assistantVersion;
      state.assistantEvent = event; state.assistantJob = state.selected; state.assistantStatus = null;
      $('assistant-consent').checked = false; $('assistant-image').checked = false; $('assistant-question').value = '';
      $('assistant-answer').hidden = true; $('assistant-answer').textContent = '';
      $('assistant-feedback').textContent = ''; $('assistant-status').textContent = 'Проверяем настройку помощника…';
      updateAssistantControls();
      try {
        const status = await api('/api/environment/assistant/status');
        if (version === state.assistantVersion && !state.disposed) showAssistantStatus(status);
      } catch (error) {
        if (version === state.assistantVersion && !state.disposed) showAssistantStatus({status: 'not_configured', message: 'Не удалось получить настройку Экокинеу. Откройте материал снова, чтобы повторить проверку.'});
      }
    }
    async function askAssistant(event) {
      event.preventDefault();
      if (state.assistantBusy || !state.assistantEvent || !state.assistantStatus || state.assistantStatus.status !== 'configured'
        || !state.assistantStatus.endpoint_host || !$('assistant-consent').checked) return;
      const question = $('assistant-question').value.trim();
      if (!question || question.length > 4000) return;
      const version = state.assistantVersion;
      const expectedHost = state.assistantStatus.endpoint_host;
      const request = {job_id: state.assistantJob, event_id: state.assistantEvent.id, message: question,
        consent: true, include_image: Boolean($('assistant-image').checked), expected_endpoint_host: expectedHost};
      state.assistantBusy = true; updateAssistantControls();
      $('assistant-answer').hidden = true; $('assistant-feedback').textContent = 'Проверяем получателя перед отправкой…';
      try {
        const current = await api('/api/environment/assistant/status');
        if (version !== state.assistantVersion || state.disposed) return;
        if (current.status !== 'configured' || current.endpoint_host !== expectedHost) {
          $('assistant-consent').checked = false; $('assistant-image').checked = false;
          showAssistantStatus(current);
          $('assistant-feedback').textContent = 'Получатель изменился или стал недоступен. Проверьте получателя и подтвердите отправку заново.';
          return;
        }
        $('assistant-feedback').textContent = 'Вопрос отправляется. Автоматического повтора не будет.';
        const answer = await api('/api/environment/assistant', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request)}, 55000);
        if (version !== state.assistantVersion || state.disposed) return;
        if (!answer || typeof answer.response !== 'string' || !answer.response.trim()) throw Error('Экокинеу вернул пустой ответ.');
        $('assistant-answer').textContent = answer.response;
        $('assistant-answer').hidden = false;
        $('assistant-feedback').textContent = 'Ответ Экокинеу на выбранную находку. Проверьте его выводы.';
      } catch (error) {
        if (version === state.assistantVersion && !state.disposed) $('assistant-feedback').textContent = `Ответ не получен: ${error.name === 'AbortError' ? 'истекло время ожидания' : error.message}. Отправка могла состояться; автоматического повтора нет.`;
      } finally {
        state.assistantBusy = false;
        if (version === state.assistantVersion) { $('assistant-consent').checked = false; $('assistant-image').checked = false; }
        if (!state.disposed) updateAssistantControls();
      }
    }
    function renderEvidence() {
      const items = filteredEvents(); const list = $('evidence-list'); list.replaceChildren();
      const shown = items.slice(0, state.pageLimit);
      $('evidence-summary').textContent = `Показано ${shown.length} из ${items.length} находок выбранного типа. Все находки требуют проверки; повторные кадры могут содержать один объект.`;
      $('show-more').hidden = shown.length >= items.length;
      if (!items.length) {
        const hasAny = state.result && state.result.events.length;
        list.append(emptyState('▧', hasAny ? 'Этот тип не найден' : 'На проверенных кадрах находок нет', hasAny ? 'Выберите другой тип наблюдений.' : 'Это не доказательство безопасности: возможны пропуски, ограничения модели и неполный охват территории.'));
        return;
      }
      for (const {event, index} of shown) {
        const card = node('article', 'evidence-card'); card.id = `environment-event-${index}`;
        const preview = node('button', 'evidence-thumb'); preview.type = 'button'; preview.setAttribute('aria-label', `Открыть кадр находки ${index + 1}`);
        preview.append(evidenceImage(event)); preview.addEventListener('click', () => openEvidence(event, index));
        const info = node('div', 'evidence-info'); const heading = node('div', 'evidence-title');
        const knownClass = Object.prototype.hasOwnProperty.call(CLASS_NAMES, event.class_name);
        heading.append(node('span', `event-badge ${knownClass ? event.class_name : ''}`, `${index + 1} · ${CLASS_NAMES[event.class_name] || 'Неизвестный тип'}`),
          node('span', 'confidence', finiteNumber(event.confidence) && event.confidence >= 0 && event.confidence <= 1 ? `Оценка ${(event.confidence * 100).toFixed(0)}%` : 'Оценка неизвестна'));
        info.append(heading, node('h4', '', event.source_name || 'Источник не указан'), node('p', '', eventDescription(event)), node('p', '', locationDescription(event)));
        if (event.possible_duplicate_of !== null && event.possible_duplicate_of !== undefined) info.append(node('p', 'duplicate-label', `Возможный повтор находки ${event.possible_duplicate_of}. Уникальность не подтверждена.`));
        info.append(node('span', 'review-label', '◷ Требует проверки человеком'));
        card.append(preview, info); list.append(card);
      }
    }
    $('media-files').addEventListener('change', event => setFiles(event.target.files));
    $('clear-files').addEventListener('click', () => { $('media-files').value = ''; setFiles([]); });
    const dropzone = $('media-files').closest('.dropzone');
    dropzone.addEventListener('dragover', event => { event.preventDefault(); if (!state.submitting) dropzone.classList.add('dragging'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragging'));
    dropzone.addEventListener('drop', event => { event.preventDefault(); dropzone.classList.remove('dragging'); if (state.submitting) return; $('media-files').value = ''; setFiles(event.dataTransfer.files); });
    $('analysis-form').addEventListener('submit', submit);
    $('refresh-status').addEventListener('click', refreshStatus);
    $('refresh-jobs').addEventListener('click', () => refreshJobs(false));
    $('resume-polling').addEventListener('click', () => { if (state.selected) selectJob(state.selected); });
    $('event-filter').addEventListener('change', () => { state.pageLimit = PAGE_SIZE; if (state.result) renderEvidence(); });
    $('show-more').addEventListener('click', () => { state.pageLimit += PAGE_SIZE; renderEvidence(); });
    $('close-dialog').addEventListener('click', () => $('evidence-dialog').close());
    $('assistant-form').addEventListener('submit', askAssistant);
    $('assistant-consent').addEventListener('change', updateAssistantControls);
    $('assistant-question').addEventListener('input', updateAssistantControls);
    $('evidence-dialog').addEventListener('close', () => {
      $('dialog-evidence').replaceChildren(); ++state.assistantVersion; state.assistantEvent = null;
      $('assistant-consent').checked = false; $('assistant-image').checked = false;
    });
    win.addEventListener('pagehide', () => { state.disposed = true; stopPolling(); for (const controller of state.controllers) controller.abort(); });
    win.addEventListener('pageshow', event => { if (event.persisted) { state.disposed = false; refreshStatus(); refreshJobs(); if (state.selected) selectJob(state.selected); } });
    updateControls(); refreshStatus(); refreshJobs(true);
    return {state, submit, setFiles, selectJob, refreshStatus, refreshJobs, renderResult, stopPolling, prepareAssistant, askAssistant};
  }
  const exported = {mediaKind, validCoordinates, captureLocation, safeAssetURL, errorText, validateUpload, summarize, projectLocations, formatTime, createApp};
  if (typeof module === 'object' && module.exports) module.exports = exported;
  else { root.EnvironmentUI = exported; if (root.document) createApp(root); }
})(typeof window !== 'undefined' ? window : globalThis);
