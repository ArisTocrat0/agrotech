"""Development-only evaluation and diagnostics. Never activates or tunes on test-development."""
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def iou(a,b):
    w=max(0,min(a[2],b[2])-max(a[0],b[0]));h=max(0,min(a[3],b[3])-max(a[1],b[1]));inter=w*h
    return inter/max(1e-12,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter)
def metrics(rows,predictions,threshold):
    tp=fp=fn=negative_alarm=negatives=0;per=[]
    for r in rows:
        preds=[p for p in predictions[str(r['source_image_id'])] if p['confidence']>=threshold];gt=r['gt'];used=set();matched=0
        for p in sorted(preds,key=lambda p:-p['confidence']):
            options=[(iou(p['bbox'],b),j) for j,b in enumerate(gt) if j not in used];best=max(options,default=(0,None))
            if best[0]>=.5:used.add(best[1]);matched+=1
        tp+=matched;fp+=len(preds)-matched;fn+=len(gt)-matched
        if r['image_role']=='verified_negative':negatives+=1;negative_alarm+=bool(preds)
        per.append({'id':r['source_image_id'],'file':r['path'],'role':r['image_role'],'site':r['site'],'split':r['split'],'gt':len(gt),'predictions':len(preds),'tp':matched,'fp':len(preds)-matched,'fn':len(gt)-matched})
    return {'threshold':threshold,'tp':tp,'fp':fp,'fn':fn,'precision':tp/max(1,tp+fp),'recall':tp/max(1,tp+fn),'negative_images':negatives,'negative_images_with_alarm':negative_alarm,'negative_image_alarm_rate':negative_alarm/max(1,negatives),'per_image':per}
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();assert a.run.replace('-','').isalnum();run=ROOT/'outputs/pilot-training'/a.run
    assert (run/'quality-report.json').exists(),'Training not completed';src=Path(json.loads((ROOT/'datasets/dronewaste-v2-binary-strict/manifest.json').read_text())['source_root'])
    out=run/'quality-evaluation';out.mkdir(exist_ok=True);allrows=[json.loads(s) for s in (src/'manifest.jsonl').read_text().splitlines()];lookup={r['source_image_id']:dict(r) for r in allrows}
    selected={}
    for split in ('val_development','test_development'):
        coco=json.loads((src/'annotations/binary_strict'/f'{split}.json').read_text());rows=[];annotations={}
        for item in coco['annotations']:
            x,y,w,h=item['bbox'];annotations.setdefault(item['image_id'],[]).append([x,y,x+w,y+h])
        for im in coco['images']:
            row=lookup[im['id']];row['gt']=annotations.get(im['id'],[]);rows.append(row)
        selected[split]=rows
    # Explicit stone/soil/roads examples already visually screened by the V2 data task.
    indices={203,210,213,214,120,124,130,139,269,275,146,99}
    stone=[r for r in allrows if r.get('review_index') in indices and r['image_role']=='verified_negative']
    context=[r for r in allrows if r['split'] in ('val_development','test_development') and r['image_role']=='context_only']
    evalrows={r['source_image_id']:r for rows in selected.values() for r in rows};evalrows.update({r['source_image_id']:r for r in stone+context})
    from PIL import Image,ImageDraw,ImageOps
    from src.pilot.detector import Detector
    registry=json.loads((ROOT/'artifacts/ecokineu-models.json').read_text());old=next(s for s in registry['models'] if s['id']=='trash-dronewaste500-v1-transfer-3e');old={**old,'enabled':True,'threshold':.01};old['path']=str(ROOT/old['path']);old['assets']=[{**s,'path':str(ROOT/s['path'])} for s in old['assets']]
    xml=run/'weights/best_openvino_model/best.xml';binary=xml.with_suffix('.bin');assert xml.exists() and binary.exists()
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    spec={'id':a.run,'path':str(xml),'sha256':digest(xml),'assets':[{'path':str(binary),'sha256':digest(binary)}],'classes':['trash'],'imgsz':640,'threshold':.01,'license':'Ultralytics AGPL-3.0 + DroneWaste data CC BY 4.0','scope':'Strict conservative binary V2; candidate; development evaluation only'}
    cache={};timings={}
    for name,model in [('candidate',spec),('legacy_quarantined',old)]:
        reg=out/(name+'-registry.json');reg.write_text(json.dumps({'models':[model]},indent=2));detector=Detector(reg);preds={};start=time.perf_counter()
        rows=list(evalrows.values())
        for i,r in enumerate(rows):
            preds[str(r['source_image_id'])]=detector.detect(Image.open(src/r['path']).convert('RGB'))
            if i%25==0:print(f'{name}: {i}/{len(rows)}',flush=True)
        timings[name]=time.perf_counter()-start;cache[name]=preds;(out/(name+'-predictions.json')).write_text(json.dumps(preds));del detector
    operator=[]
    followup=ROOT/'outputs/pilot-training/operator-followup.json'
    if followup.exists():
        detector=Detector(out/'candidate-registry.json')
        for photo in json.loads(followup.read_text())['photos']:
            source=ROOT/'outputs/pilot'/photo['id']/'original'
            assert digest(source)==photo['sha256']
            image=ImageOps.exif_transpose(Image.open(source)).convert('RGB');predictions=detector.detect(image)
            operator.append({'photo_id':photo['id'],'source_sha256':photo['sha256'],'candidate_predictions_at_min_threshold':predictions,'scope':'unlabelled operator diagnostic, no accuracy claim; not activated'})
        del detector
    grid=[]
    for threshold in (.1,.15,.2,.25,.3,.35,.4,.5,.6,.7,.8,.9):
        m=metrics(selected['val_development'],cache['candidate'],threshold);grid.append({k:v for k,v in m.items() if k!='per_image'})
    eligible=[m for m in grid if m['negative_image_alarm_rate']<=.10 and m['precision']>=.50 and m['recall']>=.25]
    score=lambda m:2*m['precision']*m['recall']/max(1e-12,m['precision']+m['recall'])
    chosen=max(eligible or grid,key=score);threshold=chosen['threshold']
    val=metrics(selected['val_development'],cache['candidate'],threshold)
    # Test-development is evaluated only at the threshold fixed above, never selected from its scores.
    test=metrics(selected['test_development'],cache['candidate'],threshold)
    legacy_val=metrics(selected['val_development'],cache['legacy_quarantined'],.14314314314314314)
    legacy_test=metrics(selected['test_development'],cache['legacy_quarantined'],.14314314314314314)
    negatives=[r for r in evalrows.values() if r['image_role']=='verified_negative']
    alarms=lambda preds,rows,t:sum(any(p['confidence']>=t for p in preds[str(r['source_image_id'])]) for r in rows)
    diag={'stone_soil_road_examples':[{'source_image_id':r['source_image_id'],'review_index':r['review_index'],'split':r['split'],'path':r['path'],'candidate_max_confidence':max((p['confidence'] for p in cache['candidate'][str(r['source_image_id'])]),default=0),'legacy_max_confidence':max((p['confidence'] for p in cache['legacy_quarantined'][str(r['source_image_id'])]),default=0)} for r in stone],
          'verified_negative_comparison':{'images':len(negatives),'candidate_alarm_images':alarms(cache['candidate'],negatives,threshold),'candidate_threshold':threshold,'legacy_alarm_images':alarms(cache['legacy_quarantined'],negatives,old['threshold'] if old['threshold']!=.01 else .14314314314314314),'legacy_threshold':.14314314314314314,'scope':'includes previously trained stone/road examples; development/regression only'},
          'context_only':{'images':len(context),'signal_images':alarms(cache['candidate'],context,threshold),'scope':'Ambiguous context is not verified clean ground truth; this is signal frequency, not a false-positive rate'}}
    recommended=bool(eligible) and test['precision']>=.5 and test['recall']>=max(.25,legacy_test['recall']-.05) and test['negative_image_alarm_rate']<=.10
    report={'run':a.run,'scope':'DEVELOPMENT ONLY; all sites previously exposed; no fresh independent holdout','independent_holdout':False,'activation':'NOT ACTIVATED; manual visual review required','candidate_recommended_for_manual_review':recommended,'predeclared_gate':{'precision_min':.5,'recall_min':.25,'verified_negative_image_alarm_rate_max':.10,'iou':.5},'legacy_same_corrected_ground_truth':{'val_development':legacy_val,'test_development':legacy_test,'scope':'Legacy weights evaluated against corrected binary target labels at original deployed threshold; not original erroneous-taxonomy metrics'},'max_recall_drop_vs_legacy_on_development':.05,'threshold_selected_on':'val_development only','threshold':threshold,'val_development':val,'test_development':test,'validation_threshold_grid':grid,'diagnostics':diag,'inference_seconds':timings,'operator_diagnostics':operator,'candidate_spec':{**spec,'threshold':threshold},'initial_weights_source':'original yolo11n, not quarantined trash weights'}
    (run/'development-evaluation.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    # Reproducible error contact sheets; never treated as unseen evaluation after viewing.
    ranked=sorted(negatives,key=lambda r:max((p['confidence'] for p in cache['candidate'][str(r['source_image_id'])]),default=0),reverse=True)[:12]
    for page in range(2):
        canvas=Image.new('RGB',(960,1120),'white');draw=ImageDraw.Draw(canvas)
        for n,r in enumerate(ranked[page*6:page*6+6]):
            im=Image.open(src/r['path']).convert('RGB');d=ImageDraw.Draw(im)
            for box in cache['candidate'][str(r['source_image_id'])]:
                if box['confidence']>=threshold:d.rectangle(box['bbox'],outline='red',width=3)
            im=im.resize((320,320));x=(n%3)*320;y=(n//3)*560;canvas.paste(im,(x,y));draw.text((x+5,y+325),r['source_file_name']+' / '+r['split'],fill='black');draw.text((x+5,y+345),'verified negative; candidate boxes',fill='black')
        canvas.save(out/f'negative-errors-{page}.jpg')
    print(json.dumps({'report':str(run/'development-evaluation.json'),'recommended_for_manual_review':recommended,'threshold':threshold,'val_precision':val['precision'],'val_recall':val['recall'],'test_development_precision':test['precision'],'test_development_recall':test['recall'],'diagnostics':diag},indent=2))
if __name__=='__main__':main()
