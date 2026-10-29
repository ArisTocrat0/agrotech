"""Versioned, bounded fine-tuning on source-labelled data; test never enters optimization."""
import hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    import argparse,fcntl
    p=argparse.ArgumentParser();p.add_argument('--epochs',type=int,default=8);p.add_argument('--name',default='uavvaste-v1-cpu-8e');p.add_argument('--imgsz',type=int,default=320);p.add_argument('--freeze',type=int,default=0);p.add_argument('--data',type=Path,default=ROOT/'datasets/uavvaste-pilot-v1/dataset.yaml');p.add_argument('--model',type=Path,default=ROOT/'artifacts/yolo11n.pt');p.add_argument('--device',choices=['cpu','0'],default='cpu');p.add_argument('--batch',type=int,default=4);args=p.parse_args()
    if args.batch not in range(1,17):raise ValueError('Batch must be 1..16')
    if args.imgsz not in (320,640) or not 0<=args.freeze<=10 or not 1<=args.epochs<=30 or not args.name.replace('-','').isalnum():raise ValueError('Invalid bounded training request')
    output=ROOT/'outputs/pilot-training';output.mkdir(parents=True,exist_ok=True)
    lock=(output/'training.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (output/args.name).exists():raise ValueError('Run already exists; use a new version, never overwrite')
    os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(output/'config'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',HF_HUB_OFFLINE='1')
    import torch
    torch.set_num_threads(2)
    if args.device!='cpu' and not torch.cuda.is_available():raise RuntimeError('Requested CUDA is unavailable; no silent CPU fallback')
    from ultralytics import YOLO,settings
    for key in ('sync','wandb','mlflow','clearml','comet','neptune'):
        if key in settings:settings.update({key:False})
    dataset=args.data.resolve().parent;manifest=json.loads((dataset/'manifest.json').read_text())
    if manifest.get('quality_status')=='quarantined_taxonomy':raise ValueError('Dataset taxonomy is quarantined; use a curated version, not higher confidence thresholds')
    bysplit={s:{r['source_sha256'] for r in manifest['records'] if r['split']==s} for s in ('train','val','test')}
    if any(bysplit[a]&bysplit[b] for a,b in [('train','val'),('train','test'),('val','test')]):raise ValueError('Split leakage')
    model=YOLO(str(args.model.resolve()))
    start=time.perf_counter()
    model.train(data=str(dataset/'dataset.yaml'),epochs=args.epochs,imgsz=args.imgsz,batch=args.batch,device=args.device,workers=0,
                project=str(output),name=args.name,exist_ok=False,seed=42,deterministic=True,cache=False,
                plots=False,amp=False,freeze=args.freeze,close_mosaic=0,patience=0,save=True,verbose=False)
    best=output/args.name/'weights/best.pt'
    # A single final holdout evaluation. Test never enters train or checkpoint selection.
    model=YOLO(str(best));metrics=model.val(data=str(dataset/'dataset.yaml'),split='test',imgsz=args.imgsz,batch=4,
                                          device=args.device,workers=0,plots=False,project=str(output),name=args.name+'-test',verbose=False)
    report={'scope':manifest.get('scope','Small UAVVaste subset, disjoint source batches; location independence not verified; no drone/user-image accuracy claim'),
            'run':args.name,'device':args.device,'batch':args.batch,'imgsz':args.imgsz,'freeze':args.freeze,'epochs_requested':args.epochs,'seconds':time.perf_counter()-start,
            'dataset':str(dataset),'initial_weights_sha256':hashlib.sha256(args.model.read_bytes()).hexdigest(),
            'dataset_manifest_sha256':hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest(),
            'split_counts':{s:len(v) for s,v in bysplit.items()},'test_metrics':metrics.results_dict,
            'weights_sha256':hashlib.sha256(best.read_bytes()).hexdigest(),'test_used_for_training':False,
            'deployment':'Experimental; manual review required; not auto-activated'}
    (output/args.name/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    (ROOT/'artifacts/pilot_training.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    # OpenVINO is a native C++ backend with a bounded 320px tensor.
    model.export(format='openvino',imgsz=args.imgsz,half=False,int8=False,dynamic=False,batch=1,device='cpu')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
