"""Frozen V3: threshold locked on calibration before any holdout model inference. No activation."""
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_quality_v2 import metrics

def write(path,data):
    tmp=path.with_suffix('.tmp');compact=path.name=='predictions.json';tmp.write_text(json.dumps(data,ensure_ascii=False,indent=None if compact else 2,separators=(',',':') if compact else None,allow_nan=False)+'\n');tmp.replace(path)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();assert a.run.replace('-','').isalnum();run=ROOT/'outputs/pilot-training'/a.run
    quality=json.loads((run/'quality-report.json').read_text());assert sha(run/'weights/best.pt')==quality['best_weights_sha256'];assert quality['state']=='exported_candidate_not_activated';dataset=ROOT/'datasets/litter-v3-land'
    assert sha(dataset/'snapshot-lock.json')==quality['dataset_snapshot_lock_sha256'];assert sha(dataset/'sealed_holdout_manifest.json')==quality['holdout_manifest_sha256']
    locked=json.loads((dataset/'snapshot-lock.json').read_text())
    for relative,digest in locked['files'].items():assert sha(dataset/relative)==digest,'Snapshot changed: '+relative
    manifest=json.loads((dataset/'manifest.json').read_text());records=manifest['records'];out=run/'quality-evaluation';out.mkdir(exist_ok=True)
    policy=json.loads((run/'predeclared-evaluation-policy.json').read_text())
    xml=run/'weights/best_openvino_model/best.xml';binpath=xml.with_suffix('.bin')
    spec={'id':a.run,'path':str(xml),'sha256':sha(xml),'assets':[{'path':str(binpath),'sha256':sha(binpath)}],'classes':['trash'],'imgsz':640,'threshold':.01,'license':'Ultralytics AGPL-3.0; training images individually licensed, frozen V3 manifest','scope':'Individual land litter candidate; unseen-batch proxy holdout; geographic independence unproven; no water-positive acceptance test'}
    reg=out/'candidate-registry.json';write(reg,{'models':[spec]});fingerprint=sha(reg)
    from src.pilot.detector import Detector
    from PIL import Image,ImageOps,ImageDraw
    detector=Detector(reg);rows={};byid={r['image_id']:r for r in records}
    for split in sorted({r['split'] for r in records}):
        coco=json.loads((dataset/'annotations'/f'{split}.json').read_text());annotations={}
        for box in coco['annotations']:
            x,y,w,h=box['bbox'];annotations.setdefault(box['image_id'],[]).append([x,y,x+w,y+h])
        rows[split]=[{**r,'source_image_id':r['image_id'],'site':r['group'],'image_role':'verified_negative' if r['role']=='reviewed_negative' else 'positive','gt':annotations.get(r['image_id'],[])} for r in records if r['split']==split]
    cache_path=out/'predictions.json';cache={'candidate_registry_sha256':fingerprint,'model_sha256':spec['sha256'],'snapshot_lock_sha256':quality['dataset_snapshot_lock_sha256'],'predictions':{}}
    if cache_path.exists():
        cache=json.loads(cache_path.read_text());assert cache['candidate_registry_sha256']==fingerprint and cache['model_sha256']==spec['sha256'] and cache['snapshot_lock_sha256']==quality['dataset_snapshot_lock_sha256']
    predictions=cache['predictions'];timing={}
    def infer(which):
        start=time.perf_counter();count=0
        for split in which:
            for r in rows[split]:
                key=str(r['image_id'])
                if key in predictions:continue
                image=dataset/r['path'];assert sha(image)==r['sha256'];predictions[key]=[{k:b[k] for k in ('bbox','confidence','class_name')} for b in detector.detect(Image.open(image).convert('RGB'))];count+=1
                if count%25==0:write(cache_path,cache);print('V3_INFER',split,count,flush=True)
        write(cache_path,cache);timing['+'.join(which)]={'newly_inferred':count,'seconds':time.perf_counter()-start}
    calibration_splits=['val','val_development_aerial','val_development_old'];calibration_rows=[r for s in calibration_splits for r in rows[s]]
    lockpath=run/'threshold-lock.json'
    if lockpath.exists():
        lock=json.loads(lockpath.read_text());assert lock['candidate_registry_sha256']==fingerprint and lock['policy_sha256']==sha(run/'predeclared-evaluation-policy.json') and lock['candidate_xml_sha256']==spec['sha256'] and lock['dataset_snapshot_lock_sha256']==quality['dataset_snapshot_lock_sha256'];calibration=json.loads((run/'calibration-evaluation.json').read_text())
    else:
        assert not (run/'holdout-consumed.json').exists(),'Holdout must not precede threshold lock'
        infer(calibration_splits);grid=[]
        for threshold in policy['threshold_grid']:
            m=metrics(calibration_rows,predictions,threshold);grid.append({k:v for k,v in m.items() if k!='per_image'})
        eligible=[m for m in grid if m['precision']>=policy['minimum_precision'] and m['recall']>=policy['minimum_recall'] and m['negative_image_alarm_rate']<=policy['maximum_negative_image_alarm_rate']]
        f1=lambda m:2*m['precision']*m['recall']/max(1e-12,m['precision']+m['recall'])
        chosen=max(eligible or grid,key=f1)
        calibration={'splits':calibration_splits,'threshold_grid':grid,'chosen':chosen,'calibration_gate_passed':bool(eligible),'holdout_used_for_selection':False,'user_photos_used_for_selection':False}
        write(run/'calibration-evaluation.json',calibration)
        lock={'candidate_registry_sha256':fingerprint,'best_pt_sha256':quality['best_weights_sha256'],'threshold':chosen['threshold'],'locked_unix':time.time(),'candidate_xml_sha256':spec['sha256'],'dataset_snapshot_lock_sha256':quality['dataset_snapshot_lock_sha256'],'sealed_holdout_sha256':quality['holdout_manifest_sha256'],'threshold_source':calibration_splits,'policy_sha256':sha(run/'predeclared-evaluation-policy.json')}
        with lockpath.open('x') as f:json.dump(lock,f,indent=2)
    threshold=lock['threshold'];holdouts=['holdout_unseen_uav_batch','holdout_new_negative_media']
    marker=run/'holdout-consumed.json'
    if marker.exists():assert json.loads(marker.read_text())['threshold_lock_sha256']==sha(lockpath),'Refuse another threshold/model for consumed holdout'
    else:
        with marker.open('x') as f:json.dump({'started_unix':time.time(),'threshold_lock_sha256':sha(lockpath),'cohorts':holdouts,'resume_only_same_model_and_threshold':True,'geographic_independence_proven':False},f,indent=2)
    infer(holdouts)
    # Remaining cohorts are explicitly development/regression; train is used only for negative diagnostics.
    infer(['test_development_aerial','test_development_old'])
    train_neg=[r for r in rows['train'] if r['image_role']=='verified_negative']
    for r in train_neg:
        key=str(r['image_id'])
        if key not in predictions:predictions[key]=[{k:b[k] for k in ('bbox','confidence','class_name')} for b in detector.detect(Image.open(dataset/r['path']).convert('RGB'))]
    write(cache_path,cache)
    cohorts={s:metrics(rows[s],predictions,threshold) for s in calibration_splits+holdouts+['test_development_aerial','test_development_old']}
    new_aerial=cohorts['holdout_unseen_uav_batch'];new_negative=cohorts['holdout_new_negative_media']
    gate=calibration['calibration_gate_passed'] and new_aerial['precision']>=policy['minimum_precision'] and new_aerial['recall']>=policy['minimum_recall'] and new_negative['negative_image_alarm_rate']<=policy['maximum_negative_image_alarm_rate']
    negatives=[r for r in records if r['role']=='reviewed_negative'];negative_diagnostics=[]
    for r in negatives:
        boxes=[p for p in predictions[str(r['image_id'])] if p['confidence']>=threshold]
        negative_diagnostics.append({'image_id':r['image_id'],'source':r['source'],'path':r['path'],'split':r['split'],'kind':r.get('negative_kind','old_aerial_negative'),'alarms':len(boxes),'max_confidence':max((p['confidence'] for p in predictions[str(r['image_id'])]),default=0),'scope':'train negative is regression only; tiny new-negative holdout is not field-wide FPR proof'})
    # Read-only operator diagnostics only after model/threshold are locked; never training or tuning.
    import urllib.request
    photos=json.load(urllib.request.urlopen('http://127.0.0.1:8010/api/pilot/photos'))['photos'];known={r['sha256'] for r in records};operator=[]
    for photo in photos:
        if photo['presentation']['kind']!='operator_upload' or photo['sha256'] in known:continue
        original=ROOT/'outputs/pilot'/photo['id']/'original';assert sha(original)==photo['sha256'];image=ImageOps.exif_transpose(Image.open(original)).convert('RGB');raw=detector.detect(image);boxes=[r for r in raw if r['confidence']>=threshold];draw=ImageDraw.Draw(image)
        for box in boxes:draw.rectangle(box['bbox'],outline='#ff3322',width=3);draw.text(box['bbox'][:2],f"candidate {box['confidence']:.2f}",fill='white',stroke_width=1,stroke_fill='black')
        image.thumbnail((1280,1280));evidence=out/(photo['id']+'-operator-candidate.jpg');image.save(evidence,quality=85)
        operator.append({'photo_id':photo['id'],'source_sha256':photo['sha256'],'predictions':boxes,'max_confidence':max((p['confidence'] for p in raw),default=0),'evidence':str(evidence.relative_to(ROOT)),'scope':'Unlabelled local diagnostic after threshold lock; not train, tuning or water-positive acceptance test'})
    # Bounded contact sheets for actual negative errors; originals are unchanged.
    worst=sorted(negative_diagnostics,key=lambda r:-r['max_confidence'])[:12]
    for page in range(2):
        canvas=Image.new('RGB',(960,760),'white');draw=ImageDraw.Draw(canvas)
        for n,item in enumerate(worst[page*6:page*6+6]):
            image=Image.open(dataset/item['path']).convert('RGB');d=ImageDraw.Draw(image)
            for box in predictions[str(item['image_id'])]:
                if box['confidence']>=threshold:d.rectangle(box['bbox'],outline='red',width=max(2,image.width//320))
            image.thumbnail((320,320));x=n%3*320;y=n//3*380;canvas.paste(image,(x,y));draw.text((x+4,y+325),f"{item['image_id']} {item['split']}",fill='black');draw.text((x+4,y+345),f"{item['kind']} alarms={item['alarms']}",fill='black')
        canvas.save(out/f'negative-review-{page}.jpg',quality=85)
    report={'run':a.run,'candidate_recommended_for_manual_review':bool(gate),'activation':'NOT ACTIVATED; manual review required','threshold':threshold,'threshold_lock_sha256':sha(lockpath),'policy':policy,'calibration':calibration,'cohorts':cohorts,'negative_diagnostics':negative_diagnostics,'operator_diagnostics':operator,'inference_timing':timing,'candidate_spec':{**spec,'threshold':threshold},'geographic_independence_proven':False,'water_positive_acceptance_test_available':False,'scope':'New aerial batches/negative-author groups held out, not proved new geography. Old cohorts development; train negatives regression. No threshold tuning after holdout.'}
    write(run/'development-evaluation.json',report);write(run/'holdout-evaluation.json',{'threshold_lock_sha256':sha(lockpath),'cohorts':{s:cohorts[s] for s in holdouts},'finished_unix':time.time(),'geographic_independence_proven':False,'water_positive_acceptance_test_available':False})
    print('V3_EVALUATION_COMPLETE',json.dumps({'threshold':threshold,'recommended_for_manual_review':bool(gate),'new_aerial':{k:v for k,v in new_aerial.items() if k!='per_image'},'new_negative':{k:v for k,v in new_negative.items() if k!='per_image'}}),flush=True)
if __name__=='__main__':main()
