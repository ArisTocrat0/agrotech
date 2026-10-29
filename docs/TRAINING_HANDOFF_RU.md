# Передача текущего обучения — 20 октября 2026

Состояние на 12:36 UTC (17:36 Asia/Qostanay), не итоговый результат. По просьбе разгрузить чат дальнейшее сопровождение можно продолжить в свежей задаче. Процессы не прерывались и не перезапускались. Никаких новых весов не активировано.

Репозиторий `/home/beka/Projects/agrotech`, ветка `pilot/ecokineu-2026-10-21`. Машинный снимок состояния — `artifacts/training-handoff.json`. Локальный интерфейс http://127.0.0.1:8010/ , PID 316510, 22 сохранённых фото. MariaDB приватная, не менять системную БД. Секреты не выводить. AgroMind и KINEU ERP не трогать. Ничего не удалять, не скачивать новые изображения, не дублировать наборы.

## Текущий trash

`outputs/pilot-training/litter-v3-land-yolo11n-full-cpu-20261020/`; PID обучения **260666**, PID supervisor **261427**. Соответствующие `.pid` находятся рядом с каталогом и в `supervisor.pid`. Не запускать второй прогон и не посылать сигналы. CPU 2 потока, batch 1, freeze 0, максимум 30 эпох, patience 6, бюджет обучения 5,5 часа с резервом на экспорт/оценку. Только best/last. Старт около 10:40 UTC.

7 эпох завершены; идёт 8-я. Лучший checkpoint — эпоха 7: validation P=0,70760, R=0,32075, mAP50=0,38343, mAP50–95=0,25841. Это встроенные validation-метрики, **не итоговая качество на holdout и не рабочий порог**. Эпоха 7 заняла 937,49 с, прошло 6811,10 с. RSS на снимке 418,4 MiB, HWM 786,5 MiB, swap процесса 435,0 MiB. Ранняя остановка отодвинулась после улучшения на 7-й эпохе.

Supervisor уже ожидает экспорт и автоматически вызовет `scripts/evaluate_quality_v3.py`. Смотреть `supervision.json`, `quality-evaluation.log`, `quality-report.json`, `development-evaluation.json`, `failure.json`. Отсутствие файла не означает ошибку. Лог TQDM читать через `.replace('\r','\n')`, не печатать целиком.

Порядок завершения:

1. Дождаться существующего supervisor и терминального отчёта. Не запускать оценку одновременно с ним. При ошибке выяснить исход; кэш допускает возобновление только при прежних хешах модели, данных и порога. Не выбирать новый порог после holdout.
2. Выполнить `.venv/bin/python scripts/verify_v3_candidate_export.py --run litter-v3-land-yolo11n-full-cpu-20261020` (после оценки, без обучения). Это parity, не метрики качества.
3. Выполнить `.venv/bin/python scripts/render_candidate_review.py --run litter-v3-land-yolo11n-full-cpu-20261020 --dataset litter-v3-land`. Просмотреть positive-review, negative-review и две operator-candidate картинки. Зелёное — разметка, красное — предсказание. Не обучать/не калибровать по пользовательским фото.
4. Записать ручное решение `manual-review.json`. Если критерии не пройдены — `verdict: rejected_not_activated`, причина и реальные числа; ничего не включать. Если пройдены и визуальный анализ приемлем — guarded `scripts/promote_quality_candidate.py --run ... --class-name trash --review-reason 'конкретные результаты и ограничения'` сохранит backup реестра, проверит parity/threshold lock и изменит только локальный реестр. Его verdict `approved_local_pilot` уже поддержан интерфейсом. Скрипт не перезапускает сервер. При включении обновить статическое предупреждение upload о временном отключении мусора; оно пока правильно для текущего состояния.
5. При активации дождаться пустой очереди, использовать только `scripts/restart_pilot_safely.py`, проверить API и версионно переобработать две пользовательские фотографии через `/api/pilot/photos/<id>/reprocess` с expected_registry_sha256. Исходники и история сохраняются. Сами фото без GPS; не придумывать координаты.

Набор `datasets/litter-v3-land`: 1634 изображения, 5272 рамки, frozen lock SHA 3257249f1dee4155e3db9dba141ebdfedb5ba006ed7aa585907cf6d7e8e98830. Восемь новых aerial batches — proxy holdout, географическая независимость не доказана; положительного водного acceptance-теста нет. Папка potato_water_v1 в data-task существует, **не добавлять её в текущий прогон и не оценивать без отдельного согласованного этапа**.

