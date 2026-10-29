"""Four in-memory training steps per mode on two public train photos. Discard all modified weights."""
import argparse,json,os,resource,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--freeze',type=int,choices=[0,10]);args=p.parse_args();run=ROOT/'outputs/pilot-training/dronewaste-v2-strict-cpu40e-20261020';out=run/'error-analysis'
    if args.freeze is None:
        results=[]
        for mode in (10,0):
            proc=subprocess.run([str(ROOT/'.venv/bin/python'),str(Path(__file__).resolve()),'--freeze',str(mode)],cwd=ROOT,capture_output=True,text=True,check=False,timeout=180)
            if proc.returncode:raise RuntimeError(proc.stderr[-4000:])
            line=next(s for s in proc.stdout.splitlines() if s.startswith('MICROBENCH '));results.append(json.loads(line[len('MICROBENCH '):]))
        report={'scope':'In-memory 4 steps/mode; first warmup excluded; batch2 fixed public train images, no augmentation/dataloader/validation/export; no weights saved or activated. Not a training run or accuracy evaluation.','modes':results,'step_time_ratio_unfrozen_to_frozen':results[1]['median_step_seconds']/results[0]['median_step_seconds']}
        (out/'unfreeze-microbenchmark.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return
    os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(out/'micro-config'),OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',HF_HUB_OFFLINE='1')
    import numpy as np,torch
    from PIL import Image
    from ultralytics import YOLO
    from ultralytics.cfg import get_cfg
    torch.set_num_threads(2);torch.manual_seed(42)
    dataset=ROOT/'datasets/dronewaste-v2-binary-strict';manifest=json.loads((dataset/'manifest.json').read_text());rows=sorted([r for r in manifest['records'] if r['split']=='train' and r['image_role']=='positive'],key=lambda r:r['sha256'])[:2]
    images=[];classes=[];boxes=[];indices=[]
    for i,r in enumerate(rows):
        images.append(np.asarray(Image.open(dataset/r['file']).convert('RGB')).transpose(2,0,1))
        for line in (dataset/'labels'/Path(r['file']).relative_to('images').with_suffix('.txt')).read_text().splitlines():
            c,*b=map(float,line.split());classes.append([c]);boxes.append(b);indices.append(i)
    batch={'img':torch.from_numpy(np.ascontiguousarray(np.stack(images))).float()/255,'cls':torch.tensor(classes),'bboxes':torch.tensor(boxes),'batch_idx':torch.tensor(indices)}
    wrapper=YOLO(str(run/'weights/best.pt'));model=wrapper.model;model.args=get_cfg(overrides=wrapper.ckpt.get('train_args') or model.args);model.train();frozen=tuple(f'model.{n}.' for n in range(args.freeze))
    for name,param in model.named_parameters():param.requires_grad_(not name.startswith(frozen) and '.dfl.' not in name)
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.0001)
    samples=[]
    for step in range(4):
        start=time.perf_counter();optimizer.zero_grad(set_to_none=True);loss,_=model.loss(batch);loss.sum().backward();optimizer.step();samples.append(time.perf_counter()-start)
    print('MICROBENCH '+json.dumps({'freeze':args.freeze,'batch':2,'imgsz':640,'torch_threads':torch.get_num_threads(),'optimizer':'AdamW','samples_seconds':samples,'median_step_seconds':statistics.median(samples[1:]),'peak_process_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad),'source_public_train_photos':[r['file'] for r in rows],'weights_discarded':True}),flush=True)
if __name__=='__main__':main()
