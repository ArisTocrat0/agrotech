"""Real model benchmark and Python/C++ output parity, with no accuracy claim."""
import json,os,statistics,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    import numpy as np
    import openvino as ov
    from PIL import Image
    from src.pilot.detector import Detector
    registry=ROOT/'artifacts/ecokineu-models.json';model=Detector(registry)
    images=sorted((ROOT/'datasets/fire-candidates-v1/images').glob('*.jpg'))
    images+=sorted((ROOT/'datasets/uavvaste-pilot-v1/images/test').glob('*.jpg'))[:3]
    images+=sorted((ROOT/'datasets/dronewaste500-v1/images/test').glob('*.png'))[:3]
    rows=[]
    for path in images:
        image=Image.open(path).convert('RGB');model.detect(image);samples=[];detections=[]
        for _ in range(3):
            start=time.perf_counter();detections=model.detect(image);samples.append(time.perf_counter()-start)
        rows.append({'image':str(path.relative_to(ROOT)),'width':image.width,'height':image.height,
                     'median_decode_excluded_seconds':statistics.median(samples),'detections':detections,
                     'scope':'Real inference, not manually labelled quality evaluation'})
    spec,net=model.models[0]
    size=spec.get('imgsz',640)
    # Deterministic tensor derived from a real photo, same exact input for C++ and Python.
    image=Image.open(images[0]).convert('RGB').resize((size,size))
    tensor=np.ascontiguousarray(np.asarray(image).transpose(2,0,1)[None],dtype=np.float32)/255
    output=net(tensor)[net.output(0)]
    python_native=[]
    for _ in range(5):
        started=time.perf_counter();net(tensor);python_native.append((time.perf_counter()-started)*1000)
    with tempfile.TemporaryDirectory(prefix='ecokineu-cpp-') as d:
        source=Path(d)/'input.f32';target=Path(d)/'output.f32';tensor.tofile(source)
        path=Path(spec['path']);path=path if path.is_absolute() else ROOT/path
        cpp=json.loads(subprocess.check_output([str(ROOT/'artifacts/native/infer_openvino'),str(path),str(source),str(target),'5']))
        actual=np.fromfile(target,dtype=np.float32).reshape(output.shape)
        error=float(np.max(np.abs(output-actual)))
        if not np.allclose(output,actual,rtol=1e-4,atol=1e-4):raise ValueError('C++ output differs from Python API')
    report={'scope':'Actual local CPU model timing. Does not include drone/network. No recognition quality claim.',
            'models':model.metadata,'images':rows,'cpp':cpp,'python_cpp_max_abs_error':error,
            'cpp_parity_passed':True,'cpu_threads':2,'python_api_same_tensor_median_inference_ms':statistics.median(python_native),
            'timing_note':'C++ vs Python API use the same first model/tensor/threads; full image rows include all models and preprocessing/NMS'}
    (ROOT/'artifacts/pilot_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
