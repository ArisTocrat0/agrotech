"""Opt-in AgroMind v2 client. No network call is made by the analysis pipeline."""
import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .media import load_photo

MAX_RESPONSE = 256 * 1024


def configuration(environ=None):
    env = os.environ if environ is None else environ
    endpoint = env.get('AGRO_ENV_AGROMIND_URL', '').strip()
    user = env.get('AGRO_ENV_AGROMIND_USER_ID', '').strip()
    if not endpoint or not user:
        raise ValueError('Связь с AgroMind выключена. Нужны AGRO_ENV_AGROMIND_URL и настоящий AGRO_ENV_AGROMIND_USER_ID.')
    parsed = urlparse(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError('AgroMind URL должен быть HTTPS без логина, пароля, query и fragment.')
    if not user.isascii() or not user.isdecimal() or not 0 < int(user) <= 2**53 - 1:
        raise ValueError('AgroMind user_id должен быть настоящим положительным целым ID, не UUID.')
    return endpoint, int(user)


def status(environ=None):
    env = os.environ if environ is None else environ
    if not env.get('AGRO_ENV_AGROMIND_URL') and not env.get('AGRO_ENV_AGROMIND_USER_ID'):
        return {'status': 'not_configured', 'message': 'AgroMind не подключён. Анализ работает независимо от помощника.'}
    try:
        endpoint, _ = configuration(env)
        return {'status': 'configured', 'endpoint_host': urlparse(endpoint).hostname,
                'message': 'Настроен совместимый v2 endpoint; доступность сервера не проверена.'}
    except ValueError as exc:
        return {'status': 'configuration_error', 'message': str(exc)}


def payload(event, question, user_id, image=None):
    if not isinstance(question, str) or not question.strip() or len(question.strip()) > 4000:
        raise ValueError('Вопрос должен содержать от 1 до 4000 символов.')
    point = event['location']
    observation = {key: event[key] for key in ['id', 'class_name', 'confidence', 'bbox', 'frame_index',
                                               'timestamp_seconds', 'review_status', 'possible_duplicate_of']}
    observation.update(location=point, interpretation='unverified_visual_hypothesis',
                       safety_notice='Capture position is not object position; assistant must not confirm fire safety or trigger alerts.')
    body = {'schema_version': 2, 'user_id': user_id, 'sessionId': None, 'message': question.strip(), 'history': [],
            'context': {'location': {'scope': 'selected_point' if point else 'unknown',
                                     'point': {'lat': point['latitude'], 'lon': point['longitude']} if point else None},
                        'drone_observation': observation}}
    if image is not None:
        from io import BytesIO
        if len(image) > 5 * 1024 * 1024:
            raise ValueError('Изображение для AgroMind должно быть не больше 5 МиБ.')
        load_photo(BytesIO(image))
        body.update(image=base64.b64encode(image).decode('ascii'), mediaType='image/jpeg')
    return body


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Consent names one endpoint, not whatever its redirect chooses.
        return None


def ask(environment, request):
    if not isinstance(request, dict) or request.get('consent') is not True:
        raise ValueError('Подтвердите отправку выбранного события и его координат настроенному AgroMind.')
    if not isinstance(request.get('include_image', False), bool):
        raise ValueError('include_image должен быть true или false.')
    endpoint, user_id = configuration()
    if request.get('expected_endpoint_host') != urlparse(endpoint).hostname:
        raise ValueError('Получатель AgroMind изменился. Проверьте адрес и подтвердите отправку заново.')
    job = environment.job(request.get('job_id', ''))
    if job['status'] != 'done':
        raise ValueError('Дождитесь завершения анализа.')
    event = next((row for row in job.get('result', {}).get('events', []) if row['id'] == request.get('event_id')), None)
    if event is None:
        raise ValueError('Событие не найдено.')
    image = None
    if request.get('include_image', False):
        prefix = f"/api/environment/files/{job['id']}/"
        relative = event['evidence_url']
        if not relative.startswith(prefix):
            raise ValueError('Некорректный файл доказательства.')
        image, _ = environment.file(job['id'], relative[len(prefix):])
    body = payload(event, request.get('message'), user_id, image)
    call = Request(endpoint, data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8'),
                   headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, method='POST')
    try:
        with build_opener(NoRedirect()).open(call, timeout=45) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError('Ответ AgroMind слишком большой.')
        answer = json.loads(raw)
        if not isinstance(answer, dict) or not isinstance(answer.get('response'), str) or not answer['response'].strip():
            raise ValueError('AgroMind вернул ответ, не соответствующий v2 контракту.')
        return {'response': answer['response'], 'advisory_only': True}
    except (HTTPError, URLError, TimeoutError) as exc:
        # Do not expose response bodies/credentials or retry an uncertain transmission.
        raise ValueError('AgroMind недоступен или отклонил запрос. Автоматического повтора нет; отправка могла состояться.') from exc
