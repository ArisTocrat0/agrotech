"""Optional real-model/DB routing smoke test. No accuracy estimate or production-photo writes."""
import argparse,base64,hashlib,json,shutil,sys,tempfile,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--asset-root',type=Path,default=ROOT);parser.add_argument('--output',type=Path,default=ROOT/'outputs/directions/live-verification.json');args=parser.parse_args()
    assets=args.asset_root.resolve();photo=assets/'datasets/fire-candidates-v1/images/fire-107639709.jpg'
    required=[photo,assets/'config.yaml',assets/'artifacts/reference_index.pt',assets/'artifacts/ecokineu-models.json',assets/'outputs/pilot-db/client.json']
    if any(not path.is_file() for path in required):raise RuntimeError('Restore the required local assets/private DB configuration first. No download or fallback fixture is used.')
    from src.pilot.service import Pilot
    import pymysql
    settings=json.loads((assets/'outputs/pilot-db/client.json').read_text());keys=[];results=[]
    with tempfile.TemporaryDirectory(prefix='agrotech-live-directions-') as temporary:
        root=Path(temporary);(root/'artifacts').mkdir();(root/'outputs/pilot-db').mkdir(parents=True)
        (root/'outputs/pilot-db/client.json').write_text(json.dumps({**settings,'_table':'photos_tests'}));shutil.copyfile(assets/'config.yaml',root/'config.yaml')
        (root/'artifacts/reference_index.pt').symlink_to(assets/'artifacts/reference_index.pt')
        registry=json.loads((assets/'artifacts/ecokineu-models.json').read_text())
        for spec in registry['models']:
            for obj in [spec,*spec.get('assets',[])]:
                if not Path(obj['path']).is_absolute():obj['path']=str(assets/obj['path'])
        (root/'artifacts/ecokineu-models.json').write_text(json.dumps(registry))
        app=Pilot(root);mission='routing-'+uuid.uuid4().hex
        try:
            for mode in ('trash','fire_smoke','weeds','common'):
                payload={'mission':mission,'name':photo.name,'analysis_mode':mode,'photo':base64.b64encode(photo.read_bytes()).decode(),'metadata':{'qa':True,'scope':'Real model routing test, not accuracy or a field observation'}}
                queued=app.ingest(payload);key=queued['photo']['id'];keys.append(key);deadline=time.monotonic()+120
                while time.monotonic()<deadline:
                    row=app.store.get(key)
                    if row['state'] in ('done','error'):break
                    time.sleep(.1)
                else:raise RuntimeError('Live inference deadline: '+mode)
                if row['state']!='done':raise RuntimeError(mode+': '+str(row['error']))
                actual={e['class_name'] for e in row['result']['events']};allowed={'trash':{'trash'},'fire_smoke':{'fire','smoke'},'weeds':{'weed'},'common':{'weed','trash','fire','smoke'}}[mode]
                assert actual<=allowed,'Cross-direction detection leak'
                if mode=='trash':assert row['result']['analysis_status']['fire']['status']=='not_analyzed'
                if mode=='fire_smoke':assert row['result']['analysis_status']['weed']['status']=='not_analyzed'
                if mode=='common':
                    assert row['result']['analysis_status']['weed']['status'].startswith('analyzed_')
                    assert row['result']['analysis_status']['fire']['status'].startswith('analyzed_')
                assert app.ingest(payload)['duplicate'],'Same-mode duplicate not recognized'
                results.append({'mode':mode,'state':row['state'],'seconds':row['result']['processing_seconds'],'events':len(row['result']['events']),'coverage':row['result']['analysis_status']})
            assert len(set(keys))==4,'Modes collided in photo deduplication'
            shared=app.direction_detectors['fire_smoke'].models[0][1] is app.detector.models[0][1]
            assert shared,'Common mode recompiled the same model'
        finally:
            app.close()
            with pymysql.connect(**settings,autocommit=True) as database:
                with database.cursor() as cursor:
                    for key in keys:cursor.execute('DELETE FROM photos_tests WHERE id=%s',(key,))
    report={'scope':'Real model and isolated MariaDB routing only; not labelled recognition accuracy. Production photos untouched.','image_sha256':hashlib.sha256(photo.read_bytes()).hexdigest(),'directions':results,'shared_compiled_model':shared}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
