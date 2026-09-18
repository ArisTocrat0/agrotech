'use strict';

(() => {
  const STORAGE_USER = 'olzha-ai-user';
  const STORAGE_SESSION = 'olzha-ai-session';
  const STORAGE_HISTORY = 'olzha-ai-history';
  const MAX_HISTORY = 60;
  const MAX_IMAGE = 12 * 1024 * 1024;

  const createId = prefix => prefix + (globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2) + Date.now().toString(36));
  const stored = (key, fallback) => {
    try {
      let value = localStorage.getItem(key);
      if (!value) {
        value = fallback();
        localStorage.setItem(key, value);
      }
      return value;
    } catch (_) {
      return fallback();
    }
  };

  let userId = stored(STORAGE_USER, () => createId('local-'));
  let sessionId = stored(STORAGE_SESSION, () => createId('chat-'));
  let history = [];
  let pendingFile = null;
  let busy = false;

  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_HISTORY) || '[]');
    if (Array.isArray(saved)) history = saved.slice(-MAX_HISTORY);
  } catch (_) {}

  const style = document.createElement('style');
  style.textContent = `
    .ai-fab{position:fixed;right:24px;bottom:24px;z-index:70;background:#b9d894;color:#1b2b1e;border:0;border-radius:999px;padding:13px 18px;font-weight:700;box-shadow:0 12px 35px #0008;display:flex;align-items:center;gap:8px}
    .ai-fab:hover{transform:translateY(-1px)}
    .ai-box{position:fixed;right:24px;bottom:82px;z-index:69;width:min(430px,calc(100vw - 32px));height:min(650px,calc(100vh - 115px));background:#18211c;border:1px solid #465548;border-radius:12px;box-shadow:0 22px 70px #000b;display:flex;flex-direction:column;overflow:hidden}
    .ai-box[hidden]{display:none!important}
    .ai-head{padding:15px 16px;background:#202b24;border-bottom:1px solid #354138;display:flex;justify-content:space-between;gap:10px}
    .ai-head small{display:block;color:#94a294;margin-top:4px}.ai-head button,.ai-attach{background:#28342b;color:#c7d3c2;border:1px solid #465548}
    .ai-head-actions{display:flex;gap:6px}.ai-msgs{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
    .assistant-bubble{max-width:88%;padding:10px 12px;border-radius:9px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.55;font-size:13px}
    .assistant-bubble.user{align-self:flex-end;background:#b9d894;color:#1a291d;border-bottom-right-radius:3px}
    .assistant-bubble.bot{align-self:flex-start;background:#263229;color:#dce5d7;border:1px solid #3e4d40;border-bottom-left-radius:3px}
    .assistant-bubble.error{align-self:flex-start;background:#44322c;color:#f0c4b7;border:1px solid #684b42}
    .ai-form{padding:10px;border-top:1px solid #354138;display:grid;grid-template-columns:auto 1fr auto;gap:7px}
    .ai-form textarea{min-height:44px;max-height:110px;resize:none;background:#111814;color:#e1e9dd;border:1px solid #445246;border-radius:8px;padding:10px;font:inherit}
    .ai-form button{min-height:44px;border-radius:8px}.ai-send{background:#b9d894;color:#1a291d;font-weight:700}.ai-file{padding:0 12px 9px;color:#aab7a6;font-size:11px}
    .ai-hint{padding:0 12px 9px;color:#839181;font-size:10px}.ai-open-page{margin:0 12px 10px;background:#222d26;color:#b9d894;border:1px solid #465548;border-radius:7px;padding:9px}

    .assistant-page-layout{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,.8fr);gap:22px;align-items:start}
    .assistant-chat-panel{padding:0;overflow:hidden;min-height:650px;display:flex;flex-direction:column}
    .assistant-page-head{padding:22px 24px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-start;gap:16px;background:linear-gradient(110deg,#25372a,#1d2822)}
    .assistant-page-head h2{font-size:25px;margin:8px 0 5px}.assistant-online{font-size:10px;letter-spacing:1px;color:#b9d894;text-transform:uppercase}.assistant-online i{display:inline-block;width:7px;height:7px;border-radius:50%;background:#9bd18b;margin-right:7px;box-shadow:0 0 0 4px #9bd18b1b}
    .assistant-page-messages{height:430px;overflow:auto;padding:24px;display:flex;flex-direction:column;gap:13px;background:#151d18}
    .assistant-page-messages .assistant-bubble{max-width:78%;font-size:14px;padding:13px 15px}
    .assistant-page-quick{display:flex;gap:8px;padding:14px 20px 0;overflow:auto;background:#1c2620}
    .assistant-page-quick button{white-space:nowrap;background:#26332a;color:#c6d3c1;border:1px solid #415043;border-radius:999px;padding:8px 11px;min-height:36px;font-size:11px}
    .assistant-page-quick button:hover{border-color:#789366;color:#dce9d3}
    .assistant-page-file{margin:12px 20px 0;padding:10px 12px;border:1px solid #465548;border-radius:7px;background:#222d26;color:#bbc8b6;font-size:12px}
    .assistant-page-form{display:grid;grid-template-columns:auto 1fr auto;gap:10px;padding:16px 20px;background:#1c2620;align-items:end}
    .assistant-page-form textarea{width:100%;resize:vertical;min-height:70px;max-height:180px;background:#111814;color:#e2e9de;border:1px solid #455348;border-radius:8px;padding:12px 13px;font:inherit;line-height:1.45}
    .assistant-page-form .assistant-page-attach{min-height:46px}.assistant-page-form .primary{min-height:46px}
    .assistant-page-note{margin:0;padding:0 20px 18px;background:#1c2620;color:#849286;font-size:10px;line-height:1.5}
    .assistant-side{display:grid;gap:18px}.assistant-side .panel{margin:0}.assistant-capabilities{display:grid;gap:4px;margin-top:18px}
    .assistant-capabilities>div{display:flex;gap:13px;padding:14px 0;border-top:1px solid var(--border)}
    .assistant-capabilities b{color:var(--green);font-size:10px;padding-top:2px}.assistant-capabilities span{display:grid;gap:5px}.assistant-capabilities strong{font-size:13px}.assistant-capabilities small{color:var(--muted);font-size:11px;line-height:1.5}
    .assistant-context-card h3{font-size:18px;margin:10px 0}.assistant-context-card .secondary{margin-top:12px;width:100%}

    @media(max-width:1000px){.assistant-page-layout{grid-template-columns:1fr}.assistant-side{grid-template-columns:1fr 1fr}.assistant-chat-panel{min-height:600px}}
    @media(max-width:760px){.ai-fab{right:12px;bottom:12px}.ai-box{right:8px;bottom:68px;width:calc(100vw - 16px);height:70vh}.assistant-side{grid-template-columns:1fr}.assistant-page-messages{height:52vh;padding:15px}.assistant-page-messages .assistant-bubble{max-width:92%;font-size:13px}.assistant-page-form{grid-template-columns:auto 1fr}.assistant-page-form .primary{grid-column:1/-1}.assistant-page-quick{padding-left:14px}.assistant-page-head{padding:18px}}
  `;
  document.head.append(style);

  const fab = document.createElement('button');
  fab.className = 'ai-fab';
  fab.type = 'button';
  fab.innerHTML = '<span>✳</span><span>AI агроном</span>';

  const box = document.createElement('section');
  box.className = 'ai-box';
  box.hidden = true;
  box.setAttribute('aria-label', 'Быстрый AI помощник агроному');
  box.innerHTML = '<div class="ai-head"><div><strong>OlzheAgro AI · Костанай</strong><small>Погода · посев · сорняки · болезни · фото</small></div><div class="ai-head-actions"><button type="button" data-ai-reset title="Новый диалог">↻</button><button type="button" data-ai-close aria-label="Закрыть">✕</button></div></div><div class="ai-msgs" aria-live="polite"></div><button type="button" class="ai-open-page" data-ai-open-page>Открыть полный помощник →</button><div class="ai-file" hidden></div><form class="ai-form"><input data-ai-image type="file" accept="image/jpeg,image/png" hidden><button type="button" class="ai-attach" data-ai-attach title="Добавить фото">＋</button><textarea data-ai-input maxlength="4000" placeholder="Спросите агронома…"></textarea><button class="ai-send" type="submit">→</button></form><div class="ai-hint">Регион: Костанайская область · фото до 12 МБ</div>';
  document.body.append(box, fab);

  const miniMessages = box.querySelector('.ai-msgs');
  const miniInput = box.querySelector('[data-ai-input]');
  const miniImage = box.querySelector('[data-ai-image]');
  const miniFile = box.querySelector('.ai-file');
  const miniSend = box.querySelector('.ai-send');

  const pageMessages = document.getElementById('assistant-page-messages');
  const pageInput = document.getElementById('assistant-page-input');
  const pageImage = document.getElementById('assistant-page-image');
  const pageFile = document.getElementById('assistant-page-file');
  const pageSend = document.getElementById('assistant-page-send');

  const persistHistory = () => {
    history = history.slice(-MAX_HISTORY);
    try { localStorage.setItem(STORAGE_HISTORY, JSON.stringify(history)); } catch (_) {}
  };

  const welcome = () => {
    if (!history.length) {
      history.push({
        role: 'bot',
        text: 'Здравствуйте. Я AI-агроном OlzheAgro. Могу подсказать по погоде в Костанае, срокам сева, сорнякам, болезням, удобрениям, почве и уборке. Также можно приложить фото растения.'
      });
      persistHistory();
    }
  };

  const renderMessages = () => {
    const targets = [miniMessages, pageMessages].filter(Boolean);
    targets.forEach(target => {
      target.replaceChildren();
      history.forEach(item => {
        const node = document.createElement('div');
        node.className = 'assistant-bubble ' + (item.role === 'user' ? 'user' : item.role === 'error' ? 'error' : 'bot');
        node.textContent = item.text;
        target.append(node);
      });
      target.scrollTop = target.scrollHeight;
    });
  };

  const addMessage = (text, role) => {
    history.push({text, role});
    persistHistory();
    renderMessages();
    return history.length - 1;
  };

  const replaceMessage = (index, text, role = 'bot') => {
    if (!history[index]) return;
    history[index] = {text, role};
    persistHistory();
    renderMessages();
  };

  const renderFile = () => {
    const label = pendingFile ? '📎 ' + pendingFile.name + ' · ' + (pendingFile.size / 1024 / 1024).toFixed(1) + ' МБ' : '';
    [miniFile, pageFile].filter(Boolean).forEach(node => {
      node.hidden = !pendingFile;
      node.textContent = label;
    });
  };

  const setFile = file => {
    pendingFile = file || null;
    if (!pendingFile) {
      if (miniImage) miniImage.value = '';
      if (pageImage) pageImage.value = '';
    }
    renderFile();
  };

  const acceptFile = file => {
    if (!file) {
      setFile(null);
      return;
    }
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      addMessage('Поддерживаются только JPG и PNG.', 'error');
      setFile(null);
      return;
    }
    if (file.size > MAX_IMAGE) {
      addMessage('Фото слишком большое. Максимальный размер — 12 МБ.', 'error');
      setFile(null);
      return;
    }
    setFile(file);
  };

  const answer = data => {
    if (typeof data === 'string') return data;
    if (Array.isArray(data)) return data.length ? answer(data[0]) : 'Ответ пуст.';
    if (!data || typeof data !== 'object') return String(data ?? 'Ответ пуст.');
    return data.output || data.response || data.text || data.message || data.answer || JSON.stringify(data, null, 2);
  };

  const selectedCropContext = message => {
    const crop = document.getElementById('field-crop')?.value?.trim();
    return crop ? message + '\n\nКонтекст локального приложения: выбранная культура — ' + crop + '.' : message;
  };

  const setBusy = value => {
    busy = value;
    if (miniSend) miniSend.disabled = value;
    if (pageSend) pageSend.disabled = value;
  };

  const send = async source => {
    if (busy) return;
    const input = source === 'page' ? pageInput : miniInput;
    const shown = input?.value.trim() || '';
    if (!shown && !pendingFile) return;

    const file = pendingFile;
    let message = shown || 'Проанализируй приложенное изображение и дай практическую рекомендацию агроному.';
    message = selectedCropContext(message);

    addMessage(shown || ('Фото: ' + file.name), 'user');
    if (input) input.value = '';
    setFile(null);

    const waitingIndex = addMessage('Анализирую…', 'bot');
    setBusy(true);

    try {
      const body = new FormData();
      body.append('message', message);
      body.append('user_id', userId);
      body.append('session_id', sessionId);
      body.append('region', 'Костанайская область, Казахстан');
      if (file) body.append('image', file, file.name);

      const response = await fetch('/api/assistant', {method: 'POST', body});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
      replaceMessage(waitingIndex, answer(data), 'bot');
    } catch (error) {
      replaceMessage(waitingIndex, 'Ошибка AI-агронома: ' + error.message, 'error');
    } finally {
      setBusy(false);
      if (source === 'page') pageInput?.focus();
      else miniInput?.focus();
    }
  };

  const resetConversation = () => {
    sessionId = createId('chat-');
    history = [];
    try {
      localStorage.setItem(STORAGE_SESSION, sessionId);
      localStorage.removeItem(STORAGE_HISTORY);
    } catch (_) {}
    setFile(null);
    welcome();
    renderMessages();
  };

  welcome();
  renderMessages();
  renderFile();

  fab.addEventListener('click', () => {
    box.hidden = !box.hidden;
    if (!box.hidden) {
      renderMessages();
      miniInput?.focus();
    }
  });
  box.querySelector('[data-ai-close]').addEventListener('click', () => { box.hidden = true; });
  box.querySelector('[data-ai-reset]').addEventListener('click', resetConversation);
  box.querySelector('[data-ai-open-page]').addEventListener('click', () => {
    box.hidden = true;
    location.hash = '#assistant';
  });
  box.querySelector('[data-ai-attach]').addEventListener('click', () => miniImage.click());
  miniImage.addEventListener('change', () => acceptFile(miniImage.files?.[0] || null));
  box.querySelector('.ai-form').addEventListener('submit', event => {
    event.preventDefault();
    send('mini');
  });
  miniInput.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      send('mini');
    }
  });

  document.getElementById('assistant-new-chat')?.addEventListener('click', resetConversation);
  document.getElementById('assistant-page-attach')?.addEventListener('click', () => pageImage?.click());
  pageImage?.addEventListener('change', () => acceptFile(pageImage.files?.[0] || null));
  document.getElementById('assistant-page-form')?.addEventListener('submit', event => {
    event.preventDefault();
    send('page');
  });
  pageInput?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      send('page');
    }
  });
  document.querySelectorAll('[data-assistant-prompt]').forEach(button => {
    button.addEventListener('click', () => {
      if (!pageInput) return;
      pageInput.value = button.dataset.assistantPrompt;
      pageInput.focus();
    });
  });

  window.addEventListener('hashchange', () => {
    if (location.hash === '#assistant') {
      renderMessages();
      setTimeout(() => pageInput?.focus(), 0);
    }
  });
})();
