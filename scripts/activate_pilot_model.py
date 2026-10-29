"""Explicit activation and rollback; preserves each previous registry snapshot."""
import argparse,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--trash-run');p.add_argument('--fire-candidate',action='store_true');p.add_argument('--restore',type=Path);a=p.parse_args()
    registry=ROOT/'artifacts/ecokineu-models.json'
    state=json.loads(registry.read_text())
    if a.restore:new=json.loads(a.restore.read_text())
    elif a.fire_candidate:
        folder=ROOT/'artifacts/fire-candidate-v6';source=json.loads((folder/'SOURCE.json').read_text())
        names=source['conversion']['classes'];mapping={'fire':'fire','smoke':'smoke','person':None}
        classes=[mapping[names[str(i)]] for i in range(len(names))]
        path=folder/'best_openvino_model/best.xml';binary=folder/'best_openvino_model/best.bin'
        sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
        spec={'id':'fire-v6-'+source['revision'][:8],'path':str(path.relative_to(ROOT)),'sha256':sha(path),
              'assets':[{'path':str(binary.relative_to(ROOT)),'sha256':sha(binary)}],
              'classes':classes,'imgsz':640,'threshold':.35,'license':'Weights card CC BY 2.0; Ultralytics runtime/export AGPL-3.0',
              'scope':'Сторонний экспериментальный baseline; person исключён; происхождение train и качество на воздушных фото не подтверждены'}
        new={'schema':1,'models':[spec]+[m for m in state['models'] if 'fire' not in m['classes'] and 'smoke' not in m['classes']]}
    elif a.trash_run:
        if not a.trash_run.replace('-','').isalnum():raise ValueError('Invalid run')
        folder=ROOT/'outputs/pilot-training'/a.trash_run/'weights/best_openvino_model'
        path=folder/'best.xml';binary=folder/'best.bin'
        for f in (path,binary):
            if not f.is_file():raise ValueError('Exported weights missing')
        sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
        import yaml
        meta=yaml.safe_load((folder/'metadata.yaml').read_text())
        report=json.loads((ROOT/'outputs/pilot-training'/a.trash_run/'report.json').read_text()) if (ROOT/'outputs/pilot-training'/a.trash_run/'report.json').exists() else {}
        quality=report.get('test_metrics',{}).get('metrics/mAP50(B)')
        calibration=ROOT/'outputs/pilot-training'/a.trash_run/'calibration.json'
        threshold=json.loads(calibration.read_text())['confidence'] if calibration.exists() else .35
        spec={'id':'trash-'+a.trash_run,'path':str(path.relative_to(ROOT)),'sha256':sha(path),
              'assets':[{'path':str(binary.relative_to(ROOT)),'sha256':sha(binary)}],
              'classes':['trash'],'imgsz':int(meta['imgsz'][0]),'threshold':threshold,'license':'Ultralytics AGPL-3.0 + UAVVaste data CC BY 4.0',
              'scope':f"{report.get('scope','Эксперимент UAVVaste')}; split={report.get('split_counts',{})}; mAP50={quality}; порог {threshold:.3f}; проверка обязательна"}
        new={'schema':1,'models':[m for m in state['models'] if m['classes']!=['trash']]+[spec]}
    else:raise ValueError('Use --trash-run or --restore')
    # Validate every weight before changing the active registry.
    for spec in new['models']:
        for item in [spec,*spec.get('assets',[])]:
            path=Path(item['path']);path=path if path.is_absolute() else ROOT/path
            if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Weight checksum mismatch')
    history=ROOT/'artifacts/model-registry-history';history.mkdir(exist_ok=True)
    previous=history/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json');previous.write_text(json.dumps(state,ensure_ascii=False,indent=2))
    temporary=registry.with_suffix('.tmp');temporary.write_text(json.dumps(new,ensure_ascii=False,indent=2));temporary.replace(registry)
    print('Activated. Previous registry:',previous);print('Restart web_pilot.py so the queue pins this version.')
if __name__=='__main__':main()
