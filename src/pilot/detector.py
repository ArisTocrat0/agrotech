"""Explicit versioned local models. Native OpenVINO inference; no network calls."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import cv2

class Detector:
    def __init__(self, registry):
        self.registry_sha256=hashlib.sha256(Path(registry).read_bytes()).hexdigest()
        self.registry = json.loads(Path(registry).read_text())
        self.models=[]
        import openvino as ov
        core=ov.Core()
        for spec in self.registry['models']:
            if spec.get('enabled',True) is False:continue
            if not isinstance(spec.get('classes'),list) or not spec['classes'] or any(c not in (None,'trash','fire','smoke','weed') for c in spec['classes']):
                raise ValueError('Неподдерживаемая карта классов модели.')
            path=Path(spec['path'])
            if not path.is_absolute():path=Path(registry).resolve().parents[1]/path
            if not path.is_file(): raise ValueError('Не найдены локальные веса: '+spec['id'])
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != spec['sha256']: raise ValueError('Контрольная сумма модели не совпала: '+spec['id'])
            for extra in spec.get('assets',[]):
                asset=Path(extra['path'])
                if not asset.is_absolute():asset=Path(registry).resolve().parents[1]/asset
                if hashlib.sha256(asset.read_bytes()).hexdigest()!=extra['sha256']:
                    raise ValueError('Контрольная сумма данных модели не совпала.')
            net=core.compile_model(str(path),'CPU',{'INFERENCE_NUM_THREADS':2,'PERFORMANCE_HINT':'LATENCY'})
            self.models.append((spec,net))
        self.metadata={'backend':'OpenVINO native CPU','runtime_version':getattr(ov,'__version__',None),
                       'registry_sha256':self.registry_sha256,'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       'preprocessing':'RGB float32 NCHW / letterbox114 / class NMS before clipping', 'models':[{k:s[k] for k in ('id','sha256','classes','license','scope','imgsz','threshold')} for s,_ in self.models]}

    def detect(self, image):
        rows=[]
        rgb=np.asarray(image)
        for spec,net in self.models:
            size=spec.get('imgsz',640)
            h,w=rgb.shape[:2]; scale=min(size/w,size/h)
            nw,nh=round(w*scale),round(h*scale)
            dx,dy=(size-nw)//2,(size-nh)//2
            canvas=np.full((size,size,3),114,dtype=np.uint8)
            canvas[dy:dy+nh,dx:dx+nw]=cv2.resize(rgb,(nw,nh))
            tensor=np.ascontiguousarray(canvas.transpose(2,0,1)[None],dtype=np.float32)/255.
            output=np.asarray(net(tensor)[net.output(0)])
            if not np.isfinite(output).all():raise ValueError('Модель вернула NaN/Infinity: '+spec['id'])
            # YOLOv8/11 raw output [1,4+C,N], no objectness term.
            if output.ndim!=3 or output.shape[1]!=4+len(spec['classes']):
                raise ValueError('Неподдерживаемая форма выхода '+spec['id']+': '+str(output.shape))
            pred=output[0].T
            scores=pred[:,4:]; ids=scores.argmax(1); conf=scores.max(1)
            keep=np.where(conf>=spec.get('threshold',.35))[0]
            boxes=[]; strengths=[]; labels=[]
            for i in keep:
                cx,cy,bw,bh=pred[i,:4]
                x1=(float(cx-bw/2)-dx)/scale; y1=(float(cy-bh/2)-dy)/scale
                x2=(float(cx+bw/2)-dx)/scale; y2=(float(cy+bh/2)-dy)/scale
                if x1>=x2 or y1>=y2: continue
                boxes.append([x1,y1,x2-x1,y2-y1]);strengths.append(float(conf[i])); labels.append(int(ids[i]))
            for cls in sorted(set(labels)):
                if spec['classes'][cls] is None:continue  # explicitly excluded model class, e.g. person
                subset=[i for i,l in enumerate(labels) if l==cls]
                picks=cv2.dnn.NMSBoxes([boxes[i] for i in subset],[strengths[i] for i in subset],spec.get('threshold',.35),.45)
                for j in np.asarray(picks).reshape(-1):
                    i=subset[int(j)]; x,y,bw,bh=boxes[i]
                    rows.append({'class_name':spec['classes'][cls], 'confidence':strengths[i], 'bbox':[x,y,x+bw,y+bh], 'model_id':spec['id']})
        selected=[]
        for row in sorted(rows,key=lambda r:r['confidence'],reverse=True)[:100]:
            x1,y1,x2,y2=row['bbox']
            row['bbox']=[max(0.,min(float(image.width),x1)),max(0.,min(float(image.height),y1)),
                         max(0.,min(float(image.width),x2)),max(0.,min(float(image.height),y2))]
            if row['bbox'][0]<row['bbox'][2] and row['bbox'][1]<row['bbox'][3]:selected.append(row)
        return selected
