"""Smoke-only val calibration, then locked test-development comparison. Never activates."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_quality_v3 import sha,write
from scripts.evaluate_quality_v2 import metrics

def f1(m):return 2*m['precision']*m['recall']/max(1e-12,m['precision']+m['recall'])
def choose(rows,pred,policy):
    grid=[{k:v for k,v in metrics(rows,pred,t).items() if k!='per_image'} for t in policy['threshold_grid']]
    eligible=[m for m in grid if m['precision']>=policy['minimum_precision'] and m['recall']>=policy['minimum_recall'] and m['negative_image_alarm_rate']<=policy['maximum_negative_image_alarm_rate']]
    return {'chosen':max(eligible or grid,key=f1),'gate_passed':bool(eligible),'grid':grid}
def main():
    p=argparse.ArgumentParser();p.add_argument('--run');p.add_argument('--baseline-only',action='store_true');a=p.parse_args()
    assert a.baseline_only or (a.run and a.run.replace('-','').isalnum())
    if a.baseline_only:
        import fcntl
        serial=(ROOT/'outputs/pilot-training/training.lock').open('a');fcntl.flock(serial,fcntl.LOCK_EX|fcntl.LOCK_NB)
        previous=ROOT/'outputs/pilot-training/litter-v3-land-yolo11n-full-cpu-20261020'
        assert (previous/'development-evaluation.json').exists() and (previous/'manual-review.json').exists(),'Review trash before smoke baseline inference'
    data=ROOT/'datasets/smoke-pyrosdis-v1';snapshot=sha(data/'snapshot-lock.json');lock=json.loads((data/'snapshot-lock.json').read_text())
    for relative,digest in lock['files'].items():assert sha(data/relative)==digest,relative
    records=json.loads((data/'manifest.json').read_text())['records'];rows={}
    for split in ('val','test_development'):
        annotations={}
        for b in json.loads((data/'annotations'/f'{split}.json').read_text())['annotations']:
            x,y,w,h=b['bbox'];annotations.setdefault(b['image_id'],[]).append([x,y,x+w,y+h])
        rows[split]=[{**r,'source_image_id':r['image_id'],'image_role':'verified_negative' if r['annotation_count']==0 else 'positive','site':r['site_group'],'gt':annotations.get(r['image_id'],[])} for r in records if r['split']==split]
    out=ROOT/'outputs/pilot-training/smoke-baseline-pyrosdis-v1';out.mkdir(exist_ok=True)
    baseline=next(s for s in json.loads((ROOT/'artifacts/ecokineu-models.json').read_text())['models'] if s['id']=='fire-v6-4a60bd37')
    baseline={**baseline,'enabled':True,'classes':[None,None,'smoke'],'threshold':.01,'path':str(ROOT/baseline['path']),'assets':[{**s,'path':str(ROOT/s['path'])} for s in baseline['assets']]}
    policy={'threshold_grid':[.05,.1,.15,.2,.25,.3,.35,.4,.5,.6,.7,.8,.9],'minimum_precision':.5,'minimum_recall':.25,'maximum_negative_image_alarm_rate':.1}
    from src.pilot.detector import Detector
    from PIL import Image
    def infer(spec,destination,splits):
        destination.mkdir(exist_ok=True);reg=destination/'registry.json';write(reg,{'models':[spec]});fingerprint=sha(reg);cachepath=destination/'predictions.json'
        cache={'registry_sha256':fingerprint,'snapshot_sha256':snapshot,'predictions':{}}
        if cachepath.exists():
            cache=json.loads(cachepath.read_text());assert cache['registry_sha256']==fingerprint and cache['snapshot_sha256']==snapshot
        detector=Detector(reg);pred=cache['predictions'];count=0
        for split in splits:
            for r in rows[split]:
                key=str(r['image_id'])
                if key in pred:continue
                pred[key]=[{k:b[k] for k in ('bbox','confidence','class_name')} for b in detector.detect(Image.open(data/r['path']).convert('RGB'))];count+=1
                if count%15==0:write(cachepath,cache);print('SMOKE_INFER',destination.name,split,count,flush=True)
        write(cachepath,cache);return pred,fingerprint
    basepred,basefp=infer(baseline,out,['val']);base_lock=out/'threshold-lock.json'
    if not base_lock.exists():
        assert not (out/'test-consumed.json').exists();cal=choose(rows['val'],basepred,policy)
        with base_lock.open('x') as f:json.dump({'registry_sha256':basefp,'snapshot_sha256':snapshot,'calibration':cal,'threshold':cal['chosen']['threshold'],'locked_unix':time.time(),'source':'val only; before candidate training','baseline_source_exposure_unknown':True},f,indent=2)
    baselock=json.loads(base_lock.read_text());assert baselock['registry_sha256']==basefp and baselock['snapshot_sha256']==snapshot
    if a.baseline_only:print('SMOKE_BASELINE_VAL_COMPLETE',json.dumps(baselock['calibration']));return
    run=ROOT/'outputs/pilot-training'/a.run;quality=json.loads((run/'quality-report.json').read_text());assert quality['state']=='exported_candidate_not_activated' and quality['dataset_snapshot_lock_sha256']==snapshot and sha(run/'weights/best.pt')==quality['best_weights_sha256']
    assert baselock['locked_unix']<quality['started_unix'],'Baseline must be locked before candidate training'
    policy=json.loads((run/'predeclared-evaluation-policy.json').read_text());xml=run/'weights/best_openvino_model/best.xml'
    spec={'id':a.run,'path':str(xml),'sha256':sha(xml),'assets':[{'path':str(xml.with_suffix('.bin')),'sha256':sha(xml.with_suffix('.bin'))}],'classes':['smoke'],'threshold':.01,'imgsz':640,'license':'Ultralytics AGPL-3.0; dataset Apache-2.0 with Pyronear/SDIS attribution','scope':'Smoke-only; Fire remains baseline route; source-derived development test'}
    candidateout=run/'quality-evaluation';pred,fp=infer(spec,candidateout,['val']);lockpath=run/'threshold-lock.json'
    if not lockpath.exists():
        assert not (run/'test-consumed.json').exists();cal=choose(rows['val'],pred,policy)
        with lockpath.open('x') as f:json.dump({'registry_sha256':fp,'snapshot_sha256':snapshot,'policy_sha256':sha(run/'predeclared-evaluation-policy.json'),'threshold':cal['chosen']['threshold'],'calibration':cal,'locked_unix':time.time()},f,indent=2)
    locked=json.loads(lockpath.read_text());assert locked['registry_sha256']==fp and locked['snapshot_sha256']==snapshot and locked['policy_sha256']==sha(run/'predeclared-evaluation-policy.json')
    for destination,lockfile in [(run,lockpath),(out,base_lock)]:
        marker=destination/'test-consumed.json'
        if marker.exists():assert json.loads(marker.read_text())['threshold_lock_sha256']==sha(lockfile)
        else:
            with marker.open('x') as f:json.dump({'threshold_lock_sha256':sha(lockfile),'started_unix':time.time(),'resume_same_model_threshold_only':True},f)
    pred,_=infer(spec,candidateout,['test_development']);basepred,_=infer(baseline,out,['test_development'])
    threshold=locked['threshold'];bt=baselock['threshold'];cohorts={}
    for split in rows:
        m=metrics(rows[split],pred,threshold);b=metrics(rows[split],basepred,bt);deployed=metrics(rows[split],basepred,.35);tags={}
        for tag in ('fog_or_low_cloud_appearance','cloud_appearance','sun_glare_or_twilight','lens_or_rain_artifact'):
            subset=[r for r in rows[split] if r['image_role']=='verified_negative' and tag in r.get('negative_review',{}).get('appearance_tags',[])]
            tags[tag]={'images':len(subset),'candidate_alarm_images':metrics(subset,pred,threshold)['negative_images_with_alarm'],'baseline_alarm_images':metrics(subset,basepred,bt)['negative_images_with_alarm']}
        cohorts[split]={'candidate':m,'baseline_val_locked':b,'baseline_deployed_035':deployed,'negative_appearance_tags':tags}
    m=cohorts['test_development']['candidate'];b=cohorts['test_development']['baseline_val_locked']
    improvement=f1(m)>=f1(b)+.02 or (m['negative_images_with_alarm']<b['negative_images_with_alarm'] and m['precision']>=b['precision']-.05 and m['recall']>=b['recall']-.05)
    tags_ok=all(v['candidate_alarm_images']<=v['baseline_alarm_images'] for split in cohorts.values() for v in split['negative_appearance_tags'].values())
    gate=locked['calibration']['gate_passed'] and m['precision']>=policy['minimum_precision'] and m['recall']>=policy['minimum_recall'] and m['negative_image_alarm_rate']<=policy['maximum_negative_image_alarm_rate'] and improvement and tags_ok
    report={'run':a.run,'candidate_recommended_for_manual_review':bool(gate),'activation':'NOT ACTIVATED','threshold':threshold,'baseline_threshold':bt,'threshold_lock_sha256':sha(lockpath),'candidate_spec':{**spec,'threshold':threshold},'cohorts':cohorts,'improvement_gate_passed':improvement,'appearance_alarm_gate_passed':tags_ok,'fire_preservation_required':True,'scope':'Source-val repartition; baseline prior source exposure unknown. Not independent geographic/event validation. No fire training.'}
    write(run/'development-evaluation.json',report);print('SMOKE_EVALUATION_COMPLETE',json.dumps({'recommended':bool(gate),'threshold':threshold,'candidate_f1':f1(m),'baseline_f1':f1(b)}))
if __name__=='__main__':main()
