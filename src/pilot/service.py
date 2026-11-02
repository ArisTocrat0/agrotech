"""Durable FIFO for independent photos. Camera position is never object position."""
import base64,hashlib,json,re,threading,time,uuid
from datetime import datetime,timezone
from io import BytesIO
from pathlib import Path
from .store import Store
from ..environment.media import load_photo,location,exif_capture_location
from ..environment.pipeline import write_json

def validate_photo(payload):
    mission=payload.get('mission','')
    if not isinstance(mission,str) or not re.fullmatch(r'[\w-]{1,80}',mission):
        raise ValueError('ID миссии: 1–80 букв, цифр, _ или -.')
    captured=payload.get('captured_at')
    if captured=='':captured=None
    if captured is not None:
        if not isinstance(captured,str) or len(captured)>40: raise ValueError('Некорректное время съёмки.')
        try: dt=datetime.fromisoformat(captured.replace('Z','+00:00'))
        except ValueError: raise ValueError('Нужно время ISO 8601 с часовым поясом.')
        if dt.tzinfo is None: raise ValueError('Время съёмки должно содержать часовой пояс.')
        captured=dt.isoformat()
    mode=payload.get('analysis_mode','environment')
    if mode not in ('environment','weeds','trash','fire_smoke','common'): raise ValueError('Неизвестный режим анализа.')
    if mode!='environment' and len(mission)>64:raise ValueError('Для отдельных направлений ID миссии: до 64 символов.')
    name=payload.get('name','photo.jpg')
    if not isinstance(name,str) or len(name)>240: raise ValueError('Некорректное имя.')
    name=Path(name.replace('\\','/')).name
    if Path(name).suffix.lower() not in ('.jpg','.jpeg','.png'): raise ValueError('Только JPEG/PNG. Видео не принимается.')
    encoded=payload.get('photo','')
    if not isinstance(encoded,str) or len(encoded)>14_000_000: raise ValueError('Фото: не больше 10 МиБ.')
    try: data=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError): raise ValueError('Некорректный base64 снимка.')
    if not data or len(data)>10*1024*1024: raise ValueError('Пустой или слишком большой снимок.')
    load_photo(BytesIO(data))
    loc=payload.get('location')
    loc=location(loc) if loc is not None else exif_capture_location(data)
    metadata=payload.get('metadata',{})
    if not isinstance(metadata,dict) or len(json.dumps(metadata,allow_nan=False).encode('utf-8'))>8000: raise ValueError('Метаданные: JSON-объект до 8 КБ.')
    return data,{'analysis_mode':mode,'mission':mission,'captured_at':captured,'name':name,'location':loc,'metadata':metadata,
                 'sha256':hashlib.sha256(data).hexdigest()}

def parse_training_tail(tail):
    # Carriage-return progress bars must be parsed per line, never across batch/epoch pairs.
    clean=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',tail);result={}
    for line in clean.splitlines():
        match=re.search(r'^\s*(\d+)/(\d+)\s+.*?(\d+)/(\d+)',line)
        if not match:continue
        epoch,epochs,batch,batches=map(int,match.groups())
        if 1<=epoch<=epochs and 0<=batch<=batches:result={'current_epoch':epoch,'maximum_epochs':epochs,'batch':batch,'batches':batches}
    return result

def analysis_coverage(row):
    """Report what this specific result actually analyzed, never turn disabled into zero."""
    result=row.get('result') or {};model=result.get('model') or {};mode=row.get('analysis_mode','environment')
    models=model.get('models') or []
    classes=set(model.get('classes') or [])|{c for m in models for c in m.get('classes',[]) if c}
    quarantined=any(m.get('id')=='trash-dronewaste500-v1-transfer-3e' for m in models)
    coverage={}
    for kind in ('trash','fire','smoke','weed'):
        requested=kind in {'weeds':('weed',),'trash':('trash',),'fire_smoke':('fire','smoke'),'common':('weed','trash','fire','smoke'),'environment':('trash','fire','smoke')}[mode]
        if not requested:status='not_analyzed';reason='Эта задача не запрашивалась.'
        elif row.get('state')=='error':status='error';reason='Ошибка обработки; отсутствие объектов не установлено.'
        elif row.get('state')!='done':status='not_analyzed';reason='Анализ ещё не завершён.'
        elif kind=='trash' and (quarantined or kind not in classes):status='disabled';reason='Распознавание мусора временно недоступно: модель обновляется. Этот снимок не проверен на мусор.'
        elif ('weeds' if kind=='weed' else 'environment') in model.get('errors',{}):status='error';reason='Ошибка детектора: '+model['errors']['weeds' if kind=='weed' else 'environment']
        elif kind not in classes:status='disabled';reason='Детектор этого класса недоступен; отсутствие объектов не установлено.'
        else:
            found=any(e['class_name']==kind for e in result.get('events',[]))
            status='analyzed_detections' if found else 'analyzed_no_detections';reason='Есть гипотезы модели.' if found else 'Модель выполнена; гипотез выше порога нет. Это не доказательство отсутствия объекта.'
        coverage[kind]={'status':status,'reason':reason}
    return coverage

