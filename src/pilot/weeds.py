"""Existing offline weed pipeline adapted without treating cosine as probability."""
import hashlib,os,tempfile
from pathlib import Path
class WeedDetector:
    def __init__(self,root):
        os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
        import torch
        torch.set_num_threads(2)
        from ..config import load_config
        from ..recognition.embeddings import DinoEmbeddingModel
        from ..recognition.classifier import ReferenceClassifier
        self.config=load_config(root/'config.yaml');m=self.config['model'];m['batch_size']=4
        self.model=DinoEmbeddingModel(m['name'],'cpu',4,offline=True)
        path=root/'artifacts/reference_index.pt'
        index=torch.load(path,map_location='cpu',weights_only=True)
        self.classifier=ReferenceClassifier(index,self.config['classification']['top_k'],
                                           self.config['classification']['similarity_threshold'],
                                           self.config['classification'].get('category_margin',.05))
        self.metadata={'backend':'Existing DINOv2 reference baseline + C++ NMS','classes':['weed'],
                       'model_name':m['name'],'cached_revision':getattr(getattr(getattr(self.model,'model',None),'config',None),'_commit_hash',None),
                       'similarity_threshold':self.config['classification']['similarity_threshold'],'category_margin':self.config['classification'].get('category_margin',.05),
                       'reference_index_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                       'scope':'Candidate vegetation and reference similarity; field detection quality unmeasured; similarity is not probability'}
    def detect(self,image):
        from ..application.inference import run_inference
        with tempfile.TemporaryDirectory(prefix='ecokineu-weeds-') as d:
            folder=Path(d);path=folder/'input.jpg';image.save(path)
            rows=run_inference(path,folder/'results',self.config,self.model,self.classifier)
            return [{'class_name':'weed','confidence':float(r['similarity_score']),
                     'score_type':'cosine_similarity_not_probability','species':r['species'],'stage':r['stage'],
                     'bbox':[r['bbox'][k] for k in ('x1','y1','x2','y2')],'model_id':'dinov2-reference-baseline'}
                    for r in rows[0]['detections'] if r['kind']=='weed'][:100]
