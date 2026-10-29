"""Frozen smoke-only CPU candidate training; validation only, never automatic activation/test evaluation."""
import argparse,fcntl,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--epochs',type=int,default=20);p.add_argument('--hours',type=float,default=3);p.add_argument('--patience',type=int,default=5);a=p.parse_args()
    assert a.name.replace('-','').isalnum() and 1<=a.epochs<=20 and 0<a.hours<=3 and 2<=a.patience<=10
    os.nice(5)
    output=ROOT/'outputs/pilot-training';output.mkdir(exist_ok=True);lock=(output/'training.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    previous=output/'litter-v3-land-yolo11n-full-cpu-20261020'
    assert (previous/'development-evaluation.json').exists() and (previous/'manual-review.json').exists(),'Finish and review trash before smoke training'
    baseline=output/'smoke-baseline-pyrosdis-v1/threshold-lock.json';assert baseline.exists(),'Lock baseline smoke validation before training'
    run=output/a.name;assert not run.exists(),'Never overwrite a run';run.mkdir()
    data=ROOT/'datasets/smoke-pyrosdis-v1';manifest=json.loads((data/'manifest.json').read_text());assert sum(r['split']=='train' for r in manifest['records'])==350 and sum(r['split']=='val' for r in manifest['records'])==75
    lock_manifest=json.loads((data/'snapshot-lock.json').read_text())
    for relative,digest in lock_manifest['files'].items():assert sha(data/relative)==digest,'Frozen snapshot changed: '+relative
    assert 'test:' not in (data/'data.yaml').read_text()
    weights=ROOT/'artifacts/yolo11n.pt';assert weights.exists()
    os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(output/'quality-config'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',HF_HUB_OFFLINE='1')
    import torch
    from ultralytics import YOLO,settings
    torch.set_num_threads(2)
    for key in ('sync','wandb','mlflow','clearml','comet','neptune'):
        if key in settings:settings.update({key:False})
    started=time.time();history=[]
    config={'run':a.name,'started_unix':started,'training_budget_deadline_unix':started+a.hours*3600,'dataset_manifest_sha256':sha(data/'manifest.json'),'initial_weights_sha256':sha(weights),'epochs_max':a.epochs,'patience':a.patience,'hours_max':a.hours,'imgsz':640,'batch':1,'freeze':0,'optimizer':'AdamW','lr0':.0003,'mosaic':0.0,'scale':.25,'dataset_snapshot_lock_sha256':sha(data/'snapshot-lock.json'),'threads':2,'geographic_independence_proven':False,'holdout_type':'Source-val re-split by site; prior baseline source exposure unknown; no independent event claim','evaluation_scope':'Smoke-only: val threshold calibration, test_development only after lock; Fire route remains intact','activation':'manual after false-positive and positive-quality review','source_license':'Apache-2.0 dataset; Pyronear and SDIS attribution in frozen manifest'}
    (run/'quality-config.json').write_text(json.dumps(config,indent=2))
    (run/'predeclared-evaluation-policy.json').write_text(json.dumps({'threshold_source': 'val ONLY', 'threshold_grid': [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9], 'minimum_precision': 0.5, 'minimum_recall': 0.25, 'maximum_negative_image_alarm_rate': 0.1, 'iou': 0.5, 'holdout_after_threshold_lock_only': True, 'user_photos_not_for_training_or_tuning': True, 'baseline_comparison': 'Compare baseline deployed 0.35 and baseline val-locked threshold; same frames. Prior baseline exposure unknown.', 'improvement_gate': {'f1_gain_min': 0.02, 'alternative': 'fewer negative alarms with precision and recall each no worse by more than 0.05', 'fog_cloud_alarms': 'must not increase on appearance-tag cohorts'}, 'fire_preservation': 'Keep unchanged baseline Fire weights and fire-class routing; candidate only replaces smoke if approved', 'activation': 'Never automatic; manual review and rollback required'},indent=2))
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
        report={**config,'state':'running','history':history,'elapsed_seconds':elapsed,'estimated_max_total_seconds':estimate,'memory_threads_actual':torch.get_num_threads(),'peak_process_rss_mib':__import__('resource').getrusage(__import__('resource').RUSAGE_SELF).ru_maxrss/1024}
        if final_validation:report['final_best_validation']=row
        temp=run/'progress.tmp';temp.write_text(json.dumps(report,indent=2,allow_nan=False));temp.replace(run/'progress.json')
        print('ECOKINEU_EPOCH '+json.dumps(row),flush=True)
        if elapsed+max(0,float(trainer.epoch_time or 0))>=a.hours*3600:trainer.stop=True
    model=YOLO(str(weights));model.add_callback('on_train_start',lambda _:torch.set_num_threads(2));model.add_callback('on_fit_epoch_end',progress)
    try:
        model.train(data=str(data/'data.yaml'),epochs=a.epochs,imgsz=640,batch=1,device='cpu',workers=0,project=str(output),name=a.name,exist_ok=True,seed=42,deterministic=True,cache=False,plots=False,amp=False,freeze=0,optimizer='AdamW',lr0=.0003,lrf=.1,momentum=.9,weight_decay=.0005,warmup_epochs=1,warmup_bias_lr=.0003,cos_lr=True,mosaic=0.0,scale=.25,close_mosaic=0,patience=a.patience,save=True,save_period=-1,verbose=False)
        best=run/'weights/best.pt';assert best.exists()
        report=json.loads((run/'progress.json').read_text());report.update(state='trained_candidate_not_activated',seconds=time.time()-started,best_weights_sha256=sha(best),epochs_completed=max(r['epoch'] for r in history))
        (run/'quality-report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
        candidate=YOLO(str(best));candidate.export(format='openvino',imgsz=640,half=False,int8=False,dynamic=False,batch=1,device='cpu')
        report['state']='exported_candidate_not_activated';(run/'quality-report.json').write_text(json.dumps(report,indent=2,allow_nan=False));print('ECOKINEU_COMPLETE '+json.dumps({'run':str(run),'seconds':report['seconds'],'epochs_completed':report['epochs_completed']}),flush=True)
    except BaseException as exc:
        (run/'failure.json').write_text(json.dumps({'error':type(exc).__name__+': '+str(exc),'elapsed_seconds':time.time()-started}));raise
if __name__=='__main__':main()
