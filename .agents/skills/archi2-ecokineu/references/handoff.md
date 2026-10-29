# Состояние передачи — 29 октября 2026

## Остановка и следующий шаг

Исходная Fedora: `/home/beka/Projects/agrotech`, чистая ветка `pilot/ecokineu-2026-10-21`, последний SHA `c5d50aa`. До публикации удалённый main проверен: `f0ccf1dd141b05a4f43a3bed3ce31e053bd4a016`. Публикация готовится отдельным коммитом поверх него без 3421 файла датасетов; исходная ветка не переписывается. Статус публикации проверять через `git ls-remote origin refs/heads/main` и сообщение текущей задачи: этот документ не является доказательством push.

В репозитории нет `.github` CI или проверенного внешнего deployment workflow. `docs/PILOT_DEPLOYMENT_CHECKLIST.md` прямо фиксирует: сервер не выбран. Внешний деплой не выполнен. Для продолжения нужен адрес/провайдер и целевая среда пользователя; не публиковать текущий HTTP напрямую, не использовать KINEU ERP. Локальный адрес — `http://127.0.0.1:8010/`; read-only healthcheck 29 октября вернул connection refused для status/photos: пилот сейчас не слушает этот порт; запуск/перезапуск не выполнялся. Исторические отчёты 21 октября не выдавать за сегодняшнюю проверку.

Первый следующий шаг Арчи 2: сравнить полученные файлы с исходными, устранить оборванные symlinks и абсолютные YAML-пути, проверить ресурсы и зависимости, затем воспроизвести baseline. Только после согласования нового эксперимента готовить новые данные/обучение. Требуется улучшение разметки/покрытия, а не подгонка порога к просмотренному holdout.

## Перенос отдельно от Git

Сохранять структуру от корня проекта:

- `datasets/litter-v3-land/`
- `datasets/smoke-pyrosdis-v1/`
- `outputs/pilot-training/litter-v3-land-yolo11n-full-cpu-20261020/`
- `outputs/pilot-training/smoke-pyrosdis-yolo11n-cpu-20261020/`

В результатах нужны `weights/best.pt`, `weights/last.pt`, отчёты оценки, threshold-lock, parity и ручной проверки. Также нужны `scripts/`, `requirements.txt`, исходный `artifacts/yolo11n.pt`, `docs/QUALITY_RESULTS_20261021_RU.md`. Четыре дерева ранее оценены примерно в 4,48 ГБ; фактический объём пересчитать с учётом разыменования.

Smoke содержит 500 symlinks; исходные фото на Fedora: `/home/beka/Documents/Codex/2026-10-20/task-2/ecokineu_smoke_pyrosdis_v1/images/`. Копировать содержимое ссылок (например `rsync -aL` с явно выбранными источником и назначением). Сначала проверить существование targets и место, после копирования — SHA256 и количество файлов. Не считать перенос завершённым без проверки на получателе. `litter-v3-land` сейчас без symlinks.

В `data.yaml` и дополнительных YAML обоих наборов абсолютный `path: /home/beka/Projects/agrotech/datasets/...`. Обновить под новый корень, сохраняя splits/метки. Проверить также пути manifest/скриптов. Не заново переразбивать набор и не перезаписывать отчёты старого опыта.

Для запуска baseline дополнительно нужны файлы из `artifacts/ecokineu-models.json`: активный Fire `artifacts/fire-candidate-v6/best_openvino_model/best.{xml,bin}`, SHA и SOURCE; weed/reference assets по `weeds.py` и конфигурации. В Git крупные веса отсутствуют по `.gitignore`; один checkout не является работающей установкой. Нельзя подменять baseline отклонённым кандидатом.

## Подтверждённые результаты и checkpoint

`quality-report.json`: litter11 эпох, smoke20; оба `development-evaluation.json` содержат `candidate_recommended_for_manual_review=false`. Litter: порог0,40, aerial precision91,7%, recall14,8% при требовании >=25%, ложные тревоги2/5 (40%) при <=10%; export parity не прошла. Smoke: порог0,05, precision40% при >=50%, recall52,2%, ложные тревоги4/15 (26,7%) при <=10%. Небольшие/неполностью независимые наборы не доказывают полевое качество. Подробности и оговорки — QUALITY_RESULTS.

