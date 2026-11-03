'use strict';
async function api(url, options, format = 'json') {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json();
    throw new Error(body.error || t('Ошибка запроса'));
  }
  return format === 'blob' ? response.blob() : response.json();
}

const hasManualReview = detection => Boolean(detection.review);
const isUncertain = detection => detection.prediction_status === 'uncertain'
  || detection.kind === 'unknown'
  || Boolean((detection.uncertainty_reasons || []).length);

// Legacy analyses remain review-queue based. Automatic analyses expose only
// uncertain objects as optional review targets; absence of a review is not an error.
const isPending = (detection, row = null) => row?.mode === 'automatic'
  ? isUncertain(detection) && !hasManualReview(detection)
  : !detection.review || detection.review === 'unknown';

function reviewMetrics(rows) {
  const items = rows.flatMap(row => (row.detections || []).map(detection => ({row,detection})));
  const automatic = Boolean(rows.length && rows.every(row => row.mode === 'automatic'));
  const total = items.length;
  const uncertain = items.filter(({detection}) => isUncertain(detection)).length;
  const manualReviewed = items.filter(({detection}) => hasManualReview(detection)).length;
  const corrected = items.filter(({detection}) => detection.manual_correction || detection.review_status === 'corrected').length;
  const recognized = items.filter(({detection}) => detection.prediction_status === 'recognized'
    || (!detection.prediction_status && detection.kind !== 'unknown' && detection.species !== 'unknown')).length;
  const pending = items.filter(({row,detection}) => isPending(detection,row)).length;
  const reviewed = automatic ? manualReviewed : total - pending;
  return {
    total, pending, reviewed, corrected, recognized, uncertain,
    confirmed: items.filter(({detection}) => detection.review === 'weed').length,
    percent: total ? Math.round((automatic ? recognized : total - pending) / total * 100) : 100
  };
}

function pendingTarget(rows, image = 0, detection = -1) {
  const current = rows[image]?.detections || [];
  for (let index = detection + 1; index < current.length; index++) {
    if (isPending(current[index], rows[image])) return {image, detection: index};
  }
  for (let offset = 1; offset <= rows.length; offset++) {
    const next = (image + offset) % rows.length;
    const index = (rows[next]?.detections || []).findIndex(d => isPending(d, rows[next]));
    if (index >= 0) return {image: next, detection: index};
  }
  return null;
}

function uncertaintyText(detection) {
  const messages = detection.uncertainty_messages || [];
  if (messages.length) return messages.join(' · ');
  const labels = {
    unsupported_crop:'Нет обучающих примеров выбранной культуры для уверенного разделения «сорняк/культура».',
    insufficient_calibration_data:'Недостаточно validation-данных для калибровки вида.',
    species_calibration_unavailable:'Порог вида не откалиброван.',
    low_species_margin:'Вид неоднозначен.',
    insufficient_category_calibration:'Недостаточно validation-данных для калибровки категории.',
    category_calibration_unavailable:'Порог категории не откалиброван.',
    low_category_margin:'Категория «сорняк/культура» неоднозначна.'
  };
  return (detection.uncertainty_reasons || []).map(reason => labels[reason] || reason).join(' · ');
}

function technicalSection(title,nodes,open=false){const details=document.createElement('details');details.className='settings-section';details.open=open;const summary=document.createElement('summary');summary.innerHTML=`<span>${t(title)}</span><small>${t('Нажмите, чтобы раскрыть')}</small>`;details.append(summary);nodes[0].before(details);nodes.forEach(node=>details.append(node));return details;}

// Load the n8n-backed agronomist assistant after shared client helpers.
const agronomistAssistant = document.createElement('script');
agronomistAssistant.src = '/assistant.js';
agronomistAssistant.async = false;
document.head.append(agronomistAssistant);