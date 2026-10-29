"""Bounded CPU candidate training; validation only, never automatic activation/test evaluation."""
import argparse,fcntl,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--epochs',type=int,default=40);p.add_argument('--hours',type=float,default=4);p.add_argument('--patience',type=int,default=8);a=p.parse_args()
    assert a.name.replace('-','').isalnum() and 1<=a.epochs<=40 and 0<a.hours<=4 and 2<=a.patience<=10
    output=ROOT/'outputs/pilot-training';output.mkdir(exist_ok=True);lock=(output/'training.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    run=output/a.name;assert not run.exists(),'Never overwrite a run';run.mkdir()
    data=ROOT/'datasets/dronewaste-v2-binary-strict';manifest=json.loads((data/'manifest.json').read_text());assert manifest['split_counts']=={'train':449,'val_development':52,'test_development':133}
    assert 'test:' not in (data/'train.yaml').read_text() and manifest['independent_holdout'] is False
    weights=ROOT/'artifacts/yolo11n.pt';assert weights.exists()
    os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(output/'quality-config'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',HF_HUB_OFFLINE='1')
    import torch
    from ultralytics import YOLO,settings
    torch.set_num_threads(2)
    for key in ('sync','wandb','mlflow','clearml','comet','neptune'):
        if key in settings:settings.update({key:False})
    started=time.time();history=[]
    config={'run':a.name,'dataset_manifest_sha256':sha(data/'manifest.json'),'initial_weights_sha256':sha(weights),'epochs_max':a.epochs,'patience':a.patience,'hours_max':a.hours,'imgsz':640,'batch':2,'freeze':10,'threads':2,'independent_holdout':False,'evaluation_scope':'development only; old test sites excluded from optimization','activation':'manual after false-positive and positive-quality review','source_license':'CC BY 4.0 / DroneWaste Morandini et al.; see dataset SOURCE_README.md'}
    (run/'quality-config.json').write_text(json.dumps(config,indent=2))
    def progress(trainer):
        epoch=int(trainer.epoch)+1;elapsed=time.time()-started
        row={'epoch':epoch,'epoch_seconds':float(trainer.epoch_time or 0),'elapsed_seconds':elapsed,'metrics':{k:float(v) for k,v in trainer.metrics.items()},'best_fitness':float(trainer.best_fitness or 0)}
        # Ultralytics final-best validation callback is not another training epoch.
        final_validation=bool(history) and not any(k.startswith('val/') for k in trainer.metrics)
        if final_validation:
            row.update(phase='final_best_validation',callback_reported_epoch=epoch,epoch=None)
        else:
            row['phase']='training_validation';history.append(row)
        estimate=(elapsed/max(1,len(history)))*a.epochs
        report={**config,'state':'running','history':history,'elapsed_seconds':elapsed,'estimated_max_total_seconds':estimate,'memory_threads_actual':torch.get_num_threads()}
        if final_validation:report['final_best_validation']=row
        temp=run/'progress.tmp';temp.write_text(json.dumps(report,indent=2,allow_nan=False));temp.replace(run/'progress.json')
        print('ECOKINEU_EPOCH '+json.dumps(row),flush=True)
        if elapsed>=a.hours*3600:trainer.stop=True
    model=YOLO(str(weights));model.add_callback('on_train_start',lambda _:torch.set_num_threads(2));model.add_callback('on_fit_epoch_end',progress)
    try:
        model.train(data=str(data/'train.yaml'),epochs=a.epochs,imgsz=640,batch=2,device='cpu',workers=0,project=str(output),name=a.name,exist_ok=True,seed=42,deterministic=True,cache=False,plots=False,amp=False,freeze=10,close_mosaic=5,patience=a.patience,save=True,save_period=5,verbose=False)
        best=run/'weights/best.pt';assert best.exists()
        report=json.loads((run/'progress.json').read_text());report.update(state='trained_candidate_not_activated',seconds=time.time()-started,best_weights_sha256=sha(best),epochs_completed=max(r['epoch'] for r in history))
        (run/'quality-report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
        candidate=YOLO(str(best));candidate.export(format='openvino',imgsz=640,half=False,int8=False,dynamic=False,batch=1,device='cpu')
        report['state']='exported_candidate_not_activated';(run/'quality-report.json').write_text(json.dumps(report,indent=2,allow_nan=False));print('ECOKINEU_COMPLETE '+json.dumps({'run':str(run),'seconds':report['seconds'],'epochs_completed':report['epochs_completed']}),flush=True)
    except BaseException as exc:
        (run/'failure.json').write_text(json.dumps({'error':type(exc).__name__+': '+str(exc),'elapsed_seconds':time.time()-started}));raise
if __name__=='__main__':main()
