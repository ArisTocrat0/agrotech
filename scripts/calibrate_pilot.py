"""Choose an exploratory confidence threshold using validation only, never test."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--data',type=Path,default=ROOT/'datasets/uavvaste-pilot-v1/dataset.yaml');a=p.parse_args()
    if not a.run.replace('-','').isalnum():raise ValueError('Invalid run')
    os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(ROOT/'outputs/pilot-training/config'))
    import numpy as np,torch
    torch.set_num_threads(2)
    from ultralytics import YOLO
    folder=ROOT/'outputs/pilot-training'/a.run
    import yaml
    size=yaml.safe_load((folder/'weights/best_openvino_model/metadata.yaml').read_text())['imgsz'][0]
    model=YOLO(str(folder/'weights/best.pt'))
    m=model.val(data=str(a.data.resolve()),split='val',imgsz=size,device='cpu',
                workers=0,batch=4,max_det=100,iou=.45,plots=False,project=str(ROOT/'outputs/pilot-training'),name=a.run+'-calibration')
    idx=int(m.box.f1_curve.mean(0).argmax());threshold=float(m.box.px[idx])
    threshold=max(.001,min(.99,threshold))
    report={'split':'validation only','selection':'maximum mean F1 on validation; exploratory, not a safety operating point',
            'confidence':threshold,'validation_precision':float(m.box.p_curve.mean(0)[idx]),
            'validation_recall':float(m.box.r_curve.mean(0)[idx]),'validation_f1':float(m.box.f1_curve.mean(0)[idx]),
            'test_used_for_selection':False,'max_det':100,'nms_iou':.45,'imgsz':size}
    (folder/'calibration.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