## Smoke — подготовлен, НЕ запущен

Пользователь разрешил данные дыма до **1 ГБ**. Проверенный source `/home/beka/Documents/Codex/2026-10-20/task-2/ecokineu_smoke_pyrosdis_v1`, интеграция `datasets/smoke-pyrosdis-v1`: 500 фото (370 положительных, 130 просмотренных отрицательных), 421 рамка, train/val/test_development 350/75/75; site и camera-day раздельные. Apache-2.0 dataset, Pyronear/SDIS attribution сохранены. Источник целиком 186 650 624 байта с архивом, изображения не копировались — используются per-file symlinks. Метаданные/разметка/хеши в Git, изображения игнорируются. Историческая role source_negative_pending_visual_review нормализована только при negative_review.decision=accept.

**Это переразбиение source val; возможная обучающая история baseline неизвестна, независимость событий не доказана.** Туман/облака — визуальные теги. Не обещать метеорологическую истину и aerial field accuracy.

Только ПОСЛЕ terminal evaluation и manual-review trash:

1. `.venv/bin/python -u scripts/evaluate_quality_smoke.py --baseline-only` — val75, блокирует shared training.lock, выбирает и фиксирует baseline-порог до обучения. Test-development пока не читает моделью. Выход `outputs/pilot-training/smoke-baseline-pyrosdis-v1/threshold-lock.json`.
2. Один detached запуск `.venv/bin/python -u scripts/train_quality_smoke.py --name smoke-pyrosdis-yolo11n-cpu-20261020 --epochs 20 --patience 5 --hours 3`. Сохранить PID в `outputs/pilot-training/smoke-pyrosdis-yolo11n-cpu-20261020.pid`, stdout/stderr в одноимённый `.log`. Дождаться создания run, записать `artifacts/smoke-active-run.json` с `{"run":"smoke-pyrosdis-yolo11n-cpu-20261020"}`, запустить один `scripts/supervise_quality_smoke.py --run ...`, сохранить supervisor.pid. **Не запускать рядом тяжёлые задачи или Chrome.** Trainer сам требует оценку/решение trash и baseline lock.
3. Это transfer от исходного локального YOLO11n, а не V2/V3 trash weights; CPU2, batch1, freeze0, max3h, cacheFalse, workers0, best/last. Первый epoch даст фактическую оценку времени и памяти. Новых загрузок нет. Не менять параметры/данные посередине.
4. Supervisor экспортирует/оценивает smoke: порог val-only, затем test-development. Сравнивает baseline с val-locked порогом и исходным 0,35; показывает P/R/F1 и ложные тревоги на fog/cloud/glare/lens тегах. Критерий заранее сохранён в predeclared-evaluation-policy.json. Не подбирать порог на test или двух пользовательских фотографиях.
5. `.venv/bin/python scripts/verify_smoke_candidate_export.py --run ...`, затем визуальный анализ. При провале оставить прежнюю модель. При реальном улучшении `promote_quality_candidate.py --class-name smoke ...` сохранит **старый Fire**: прежние веса неизменны, Fire class0 продолжает работать, прежний Smoke class2 маскируется, новый Smoke добавляется отдельно. Проверить численную неизменность Fire на двух существующих публичных кадрах. Нельзя заменить FireSmoke целиком на smoke-only и потерять огонь. Нельзя заявлять, что на smoke-only данных дообучен Fire.

Проверены синтаксис новых Python/JS и 11 тестов pilot/MariaDB + 3 parser-теста. Реальное smoke-обучение/оценка ещё не выполнены; prepared scripts не выдавать за результаты. Для браузерной проверки после обучения использовать свежую QA-миссию, чтобы dedup не вернул старую версию; не удалять пользовательские данные или архивы.

Новых разрешений для перечисленных локальных действий не требуется. Это передача незавершённого длительного этапа, не отказ и не неизвестный исход мутации. Реестр активных моделей остался 41a5cdc82ed184eb4777bfff7551c157e9a216450145e742e11edd94e5ae7953; trash отключён, FireSmoke baseline сохранён.
