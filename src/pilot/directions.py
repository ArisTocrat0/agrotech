"""Direction routing. Common is orchestration, never an extra model."""
import copy

DIRECTIONS={'weeds':{'title':'Сорняки','classes':['weed'],'datasets':[]},
 'trash':{'title':'Мусор','classes':['trash'],'datasets':['litter-v3-land','dronewaste-v2-binary-strict','uavvaste-pilot-v1']},
 'fire_smoke':{'title':'Дым и огонь','classes':['fire','smoke'],'datasets':['smoke-pyrosdis-v1','fire-candidates-v1']}}

def detect_direction(app,mode,image,environment):
    requested={'environment':['trash','fire','smoke'],'common':['weed','trash','fire','smoke'],
               **{k:v['classes'] for k,v in DIRECTIONS.items()}}[mode]
    rows=[];models=[];errors={}
    if any(c in requested for c in ('trash','fire','smoke')):
        try:
            # Native adapter skips irrelevant networks before inference.
            from .detector import Detector
            detected=environment.detect(image,allowed_classes=requested) if isinstance(environment,Detector) else environment.detect(image)
            rows.extend(r for r in detected if r['class_name'] in requested)
            for original in environment.metadata.get('models',[]):
                spec=copy.deepcopy(original)
                spec['classes']=[c if c in requested else None for c in spec['classes']]
                if any(spec['classes']):models.append(spec)
        except Exception as exc:
            if mode!='common':raise
            errors['environment']=str(exc)
    if 'weed' in requested:
        try:
            if app.weed_detector is None:
                if hasattr(app,'load_weed_detector'):app.load_weed_detector()
                else:
                    from .weeds import WeedDetector
                    app.weed_detector=WeedDetector(app.root)
            rows.extend(app.weed_detector.detect(image))
            models.append(copy.deepcopy(app.weed_detector.metadata))
        except Exception as exc:
            if mode!='common':raise
            errors['weeds']=str(exc)
    if mode=='weeds':return rows,copy.deepcopy(app.weed_detector.metadata)
    meta={'backend':'Sequential direction orchestration','models':models,'direction':mode,'errors':errors}
    if mode!='weeds':meta['registry_sha256']=getattr(environment,'registry_sha256',None)
    return rows,meta

class UnavailableDetector:
    def __init__(self,error):self.error=error;self.metadata={'models':[]}
    def detect(self,image):raise RuntimeError(self.error)
