"""Offline bounded V2 audit/parity/tile experiment. No training, deployment or user-photo tuning."""
import argparse,collections,hashlib,json,math,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_quality_v2 import iou,metrics

def nms_global(rows,threshold=.2):
    import cv2,numpy as np
    if not rows:return []
    boxes=[[r['bbox'][0],r['bbox'][1],r['bbox'][2]-r['bbox'][0],r['bbox'][3]-r['bbox'][1]] for r in rows]
    picks=cv2.dnn.NMSBoxes(boxes,[r['confidence'] for r in rows],threshold,.45)
    return sorted([rows[int(i)] for i in np.asarray(picks).reshape(-1)],key=lambda r:-r['confidence'])[:100]

def tiled(detector,image,size=640,overlap=160):
    def starts(length):
        if length<=size:return [0]
        positions=list(range(0,length-size+1,size-overlap))
        if positions[-1]!=length-size:positions.append(length-size)
        return positions
    rows=[];windows=[];start=time.perf_counter()
    for y in starts(image.height):
        for x in starts(image.width):
            box=(x,y,min(x+size,image.width),min(y+size,image.height));windows.append(box)
            for r in detector.detect(image.crop(box)):
                a,b,c,d=r['bbox'];rows.append({**r,'bbox':[a+x,b+y,c+x,d+y]})
    merged=nms_global(rows)
    return merged,{'seconds':time.perf_counter()-start,'tiles':len(windows),'windows':windows,'detections_before_global_nms':len(rows)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',default='dronewaste-v2-strict-cpu40e-20261020');args=parser.parse_args();assert args.run.replace('-','').isalnum()
    run=ROOT/'outputs/pilot-training'/args.run;out=run/'error-analysis';out.mkdir(exist_ok=True)
    os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(out/'config'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',HF_HUB_OFFLINE='1')
    import cv2,numpy as np,torch
    from PIL import Image,ImageDraw
    from ultralytics import YOLO
    from ultralytics.data.augment import LetterBox
    from ultralytics.utils import torch_utils
    torch_utils.NUM_THREADS=2
    from src.pilot.detector import Detector
    torch.set_num_threads(2)
    dataset=ROOT/'datasets/dronewaste-v2-binary-strict';manifest=json.loads((dataset/'manifest.json').read_text());source=Path(manifest['source_root']);lookup={r['source_image_id']:r for r in manifest['records']}
    report={'scope':'Development error diagnosis only; no independent holdout; no user photos used; no model activation','run':args.run,'threshold_fixed_from_prior_validation':.2,'threads':2,'dataset_sha256':hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest()}
    # Verify the exact derivative fed to training against independently retained COCO.
    conversion=[];size_rows=[];ground_truth={};max_delta=0;overlap_pairs=0;overlap_images=set();total=0
    predictions=json.loads((run/'quality-evaluation/candidate-predictions.json').read_text())
    for split in ('train','val_development','test_development'):
        coco=json.loads((source/'annotations/binary_strict'/f'{split}.json').read_text());anns=collections.defaultdict(list)
        for a in coco['annotations']:anns[a['image_id']].append(a)
        checked=0
        for im in coco['images']:
            record=lookup[im['id']];assert hashlib.sha256((dataset/record['file']).read_bytes()).hexdigest()==record['sha256'];assert record['binary_strict_eligible'] and record['image_role']!='context_only'
            if record['image_role']=='positive':assert record['context_annotation_count']==0
            label=dataset/'labels'/Path(im['file_name']).with_suffix('.txt');actual=[list(map(float,line.split())) for line in label.read_text().splitlines()]
            expected=[];gt=[]
            for a in anns[im['id']]:
                assert a['category_id']==1 and a['source_category_id'] in manifest['source_policy']['pollution_coco_category_ids']
                x,y,w,h=a['bbox'];expected.append([0,(x+w/2)/640,(y+h/2)/640,w/640,h/640]);gt.append([x,y,x+w,y+h])
            assert len(actual)==len(expected)
            if actual:max_delta=max(max_delta,float(np.max(np.abs(np.array(actual)-expected)))*640)
            assert all(a[0]==0 and all(math.isfinite(v) for v in a) for a in actual)
            assert (bool(actual) or record['image_role']=='verified_negative')
            for i,a in enumerate(gt):
                for b in gt[i+1:]:
                    if iou(a,b)>.45:overlap_pairs+=1;overlap_images.add(im['id'])
            total+=len(gt);checked+=1;ground_truth[im['id']]=gt
            if split=='train':continue
            preds=[p for p in predictions[str(im['id'])] if p['confidence']>=.2];used=set()
            for p in sorted(preds,key=lambda p:-p['confidence']):
                score,j=max([(iou(p['bbox'],b),j) for j,b in enumerate(gt) if j not in used],default=(0,None))
                if score>=.5:used.add(j)
            for j,b in enumerate(gt):
                area=(b[2]-b[0])*(b[3]-b[1]);bucket='small_<32px' if area<32**2 else 'medium_32to96px' if area<96**2 else 'large_>=96px'
                raw=predictions[str(im['id'])];best_iou=max((iou(b,p['bbox']) for p in preds),default=0);low=max((p['confidence'] for p in raw if iou(b,p['bbox'])>=.5),default=0)
                reason='matched' if j in used else 'below_fixed_confidence' if 0<low<.2 else 'localization_or_merge' if best_iou>=.1 else 'no_overlapping_detection_at_fixed_threshold'
                size_rows.append({'split':split,'source_image_id':im['id'],'source_category_id':anns[im['id']][j]['source_category_id'],'area_px':area,'short_side_px':min(b[2]-b[0],b[3]-b[1]),'bucket':bucket,'matched':j in used,'reason':reason})
        conversion.append({'split':split,'images_checked':checked,'annotations':sum(map(len,anns.values()))})
    assert max_delta<.001
    report['conversion']={'splits':conversion,'max_roundtrip_pixel_error':max_delta,'class_mapping':'COCO category1 -> YOLO index0 -> model name trash; only policy whitelist','source_gt_pairs_iou_above_nms_045':overlap_pairs,'images_with_gt_overlap_above_045':len(overlap_images),'gt_annotations':total,'note':'Overlapping legitimate targets can compete after binary merging; overlap counts alone do not prove actual NMS losses.'}
    report['object_sizes']={}
    for split in ('val_development','test_development'):
        report['object_sizes'][split]={}
        for bucket in ('small_<32px','medium_32to96px','large_>=96px'):
            rows=[r for r in size_rows if r['split']==split and r['bucket']==bucket]
            report['object_sizes'][split][bucket]={'targets':len(rows),'matched':sum(r['matched'] for r in rows),'recall':sum(r['matched'] for r in rows)/max(1,len(rows)),'miss_reasons':dict(collections.Counter(r['reason'] for r in rows if not r['matched']))}
    (out/'object-errors.json').write_text(json.dumps(size_rows,indent=2))
    spec=json.loads((run/'development-evaluation.json').read_text())['candidate_spec'];spec={**spec,'threshold':.2};reg=out/'candidate-registry.json';reg.write_text(json.dumps({'models':[spec]},indent=2));detector=Detector(reg);pt=YOLO(str(run/'weights/best.pt'));assert pt.names=={0:'trash'};pt.model.eval()
    class Capture:
        def __init__(self,net):self.net=net
        def output(self,i):return self.net.output(i)
        def __call__(self,tensor):self.tensor=tensor.copy();self.result=self.net(tensor);return self.result
    capture=Capture(detector.models[0][1]);detector.models=[(spec,capture)]
    chosen=[]
    for role in ('positive','verified_negative'):
        chosen+=sorted([r for r in manifest['records'] if r['split']=='val_development' and r['image_role']==role],key=lambda r:r['sha256'])[:2]
    uav_manifest=json.loads((ROOT/'datasets/uavvaste-pilot-v1/manifest.json').read_text());uav=sorted([r for r in uav_manifest['records'] if r['split']=='val'],key=lambda r:r['sha256'])
    samples=[(r['file'],Image.open(dataset/r['file']).convert('RGB')) for r in chosen]
    samples +=[(r['file'],Image.open(ROOT/'datasets/uavvaste-pilot-v1'/r['file']).convert('RGB')) for r in uav[:2]]
    # Non-empty-output controls verify real post-NMS coordinates, not sample accuracy.
    evaluation=json.loads((run/'development-evaluation.json').read_text())
    controls=[max(evaluation['test_development']['per_image'],key=lambda r:r['tp']),max(evaluation['val_development']['per_image'],key=lambda r:r['fp'])]
    for item in controls:
        record=lookup[item['id']];samples.append(('post_nms_control/'+record['file'],Image.open(dataset/record['file']).convert('RGB')))
    # Odd non-square resize fixture checks transform mechanics only, not recognition quality.
    samples.append(('transform_fixture_public_resize_701x433',samples[-2][1].resize((701,433))))
    report['parity_sampling']='Four hash-selected V2 validation images, two hash-selected prior UAV validation images, two explicitly selected non-empty-output development controls, one artificial non-square resize of a public control; no recognition accuracy claim.'
    parity=[]
    for name,image in samples:
        actual=detector.detect(image);expected_array=LetterBox(new_shape=(640,640),auto=False,scale_fill=False,scaleup=True,stride=32)(image=np.asarray(image));tensor=np.ascontiguousarray(expected_array.transpose(2,0,1)[None],dtype=np.float32)/255
        pixel_error=float(np.max(np.abs(capture.tensor-tensor)));assert pixel_error==0
        with torch.inference_mode():raw=pt.model(torch.from_numpy(tensor));raw=raw[0] if isinstance(raw,(tuple,list)) else raw;raw=raw.cpu().numpy()
        native=np.asarray(capture.result[capture.output(0)]);assert raw.shape==native.shape==(1,5,8400)
        coord_error=float(np.max(np.abs(raw[:,:4]-native[:,:4])));score_error=float(np.max(np.abs(raw[:,4:]-native[:,4:])))
        official=pt.predict(source=image,imgsz=640,rect=False,conf=.2,iou=.45,max_det=100,device='cpu',verbose=False)[0];expected=[{'bbox':b.xyxy[0].tolist(),'confidence':float(b.conf.item())} for b in official.boxes]
        remaining=list(expected);box_error=score_post=0.
        for row in actual:
            if not remaining:box_error=999;break
            error,j,b=min((float(np.max(np.abs(np.array(row['bbox'])-b['bbox']))),j,b) for j,b in enumerate(remaining));remaining.pop(j);box_error=max(box_error,error);score_post=max(score_post,abs(row['confidence']-b['confidence']))
        assert coord_error<.05 and score_error<.0001 and len(actual)==len(expected) and not remaining and box_error<.75 and score_post<.003,'Adapter parity contract failed'
        parity.append({'image':name,'width':image.width,'height':image.height,'input_tensor_max_abs_error':pixel_error,'raw_coordinate_max_abs_error_px':coord_error,'raw_score_max_abs_error':score_error,'native_detections':len(actual),'pytorch_official_detections':len(expected),'post_nms_bbox_max_abs_error_px':box_error,'post_nms_score_max_abs_error':score_post,'remaining_unmatched':len(remaining),'raw_finite':bool(np.isfinite(native).all()),'torch_threads_actual':torch.get_num_threads()})
        print('PARITY',json.dumps(parity[-1]),flush=True)
    report['pytorch_openvino_parity']=parity
    # Fixed four public validation frames, selected before inference by hash, native exported dimensions.
    tiles=[];tile_preds={};full_preds={};tile_rows=[]
    for n,r in enumerate(uav[:4]):
        image=Image.open(ROOT/'datasets/uavvaste-pilot-v1'/r['file']).convert('RGB');label=ROOT/'datasets/uavvaste-pilot-v1/labels'/Path(r['file']).relative_to('images').with_suffix('.txt');gt=[]
        for line in label.read_text().splitlines():
            _,cx,cy,w,h=map(float,line.split());gt.append([(cx-w/2)*image.width,(cy-h/2)*image.height,(cx+w/2)*image.width,(cy+h/2)*image.height])
        start=time.perf_counter();full=detector.detect(image);full_seconds=time.perf_counter()-start;merged,info=tiled(detector,image)
        sample={'source_image_id':n,'image_role':'positive','gt':gt,'path':r['file'],'site':r['batch'],'split':'prior_exposed_val_development'};tile_rows.append(sample);full_preds[str(n)]=full;tile_preds[str(n)]=merged
        canvas=image.copy();draw=ImageDraw.Draw(canvas)
        for box in gt:draw.rectangle(box,outline='#00ff55',width=4)
        for row in merged:draw.rectangle(row['bbox'],outline='#ff3322',width=2)
        draw.text((5,5),'PUBLIC DEVELOPMENT DIAGNOSTIC / red: tiled candidate / green: source target',fill='white',stroke_width=1,stroke_fill='black')
        canvas.save(out/f'tiled-case-{n}.jpg')
        tiles.append({'image':r['file'],'sha256':r['sha256'],'width':image.width,'height':image.height,'targets':len(gt),'full_seconds':full_seconds,'full_detections':len(full),'tiled_detections':len(merged),**info});print('TILES',json.dumps(tiles[-1]),flush=True)
    report['tiled_experiment']={'policy':'fixed640px tiles,160px requested overlap, full border coverage, global class NMS0.45, confidence0.20; no user-photo or parameter tuning','scope':'Four hash-selected public UAVVaste validation images previously exposed; diagnostic only, not independent evaluation. Edge windows can overlap more than160px.','images':tiles,'full_metrics':metrics(tile_rows,full_preds,.2),'tiled_metrics':metrics(tile_rows,tile_preds,.2),'no_clean_negative_big_photo_set':True,'not_integrated_in_live_app':True}
    (out/'tile-predictions.json').write_text(json.dumps({'full':full_preds,'tiled':tile_preds},indent=2))
    report['weights_sha256']=hashlib.sha256((run/'weights/best.pt').read_bytes()).hexdigest();report['active_registry_sha256']=hashlib.sha256((ROOT/'artifacts/ecokineu-models.json').read_bytes()).hexdigest()
    (out/'analysis.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print('SAVED',out/'analysis.json',flush=True)
if __name__=='__main__':main()
