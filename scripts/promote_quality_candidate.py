"""Explicit local promotion after terminal evaluation, parity and human-agent visual review. No restart."""
import argparse,json,time,urllib.request,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(path,data):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--class-name',choices=['trash','smoke'],required=True);p.add_argument('--review-reason',required=True);a=p.parse_args();assert a.run.replace('-','').isalnum() and len(a.review_reason)>30
 run=ROOT/'outputs/pilot-training'/a.run;report=json.loads((run/'development-evaluation.json').read_text());parity=json.loads((run/'candidate-parity.json').read_text());quality=json.loads((run/'quality-report.json').read_text())
 assert report['candidate_recommended_for_manual_review'] is True and parity['passed'] is True
 assert parity['best_pt_sha256']==quality['best_weights_sha256']==sha(run/'weights/best.pt')
 lock=run/'threshold-lock.json';assert report['threshold_lock_sha256']==sha(lock)
 spec=report['candidate_spec'];assert spec['classes']==[a.class_name] and spec['id']==a.run and spec['threshold']==json.loads(lock.read_text())['threshold']
 assert parity['xml_sha256']==spec['sha256'] and parity['threshold']==spec['threshold']
 for asset in [spec,*spec['assets']]:
  path=Path(asset['path']);assert path.is_relative_to(ROOT) and sha(path)==asset['sha256'];asset['path']=str(path.relative_to(ROOT))
 photos=json.load(urllib.request.urlopen('http://127.0.0.1:8010/api/pilot/photos'))['photos'];assert not any(r['state'] in ('queued','running') for r in photos),'Wait for idle queue'
 registry=ROOT/'artifacts/ecokineu-models.json';oldsha=sha(registry);models=json.loads(registry.read_text());assert not any(s['id']==a.run for s in models['models']),'Already configured; inspect status instead of repeating'
 if a.class_name=='smoke':
  # Keep Fire weights and class index, suppress only the superseded Smoke output.
  baseline=next(s for s in models['models'] if s['id']=='fire-v6-4a60bd37');assert baseline.get('enabled',True) and baseline['classes']==['fire',None,'smoke']
  baseline['classes']=['fire',None,None];baseline['scope']+='; Smoke routed separately to '+a.run
 else:
  for model in models['models']:
   assert not (model.get('enabled',True) and 'trash' in model['classes']),'Existing trash model needs explicit versioned replacement review'
 spec['enabled']=True;models['models'].append(spec)
 assert any(s.get('enabled',True) and 'fire' in s['classes'] for s in models['models']),'Fire route must survive'
 backup=ROOT/'outputs/pilot-training/registry-history';backup.mkdir(exist_ok=True);dest=backup/f'{time.time_ns()}-{oldsha}.json'
 with dest.open('xb') as f:f.write(registry.read_bytes())
 assert sha(registry)==oldsha,'Registry changed during review'
 write(registry,models)
 decision={'verdict':'approved_local_pilot','run':a.run,'class':a.class_name,'reason':a.review_reason,'reviewed_unix':time.time(),'prior_registry_sha256':oldsha,'new_registry_sha256':sha(registry),'rollback_registry':str(dest.relative_to(ROOT)),'restart_required':True,'original_photos_unchanged':True,'scope':report['scope']}
 write(run/'manual-review.json',decision);print(json.dumps(decision,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
