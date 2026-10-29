"""Actual local inference smoke-check; not a recognition quality evaluation."""
from pathlib import Path
import json,sys,time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
def main():
    from PIL import Image
    from src.pilot.detector import Detector
    detector=Detector(ROOT/'artifacts/ecokineu-models.json')
    assert len(detector.models)==1 and detector.models[0][0]['classes']==['fire',None,'smoke']
    path=next((ROOT/'datasets/fire-candidates-v1/images').glob('*'))
    image=Image.open(path).convert('RGB');times=[]
    for _ in range(3):
        start=time.perf_counter();rows=detector.detect(image);times.append(time.perf_counter()-start)
    assert all(r['class_name'] in ('fire','smoke') for r in rows)
    report={'active_ids':[s['id'] for s,_ in detector.models],'registry_sha256':detector.registry_sha256,
            'source':str(path.relative_to(ROOT)),'inference_preprocess_nms_seconds':times,
            'no_accuracy_claim':True,'trash_disabled':True}
    (ROOT/'artifacts/quarantine_smoke_check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
if __name__=='__main__':main()