Во всех четырёх `best.pt/last.pt` проверена метаинформация pickle в ZIP без исполнения модели: Ultralytics8.4.154, epoch=-1, optimizer=None. Точный resume с восстановлением optimizer/epoch невозможен; допустим новый fine-tuning с новым run ID/бюджетом/планом оценки. Не использовать `resume=True` как обещание продолжить тот же опыт. Не десериализовать непроверенные pickle с `weights_only=False`.

Текущий registry содержит `fire-v6-4a60bd37`, classes `[fire,null,smoke]`, threshold0,35; старый trash disabled. Новые кандидаты отсутствуют. Fire/Smoke не разделять перестановкой классов. Сорняки — отдельный DINO/reference baseline; высокая reference classification accuracy не является aerial detection метрикой.

## Команды и границы запуска

Из корня checkout, с подготовленным проектным venv:

```bash
.venv/bin/python -B -m unittest scripts.test_pilot_detector scripts.test_quality_metrics scripts.test_tiled_geometry scripts.test_training_progress scripts.test_training_recovery scripts.test_public_diagnostic scripts.test_analysis_coverage -v
```

29 октября этот набор: 24 теста OK. Он проверяет контракты/геометрию/защиты, не фактическую точность моделей. Попытка включить test_reprocess добавила 19 ошибок подготовки MariaDB (нет приватного client.json); интеграционное прохождение не заявляется. Python syntax проверен без исполнения. `test_training_recovery.py` в этой публикации исправлен: импорт recovery-скрипта определяется относительно файла теста вместо жёсткого пути Fedora. `scripts/test_pilot.py`, `test_reprocess.py`, HTTP integration требуют подготовленной изолированной MariaDB; без `outputs/pilot-db/client.json` падают. Не копировать credentials в Git и не запускать тесты на чужой БД. Не заявлять весь integration suite пройденным по unit-набору.

Для локального пилота после подготовки приватного окружения и проверки скриптов:

```bash
bash scripts/start_pilot.sh
```

Скрипт вызывает `scripts/local_db.py` (создание/запуск локальной БД), затем `web_pilot.py --port 8010`; поэтому это действие с состоянием, не read-only проверка. Проверить `GET /api/pilot/status` и `/api/pilot/photos`, active/configured registry SHA, отсутствие активной очереди перед рестартом. `scripts/restart_pilot_safely.py` — только известный idle local PID, не чужие процессы. Не использовать demo_photos для healthcheck: он добавляет фотографии.

Существующие исследовательские точки входа (сначала читать код и `--help`, не запускать автоматически): `train_quality_v3.py --name <new-id> --epochs <n> --hours <budget> --patience <n>`, аналогично `train_quality_smoke.py`; `evaluate_quality_v3.py`, `evaluate_quality_smoke.py`, `verify_v3_candidate_export.py`, `verify_smoke_candidate_export.py`. Проверить их pinned run IDs и пути прежде адаптации. Не выполнять integration/data-building скрипты поверх перенесённого замороженного опыта без плана.

`recover_quality_training.py --run <known-run>` по умолчанию диагностика; `--execute` изменяет run и не решает stripped-checkpoint resume. `promote_quality_candidate.py` меняет registry только при пройденных gates/parity/manual review; нынешние два кандидата эти условия не выполняют. Не обходить assertions и не переписывать метрики ради допуска.

## Отчёт после продолжения

Указать checkout/SHA, что реально перенесено и проверено, тесты с результатами, активные модели, новый run/оценку при наличии. Разделять push, CI, локальный старт и внешний деплой. Для деплоя нужны конкретный target и успешный healthcheck точной версии; успешный push не является деплоем. Не наследовать сегодняшнее поручение как постоянное разрешение будущих публикаций.