class Pilot:
    def __init__(self,root,detector_factory=None):
        self.root=Path(root);self.base=self.root/'outputs/pilot';self.base.mkdir(parents=True,exist_ok=True)
        self.compute_lock=threading.RLock();self.ingest_lock=threading.Lock();self.stop=threading.Event();self.wake=threading.Event()
        self.detector_factory=detector_factory
        self.registry=self.root/'artifacts/ecokineu-models.json'
        self.detector=None;self.weed_detector=None;self.model_error=None;self.direction_detectors={};self.compiled_models={}
        # Advisory process lock prevents two servers consuming the same queue.
        import fcntl
        self.lockfile=(self.base/'worker.lock').open('a')
        try: fcntl.flock(self.lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lockfile.close()
            raise RuntimeError('Другой сервер уже обрабатывает эту очередь.')
        self.store=Store(self.root/'outputs/pilot-db/client.json')
        from .workspaces import Workspaces
        self.workspaces=Workspaces(self)
        self.worker=threading.Thread(target=self.run,name='photo-queue',daemon=True);self.worker.start()

    def ingest(self,payload):
        data,fields=validate_photo(payload)
        with self.ingest_lock:
            # Preserve the legacy unique key while allowing the same photo in distinct workspaces.
            dedup_mission=fields['mission'] if fields['analysis_mode']=='environment' else fields['mission']+'::'+fields['analysis_mode']
            old=self.store.duplicate(dedup_mission,fields['sha256'])
            if old:
                for key in ('captured_at','location','metadata','analysis_mode'):
                    if old.get(key)!=fields[key]: raise ValueError('Снимок уже принят с другими метаданными. Проверьте ID миссии и GPS.')
                return {'duplicate':True,'photo':old}
            if sum(r['state']=='queued' for r in self.store.list())>=500: raise ValueError('Очередь заполнена: дождитесь обработки.')
            key=uuid.uuid4().hex;folder=self.base/key;folder.mkdir()
            (folder/'original').write_bytes(data)
            row={'id':key,**fields,'dedup_mission':dedup_mission,'state':'queued','created':datetime.now(timezone.utc).isoformat(),
                 'result':None,'error':None,'attempts':0,'acquisition':'uploaded_photo_sequence'}
            self.store.add(row); self.wake.set()
            return {'duplicate':False,'photo':row}

    def diagnose_public_photo(self,key):
        """Real in-memory QA on an existing public photo; preserve all saved evidence/history."""
        with self.ingest_lock:
            if any(r['state'] in ('queued','running') for r in self.store.list()):
                raise ValueError('Дождитесь пустой очереди перед диагностикой.')
            shown=next((r for r in self.photos() if r['id']==key),None)
            if shown is None or shown['presentation']['kind']!='public_demo':
                raise ValueError('Диагностика разрешена только для существующего публичного QA-фото.')
            row=self.store.get(key)
            if row.get('analysis_mode')!='environment':raise ValueError('Нужен environment-снимок.')
            original=self.base/key/'original'
            if hashlib.sha256(original.read_bytes()).hexdigest()!=row['sha256']:
                raise ValueError('Хеш исходного фото изменился.')
            if self.detector is None:
                if self.detector_factory:self.detector=self.detector_factory()
                else:
                    from .detector import Detector
                    self.detector=Detector(self.registry)
            if self.detector.registry_sha256!=hashlib.sha256(self.registry.read_bytes()).hexdigest():
                raise ValueError('Загружен другой реестр: нужен безопасный перезапуск.')
            started=time.perf_counter();detections=self.detector.detect(load_photo(original))
            return {'photo_id':key,'source_sha256':row['sha256'],'model':self.detector.metadata,
                    'detections':detections,'seconds':time.perf_counter()-started,
                    'persisted':False,'scope':'Public qualitative QA only; not independent accuracy, holdout or a user flight.'}

    def retry(self,key):
        with self.ingest_lock:
            row=self.store.get(key)
            if row['state']!='error': raise ValueError('Повтор разрешён только после ошибки.')
            self.store.update(key,state='queued',error=None);self.wake.set()
        return {'id':key,'state':'queued'}

    def review(self,key,event_id,status):
        if status not in ('unreviewed','confirmed','rejected'): raise ValueError('Некорректный статус проверки.')
        with self.ingest_lock:
            row=self.store.get(key)
            if row['state']!='done': raise ValueError('Анализ ещё не завершён.')
            event=next((e for e in row['result']['events'] if e['id']==event_id),None)
            if event is None: raise ValueError('Находка не найдена.')
            event.update(review_status=status,reviewed_at=datetime.now(timezone.utc).isoformat())
            self.store.update(key,result=row['result'])
        return {'status':status}

    def reprocess(self,key,expected_registry_sha256):
        """Explicit new-version analysis bypasses ingest dedup, preserving old evidence/reviews."""
        import shutil
        with self.ingest_lock:
            row=self.store.get(key)
            if row.get('analysis_mode')!='environment':raise ValueError('Новая версия мусора применяется только к environment-снимкам.')
            if row['state'] in ('queued','running'):raise ValueError('Снимок уже находится в очереди.')
            if not self.registry.exists():raise ValueError('Новая модель не настроена.')
            digest=hashlib.sha256(self.registry.read_bytes()).hexdigest()
            if expected_registry_sha256!=digest:raise ValueError('Версия изменилась: обновите страницу.')
            specs=json.loads(self.registry.read_text())['models']
            if not any(s.get('enabled',True) and 'trash' in s.get('classes',[]) for s in specs):raise ValueError('Распознавание мусора временно недоступно: модель обновляется.')
            if self.detector is not None and getattr(self.detector,'registry_sha256',None)!=digest:raise ValueError('Новые веса ещё не загружены: необходим безопасный перезапуск сервера.')
            prior=(row.get('result') or {}).get('model',{}).get('registry_sha256')
            if prior==digest:return {'duplicate':True,'photo':row,'note':'Эта версия уже обработала снимок.'}
            folder=self.base/key;version=str(time.time_ns());archive=folder/'history'/version;archive.mkdir(parents=True)
            write_json(archive/'photo.json',row)
            for name in ('annotated.jpg','result.json'):
                if (folder/name).exists():shutil.copyfile(folder/name,archive/name)
            history=list(row.get('analysis_history',[]));history.append({'version':version,'registry_sha256':prior,'completed':row.get('completed'),'evidence_directory':str(archive.relative_to(self.root))})
            updated=self.store.update(key,state='queued',result=None,error=None,analysis_history=history,reprocess_requested_at=datetime.now(timezone.utc).isoformat(),requested_registry_sha256=digest)
            self.wake.set();return {'duplicate':False,'photo':updated}

    def photos(self):
        """Presentation provenance is derived from pinned dataset hashes, never GPS guesses."""
        import html
        sources={}
        for name in ('uavvaste-pilot-v1','dronewaste500-v1','fire-candidates-v1','dronewaste-v2-binary-strict','litter-v3-land','smoke-pyrosdis-v1'):
            manifest=self.root/'datasets'/name/'manifest.json'
            if not manifest.exists():continue
            data=json.loads(manifest.read_text())
            for item in data.get('records',[]):
                credit=html.unescape(re.sub(r'<[^>]+>','',item.get('author_html') or item.get('author') or ''))
                if name=='litter-v3-land' and not credit:credit={'taco':'Pedro F. Proença & Pedro Simões, TACO','uavvaste':'PUTvision / Kraft et al., UAVVaste','dronewaste_negative':'Morandini et al., DroneWaste'}.get(item.get('source'),'Источник указан в manifest')
                if name=='uavvaste-pilot-v1':credit='Kraft, Piechocki, Ptak, Walas (2021), UAVVaste'
                if name in ('dronewaste500-v1','dronewaste-v2-binary-strict'):credit='Morandini et al. (2025), DroneWaste v1.0'
                sources[item['sha256']]={'dataset':name,'credit':credit,'license':item.get('license') or data.get('license'),
                    'url':item.get('source_page') or item.get('source_record') or data.get('source_record') or data.get('record'),
                    'file':item.get('source_file') or item.get('file') or item.get('source_file_name') or item.get('path')}
        rows=self.store.list()
        for row in rows:
            meta=row.get('metadata') or {};known=sources.get(row['sha256'])
            if known:
                row['presentation']={'kind':'public_qa' if meta.get('qa') else 'public_demo','label':'Публичный QA-пример' if meta.get('qa') else 'Публичный демонстрационный пример',
                    'notice':'Не наблюдение с дрона в Казахстане. Публичный материал для проверки пилота.','source':known}
            elif meta.get('demo') or meta.get('qa'):
                row['presentation']={'kind':'local_reference_demo','label':'Демонстрационный локальный эталон',
                    'notice':'Не полевое наблюдение и не подтверждённая находка в Казахстане.',
                    'source':{'file':meta.get('source_path') or meta.get('source'),'credit':'Источник указан в метаданных загрузки','license':'Не определена по метаданным'}}
            else:row['presentation']={'kind':'operator_upload','label':'Загруженный снимок','notice':'','source':None}
        for row in rows:row['analysis_status']=analysis_coverage(row)
        return rows

    def training_status(self,pointer_name):
        quality=None
        pointer=self.root/'artifacts'/pointer_name
        if pointer.exists():
            info=json.loads(pointer.read_text());run=info.get('run','')
            if re.fullmatch(r'[A-Za-z0-9-]+',run):
                base=self.root/'outputs/pilot-training'/run
                quality=dict(info)
                for filename in ('quality-config.json','progress.json','quality-report.json','failure.json','development-evaluation.json','manual-review.json','supervision.json'):
                    path=base/filename
                    if path.exists():quality[filename]=json.loads(path.read_text())
        if quality:
            live={'training_alive':False,'supervisor_alive':False}
            base=self.root/'outputs/pilot-training'/quality['run']
            for label,pidfile,token in [('training',base.with_suffix('.pid'),'train_quality_'),('supervisor',base/'supervisor.pid','supervise_quality_')]:
                try:
                    pid=int(pidfile.read_text());proc=Path('/proc')/str(pid);cmd=(proc/'cmdline').read_bytes()
                    if token.encode() not in cmd or quality['run'].encode() not in cmd:continue
                    live[label+'_alive']=True;live[label+'_pid']=pid
                    if label=='training':
                        status={line.split(':',1)[0]:line.split(':',1)[1].strip().split()[0] for line in (proc/'status').read_text().splitlines() if line.startswith(('VmRSS:','VmHWM:','VmSwap:'))}
                        live.update(rss_mib=round(int(status.get('VmRSS',0))/1024,1),peak_rss_mib=round(int(status.get('VmHWM',0))/1024,1),swap_mib=round(int(status.get('VmSwap',0))/1024,1))
                except (OSError,ValueError):pass
            try:
                log=base.with_suffix('.log')
                with log.open('rb') as stream:
                    stream.seek(max(0,log.stat().st_size-4096));tail=stream.read().decode('utf-8','replace')
                live.update(parse_training_tail(tail))
                live['log_updated_utc']=datetime.fromtimestamp(log.stat().st_mtime,timezone.utc).isoformat()
            except OSError:pass
            quality['live_process']=live
        return quality

    def status(self):
        specs=[]
        if self.registry.exists():
            specs=[{**{k:s[k] for k in ('id','classes','scope','license')},'enabled':s.get('enabled',True),'disabled_reason':s.get('disabled_reason')} for s in json.loads(self.registry.read_text())['models']]
        datasets=[]
        for name in ('uavvaste-pilot-v1','dronewaste500-v1','fire-candidates-v1','dronewaste-v2-binary-strict','litter-v3-land','smoke-pyrosdis-v1'):
            manifest=self.root/'datasets'/name/'manifest.json'
            if not manifest.exists():continue
            data=json.loads(manifest.read_text());counts={}
            for row in data.get('records',[]):counts[row.get('split','unknown')]=counts.get(row.get('split','unknown'),0)+1
            license=data.get('license') or ', '.join(sorted({r.get('license','unknown') for r in data.get('records',[])}))
            datasets.append({'id':name,'photos':len(data.get('records',[])),'splits':counts,'license':license,
                             'scope':data.get('scope') or data.get('limitation'),'manifest':str(manifest.relative_to(self.root)),
                             'derived_annotations':data.get('derived_annotations'),'excluded_category_ids':data.get('excluded_category_ids',[])})
        configured_sha=hashlib.sha256(self.registry.read_bytes()).hexdigest() if self.registry.exists() else None
        loaded_sha=getattr(self.detector,'registry_sha256',None) if self.detector else None
        active_models=list((getattr(self.detector,'metadata',{}) or {}).get('models',[s for s in specs if s['enabled']]))
        weed_rows=[r for r in self.store.list() if r.get('analysis_mode')=='weeds' and r.get('state')=='done']
        last_weed=weed_rows[-1] if weed_rows else None
        index=self.root/'artifacts/reference_index.pt'
        weed_meta=dict(getattr(self.weed_detector,'metadata',{}) or ((last_weed or {}).get('result') or {}).get('model',{}))
        weed_state=json.loads((self.workspaces.base/'weeds/models.json').read_text())
        selected_weed=next((v for v in weed_state['versions'] if v['id'] in weed_state['active'] and v['accepted'] and v.get('spec')),None)
        if selected_weed:
            weed_meta=dict(selected_weed['spec']);weed_meta['loaded']=self.weed_detector is not None;active_models.append(weed_meta)
        elif index.exists():
            from ..config import load_config
            cfg=load_config(self.root/'config.yaml')
            weed_meta.update(id='dinov2-reference-baseline',classes=['weed'],model_name=cfg['model']['name'],
                reference_index_sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
                configured_similarity_threshold=cfg['classification']['similarity_threshold'],
                scope='Сходство с эталоном, не вероятность; качество детекции на поле не измерено. Общая очередь блокируется на время анализа.',
                license='Исходная кэшированная модель facebook/dinov2-small; см. её условия',loaded=self.weed_detector is not None,
                last_processing_seconds=((last_weed or {}).get('result') or {}).get('processing_seconds'))
            active_models.append(weed_meta)

        quality=self.training_status('quality-active-run.json')
        smoke_quality=self.training_status('smoke-active-run.json')
        return {'quality_training':quality,'smoke_training':smoke_quality,'weed_model':weed_meta,'configured_models':specs,'activation_requires_restart':bool(self.detector is not None and configured_sha and configured_sha!=loaded_sha),
                'active_registry_sha256':loaded_sha,'configured_registry_sha256':configured_sha,'datasets':datasets,'name':'Экокинеу','acquisition':'Последовательность загруженных фото; дрон не подключён',
                'database':'MariaDB / ecokineu_pilot / private Unix socket','models':active_models,
                'model_error':self.model_error,'model_loaded':self.detector is not None}

    def load_weed_detector(self):
        state=json.loads((self.workspaces.base/'weeds/models.json').read_text())
        selected=next((v for v in state['versions'] if v['id'] in state['active'] and v['accepted'] and v.get('spec')),None)
        if selected:
            from .detector import Detector
            spec=json.loads(json.dumps(selected['spec']))
            for obj in [spec,*spec.get('assets',[])]:
                if not Path(obj['path']).is_absolute():obj['path']=str(self.root/obj['path'])
            registry=self.workspaces.base/'weeds/effective-models.json';write_json(registry,{'models':[spec]})
            self.weed_detector=Detector(registry,allowed_classes=['weed'],compiled_cache=self.compiled_models)
        else:
            from .weeds import WeedDetector
            self.weed_detector=WeedDetector(self.root)
        return self.weed_detector

    def run(self):
        while not self.stop.is_set():
            try:
                rows=[r for r in self.store.list() if r['state']=='queued']
                if not rows:
                    self.wake.wait(1);self.wake.clear();continue
                if self.workspaces.orphan_busy():
                    self.stop.wait(1);continue
                # Respect legacy training scripts sharing the same advisory lock.
                import fcntl
                training_lock=self.root/'outputs/pilot-training/training.lock'
                if training_lock.exists():
                    with training_lock.open('r') as lock:
                        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        except BlockingIOError:
                            self.stop.wait(1);continue
                row=rows[0];key=row['id'];self.store.update(key,state='running',attempts=row['attempts']+1,error=None)
                started=time.perf_counter()
                try:
                    with self.compute_lock:
                        if row.get('analysis_mode')=='weeds':
                            if self.weed_detector is None:
                                self.load_weed_detector()
                            active=self.weed_detector
                        else:
                            mode=row.get('analysis_mode','environment');cache_key='environment' if mode in ('common','environment') else mode
                            active=self.detector if cache_key=='environment' else self.direction_detectors.get(cache_key)
                            if active is None:
                                try:
                                    if self.detector_factory:active=self.detector_factory()
                                    else:
                                        from .detector import Detector
                                        from .directions import DIRECTIONS
                                        allowed=None if cache_key=='environment' else DIRECTIONS[cache_key]['classes']
                                        active=Detector(self.registry,allowed_classes=allowed,compiled_cache=self.compiled_models)
                                    if cache_key=='environment':self.detector=active
                                    else:self.direction_detectors[cache_key]=active
                                    self.model_error=None
                                except Exception as exc:
                                    if mode!='common':raise
                                    from .directions import UnavailableDetector
                                    active=UnavailableDetector(str(exc))
                        if row.get('requested_registry_sha256') and getattr(active,'registry_sha256',None)!=row['requested_registry_sha256']:raise ValueError('Версия модели изменилась до обработки; повторите новой версией явно.')
                        result=self.analyze(row,active)
                    elapsed=time.perf_counter()-started
                    result['processing_seconds']=round(elapsed,4)
                    self.store.update(key,state='done',result=result,completed=datetime.now(timezone.utc).isoformat(),error=None)
                except Exception as exc:
                    self.model_error=str(exc)[:1000]
                    self.store.update(key,state='error',error=str(exc)[:1000])
            except Exception:
                import traceback;traceback.print_exc();self.stop.wait(2)

    def analyze(self,row,detector):
        from PIL import ImageDraw
        from ..environment.pipeline import validated_detection
        folder=self.base/row['id'];image=load_photo(folder/'original')
        image.save(folder/'source.jpg',quality=92)
        draw=ImageDraw.Draw(image);events=[]
        palette={'trash':'#ffd21f','fire':'#ff5533','smoke':'#b4c4dc','weed':'#58e08d'}
        from .directions import detect_direction
        raw_rows,metadata=detect_direction(self,row.get('analysis_mode','environment'),image,detector)
        for raw in raw_rows:
            valid=validated_detection(raw,*image.size,0,allowed_classes=('trash','fire','smoke','weed'))
            if not valid: continue
            event={'id':uuid.uuid4().hex,**valid,'model_id':raw.get('model_id'),'score_type':raw.get('score_type','model_confidence_not_calibrated'),'species':raw.get('species'),'stage':raw.get('stage'),
                   'location':row['location'],'object_location':None,'review_status':'unreviewed',
                   'possible_duplicate_of':None}
            draw.rectangle(event['bbox'],outline=palette[event['class_name']],width=3)
            draw.text((event['bbox'][0],event['bbox'][1]),f"{event['class_name']} {event['confidence']:.2f}",fill='white',stroke_width=1,stroke_fill='black')
            events.append(event)
        image.save(folder/'annotated.jpg',quality=92)
        result={'model':metadata,'events':events,'width':image.width,'height':image.height,
                'source_sha256':row['sha256'],'note':'Гипотезы модели. Совпадения на соседних фото могут относиться к одному объекту.'}
        result['analysis_status']=analysis_coverage({**row,'state':'done','result':result})
        write_json(folder/'result.json',result)
        return result

    def geojson(self):
        features=[]
        for row in self.photos():
            for e in (row.get('result') or {}).get('events',[]):
                point=e['location']
                features.append({'type':'Feature','id':e['id'],'geometry':None if not point else
                                 {'type':'Point','coordinates':[point['longitude'],point['latitude']]},
                                 'properties':{**e,'photo_id':row['id'],'mission':row['mission'],'captured_at':row['captured_at'],
                                               'data_origin':row['presentation'],'result_registry_sha256':row['result']['model'].get('registry_sha256'),
                                               'geometry_role':'capture_position_not_object' if point else 'unknown'}})
        return {'type':'FeatureCollection','features':features}

    def close(self):
        self.workspaces.close()
        self.stop.set();self.wake.set();self.worker.join(timeout=30)
        if not self.worker.is_alive():
            self.store.db.close();self.lockfile.close()
