"""Same-image before/after latency and C++ parity. Never a recognition-quality estimate."""
import argparse,hashlib,importlib.util,json,statistics,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-ref',required=True,help='Local git revision containing the previous detector adapter')
    p.add_argument('--repeats',type=int,default=5)
    p.add_argument('--output',type=Path,default=ROOT/'outputs/directions/benchmark.json')
    args=p.parse_args()
    if not 3<=args.repeats<=20:p.error('repeats must be between 3 and 20')
    import numpy as np
    from PIL import Image
    sys.path.insert(0,str(ROOT))
    from src.pilot.detector import Detector
    baseline=subprocess.run(['git','show',args.baseline_ref+':src/pilot/detector.py'],cwd=ROOT,capture_output=True)
    if baseline.returncode:raise RuntimeError('Baseline detector is unavailable in that revision; choose a local pre-change commit.')
    registry=ROOT/'artifacts/ecokineu-models.json'
    images=sorted((ROOT/'datasets/fire-candidates-v1/images').glob('*.jpg'))[:2]
    images+=sorted((ROOT/'datasets/uavvaste-pilot-v1/images/test').glob('*.jpg'))[:1]
    if not images:raise RuntimeError('No local control images. Restore the saved datasets; no download is attempted.')
    rows=[];cpp={}
    with tempfile.TemporaryDirectory(prefix='agrotech-benchmark-') as temporary:
        temporary=Path(temporary);source=temporary/'before.py';source.write_bytes(baseline.stdout)
        module_spec=importlib.util.spec_from_file_location('agrotech_baseline_detector',source)
        module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
        before=module.Detector(registry);after=Detector(registry)
        for path in images:
            image=Image.open(path).convert('RGB');expected=before.detect(image);actual=after.detect(image)
            if expected!=actual:raise RuntimeError('Detection regression: '+str(path))
            samples={'before':[],'after':[]}
            for repeat in range(args.repeats):
                order=[('before',before),('after',after)]
                if repeat%2:order.reverse()
                for label,detector in order:
                    started=time.perf_counter();detector.detect(image);samples[label].append((time.perf_counter()-started)*1000)
            rows.append({'image':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'before_ms':statistics.median(samples['before']),'after_ms':statistics.median(samples['after']),
                         'detections_identical':True})
        binary=ROOT/'artifacts/native/infer_openvino'
        if not binary.is_file():cpp={'status':'unavailable','reason':'Build scripts/build_openvino.py first; no Python substitute reported as C++.'}
        elif not after.models:cpp={'status':'unavailable','reason':'No enabled local models.'}
        else:
            spec,net=after.models[0];size=spec.get('imgsz',640)
            image=Image.open(images[0]).convert('RGB').resize((size,size))
            tensor=np.ascontiguousarray(np.asarray(image).transpose(2,0,1)[None],dtype=np.float32)/255
            expected=net(tensor)[net.output(0)].copy();samples=[]
            for _ in range(args.repeats):
                started=time.perf_counter();net(tensor);samples.append((time.perf_counter()-started)*1000)
            tensor.tofile(temporary/'input.f32');model=Path(spec['path']);model=model if model.is_absolute() else ROOT/model
            command=[str(binary),str(model),str(temporary/'input.f32'),str(temporary/'output.f32'),str(args.repeats)]
            result=subprocess.run(command,capture_output=True,text=True,check=True)
            cpp=json.loads(result.stdout);actual=np.fromfile(temporary/'output.f32',dtype=np.float32).reshape(expected.shape)
            cpp.update(max_abs_error=float(np.max(np.abs(expected-actual))),parity=bool(np.allclose(expected,actual,rtol=1e-4,atol=1e-4)),python_api_same_tensor_ms=statistics.median(samples))
            if not cpp['parity']:raise RuntimeError('C++ raw-output parity failed')
        report={'scope':'Latency/output regression only; not independent recognition accuracy. Decode excluded. CPU 2 threads.',
                'baseline_ref':args.baseline_ref,'baseline_adapter_sha256':hashlib.sha256(baseline.stdout).hexdigest(),
                'repeats':args.repeats,'images':rows,'cpp':cpp,'models':after.metadata,
                'note':'Small samples and CPU contention cannot establish a general speedup. Same-size tensor reuse needs multiple accepted networks.'}
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
        print(json.dumps({'report':str(args.output),'images':rows,'cpp':cpp},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
