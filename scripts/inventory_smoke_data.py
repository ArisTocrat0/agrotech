"""Read-only inventory of smoke/fire training metadata in known project roots."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    import yaml
    roots=[ROOT/'datasets',ROOT/'artifacts',ROOT/'outputs/sources/AgroMindKZ',Path('/home/beka/Projects/AgriFireShield')]
    skipped={'node_modules','.git','.venv','vendor','images','__pycache__','raw'};datasets=[];models=[];scanned=0
    for root in roots:
        for directory,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in skipped]
            for name in files:
                p=Path(directory)/name
                if p.suffix.lower() not in ('.yaml','.yml','.json') or p.stat().st_size>5_000_000:continue
                try:data=yaml.safe_load(p.read_text()) if p.suffix in ('.yaml','.yml') else json.loads(p.read_text())
                except (OSError,UnicodeError,ValueError,yaml.YAMLError):continue
                scanned+=1
                if not isinstance(data,dict):continue
                names=data.get('names',{});names=list(names.values()) if isinstance(names,dict) else names if isinstance(names,list) else []
                cats=data.get('categories',[]);category_names=[str(c.get('name','')) for c in cats if isinstance(c,dict)] if isinstance(cats,list) else []
                labels=[s for s in names+category_names if any(t in str(s).lower() for t in ('smoke','fire','дым','пожар'))]
                if not labels:continue
                entry={'path':str(p),'classes':labels}
                if 'train' in data or 'annotations' in data:entry.update(train=data.get('train'),val=data.get('val'),test=data.get('test'),annotations=len(data.get('annotations',[])));datasets.append(entry)
                else:models.append(entry)
    fire=ROOT/'datasets/fire-candidates-v1/manifest.json';manifest=json.loads(fire.read_text());registry=json.loads((ROOT/'artifacts/ecokineu-models.json').read_text());baseline=next(s for s in registry['models'] if 'smoke' in s['classes'])
    report={'scope':'Known project roots only; no downloads or deletion; filenames/directories omitted from dependency trees','roots':[str(p) for p in roots],'metadata_files_scanned':scanned,'labelled_smoke_fire_dataset_candidates':datasets,'model_metadata_not_training_data':models,'unlabelled_fire_candidates':{'manifest':str(fire),'photos':len(manifest['records']),'splits':sorted({r['split'] for r in manifest['records']}),'labelled_smoke_objects':0,'usable_for_supervised_smoke_training':False},'preserved_active_baseline':{'id':baseline['id'],'classes':baseline['classes'],'sha256':baseline['sha256'],'license':baseline['license']},'training_started_for_smoke':False,'blocker':'No local verified labelled smoke/fire train/validation/test corpus found. Pretrained weights and two unlabelled fire photos are not such a corpus.','required_before_download':'A named permitted source with image licenses, smoke/fire boxes, scene/session split and exact selected byte count. Proposed pilot cap <=200MiB; planning target300-500 scene-varied frames incl verified negatives, not an accuracy guarantee. No download is authorized or started by this inventory.','proposed_next_stage':'Separate fire and smoke classes; preserve baseline and compare per-class P/R plus cloud/fog/dust/water false alarms. Run sequentially after trash, not concurrently.'}
    (ROOT/'artifacts/smoke_data_inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
