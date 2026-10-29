"""Two public qualitative samples, never an independent accuracy estimate."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    from PIL import Image
    from src.pilot.detector import Detector
    folder=ROOT/'artifacts/fire-candidate-v6/best_openvino_model';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    spec={'id':'fire-v6-candidate','path':str(folder/'best.xml'),'sha256':sha(folder/'best.xml'),
          'assets':[{'path':str(folder/'best.bin'),'sha256':sha(folder/'best.bin')}],'classes':['fire',None,'smoke'],
          'imgsz':640,'threshold':.35,'license':'Weights CC BY 2.0; Ultralytics AGPL-3.0','scope':'Candidate, no accuracy claim'}
    registry=ROOT/'outputs/fire-candidate-registry.json';registry.write_text(json.dumps({'models':[spec]}));d=Detector(registry);rows=[]
    for path in sorted((ROOT/'datasets/fire-candidates-v1/images').glob('*.jpg')):
        pred=d.detect(Image.open(path).convert('RGB'));rows.append({'image':path.name,'detections':pred});print(path.name,pred)
    report={'scope':'Qualitative examples only, unlabelled, may overlap unknown model training; not accuracy metrics','results':rows}
    (ROOT/'artifacts/fire_candidate_check.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
