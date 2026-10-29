"""Read-only source integration of conservative binary V2, no context relabelling."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);args=p.parse_args();src=args.source.resolve()
    policy=json.loads((src/'inference_policy.json').read_text());check=json.loads((src/'integration_check.json').read_text())
    assert check['status']=='PASS' and check['independent_holdout'] is False
    records=[json.loads(s) for s in (src/'manifest.jsonl').read_text().splitlines()];lookup={r['source_image_id']:r for r in records}
    target=ROOT/'datasets/dronewaste-v2-binary-strict';target.mkdir(parents=True,exist_ok=True);out=[];sites={};counts={}
    for split,expected in [('train',449),('val_development',52),('test_development',133)]:
        data=json.loads((src/'annotations/binary_strict'/f'{split}.json').read_text());assert len(data['images'])==expected
        annotations={}
        for a in data['annotations']:
            assert a['category_id']==1 and a['source_category_id'] in policy['pollution_coco_category_ids'];annotations.setdefault(a['image_id'],[]).append(a)
        sites[split]=set();counts[split]=0
        for im in data['images']:
            r=lookup[im['id']];assert r['binary_strict_eligible'] and r['split']==split
            assert r['image_role'] in ('positive','verified_negative')
            if r['image_role']=='positive':assert not r['context_annotation_count']
            source=src/'images'/im['file_name'];assert sha(source)==r['sha256'];sites[split].add(r['site'])
            image=target/'images'/im['file_name'];image.parent.mkdir(parents=True,exist_ok=True)
            if image.is_symlink():assert image.resolve()==source.resolve()
            elif image.exists():raise ValueError('Refuse to overwrite existing image')
            else:image.symlink_to(source)
            rows=[]
            for a in annotations.get(im['id'],[]):
                x,y,w,h=a['bbox'];assert w>0 and h>0 and x>=0 and y>=0 and x+w<=640.001 and y+h<=640.001
                rows.append(f'0 {(x+w/2)/640:.9f} {(y+h/2)/640:.9f} {w/640:.9f} {h/640:.9f}')
            if not rows:assert r['image_role']=='verified_negative'
            label=target/'labels'/Path(im['file_name']).with_suffix('.txt');label.parent.mkdir(parents=True,exist_ok=True);label.write_text('\n'.join(rows)+('\n' if rows else ''))
            out.append({**r,'file':str(image.relative_to(target)),'source_sha256':r['sha256'],'source_annotation_count':len(rows)});counts[split]+=1
    for a,b in [('train','val_development'),('train','test_development'),('val_development','test_development')]:assert not sites[a]&sites[b]
    assert len({r['sha256'] for r in out})==len(out) and len({r['pixel_sha256'] for r in out})==len(out)
    manifest={'version':'dronewaste-v2-binary-strict','source_root':str(src),'source_manifest_sha256':sha(src/'manifest.jsonl'),'license':'CC BY 4.0','source_record':'https://doi.org/10.5281/zenodo.17045559','source_attribution':'Morandini et al., DroneWaste v1.0; see SOURCE_README.md','independent_holdout':False,'scope':'Conservative waste candidates; ambiguous annotated scenes excluded; development sites previously exposed. Not proof of illegal dumping or drone field accuracy.','split_counts':counts,'source_policy':policy,'records':out}
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for name in ('README.md','inference_policy.json','validation.json','integration_check.json','taxonomy_mapping.json','source_classes.json'):(target/('SOURCE_README.md' if name=='README.md' else name)).write_bytes((src/name).read_bytes())
    # No test key in training YAML. Test-development is isolated in a separate evaluation YAML.
    (target/'train.yaml').write_text(f'path: {target}\ntrain: images/train\nval: images/val_development\nnames: [trash]\n')
    (target/'development-eval.yaml').write_text(f'path: {target}\ntrain: images/train\nval: images/test_development\nnames: [trash]\n')
    print(json.dumps({'target':str(target),'split_counts':counts,'independent_holdout':False}))
if __name__=='__main__':main()
