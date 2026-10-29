"""Metadata-only smoke integration with per-file image links; no image/archive copies or downloads."""
import argparse,collections,hashlib,json,os,shutil,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args();src=a.source.resolve();dst=ROOT/'datasets/smoke-pyrosdis-v1';assert not dst.exists(),'Do not overwrite an integrated version';os.nice(5)
    verify=json.loads((src/'verification.json').read_text());assert verify['status']=='PASS' and verify['images']==500 and verify['boxes']==421
    allocated=sum(p.lstat().st_blocks*512 for p in [src,*src.rglob('*')]);assert allocated<1_000_000_000
    archive=json.loads((src/'source/archive_verified.json').read_text());assert sha(src/'source/val.parquet')==archive['sha256']==archive['expected_hf_lfs_sha256']
    records=[json.loads(s) for s in (src/'manifest.jsonl').read_text().splitlines()];assert len({r['sha256'] for r in records})==len({r['pixel_sha256'] for r in records})==500
    from PIL import Image,ImageOps
    photos=json.load(urllib.request.urlopen('http://127.0.0.1:8010/api/pilot/photos'))['photos'];private=[r for r in photos if r['presentation']['kind']=='operator_upload'];private_hash={r['sha256'] for r in private};private_pixel={hashlib.sha256(ImageOps.exif_transpose(Image.open(ROOT/'outputs/pilot'/r['id']/'original')).convert('RGB').tobytes()).hexdigest() for r in private}
    assert not private_hash&{r['sha256'] for r in records};assert not private_pixel&{r['pixel_sha256'] for r in records}
    groups=collections.defaultdict(set);days=collections.defaultdict(set);normalized=[];counts={};maxerror=0
    dst.mkdir(parents=True)
    for name in ('README.md','manifest.jsonl','verification.json','statistics.json','disk_usage.json','quarantine_initial.json','selection_exclusions.json'):shutil.copyfile(src/name,dst/name)
    shutil.copytree(src/'labels',dst/'labels');shutil.copytree(src/'annotations',dst/'annotations');(dst/'source').mkdir();(dst/'qa').mkdir()
    for f in (src/'source').iterdir():
        if f.is_file() and f.suffix in ('.json','.md','.txt'):shutil.copyfile(f,dst/'source'/f.name)
    shutil.copyfile(src/'qa/negative_review.json',dst/'qa/negative_review.json')
    for split,expected in [('train',350),('val',75),('test_development',75)]:
        coco=json.loads((dst/'annotations'/f'{split}.json').read_text());assert [c['name'] for c in coco['categories']]==['smoke'];annotations=collections.defaultdict(list)
        for box in coco['annotations']:assert box['category_id']==1;annotations[box['image_id']].append(box)
        selected=[r for r in records if r['split']==split];assert len(selected)==expected;counts[split]={'images':len(selected),'positive':0,'negative':0,'boxes':0}
        for r in selected:
            relative=Path(r['path']);assert not relative.is_absolute() and '..' not in relative.parts and relative.parts[:2]==('images',split)
            original=src/relative;assert sha(original)==r['sha256']
            with original.open('rb') as stream:stream.seek(-2,2);assert stream.read()==b'\xff\xd9','Reject JPEG needing loader repair'
            with Image.open(original) as im:
                im.load();assert im.size==(r['width'],r['height']) and im.getexif().get(274,1) in (None,1);assert hashlib.sha256(im.convert('RGB').tobytes()).hexdigest()==r['pixel_sha256']
            target=dst/relative;target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(original)
            labels=[list(map(float,s.split())) for s in (dst/'labels'/split/(original.stem+'.txt')).read_text().splitlines()];truth=annotations[r['image_id']];assert len(labels)==len(truth)==r['annotation_count']
            for line,box in zip(labels,truth):
                c,cx,cy,w,h=line;assert c==0;back=[(cx-w/2)*r['width'],(cy-h/2)*r['height'],w*r['width'],h*r['height']];maxerror=max(maxerror,max(abs(a-b) for a,b in zip(back,box['bbox'])))
            positive=bool(labels)
            if not positive:assert r.get('negative_review',{}).get('decision')=='accept'
            groups[r['site_group']].add(split);days[r['camera_day']].add(split);counts[split]['positive' if positive else 'negative']+=1;counts[split]['boxes']+=len(labels)
            normalized.append({**r,'source_role':r['role'],'role':'positive_smoke' if positive else 'verified_negative','file':r['path'],'source_sha256':r['sha256'],'source_image_id':r['image_id'],'source':'pyro_sdis','author':r['attribution']})
    assert maxerror<1e-5 and all(len(v)==1 for v in groups.values()) and all(len(v)==1 for v in days.values())
    manifest={'version':'smoke-pyrosdis-v1','source_root':str(src),'source_manifest_sha256':sha(src/'manifest.jsonl'),'license':'Apache-2.0 dataset; preserve Pyronear/SDIS attribution','source_record':'https://huggingface.co/datasets/pyronear/pyro-sdis','scope':'Smoke-only candidate; Fire must be preserved through separate route. New split of source val, no event/geographic independence or source-trained baseline independence proof.','split_counts':counts,'geographic_independence_proven':False,'records':normalized}
    (dst/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for name in ('data.yaml','test_development.yaml'):(dst/name).write_text((src/name).read_text().replace(str(src),str(dst)))
    hashes={str(p.relative_to(dst)):sha(p) for p in sorted(dst.rglob('*')) if p.is_file()}
    lock={'files':hashes,'source':str(src),'source_allocated_bytes':allocated,'source_budget_bytes':1_000_000_000,'image_copies':0,'archive_copies':0,'images_linked':500,'private_photos_excluded':len(private),'max_coco_yolo_error_px':maxerror}
    (dst/'snapshot-lock.json').write_text(json.dumps(lock,indent=2)+'\n');print(json.dumps({'dataset':str(dst),'counts':counts,'source_allocated_bytes':allocated,'image_copies':0,'private_photos_excluded':len(private),'roundtrip_px':maxerror},indent=2))
if __name__=='__main__':main()
