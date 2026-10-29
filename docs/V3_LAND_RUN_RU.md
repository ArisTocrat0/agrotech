# Экокинеу: фиксированный land-прогон V3

Run:`litter-v3-land-yolo11n-full-cpu-20261020`. Состояние/результат смотрите в `outputs/pilot-training/<run>/`, а не по этому статичному документу. Повторно обучение/supervisor для просмотра не запускаются.

Принят источник `/home/beka/Documents/Codex/2026-10-20/task-2/ecokineu_litter_v3_land`. Его README/data.yaml/integration_check/manifest прочитаны. Собственная копия `datasets/litter-v3-land` прошла повторную полную проверку1634 файлов,5272bbox, уникальных SHA/pixels, нормализации COCO→YOLO, групп и сохранности holdout. `snapshot-lock.json` фиксирует все входы. Нельзя менять этот набор во время run и добавлять водное дополнение.

765 train (648positive/117negative),139val(136/3). Для калибровки после отбора checkpoint добавляются41 старое aerial validation и28 старых validation negatives:208development-кадров. Старые test остаются отдельными development, не входят в train/val/калибровку. Holdout:554 ранее не использованных aerial batch-фото +5 новых negatives по другим авторским группам. Это batch/author proxy, **географическая независимость не доказана**, положительного водного теста нет. Лицензии индивидуальны, Commons не объявляется общим CC BY4; source manifests/attribution сохранены.

Пользовательские фото исключены из train/tuning: совпадений файловых/пиксельных SHA нет. Дополнительный консервативный dHash-контроль двух фото против tuning не нашёл близких<=6; минимумы18 и13. Они могут использоваться лишь как отдельная ненастраиваемая диагностика после фиксации порога.

## Обучение и оценка

Исходный pretrained `artifacts/yolo11n.pt`, не отвергнутые V2-веса. freeze0 (все обучаемые слои, кроме фиксированного DFL),CPU2threads,nice+5,batch1,640px,AdamW lr0=0.0003,lrf0.1,cosLR,warmup1epoch с biasLR0.0003,scale0.25,mosaic0,workers0,cache=false,seed42,max30epochs,patience6. Это заранее выбранный land-baseline; многим aerial-объектам при640 остаётся очень мало пикселей, поэтому качество не обещается.

Плановый предел training5.5ч с резервом в общем6ч на экспорт/оценку. На границе эпохи проверяется остаток против длительности предыдущей, чтобы не начинать ожидаемо не помещающуюся эпоху. Реальное время/память пишутся после каждой эпохи. Только best/last, save_period=-1, полный датасет в RAM не кэшируется, NPY-кэша нет; остаётся небольшой ограниченный внутренний буфер загрузчика. Веса не активируются автоматически.

`evaluate_quality_v3.py` сначала выполняет калибровку208development-кадров. Сетка confidence0.05…0.90 задана в `predeclared-evaluation-policy.json`, минимумы P0.50/R0.25/negative-image alarm rate<=0.10 — только нижний фильтр пилота, не production-приёмка. Выбирается F1 среди прошедших либо диагностический максимумF1 с явным отказом. `threshold-lock.json` пишется до первого inference holdout. `holdout-consumed.json` отмечает расходование holdout; восстановление возможно только с теми же model/data/threshold и сохранёнными выходами, не с новым подбором.

После этого оцениваются554+5 holdout, отдельные старые development, проверенные train-negatives как regression и локальные user-диагностики. На5 negative точность FPR крайне ограничена, нельзя обещать отсутствие ложных тревог. Проверять отдельно gravel/mesh/water по `negative_kind`. Новый водный пакет `/home/beka/Documents/Codex/2026-10-20/task-2/ecokineu_potato_water_v1` только учтён как доступный: не копировался и не добавлен в текущий run.

## Память, хранение, ограничения пользователя

До новой инструкции о памяти была создана логическая копия V3. На Btrfs проверено: images4.06GiB total,0.00B exclusive,4.06GiB shared — блоки CoW общие с источником, второго физического объёма изображений4GiB не занято. Дополнительных полных копий/скачиваний не делается. Никакие архивы, кэши, исходники или старые веса не удаляются: пользователь очистит сам.

При запуске было~0.94GiB available RAM,~69GiB free disk. В начале первой эпохи RSS~343MiB, наблюдавшийся VmHWM~787MiB, VmSwap~426MiB; это промежуточный факт, не гарантия максимума. Для best/last,IR,логов/отчётов резервируется до150MiB дополнительного диска; фактическое использование проверяется. Параллельного тяжёлого smoke-run нет. Fire/smoke baseline,weed,карта и журнал сохраняются.

## Управление и восстановление

Training PID хранится в `outputs/pilot-training/<run>.pid`, supervisor — `<run>/supervisor.pid`; не дублировать. Состояние:quality-config.json,progress.json,quality-report.json,failure.json,supervision.json. Один общий training.lock защищает от параллельного обучения. При ошибке сначала проверить жив ли процесс и checkpoint; не перезаписывать run.

Итог:calibration-evaluation.json,threshold-lock.json,holdout-evaluation.json,development-evaluation.json,manual-review.json. Ручная проверка обязательна; подключение только после принятия с registry backup/SHA/откатом, затем версионная reprocess сохранённых фото. Пока старый trash и V2 не активированы.

Smoke — отдельный запрошенный этап после trash. Локально размеченного smoke/fire корпуса не найдено; точный блокер и бюджет предварительного пакета описаны в `docs/SMOKE_FINE_TUNING_PLAN_RU.md`. Без принятия данных дообучение дыма не заявляется выполненным.
