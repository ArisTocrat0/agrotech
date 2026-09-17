"""Reproducible CPU microbenchmark; does not claim full pipeline FPS."""
import json
import platform
import random
import sys
from pathlib import Path
from statistics import median
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.domain.types import WeedDetection
from src.vision.nms import nms,kernel


def main():
    if kernel() is None:
        raise RuntimeError('Build C++ NMS first: python scripts/build_native.py')
    rng=random.Random(42)
    detections=[]
    for i in range(1500):
        x,y=rng.randrange(4096),rng.randrange(3072)
        detections.append(WeedDetection(i,str(i%5),'stage',rng.random(),x,y,x+40,y+40))
    timings={}
    expected = nms(detections, backend='python')
    actual = nms(detections, backend='cpp')
    if [id(d) for d in expected] != [id(d) for d in actual]:
        raise RuntimeError('Python and C++ NMS results differ')
    for backend in ['python','cpp']:
        nms(detections,backend=backend)
        samples=[]
        for _ in range(5):
            start=perf_counter();nms(detections,backend=backend);samples.append(perf_counter()-start)
        timings[backend]=median(samples)
    report={'operation':'class-aware NMS only','boxes':1500,'classes':5,'seed':42,
            'native_available':kernel() is not None,'python_seconds':timings['python'],
            'native_seconds':timings['cpp'],'speedup':timings['python']/timings['cpp'],
            'platform':platform.platform(),'scope':'Does not measure DINOv2 or full-frame FPS.'}
    output=Path(__file__).resolve().parents[1]/'artifacts/benchmark_nms.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
