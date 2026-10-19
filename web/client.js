'use strict';
async function api(url, options, format = 'json') {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json();
    throw new Error(body.error || t('Ошибка запроса'));
  }
  return format === 'blob' ? response.blob() : response.json();
}

// One definition shared by dashboard and review navigation.
const isPending = detection => {
  if (detection.review && detection.review !== 'unknown') return false;
  if (detection.review_required === false) return false;
  return true;
};
function reviewMetrics(rows) {
  const detections = rows.flatMap(row => row.detections);
  const pending = detections.filter(isPending).length;
  const total = detections.length;
  return {total, pending, reviewed: total - pending,
    confirmed: detections.filter(d => d.review === 'weed').length,
    percent: total ? Math.round((total - pending) / total * 100) : 100};
}
function pendingTarget(rows, image = 0, detection = -1) {
  const current = rows[image]?.detections || [];
  for (let index = detection + 1; index < current.length; index++) {
    if (isPending(current[index])) return {image, detection: index};
  }
  for (let offset = 1; offset <= rows.length; offset++) {
    const next = (image + offset) % rows.length;
    const index = rows[next].detections.findIndex(isPending);
    if (index >= 0) return {image: next, detection: index};
  }
  return null;
}

function technicalSection(title,nodes,open=false){const details=document.createElement('details');details.className='settings-section';details.open=open;const summary=document.createElement('summary');summary.innerHTML=`<span>${t(title)}</span><small>${t('Нажмите, чтобы раскрыть')}</small>`;details.append(summary);nodes[0].before(details);nodes.forEach(node=>details.append(node));return details;}

// Load the n8n-backed agronomist assistant after shared client helpers.
const agronomistAssistant = document.createElement('script');
agronomistAssistant.src = '/assistant.js';
agronomistAssistant.async = false;
document.head.append(agronomistAssistant);
