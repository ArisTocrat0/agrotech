"""Reference the independently prepared 500 photos; no download/copy or split change."""
import argparse,hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT=Path('/home/beka/Documents/Codex/2026-10-20/task-2/ecokineu_dronewaste_500')
OUT=ROOT/'datasets/dronewaste500-v1'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path,nargs='?',default=DEFAULT);parser.add_argument('--restore-links',action='store_true');args=parser.parse_args();source=args.source
    if (OUT/'manifest.json').exists():
        if not args.restore_links:raise ValueError('Version exists; use --restore-links only to verify/reconstruct links')
        previous=json.loads((OUT/'manifest.json').read_text())
        if hashlib.sha256((source/'manifest.jsonl').read_bytes()).hexdigest()!=previous['source_manifest_sha256']:raise ValueError('Source manifest differs; use a new dataset version')
        origins={r['source_image_id']:r for r in (json.loads(s) for s in (source/'manifest.jsonl').read_text().splitlines() if s.strip())}
        for row in previous['records']:
            src=(source/origins[row['source_image_id']]['path']).resolve();target=OUT/row['file']
            if hashlib.sha256(src.read_bytes()).hexdigest()!=row['source_sha256']:raise ValueError('Source changed')
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.is_symlink() and target.resolve()==src:continue
            if target.is_symlink():target.unlink()
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Conflicting local file; not overwritten')
            else:target.symlink_to(src)
        (OUT/'dataset.yaml').write_text('path: '+str(OUT)+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames: [trash]\n')
        print('500 source links verified/restored; labels and splits unchanged');return
    records=[json.loads(s) for s in (source/'manifest.jsonl').read_text().splitlines() if s.strip()]
    if len(records)!=500 or len({r['sha256'] for r in records})!=500:raise ValueError('Expected 500 unique verified images')
    sites={s:{r['site'] for r in records if r['split']==s} for s in ('train','val','test')}
    if any(sites[a]&sites[b] for a,b in [('train','val'),('train','test'),('val','test')]):raise ValueError('Site leakage')
    for split,count in [('train',350),('val',75),('test',75)]:
        if sum(r['split']==split for r in records)!=count:raise ValueError('Unexpected split count')
    OUT.mkdir(parents=True,exist_ok=True);converted=[];counts={};excluded=0
    for split in ('train','val','test'):
        coco=json.loads((source/'annotations'/(split+'.json')).read_text());ann={}
        for a in coco['annotations']:
            if a['category_id']==18:excluded+=1;continue # ambiguous roof/Asbestos labels: no visual chemical claim
            ann.setdefault(a['image_id'],[]).append(a)
        rows={r['source_image_id']:r for r in records if r['split']==split};counts[split]=0
        for image in coco['images']:
            row=rows[image['id']];src=(source/row['path']).resolve()
            if not src.is_relative_to(source.resolve()) or hashlib.sha256(src.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Source changed: '+row['path'])
            target=OUT/'images'/split/src.name;target.parent.mkdir(parents=True,exist_ok=True);target.symlink_to(src)
            lines=[]
            for a in ann.get(image['id'],[]):
                x,y,w,h=a['bbox'];iw,ih=image['width'],image['height']
                if any(not math.isfinite(v) for v in (x,y,w,h)) or min(x,y)<0 or min(w,h)<=0 or x+w>iw+.01 or y+h>ih+.01:raise ValueError('Invalid bbox')
                lines.append(f'0 {(x+w/2)/iw:.8f} {(y+h/2)/ih:.8f} {w/iw:.8f} {h/ih:.8f}')
            labels=OUT/'labels'/split;labels.mkdir(parents=True,exist_ok=True);(labels/(src.stem+'.txt')).write_text('\n'.join(lines)+('\n' if lines else ''))
            counts[split]+=len(lines)
            converted.append({'file':str(target.relative_to(OUT)),'source_path':str(src),'split':split,'site':row['site'],
                              'source_image_id':row['source_image_id'],'source_sha256':row['sha256'],'sha256':row['sha256'],
                              'annotations':len(lines),'source_category_ids':row['category_ids']})
    manifest={'version':'dronewaste500-v1','source_root':str(source),'source_manifest_sha256':hashlib.sha256((source/'manifest.jsonl').read_bytes()).hexdigest(),
              'license':'CC BY 4.0','attribution':str(source/'README.md'),'source_record':'https://zenodo.org/records/17045559',
              'source_annotations':2232,'derived_annotations':counts,'excluded_annotations':excluded,'excluded_category_ids':[18],
              'class_mapping':'All source categories except 18 Asbestos -> trash candidate; original source untouched',
              'scope':'Orthomosaic dump/material piles, not individual street litter; no GPS/time; site-disjoint 350/75/75 unchanged',
              'records':converted}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (OUT/'dataset.yaml').write_text('path: '+str(OUT)+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames: [trash]\n')
    (OUT/'ATTRIBUTION.txt').write_text((source/'README.md').read_text()+'\n\nDerived integration: symlinks only, original site splits unchanged. Source Asbestos category18 excluded from YOLO labels; other19 categories collapsed to trash. Original image/COCO bytes unchanged.\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='records'},indent=2))
if __name__=='__main__':main()
