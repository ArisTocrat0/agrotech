"""Compare our photo preprocessing/boxes with official Ultralytics IR backend.

Low thresholds here exist ONLY for contract verification, not deployed settings.
"""
import json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(ROOT/'outputs/pilot-verify-config'))
    import numpy as np,torch
    torch.set_num_threads(2)
    from PIL import Image
    from ultralytics import YOLO
    from src.pilot.detector import Detector
    adapter=Detector(ROOT/'artifacts/ecokineu-models.json');rows=[]
    for spec,net in list(adapter.models):
        sample=ROOT/('datasets/fire-candidates-v1/images/fire-248462.jpg' if 'fire' in spec['classes'] else 'datasets/uavvaste-pilot-v1/images/test/batch_03_img_1560.jpg')
        threshold=.05 if 'fire' in spec['classes'] else .001
        spec={**spec,'threshold':threshold};adapter.models=[(spec,net)]
        photo=Image.open(sample).convert('RGB');actual=adapter.detect(photo)
        path=Path(spec['path']);path=path if path.is_absolute() else ROOT/path
        with tempfile.TemporaryDirectory(prefix='ecokineu-ir-reference-') as d:
            alias=Path(d)/'reference_openvino_model';alias.symlink_to(path.parent,target_is_directory=True)
            official=YOLO(str(alias),task='detect')
            result=official.predict(source=photo,imgsz=spec['imgsz'],conf=threshold,iou=.45,device='cpu',max_det=100,verbose=False,rect=False,classes=[i for i,name in enumerate(spec['classes']) if name is not None])[0]
        expected=[]
        for b in result.boxes:
            expected.append({'class_name':spec['classes'][int(b.cls.item())],'confidence':float(b.conf.item()),'bbox':b.xyxy[0].tolist()})
        expected=[r for r in expected if r['bbox'][0]<r['bbox'][2] and r['bbox'][1]<r['bbox'][3]]
        if len(actual)!=len(expected):raise ValueError(f"{spec['id']}: counts differ {len(actual)} vs {len(expected)}")
        max_error=0.
        remaining=list(expected)
        # Match spatially: near-equal scores can exchange order across CPU thread configs.
        for a in actual:
            choices=[(float(np.max(np.abs(np.array(a['bbox'])-b['bbox']))),i,b) for i,b in enumerate(remaining) if a['class_name']==b['class_name']]
            if not choices:raise ValueError('Class mismatch')
            error,i,b=min(choices,key=lambda x:x[0])
            if error>.75 or abs(a['confidence']-b['confidence'])>.003:
                raise ValueError(f"Adapter mismatch: {a} vs {b}")
            remaining.pop(i);max_error=max(max_error,error)
        print(spec['id'],'matched',len(actual),'objects; maximum bbox error',max_error,flush=True)
        rows.append({'model':spec['id'],'objects_compared':len(actual),'threshold_for_contract_check_only':threshold,
                     'max_bbox_pixel_error':max_error,'passed':True})
    report={'scope':'Adapter parity only, not recognition quality','results':rows}
    (ROOT/'artifacts/pilot_adapter_parity.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
