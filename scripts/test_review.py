"""Offline tests for crop/weed separation, review persistence and crop-row geometry."""
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch
from PIL import Image,ImageDraw
from src.domain.types import WeedDetection
from src.domain.agronomy import assessment, plant_info
from src.vision.nms import nms, kernel
from src.vision.rows import estimate_rows
from src.vision.vegetation import VegetationDetector
from src.config import load_config
from src.infrastructure.exporters import image_result,save_results
from src.application.review import load_results,save_decision,save_geometry
from src.recognition.classifier import ReferenceClassifier


class ReviewTests(unittest.TestCase):
    def test_native_matches_python(self):
        rng=random.Random(42)
        detections=[]
        for i in range(400):
            x,y=rng.randrange(200),rng.randrange(200)
            detections.append(WeedDetection(i,str(i%3),'stage',rng.random(),x,y,x+rng.randrange(1,80),y+rng.randrange(1,80)))
        for threshold in [0,.4,1]:
            expected=nms(detections,threshold,backend='python')
            actual=nms(detections,threshold)
            self.assertEqual([(d.x1,d.y1,d.similarity_score) for d in expected],[(d.x1,d.y1,d.similarity_score) for d in actual])

    def test_crop_ambiguity_and_counts(self):
        index={'embeddings':torch.tensor([[1.,0.],[0.,1.]]),'metadata':{'records':[
            {'species':'Пшеница','stage':'Всходы','kind':'crop'},
            {'species':'Пырей ползучий','stage':'Розетка','kind':'weed'}]}}
        classifier=ReferenceClassifier(index,top_k=1)
        out=classifier.classify(torch.tensor([[1.,0.],[0.,1.],[.7,.7]]))
        self.assertEqual([row[0] for row in out],['Пшеница','Пырей ползучий','unknown'])
        row=image_result('field.jpg',100,100,[WeedDetection(1,'Пшеница','Всходы',.8,0,0,20,20,'crop'),
                                              WeedDetection(2,'Пырей ползучий','Розетка',.8,20,20,40,40)])
        self.assertEqual((row['crop_count'],row['total_weeds']),(1,1))

    def test_decision_persists_and_does_not_modify_prediction(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            save_results([image_result('field.jpg',100,100,[WeedDetection(1,'Пырей ползучий','Розетка',.8,0,0,20,20)])],folder)
            before=(folder/'results.json').read_bytes()
            result=save_decision(folder,0,1,'crop')[0]
            self.assertEqual(result['total_weeds'],0)
            self.assertEqual(result['crop_count'],1)
            self.assertEqual(result['detections'][0]['species'],'unknown')
            self.assertEqual(result['detections'][0]['prediction']['species'],'Пырей ползучий')
            self.assertEqual(load_results(folder)[0]['detections'][0]['review'],'crop')
            self.assertEqual((folder/'results.json').read_bytes(),before)
            with self.assertRaises(ValueError): save_decision(folder,0,100,'weed')
            with self.assertRaises(ValueError): save_decision(folder,-1,1,'weed')
            with self.assertRaises(ValueError): save_decision(folder,0,1,'execute')
            result=save_decision(folder,0,1,'weed')[0]
            self.assertEqual(result['total_weeds'],1)
            self.assertEqual(result['detections'][0]['species'],'Пырей ползучий')

    def test_density_boundaries_and_missing_scale(self):
        annual={'kind':'weed','lifecycle':'annual','stage':'4-6 листьев'}
        for n,level in [(5,'low'),(6,'medium'),(15,'medium'),(16,'high')]:
            self.assertEqual(assessment([annual]*n,100,100,1)['level'],level)
        self.assertEqual(assessment([{'kind':'weed','lifecycle':'perennial'}]*2,100,100,1)['level'],'critical')
        self.assertEqual(assessment([annual],100,100)['level'],'scale_required')
        self.assertIsNone(assessment([annual],100,100)['area_m2'])
        with self.assertRaises(ValueError): assessment([],100,100,float('nan'))

    def test_rows_and_scale_persistence(self):
        image=Image.new('RGB',(600,600),(90,60,40))
        draw=ImageDraw.Draw(image)
        for x in [80,180,280,380,480]: draw.rectangle((x,0,x+8,599),fill=(40,190,40))
        detector=VegetationDetector(load_config()['vegetation'])
        rows=estimate_rows(image,detector)
        self.assertEqual(rows['count'],5)
        self.assertIsNone(estimate_rows(Image.new('RGB',(600,600),'black'),detector)['count'])
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'input').mkdir();image.save(folder/'input/field.png')
            save_results([image_result('field.png',600,600,[])],folder)
            result=save_geometry(folder,0,1)[0]
            self.assertEqual(result['rows']['count'],5)
            self.assertEqual(result['agronomy']['area_m2'],36)
            self.assertEqual(load_results(folder)[0]['gsd_cm'],1)


if __name__=='__main__': unittest.main(verbosity=2)
