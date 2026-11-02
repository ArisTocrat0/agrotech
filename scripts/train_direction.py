"""Bounded offline training adapter. New direction runs only; original data and weights are read-only."""
import argparse,json,os,time,sys,hashlib,fcntl
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
ROOT=Path(__file__).resolve().parents[1];run=Path(a.run).resolve()
assert run.is_relative_to(ROOT/'outputs/directions')
config=json.loads((run/'run.json').read_text());assert type(config['epochs']) is int and 1<=config['epochs']<=3
assert config['direction'] in ('weeds','trash','fire_smoke')
assert config['dataset']=='isolated' or config['dataset']=={'trash':'litter-v3-land','fire_smoke':'smoke-pyrosdis-v1'}.get(config['direction'])
lockpath=ROOT/'outputs/pilot-training/training.lock';lockpath.parent.mkdir(parents=True,exist_ok=True)
lock=lockpath.open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
data=ROOT/'outputs/directions'/config['direction']/'dataset' if config['dataset']=='isolated' else ROOT/'datasets'/config['dataset'];snapshot=json.loads((data/'snapshot-lock.json').read_text())
for relative,digest in snapshot['files'].items():
    source=(data/relative).resolve();assert source.is_relative_to(data.resolve())
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest,'Frozen dataset changed: '+relative
# Ultralytics writes label caches even with cache=False. Keep every write in the new run.
import yaml,shutil
source_config=yaml.safe_load((data/'data.yaml').read_text())
view=run/'dataset';view.mkdir()
for split in ('train','val'):
    relative=source_config[split]
    assert isinstance(relative,str) and not Path(relative).is_absolute()
    origin=(data/relative).resolve();assert origin.is_relative_to(data.resolve())
    destination=view/'images'/split;destination.mkdir(parents=True)
    labels=view/'labels'/split;labels.mkdir(parents=True)
    images=[p for p in sorted(origin.iterdir()) if p.suffix.lower() in ('.jpg','.jpeg','.png')]
    assert images,'Missing '+split+' images'
    for image in images:
        annotation=data/'labels'/split/(image.stem+'.txt')
        assert annotation.is_file(),'Missing annotation (not a verified negative): '+str(annotation)
        (destination/image.name).symlink_to(image)
        shutil.copyfile(annotation,labels/annotation.name)
(run/'dataset-snapshot.json').write_text(json.dumps(snapshot,indent=2))
(view/'data.yaml').write_text(json.dumps({'path':str(view),'train':'images/train','val':'images/val','names':source_config['names']}))
(run/'runtime-config/Ultralytics').mkdir(parents=True,exist_ok=True)
os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(run/'runtime-config'),HF_HUB_OFFLINE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
os.nice(5)
import torch
from ultralytics import YOLO,settings
torch.set_num_threads(2)
for key in ('sync','wandb','mlflow','clearml','comet','neptune'):
    if key in settings:settings.update({key:False})
started=time.monotonic();history=[]
def progress(trainer):
    final_validation=bool(history) and not any(k.startswith('val/') for k in trainer.metrics)
    row={'epoch':None if final_validation else int(trainer.epoch)+1,'phase':'final_validation' if final_validation else 'training_validation','metrics':{k:float(v) for k,v in trainer.metrics.items()},'seconds':time.monotonic()-started}
    box=getattr(getattr(getattr(trainer,'validator',None),'metrics',None),'box',None)
    per_class={}
    if box is not None:
        for index,class_id in enumerate(box.ap_class_index):
            precision,recall,map50,map95=box.class_result(index)
            names=source_config['names'];name=names[int(class_id)]
            per_class[name]={'precision':float(precision),'recall':float(recall),'mAP50':float(map50),'mAP50_95':float(map95)}
    row['per_class_validation']=per_class
    history.append(row);temp=run/'progress.tmp';temp.write_text(json.dumps({'history':history,'scope':'Validation metrics only; no independent accuracy claim','cpu_threads_actual':torch.get_num_threads(),'initial_weights_sha256':hashlib.sha256((ROOT/'artifacts/yolo11n.pt').read_bytes()).hexdigest(),'dataset_snapshot_sha256':hashlib.sha256((data/'snapshot-lock.json').read_bytes()).hexdigest(),'classes':(['weed'] if config['direction']=='weeds' else ['trash'] if config['direction']=='trash' else ['fire','smoke'] if config['dataset']=='isolated' else ['smoke'])},allow_nan=False));temp.replace(run/'progress.json')
    if time.monotonic()-started>=15*60:trainer.stop=True
model=YOLO(str(ROOT/'artifacts/yolo11n.pt'));model.add_callback('on_train_start',lambda _:torch.set_num_threads(2));model.add_callback('on_val_start',lambda _:torch.set_num_threads(2));model.add_callback('on_fit_epoch_end',progress)
model.train(data=str(view/'data.yaml'),epochs=config['epochs'],imgsz=640,batch=1,device='cpu',workers=0,project=str(run),name='training',exist_ok=False,cache=False,plots=False,amp=False,seed=42,deterministic=True,freeze=0,patience=3,verbose=False)
# Candidate deliberately remains inactive; quality review/export is a separate action.
# Export the new candidate inside its own run; activation always remains separate.
best=run/'training/weights/best.pt';assert best.is_file(),'Training did not save best.pt'
exported=Path(YOLO(str(best)).export(format='openvino',imgsz=640,half=False,int8=False,dynamic=False,batch=1,device='cpu'))
xmls=list(exported.glob('*.xml'));assert len(xmls)==1,'Expected one OpenVINO XML'
xml=xmls[0];binary=xml.with_suffix('.bin');assert binary.is_file()
names=source_config['names'];classes=[names[k] for k in sorted(names,key=int)] if isinstance(names,dict) else names
spec={'id':config['id'],'path':str(xml),'sha256':hashlib.sha256(xml.read_bytes()).hexdigest(),'assets':[{'path':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}],'classes':classes,'imgsz':640,'threshold':.35,'license':'Ultralytics AGPL-3.0; input image rights remain those of their sources','scope':'Inactive local candidate; per-class independent holdout, hard negatives, native parity and manual approval required.'}
(run/'candidate-spec.json').write_text(json.dumps(spec,indent=2))
