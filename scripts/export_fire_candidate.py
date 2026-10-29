"""Convert pinned external checkpoint using weights_only and trusted class allowlist.

Never calls torch.load(weights_only=False) or executes checkpoint-supplied code.
The production worker uses only the exported safe-format IR.
"""
import hashlib,importlib,inspect,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    os.environ.update(YOLO_OFFLINE='true',YOLO_AUTOINSTALL='false',YOLO_CONFIG_DIR=str(ROOT/'outputs/pilot-export-config'))
    import torch
    torch.set_num_threads(2)
    from ultralytics import YOLO
    folder=ROOT/'artifacts/fire-candidate-v6';path=folder/'best.pt'
    manifest=json.loads((folder/'SOURCE.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('Checkpoint hash mismatch')
    safe=[]
    for name in torch.serialization.get_unsafe_globals_in_checkpoint(path):
        module,attr=name.rsplit('.',1)
        if not module.startswith(('ultralytics.nn.','torch.nn.modules.')):raise ValueError('Untrusted checkpoint global: '+name)
        obj=getattr(importlib.import_module(module),attr)
        if not inspect.isclass(obj) or not issubclass(obj,torch.nn.Module):raise ValueError('Only known module classes allowed: '+name)
        safe.append((obj,name))
    with torch.serialization.safe_globals(safe):checkpoint=torch.load(path,map_location='cpu',weights_only=True)
    model=checkpoint.get('ema') or checkpoint['model']
    model.task='detect';model.pt_path=str(path)
    print('Safe-loaded classes:',model.names,flush=True)
    wrapper=YOLO('yolov8s.yaml',task='detect');wrapper.model=model.float().eval();wrapper.task='detect'
    print(wrapper.export(format='openvino',imgsz=640,half=False,int8=False,dynamic=False,batch=1,device='cpu'))
    manifest['conversion']={'loader':'torch weights_only=True; explicit trusted nn.Module classes only','globals':list(torch.serialization.get_unsafe_globals_in_checkpoint(path)),'classes':model.names,'runtime':'Exported OpenVINO IR only'}
    (folder/'SOURCE.json').write_text(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
