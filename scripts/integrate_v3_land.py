"""Freeze an independent V3 land snapshot; no original dataset changes or holdout viewing."""
import collections,hashlib,json,shutil,subprocess,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args();src=a.source.resolve();dst=ROOT/'datasets/litter-v3-land';assert not dst.exists(),'Snapshot already exists: do not overwrite'
    check=json.loads((src/'integration_check.json').read_text());assert check['status']=='PASS' and check['images']==1634 and check['historical_test_batches_not_in_train_or_val'] and not check['private_user_photos_used']
    records=[json.loads(s) for s in (src/'manifest.jsonl').read_text().splitlines()];assert len({r['sha256'] for r in records})==len(records)==1634
    photos=json.load(urllib.request.urlopen('http://127.0.0.1:8010/api/pilot/photos'))['photos'];private=[r for r in photos if r['presentation']['kind']=='operator_upload']
    from PIL import Image,ImageOps
    private_hash={r['sha256'] for r in private};private_pixels={hashlib.sha256(ImageOps.exif_transpose(Image.open(ROOT/'outputs/pilot'/r['id']/'original')).convert('RGB').tobytes()).hexdigest() for r in private}
    assert not private_hash&{r['sha256'] for r in records};assert not private_pixels&{r['pixel_sha256'] for r in records}
    old=json.loads((ROOT/'datasets/dronewaste-v2-binary-strict/manifest.json').read_text());old_test={r['sha256'] for r in old['records'] if r['split']=='test_development'}
    tuning={'train','val','val_development_aerial','val_development_old'}
    assert not old_test&{r['sha256'] for r in records if r['split'] in tuning}
    for r in records:
        if r['source']=='dronewaste_negative' and r.get('prior_batch_exposure')=='test':assert r['split']=='test_development_old'
        if r['source']=='uavvaste' and r.get('prior_batch_exposure')=='test':assert r['split']=='test_development_aerial'
    dst.mkdir(parents=True)
    for name in ('annotations','labels','source'):shutil.copytree(src/name,dst/name)
    (dst/'qa').mkdir();shutil.copyfile(src/'qa/near_duplicate_pairs.json',dst/'qa/near_duplicate_pairs.json')
    for name in ('commons_candidates.json','commons_review.json','final_samples.json'):
        if (src/'qa'/name).exists():shutil.copyfile(src/'qa'/name,dst/'qa'/name)
    for name in ('README.md','manifest.jsonl','integration_check.json','validation.json','sealed_holdout_manifest.json','taxonomy_mapping.json','source_class_definitions.json','object_scale_statistics.json','split_statistics.json','taco_component_assignment.json'):
        shutil.copyfile(src/name,dst/name)
    for n,r in enumerate(records):
        source=src/r['path'];target=dst/r['path'];target.parent.mkdir(parents=True,exist_ok=True);assert sha(source)==r['sha256'];shutil.copyfile(source,target);assert sha(target)==r['sha256']
        if n%200==0:print('SNAPSHOT',n,len(records),flush=True)
    (dst/'scripts').mkdir();shutil.copyfile(src/'scripts/verify_dataset.py',dst/'scripts/verify_dataset.py')
    subprocess.run([str(ROOT/'.venv/bin/python'),str(dst/'scripts/verify_dataset.py')],check=True)
    for path in src.glob('*.yaml'):(dst/path.name).write_text(path.read_text().replace(str(src),str(dst)))
    manifest={'version':'litter-v3-land','source_root':str(src),'source_manifest_sha256':sha(src/'manifest.jsonl'),'license':'Per-image licenses; TACO/UAVVaste/DroneWaste CC BY4; Commons individually attributed','scope':'Individual land litter, unseen UAV batches held out; geography independence unproven; no water-positive test','geographic_independence_proven':False,'records':records}
    (dst/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    locked={str(p.relative_to(dst)):sha(p) for p in sorted(dst.rglob('*')) if p.is_file() and not str(p.relative_to(dst)).startswith('scripts/')}
    (dst/'snapshot-lock.json').write_text(json.dumps({'source':str(src),'files':locked,'private_photo_hashes_excluded':len(private),'old_test_excluded_from_train_tuning':True,'data_mutable_during_run':False},indent=2)+'\n')
    print(json.dumps({'snapshot':str(dst),'image_count':len(records),'snapshot_lock_sha256':sha(dst/'snapshot-lock.json'),'private_photos_excluded':len(private)}),flush=True)
if __name__=='__main__':main()
