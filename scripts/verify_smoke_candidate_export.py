"""Candidate-only PyTorch/OpenVINO parity on calibration images; never uses holdout/user photos."""
import argparse,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();assert a.run.replace('-','').isalnum();run=ROOT/'outputs/pilot-training'/a.run
    os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(run/'parity-config'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',HF_HUB_OFFLINE='1')
    import numpy as np,torch
    from PIL import Image
    from ultralytics import YOLO
    from ultralytics.data.augment import LetterBox
    from ultralytics.utils import torch_utils,nms,ops
    from src.pilot.detector import Detector
    torch.set_num_threads(2);torch_utils.NUM_THREADS=2
    dataset=ROOT/'datasets/smoke-pyrosdis-v1';records=json.loads((dataset/'manifest.json').read_text())['records'];evaluation=json.loads((run/'development-evaluation.json').read_text());spec=evaluation['candidate_spec'];threshold=evaluation['threshold']
    reg=run/'quality-evaluation/registry.json';detector=Detector(reg);detector.models[0][0]['threshold']=threshold
    pt=YOLO(str(run/'weights/best.pt'));assert pt.names=={0:'smoke'};pt.model.eval()
    class Capture:
        def __init__(self,net):self.net=net
        def output(self,i):return self.net.output(i)
        def __call__(self,x):self.tensor=x.copy();self.result=self.net(x);return self.result
    capture=Capture(detector.models[0][1]);detector.models=[(detector.models[0][0],capture)]
    selected=sorted([r for r in records if r['split']=='val'],key=lambda r:r['sha256'])[:3]
    # Add nonempty controls selected solely from the already-consumed calibration output.
    cohorts=evaluation['cohorts'];ids=[max(cohorts['val']['candidate']['per_image'],key=lambda r:r['tp'])['id'],max(cohorts['val']['candidate']['per_image'],key=lambda r:r['fp'])['id']]
    selected+=[next(r for r in records if r['image_id']==i) for i in ids];rows=[]
    for record in selected:
        assert record['split'] in ('val',)
        path=dataset/record['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256'];image=Image.open(path).convert('RGB');actual=detector.detect(image)
        expected_image=LetterBox(new_shape=(640,640),auto=False,scale_fill=False,scaleup=True,stride=32)(image=np.asarray(image));tensor=np.ascontiguousarray(expected_image.transpose(2,0,1)[None],dtype=np.float32)/255
        pixel=float(np.max(np.abs(tensor-capture.tensor)));assert pixel==0
        with torch.inference_mode():raw=pt.model(torch.from_numpy(tensor));raw=raw[0] if isinstance(raw,(tuple,list)) else raw;raw=raw.cpu().numpy()
        native=np.asarray(capture.result[capture.output(0)]);assert raw.shape==native.shape==(1,5,8400) and np.isfinite(native).all()
        coord=float(np.max(np.abs(raw[:,:4]-native[:,:4])));score=float(np.max(np.abs(raw[:,4:]-native[:,4:])))
        post=nms.non_max_suppression(torch.from_numpy(raw.copy()),conf_thres=threshold,iou_thres=.45,max_det=100,nc=1)[0]
        gain=min(640/image.width,640/image.height);pad=((640-round(image.width*gain))//2,(640-round(image.height*gain))//2)
        original_boxes=ops.scale_boxes((640,640),post[:,:4].clone(),(image.height,image.width),ratio_pad=((gain,gain),pad))
        remaining=[{'bbox':box.tolist(),'confidence':float(post[i,4].item())} for i,box in enumerate(original_boxes)];count=len(remaining);box_error=post_score=0.
        assert len(actual)==count,'NMS counts differ'
        for item in actual:
            error,j,b=min((float(np.max(np.abs(np.array(item['bbox'])-b['bbox']))),j,b) for j,b in enumerate(remaining));remaining.pop(j);box_error=max(box_error,error);post_score=max(post_score,abs(item['confidence']-b['confidence']))
        # Reference uses the actual LetterBox ratio/padding, avoiding default inverse-rounding ambiguity.
        assert coord<.05 and score<.0001 and box_error<.75 and post_score<.003
        rows.append({'image':record['path'],'role':'calibration transform/control, not holdout or accuracy sample','input_tensor_max_error':pixel,'raw_coordinate_max_error_px':coord,'raw_score_max_error':score,'detections_compared':count,'post_nms_bbox_max_error_original_px':box_error,'post_nms_score_max_error':post_score,'reference_inverse':'Ultralytics scale_boxes with exact actual LetterBox ratio_pad','torch_threads':torch.get_num_threads(),'passed':True})
    report={'passed':True,'run':a.run,'scope':'Implementation parity only; calibration samples, no holdout/user-photo selection','best_pt_sha256':hashlib.sha256((run/'weights/best.pt').read_bytes()).hexdigest(),'xml_sha256':spec['sha256'],'threshold':threshold,'images':rows}
    (run/'candidate-parity.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
