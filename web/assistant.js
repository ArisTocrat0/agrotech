'use strict';
(() => {
  const key = (name, prefix) => {
    try {
      let value = localStorage.getItem(name);
      if (!value) {
        value = prefix + (crypto.randomUUID?.() || Math.random().toString(36).slice(2));
        localStorage.setItem(name, value);
      }
      return value;
    } catch (_) { return prefix + Math.random().toString(36).slice(2); }
  };
  let userId = key('olzha-ai-user', 'local-');
  let sessionId = key('olzha-ai-session', 'chat-');
  let file = null, busy = false;

  const style = document.createElement('style');
  style.textContent = '.ai-fab{position:fixed;right:24px;bottom:24px;z-index:70;background:#b9d894;color:#1b2b1e;border:0;border-radius:999px;padding:13px 18px;font-weight:700;box-shadow:0 12px 35px #0008}.ai-box{position:fixed;right:24px;bottom:82px;z-index:69;width:min(430px,calc(100vw - 32px));height:min(650px,calc(100vh - 115px));background:#18211c;border:1px solid #465548;border-radius:12px;box-shadow:0 22px 70px #000b;display:flex;flex-direction:column;overflow:hidden}.ai-box[hidden]{display:none!important}.ai-head{padding:15px 16px;background:#202b24;border-bottom:1px solid #354138;display:flex;justify-content:space-between;gap:10px}.ai-head small{display:block;color:#94a294;margin-top:4px}.ai-head button,.ai-attach{background:#28342b;color:#c7d3c2;border:1px solid #465548}.ai-msgs{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px}.ai-msg{max-width:88%;padding:10px 12px;border-radius:9px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5;font-size:13px}.ai-user{align-self:flex-end;background:#b9d894;color:#1a291d}.ai-bot{align-self:flex-start;background:#263229;border:1px solid #3e4d40}.ai-error{align-self:flex-start;background:#44322c;color:#f0c4b7}.ai-form{padding:10px;border-top:1px solid #354138;display:grid;grid-template-columns:auto 1fr auto;gap:7px}.ai-form textarea{min-height:44px;max-height:110px;resize:none;background:#111814;color:#e1e9dd;border:1px solid #445246;border-radius:8px;padding:10px}.ai-form button{min-height:44px;border-radius:8px}.ai-send{background:#b9d894;color:#1a291d;font-weight:700}.ai-file{padding:0 12px 9px;color:#aab7a6;font-size:11px}.ai-hint{padding:0 12px 9px;color:#839181;font-size:10px}@media(max-width:760px){.ai-fab{right:12px;bottom:12px}.ai-box{right:8px;bottom:68px;width:calc(100vw - 16px);height:70vh}}';
  document.head.append(style);

  const fab = document.createElement('button');
  fab.className = 'ai-fab'; fab.type = 'button'; fab.textContent = '✳ AI агроном';

  const box = document.createElement('section');
  box.className = 'ai-box'; box.hidden = true;
  box.innerHTML = '<div class="ai-head"><div><strong>OlzheAgro AI · Костанай</strong><small>Погода · посев · сорняки · болезни · фото</small></div><div><button type="button" data-reset>↻</button> <button type="button" data-close>✕</button></div></div><div class="ai-msgs"></div><div class="ai-file" hidden></div><form class="ai-form"><input data-image type="file" accept="image/jpeg,image/png" hidden><button type="button" class="ai-attach" data-attach>＋</button><textarea data-input maxlength="4000" placeholder="Спросите агронома…"></textarea><button class="ai-send" type="submit">→</button></form><div class="ai-hint">Регион: Костанайская область · фото до 12 МБ</div>';
  document.body.append(box, fab);

  const msgs = box.querySelector('.ai-msgs'), input = box.querySelector('[data-input]');
  const image = box.querySelector('[data-image]'), fileLine = box.querySelector('.ai-file');
  const sendBtn = box.querySelector('.ai-send');

  const add = (text, type) => {
    const el = document.createElement('div');
    el.className = 'ai-msg ' + type; el.textContent = text; msgs.append(el);
    msgs.scrollTop = msgs.scrollHeight; return el;
  };
  const welcome = () => { if (!msgs.children.length) add('Здравствуйте. Я AI-агроном OlzheAgro. Спросите про погоду, сроки сева, сорняки, болезни, удобрения или приложите фото растения.', 'ai-bot'); };
  const setFile = f => {
    file = f || null; image.value = file ? image.value : '';
    fileLine.hidden = !file;
    fileLine.textContent = file ? '📎 ' + file.name + ' · ' + (file.size/1024/1024).toFixed(1) + ' МБ' : '';
  };
  const answer = data => {
    if (typeof data === 'string') return data;
    if (Array.isArray(data)) return data.length ? answer(data[0]) : 'Ответ пуст.';
    if (!data || typeof data !== 'object') return String(data ?? 'Ответ пуст.');
    return data.output || data.response || data.text || data.message || data.answer || JSON.stringify(data, null, 2);
  };
  const send = async () => {
    if (busy) return;
    const shown = input.value.trim();
    if (!shown && !file) return;
    const currentFile = file;
    const crop = document.getElementById('field-crop')?.value?.trim();
    let message = shown || 'Проанализируй приложенное изображение и дай практическую рекомендацию агроному.';
    if (crop) message += '\n\nКонтекст локального приложения: выбранная культура — ' + crop + '.';
    add(shown || ('Фото: ' + currentFile.name), 'ai-user');
    input.value = ''; setFile(null);
    const waiting = add('Анализирую…', 'ai-bot');
    busy = true; sendBtn.disabled = true;
    try {
      const body = new FormData();
      body.append('message', message); body.append('user_id', userId);
      body.append('session_id', sessionId); body.append('region', 'Костанайская область, Казахстан');
      if (currentFile) body.append('image', currentFile, currentFile.name);
      const response = await fetch('/api/assistant', {method:'POST', body});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
      waiting.textContent = answer(data);
    } catch (error) {
      waiting.className = 'ai-msg ai-error'; waiting.textContent = 'Ошибка AI-агронома: ' + error.message;
    } finally { busy = false; sendBtn.disabled = false; input.focus(); }
  };

  fab.addEventListener('click', () => { box.hidden = !box.hidden; if (!box.hidden) { welcome(); input.focus(); } });
  box.querySelector('[data-close]').addEventListener('click', () => box.hidden = true);
  box.querySelector('[data-reset]').addEventListener('click', () => {
    sessionId = 'chat-' + (crypto.randomUUID?.() || Math.random().toString(36).slice(2));
    try { localStorage.setItem('olzha-ai-session', sessionId); } catch (_) {}
    msgs.replaceChildren(); setFile(null); welcome();
  });
  box.querySelector('[data-attach]').addEventListener('click', () => image.click());
  image.addEventListener('change', () => {
    const selected = image.files?.[0] || null;
    if (selected && selected.size > 12*1024*1024) { add('Фото больше 12 МБ.', 'ai-error'); setFile(null); return; }
    setFile(selected);
  });
  box.querySelector('.ai-form').addEventListener('submit', event => { event.preventDefault(); send(); });
  input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(); } });
})();
