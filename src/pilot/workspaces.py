"""Isolated direction metadata and a single, durable, bounded local training queue."""
import json,threading,uuid,subprocess,time,sys,os
from pathlib import Path
from .directions import DIRECTIONS
from ..environment.pipeline import write_json

class Workspaces:
    def __init__(self,app):
        self.app=app;self.root=app.root;self.base=self.root/'outputs/directions'
        self.lock=threading.RLock();self.stop=threading.Event();self.process=None
        for key in DIRECTIONS:
            (self.base/key/'runs').mkdir(parents=True,exist_ok=True)
            config=self.base/key/'config.json'
            if not config.exists():write_json(config,{'epochs':1,'cpu_threads':2,'batch':1,'maximum_minutes':15})
        self.initialize_versions()
        if any(json.loads((self.base/key/'models.json').read_text())['history'] for key in DIRECTIONS):self.write_effective_registry()
        for p in self.base.glob('*/runs/*/run.json'):
            item=json.loads(p.read_text())
            if item['state'] in ('running','orphan_running','cancelling'):
                item.update(state=('cancelling' if item['state']=='cancelling' else 'orphan_running') if self.owned_process_alive(item) else ('cancelled' if item['state']=='cancelling' else 'interrupted'),error='Сервер остановлен. Прогон не перезапускается автоматически.');write_json(p,item)
        self.worker=threading.Thread(target=self.work,daemon=True,name='training-queue');self.worker.start()

    def owned_process_alive(self,run):
        try:
            pid=run.get('pid')
            if not isinstance(pid,int) or pid<=1:return False
            command=(Path('/proc')/str(pid)/'cmdline').read_bytes()
            folder=str(self.base/run['direction']/'runs'/run['id']).encode()
            return b'train_direction.py' in command and folder in command
        except (OSError,KeyError):return False

    def orphan_busy(self):
        busy=False
        with self.lock:
            for key in DIRECTIONS:
                for run in self.runs(key):
                    if run['state'] not in ('orphan_running','cancelling'):continue
                    if self.owned_process_alive(run):busy=True
                    else:
                        run.update(state='cancelled' if run['state']=='cancelling' else 'interrupted',error='Процесс после остановки сервера завершён. Проверьте журнал; автоповтора нет.')
                        run.pop('progress',None);write_json(self.base/key/'runs'/run['id']/'run.json',run)
        return busy

    def initialize_versions(self):
        registry=self.root/'artifacts/ecokineu-models.json'
        specs=json.loads(registry.read_text())['models'] if registry.exists() else []
        for key,direction in DIRECTIONS.items():
            path=self.base/key/'models.json'
            if path.exists():continue
            versions=[]
            for spec in specs:
                if not set(direction['classes']).intersection(spec['classes']):continue
                accepted=spec.get('enabled',True) is not False
                versions.append({'id':spec['id'],'accepted':accepted,'spec':spec,'reason':'Сохранённая настроенная модель; полевое качество не подтверждено.' if accepted else spec.get('disabled_reason','Кандидат не принят')})
            if key=='weeds':versions=[{'id':'dinov2-reference-baseline','accepted':True,'reason':'Сохранённый эталонный baseline; не переобучался.'}]
            write_json(path,{'active':[v['id'] for v in versions if v['accepted']],'history':[],'versions':versions})

    def register_reviewed(self,key,run_id):
        import hashlib,math
        if not isinstance(run_id,str) or len(run_id)!=32 or any(c not in '0123456789abcdef' for c in run_id):raise ValueError('Некорректный прогон.')
        folder=self.base/key/'runs'/run_id
        with self.app.compute_lock,self.lock,self.app.ingest_lock:
            if self.process or any(r['state'] in ('queued','running') for r in self.app.store.list()):raise ValueError('Дождитесь завершения текущих задач.')
            if not (folder/'run.json').exists():raise ValueError('Прогон не найден.')
            if json.loads((folder/'run.json').read_text())['state']!='candidate':raise ValueError('Допуск разрешён только после завершения обучения кандидата.')
            required=['manual-review.json','development-evaluation.json','native-parity.json']
            if any(not (folder/name).is_file() for name in required):raise ValueError('Нужны реальная оценка по классам и hard negatives, native parity и ручное решение. Кандидат остаётся неактивным.')
            review=json.loads((folder/'manual-review.json').read_text());evaluation=json.loads((folder/'development-evaluation.json').read_text());parity=json.loads((folder/'native-parity.json').read_text())
            if review.get('verdict')!='approved_local_pilot' or evaluation.get('candidate_recommended_for_manual_review') is not True or parity.get('passed') is not True:raise ValueError('Проверка качества / native parity не пройдена. Кандидат нельзя включить.')
            spec=evaluation.get('candidate_spec',{});classes=[c for c in spec.get('classes',[]) if c]
            if not classes or not set(classes)<=set(DIRECTIONS[key]['classes']):raise ValueError('Классы кандидата не соответствуют направлению.')
            for cls in classes:
                metric=evaluation.get('per_class_holdout',{}).get(cls,{})
                values=[metric.get('precision'),metric.get('recall')]
                if any(not isinstance(value,(float,int)) or not math.isfinite(value) or not 0<=value<=1 for value in values) or values[0]<.5 or values[1]<.25 or metric.get('positive_images',0)<10:raise ValueError('Нет достаточной положительной holdout-проверки класса '+cls)
            negatives=evaluation.get('hard_negatives',{})
            if negatives.get('images',0)<10 or not 0<=negatives.get('images_with_alarm',-1)<=negatives['images']*.1:raise ValueError('Не пройдена проверка hard negatives.')
            if 'trash' in classes and negatives.get('rocks_images',0)<5:raise ValueError('Нет достаточной проверки на камнях.')
            if evaluation.get('train_holdout_overlap') is not False or not evaluation.get('holdout_scope'):raise ValueError('Не описана независимость holdout от обучения.')
            for obj in [spec,*spec.get('assets',[])]:
                source=Path(obj.get('path',''));source=source if source.is_absolute() else self.root/source
                if not source.resolve().is_relative_to(folder.resolve()) or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=obj.get('sha256'):raise ValueError('Веса должны принадлежать этому прогону и совпадать с проверенными hash.')
                obj['path']=str(source.resolve())
            if parity.get('model_sha256')!=spec['sha256']:raise ValueError('Parity относится к другой версии весов.')
            for field in ('license','scope','imgsz','threshold','id'):
                if field not in spec:raise ValueError('Неполный candidate_spec: '+field)
            if spec['id']!=run_id:raise ValueError('ID версии должен совпадать с прогоном.')
            if type(spec['imgsz']) is not int or spec['imgsz'] not in (320,640,1024):raise ValueError('Неподдерживаемый размер входа кандидата.')
            threshold=spec['threshold']
            if type(threshold) not in (int,float) or not math.isfinite(threshold) or not 0<threshold<1:raise ValueError('Некорректный порог кандидата.')
            from .detector import Detector
            from PIL import Image
            probe=folder/'acceptance-registry.json';write_json(probe,{'models':[spec]})
            try:Detector(probe).detect(Image.new('RGB',(spec['imgsz'],spec['imgsz'])))
            except Exception as exc:raise ValueError('Кандидат непригоден для текущего native adapter: '+str(exc))
            path=self.base/key/'models.json';state=json.loads(path.read_text())
            if not any(v['id']==run_id for v in state['versions']):
                state['versions'].append({'id':run_id,'accepted':True,'spec':spec,'reason':'Принят вручную для локального пилота по сохранённым отчётам; ограничения holdout сохраняются.','evidence':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in required}});write_json(path,state)
            return state

    def select(self,key,version):
        with self.lock,self.app.ingest_lock:
            if self.process or any(r['state'] in ('queued','running','orphan_running','cancelling') for name in DIRECTIONS for r in self.runs(name)) or any(r['state'] in ('queued','running') for r in self.app.store.list()):raise ValueError('Дождитесь завершения анализа и обучения.')
            path=self.base/key/'models.json';state=json.loads(path.read_text())
            selected=next((v for v in state['versions'] if v['id']==version and v['accepted']),None)
            if selected is None:raise ValueError('Версия не принята. Отклонённые кандидаты включать нельзя.')
            if state['active']==[version]:return state
            state['history'].append({'active':state['active'],'time':time.time()});state['active']=[version];write_json(path,state)
            self.write_effective_registry()
            return state

    def write_effective_registry(self):
        # Direction snapshots retain original Fire classes when a smoke-only model is selected.
        models=[]
        for key in ('trash','fire_smoke'):
            state=json.loads((self.base/key/'models.json').read_text())
            selected=[v['spec'] for v in state['versions'] if v['id'] in state['active'] and v['accepted']]
            if key=='fire_smoke' and not any('fire' in spec['classes'] for spec in selected):
                # A smoke-only selection must preserve the saved Fire route.
                baseline=json.loads((self.root/'artifacts/ecokineu-models.json').read_text())['models']
                for spec in baseline:
                    if spec.get('enabled',True) and 'fire' in spec['classes']:
                        fire=json.loads(json.dumps(spec));fire['classes']=[c if c=='fire' else None for c in fire['classes']];selected.append(fire)
            for original in selected:
                spec=json.loads(json.dumps(original));spec['classes']=[c if c in DIRECTIONS[key]['classes'] else None for c in spec['classes']]
                if not any(spec['classes']):continue
                for obj in [spec,*spec.get('assets',[])]:
                    if not Path(obj['path']).is_absolute():obj['path']=str(self.root/obj['path'])
                models.append(spec)
        target=self.base/'effective-models.json';write_json(target,{'models':models})
        self.app.registry=target;self.app.detector=None;self.app.weed_detector=None;self.app.direction_detectors.clear();self.app.compiled_models.clear()

    def runs(self,key):
        result=[]
        for p in sorted((self.base/key/'runs').glob('*/run.json')):
            item=json.loads(p.read_text());progress=p.parent/'progress.json'
            if progress.exists():item['progress']=json.loads(progress.read_text())
            result.append(item)
        return result

    def status(self,key):
        if key=='common':return {'scope':'Три существующих направления; последовательная обработка. Недоступный класс не считается проверенным.','datasets':[],'models':[],'runs':[]}
        spec=DIRECTIONS[key];datasets=[]
        for name in spec['datasets']:
            path=self.root/'datasets'/name/'manifest.json'
            if path.exists():
                data=json.loads(path.read_text());counts={}
                for row in data.get('records',[]):counts[row.get('split','unknown')]=counts.get(row.get('split','unknown'),0)+1
                datasets.append({'id':name,'splits':counts,'photos':len(data.get('records',[])),'manifest':str(path.relative_to(self.root)),'scope':data.get('scope',data.get('limitation'))})
        registry=self.root/'artifacts/ecokineu-models.json';models=[]
        if registry.exists():models=[s for s in json.loads(registry.read_text())['models'] if set(s['classes']).intersection(spec['classes'])]
        if key=='weeds':models=[{'id':'dinov2-reference-baseline','preserved':True,'quality':'Качество полевой детекции не измерено','available':(self.root/'artifacts/reference_index.pt').is_file()}]
        data={'trash':'litter-v3-land','fire_smoke':'smoke-pyrosdis-v1'}.get(key)
        own=self.dataset(key);splits={r['split'] for r in own['records']}
        if {'train','val'}<=splits:data='isolated'
        dataset_path=self.base/key/'dataset' if data=='isolated' else self.root/'datasets'/str(data)
        available=bool(data and (dataset_path/'data.yaml').is_file() and (dataset_path/'snapshot-lock.json').is_file() and (self.root/'artifacts/yolo11n.pt').is_file())
        missing_labels=0;split_counts={}
        if available:
            for split in ('train','val'):
                images=[p for p in (dataset_path/'images'/split).glob('*') if p.suffix.lower() in ('.jpg','.jpeg','.png')]
                split_counts[split]=len(images)
                missing_labels+=sum(not (dataset_path/'labels'/split/(image.stem+'.txt')).is_file() for image in images)
            if missing_labels or not all(split_counts.values()):available=False
        reason=('Нет готового размеченного train/val набора для обучения сорняков. Сохранён эталонный baseline.' if key=='weeds' and not available else 'Обучение кандидата: CPU, 2 потока, batch 1, не более 3 эпох / 15 минут. Автоактивации нет.' if available else 'Отсутствуют data.yaml, замороженная разметка или начальные веса.')
        if split_counts and not all(split_counts.values()):reason='Train или validation не содержит изображений.'
        if missing_labels:reason=f'Отсутствует разметка у {missing_labels} снимков. Пропущенная разметка не считается negative.'
        if key=='fire_smoke' and data!='isolated':reason+=' Доступный train-набор содержит только дым; огонь не переобучается и не заменяется.'
        return {'id':key,'scope':'Анализ только классов: '+', '.join(spec['classes']),'datasets':datasets,'models':models,'training':{'available':available,'reason':reason,'dataset':data,'split_counts':split_counts,'missing_labels':missing_labels},'own_dataset':own,'config':json.loads((self.base/key/'config.json').read_text()),'legacy_quality':self.app.training_status({'trash':'quality-active-run.json','fire_smoke':'smoke-active-run.json'}.get(key,'')) if key!='weeds' and hasattr(self.app,'training_status') else None,'runs':self.runs(key),'versions':json.loads((self.base/key/'models.json').read_text())}

    def source_sample(self,key,dataset,index,kind):
        if dataset not in DIRECTIONS[key]['datasets']:raise ValueError('Датасет не принадлежит направлению.')
        base=self.root/'datasets'/dataset;manifest=json.loads((base/'manifest.json').read_text());records=manifest.get('records',[])
        if not 0<=index<len(records):raise ValueError('Снимок не найден.')
        row=records[index];relative=row.get('path') or row.get('file')
        if not isinstance(relative,str):raise ValueError('Путь к снимку не указан в manifest.')
        import hashlib
        rel=Path(relative)
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('Некорректный путь снимка.')
        image=(base/rel).resolve()
        if not image.is_file():raise ValueError('Снимок недоступен.')
        # Frozen datasets may link to their original extracted public source.
        # Only the image pinned by this manifest is exposed, never an arbitrary symlink target.
        digest=row.get('sha256')
        if not digest or hashlib.sha256(image.read_bytes()).hexdigest()!=digest:raise ValueError('Снимок не совпадает с manifest.')
        if kind=='image':
            from io import BytesIO
            from ..environment.media import load_photo
            buffer=BytesIO();load_photo(image).save(buffer,format='JPEG',quality=90);return buffer.getvalue()
        parts=list(Path(relative).parts)
        if 'images' not in parts:return {'record':row,'labels':None,'status':'missing_annotations'}
        parts[parts.index('images')]='labels';annotation=base/Path(*parts).with_suffix('.txt')
        if not annotation.resolve().is_relative_to(base.resolve()):
            lock=base/'snapshot-lock.json';snapshot=json.loads(lock.read_text()) if lock.exists() else {}
            expected=snapshot.get('files',{}).get(str(annotation.relative_to(base)))
            if not annotation.is_file() or not expected or hashlib.sha256(annotation.read_bytes()).hexdigest()!=expected:raise ValueError('Разметка не совпадает с замороженным snapshot.')
        return {'record':row,'labels':annotation.read_text() if annotation.is_file() else None,'status':'available' if annotation.is_file() else 'missing_annotations'}

    def dataset(self,key):
        path=self.base/key/'dataset/manifest.json'
        return json.loads(path.read_text()) if path.exists() else {'classes':DIRECTIONS[key]['classes'],'records':[]}

    def add_sample(self,key,payload):
        from .service import validate_photo
        import hashlib,math
        from io import BytesIO
        from ..environment.media import load_photo
        with self.lock:
            if any(r['state'] in ('queued','running','orphan_running','cancelling') for r in self.runs(key)):raise ValueError('Во время обучения датасет заморожен.')
            data,_=validate_photo({**payload,'mission':'dataset-'+key,'analysis_mode':key})
            split=payload.get('split');labels=payload.get('labels')
            if split not in ('train','val'):raise ValueError('Разрешены отдельные train или val. Независимый test не используется для обучения.')
            if not isinstance(labels,str) or len(labels)>100000:raise ValueError('Нужна YOLO-разметка; пустая строка означает проверенный negative.')
            parsed=[]
            for line in labels.splitlines():
                if not line.strip():continue
                values=line.split()
                if len(values)!=5:raise ValueError('YOLO: class cx cy width height, нормированные 0..1.')
                try:cls=int(values[0]);x,y,w,h=map(float,values[1:])
                except ValueError:raise ValueError('Некорректная YOLO-разметка.')
                if not 0<=cls<len(DIRECTIONS[key]['classes']) or not all(math.isfinite(v) for v in (x,y,w,h)) or not (0<w<=1 and 0<h<=1 and w/2<=x<=1-w/2 and h/2<=y<=1-h/2):raise ValueError('Класс или рамка вне диапазона.')
                parsed.append(f'{cls} {x} {y} {w} {h}')
            manifest=self.dataset(key);digest=hashlib.sha256(data).hexdigest()
            if any(row['sha256']==digest for row in manifest['records']):raise ValueError('Фото уже в датасете; дубли между train/val запрещены.')
            base=self.base/key/'dataset';image_dir=base/'images'/split;label_dir=base/'labels'/split
            image_dir.mkdir(parents=True,exist_ok=True);label_dir.mkdir(parents=True,exist_ok=True)
            image=image_dir/(digest+'.jpg');label=label_dir/(digest+'.txt')
            load_photo(BytesIO(data)).save(image,quality=95);label.write_text('\n'.join(parsed)+'\n' if parsed else '')
            row={'id':digest,'sha256':digest,'split':split,'image':str(image.relative_to(base)),'label':str(label.relative_to(base)),'objects':len(parsed)}
            manifest['records'].append(row);write_json(base/'manifest.json',manifest)
            write_json(base/'data.yaml',{'path':str(base),'train':'images/train','val':'images/val','names':DIRECTIONS[key]['classes']})
            files={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [base/'manifest.json',base/'data.yaml',*[base/r[k] for r in manifest['records'] for k in ('image','label')]]}
            write_json(base/'snapshot-lock.json',{'files':files})
            return row

    def log(self,key,run_id):
        if not isinstance(run_id,str) or len(run_id)!=32 or any(c not in '0123456789abcdef' for c in run_id):raise ValueError('Некорректный прогон.')
        path=self.base/key/'runs'/run_id/'train.log'
        if not path.exists():return {'tail':'Журнал ещё не создан.'}
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-16000));return {'tail':stream.read().decode('utf-8','replace')}

    def sample(self,key,sample_id,kind):
        row=next((r for r in self.dataset(key)['records'] if r['id']==sample_id),None)
        if row is None:raise ValueError('Снимок датасета не найден.')
        base=self.base/key/'dataset'
        return (base/row['image']).read_bytes() if kind=='image' else {'record':row,'labels':(base/row['label']).read_text(),'classes':DIRECTIONS[key]['classes']}

    def enqueue(self,key,payload):
        with self.lock:
            status=self.status(key)
            if not status['training']['available']:raise ValueError(status['training']['reason'])
            defaults=json.loads((self.base/key/'config.json').read_text())
            epochs=payload.get('epochs',defaults['epochs'])
            if isinstance(epochs,bool) or not isinstance(epochs,int) or not 1<=epochs<=3:raise ValueError('От 1 до 3 эпох.')
            if any(r['state'] in ('queued','running','orphan_running','cancelling') for r in self.runs(key)):raise ValueError('У направления уже есть активный прогон.')
            run={'id':uuid.uuid4().hex,'direction':key,'dataset':status['training']['dataset'],'epochs':epochs,'state':'queued','created':time.time(),'activation':'candidate_only'}
            write_json(self.base/key/'config.json',{**defaults,'epochs':epochs})
            path=self.base/key/'runs'/run['id'];path.mkdir();write_json(path/'run.json',run)
            return run

    def cancel(self,key,run_id):
        with self.lock:
            if not isinstance(run_id,str) or len(run_id)!=32 or any(c not in '0123456789abcdef' for c in run_id):raise ValueError('Некорректный прогон.')
            p=self.base/key/'runs'/run_id/'run.json'
            if not p.exists():raise ValueError('Прогон не найден.')
            run=json.loads(p.read_text())
            if run['state'] not in ('queued','running','orphan_running','cancelling'):raise ValueError('Прогон уже завершён.')
            run['state']='cancelled' if run['state']=='queued' else 'cancelling';write_json(p,run)
            if self.process and getattr(self.process,'run_id',None)==run_id:self.process.terminate()
            elif self.owned_process_alive(run):
                import signal
                os.kill(run['pid'],signal.SIGTERM)
            return run

    def external_training_busy(self):
        import fcntl
        path=self.root/'outputs/pilot-training/training.lock'
        if not path.exists():return False
        with path.open('r') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return True
        return False

    def work(self):
        while not self.stop.wait(.5):
            if self.orphan_busy() or self.external_training_busy():continue
            pending=sorted([(r['created'],key,r) for key in DIRECTIONS for r in self.runs(key) if r['state']=='queued'])
            if not pending:continue
            _,key,run=pending[0];folder=self.base/key/'runs'/run['id'];p=folder/'run.json'
            # The same lock serializes photo inference and training on a 6 GiB laptop.
            with self.app.compute_lock:
                with self.lock:
                    if self.stop.is_set():return
                    if json.loads(p.read_text())['state']!='queued':continue
                    run['state']='running';write_json(p,run)
                    try:
                        log=(folder/'train.log').open('ab')
                        self.process=subprocess.Popen([sys.executable,str(self.root/'scripts/train_direction.py'),'--run',str(folder)],cwd=self.root,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                        self.process.run_id=run['id'];run['pid']=self.process.pid;write_json(p,run)
                    except Exception as exc:
                        run.update(state='error',error=str(exc));write_json(p,run);continue
                deadline=time.monotonic()+16*60
                while self.process.poll() is None:
                    memory_kib=0
                    try:
                        memory_kib=int(next(line.split()[1] for line in (Path('/proc')/str(self.process.pid)/'status').read_text().splitlines() if line.startswith('VmRSS:')))
                    except (OSError,StopIteration,ValueError):pass
                    if self.stop.wait(.5) or time.monotonic()>deadline or memory_kib>3*1024*1024:
                        self.process.terminate();break
                try:code=self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:self.process.kill();code=self.process.wait()
                log.close()
                with self.lock:
                    saved=json.loads(p.read_text())
                    if saved['state']=='cancelling':
                        saved.update(state='cancelled',exit_code=code,finished=time.time());write_json(p,saved)
                    elif saved['state']!='cancelled':
                        saved.update(state='interrupted' if self.stop.is_set() else 'candidate' if code==0 else 'error',exit_code=code,finished=time.time());write_json(p,saved)
                    self.process=None

    def close(self):
        self.stop.set()
        with self.lock:
            if self.process and self.process.poll() is None:self.process.terminate()
        self.worker.join(timeout=20)
