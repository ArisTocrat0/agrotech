"""Manual crash recovery for the two authorized runs. Dry-run unless --execute.
Never installs startup hooks, changes registry, starts a fresh run, or signals a process.
"""
import argparse, fcntl, hashlib, json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNS={'litter-v3-land-yolo11n-full-cpu-20261020':('litter-v3-land','v3','trash'), 'smoke-pyrosdis-yolo11n-cpu-20261020':('smoke-pyrosdis-v1','smoke','smoke')}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def write(p,v):
    tmp=p.with_suffix(p.suffix+'.recovery-tmp');tmp.write_text(json.dumps(v,indent=2)+'\n');tmp.replace(p)
def live_workers():
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid(): continue
        try:
            args=(p/'cmdline').read_bytes().split(b'\0'); words=[w.decode(errors='replace') for w in args]
            # Match actual script argv, never parent shell command text or a PID alone.
            if any(Path(w).name in ('train_quality_v3.py','train_quality_smoke.py','supervise_quality_v3.py','supervise_quality_smoke.py','evaluate_quality_v3.py','evaluate_quality_smoke.py','recover_quality_training.py') for w in words):found.append({'pid':int(p.name),'argv':words})
        except (FileNotFoundError,ProcessLookupError):pass
    return found

def restore_stopper(trainer,history):
    best=0.;epoch=0
    for r in history:
        fitness=float(r['metrics'].get('metrics/mAP50-95(B)',0))
        if fitness>best or best==0:best=fitness;epoch=r['epoch']
    trainer.stopper.best_fitness=best;trainer.stopper.best_epoch=epoch
    trainer.stopper.possible_stop=(trainer.start_epoch-epoch)>=trainer.stopper.patience-1

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True,choices=RUNS);p.add_argument('--execute',action='store_true');a=p.parse_args()
    output=ROOT/'outputs/pilot-training';run=output/a.run
    workers=live_workers()
    if workers: print(json.dumps({'action':'no_op_live_workers','workers':workers},indent=2));return
    # Both recovery callers and normal trainers serialize on the same lock.
    serial=(output/'training.lock').open('a');fcntl.flock(serial,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        assert not live_workers(),'Worker appeared while acquiring lock'
        assert run.is_dir(),'Recovery never starts a run that has not already begun'
        assert not (run/'failure.json').exists(),'Recorded failure requires diagnosis; no automatic retry'
        data_name,kind,cls=RUNS[a.run];data=ROOT/'datasets'/data_name
        config=read(run/'quality-config.json');progress=read(run/'progress.json')
        assert config['run']==a.run and config['threads']==2 and config['batch']==1
        assert sha(data/'snapshot-lock.json')==config['dataset_snapshot_lock_sha256']
        assert sha(data/'manifest.json')==config['dataset_manifest_sha256']
        for rel,digest in read(data/'snapshot-lock.json')['files'].items():assert sha(data/rel)==digest,rel
        assert sha(ROOT/'artifacts/yolo11n.pt')==config['initial_weights_sha256']
        if kind=='v3':assert sha(data/'sealed_holdout_manifest.json')==config['holdout_manifest_sha256']
        else:
            previous=output/'litter-v3-land-yolo11n-full-cpu-20261020'
            assert (previous/'manual-review.json').exists() and (previous/'development-evaluation.json').exists()
            assert (output/'smoke-baseline-pyrosdis-v1/threshold-lock.json').exists()
        evaluation=run/'development-evaluation.json'
        if evaluation.exists():print(json.dumps({'action':'no_op_evaluation_exists','path':str(evaluation)}));return
        quality=read(run/'quality-report.json') if (run/'quality-report.json').exists() else None
        stage='evaluate' if quality and quality['state']=='exported_candidate_not_activated' else 'export' if quality and quality['state']=='trained_candidate_not_activated' else 'resume_training'
        evidence={'run':a.run,'stage':stage,'config_sha256':sha(run/'quality-config.json'),'policy_sha256':sha(run/'predeclared-evaluation-policy.json'),'progress':progress,'supervision':read(run/'supervision.json') if (run/'supervision.json').exists() else None,'supervision_sha256':sha(run/'supervision.json') if (run/'supervision.json').exists() else None,'locks':{str(f.relative_to(run)):sha(f) for f in run.rglob('*') if f.is_file() and f.name in ('threshold-lock.json','holdout-consumed.json','test-consumed.json')},'recorded_unix':time.time()}
        if not a.execute:print(json.dumps({'action':'validated_plan_no_mutation','stage':stage,'checkpoint':str(run/'weights/last.pt'),'note':'Checkpoint deserialization and optimizer checks occur only after explicit execution; live workers always block.'},indent=2));return
        os.nice(5);os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(output/'quality-config'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',HF_HUB_OFFLINE='1')
        import torch
        from ultralytics import YOLO,settings
        torch.set_num_threads(2)
        for key in ('sync','wandb','mlflow','clearml','comet','neptune'):
            if key in settings:settings.update({key:False})
        if stage=='resume_training':
            # Locally generated, trusted checkpoint only. Reject partial writes and stripped final checkpoints.
            ckptpath=run/'weights/last.pt';digest=sha(ckptpath);ckpt=torch.load(ckptpath,map_location='cpu',weights_only=False);assert sha(ckptpath)==digest
            epoch=ckpt['epoch']+1;history=progress['history']
            assert ckpt.get('optimizer') and ckpt.get('ema') is not None
            assert 0<epoch<config['epochs_max'] and history and epoch==history[-1]['epoch'],'Checkpoint/progress gap requires manual diagnosis; never discard history'
            args=ckpt['train_args']
            for k,v in {'epochs':config['epochs_max'],'batch':1,'imgsz':640,'workers':0,'device':'cpu','patience':config['patience'],'freeze':0,'optimizer':'AdamW','lr0':.0003,'seed':42,'deterministic':True,'cache':False}.items():assert args[k]==v,(k,args[k],v)
            assert Path(args['data']).resolve()==(data/'data.yaml').resolve()
            assert Path(args['save_dir']).resolve()==run.resolve()
            assert ckpt['ema'].names=={0:cls}
            assert all(torch.isfinite(v).all() for v in ckpt['ema'].state_dict().values() if isinstance(v,torch.Tensor))
            last_time=float(history[-1]['epoch_seconds']);remaining=config['training_budget_deadline_unix']-time.time()
            assert remaining>last_time,'Original absolute budget expired/insufficient; no automatic extension or fresh training'
            assert epoch-max(history,key=lambda r:float(r['metrics'].get('metrics/mAP50-95(B)',0)))['epoch']<config['patience'],'Early stopping already due; manual finalization required'
            evidence['checkpoint_sha256']=digest;evidence['checkpoint_epoch']=epoch
            write(run/f'recovery-snapshot-{time.time_ns()}.json',evidence)
            attempt=time.time();base_elapsed=progress['elapsed_seconds'];del ckpt
            model=YOLO(str(ckptpath))
            def start(t):
                torch.set_num_threads(2);restore_stopper(t,history)
            def update(t):
                nonlocal progress
                if any(k.startswith('val/') for k in t.metrics):
                    row={'epoch':int(t.epoch)+1,'epoch_seconds':float(t.epoch_time or 0),'elapsed_seconds':base_elapsed+time.time()-attempt,'metrics':{k:float(v) for k,v in t.metrics.items()},'best_fitness':float(t.best_fitness or 0),'phase':'training_validation'}
                    assert row['epoch']==history[-1]['epoch']+1;history.append(row)
                    progress={**progress,'history':history,'elapsed_seconds':row['elapsed_seconds'],'state':'running','recovered':True}
                    write(run/'progress.json',progress)
                    if time.time()+max(0,row['epoch_seconds'])>=config['training_budget_deadline_unix']:t.stop=True
            model.add_callback('on_train_start',start);model.add_callback('on_fit_epoch_end',update)
            model.train(resume=True,data=str(data/'data.yaml'),device='cpu',batch=1,workers=0,cache=False,save_dir=str(run))
            quality={**read(run/'progress.json'),'state':'trained_candidate_not_activated','best_weights_sha256':sha(run/'weights/best.pt'),'epochs_completed':history[-1]['epoch'],'seconds':base_elapsed+time.time()-attempt}
            write(run/'quality-report.json',quality);stage='export'
        else:write(run/f'recovery-snapshot-{time.time_ns()}.json',evidence)
        if stage=='export':
            assert sha(run/'weights/best.pt')==quality['best_weights_sha256']
            YOLO(str(run/'weights/best.pt')).export(format='openvino',imgsz=640,half=False,int8=False,dynamic=False,batch=1,device='cpu')
            quality['state']='exported_candidate_not_activated';write(run/'quality-report.json',quality)
        assert sha(run/'predeclared-evaluation-policy.json')==evidence['policy_sha256']
        write(run/'recovery-supervision.json',{'state':'evaluating_existing_candidate','started_unix':time.time(),'prior_supervision_sha256':evidence['supervision_sha256']})
        with (run/'quality-evaluation.log').open('ab') as log:
            result=subprocess.run([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/f'scripts/evaluate_quality_{kind}.py'),'--run',a.run],cwd=ROOT,stdout=log,stderr=log,timeout=5400)
        write(run/'recovery-supervision.json',{'state':'evaluation_complete_not_activated' if result.returncode==0 else 'evaluation_failed_no_activation','exit_code':result.returncode,'completed_unix':time.time()})
        assert result.returncode==0,'Evaluation failed; inspect existing log, no fresh threshold/test reset'
        print('RECOVERY_COMPLETE_NOT_ACTIVATED')
    finally:
        serial.close()
if __name__=='__main__':main()
