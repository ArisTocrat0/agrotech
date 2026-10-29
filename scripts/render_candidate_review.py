"""Bounded post-lock review sheets; reads cached predictions, never tunes or reruns model."""
import argparse,json,hashlib
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--dataset',required=True);a=p.parse_args();assert a.run.replace('-','').isalnum() and a.dataset.replace('-','').isalnum()
 run=ROOT/'outputs/pilot-training'/a.run;report=json.loads((run/'development-evaluation.json').read_text());manifest=json.loads((ROOT/'datasets'/a.dataset/'manifest.json').read_text());pred=json.loads((run/'quality-evaluation/predictions.json').read_text())['predictions'];threshold=report['threshold'];records=manifest['records'];out=run/'quality-evaluation';selection=[]
 # Fixed hash order within each evaluated positive split, independent of confidence/error.
 for split in sorted({r['split'] for r in records if r['split']!='train'}):
  candidates=[r for r in records if r['split']==split and str(r['image_id']) in pred and r.get('annotation_count',len(r.get('boxes',[])))>0]
  selection+=sorted(candidates,key=lambda r:hashlib.sha256(str(r['image_id']).encode()).hexdigest())[:6]
 truth={}
 for split in {r['split'] for r in selection}:
  for b in json.loads((ROOT/'datasets'/a.dataset/'annotations'/f'{split}.json').read_text())['annotations']:
   x,y,w,h=b['bbox'];truth.setdefault(b['image_id'],[]).append([x,y,x+w,y+h])
 for page in range((len(selection)+5)//6):
  canvas=Image.new('RGB',(1200,900),'white');draw=ImageDraw.Draw(canvas)
  for n,r in enumerate(selection[page*6:page*6+6]):
   im=Image.open(ROOT/'datasets'/a.dataset/r['path']).convert('RGB');d=ImageDraw.Draw(im)
   for box in truth.get(r['image_id'],[]):d.rectangle(box,outline='#00ff66',width=max(2,im.width//500))
   for box in pred[str(r['image_id'])]:
    if box['confidence']>=threshold:d.rectangle(box['bbox'],outline='red',width=max(2,im.width//400))
   im.thumbnail((400,370));x=n%3*400;y=n//3*450;canvas.paste(im,(x,y));draw.text((x+4,y+380),f"{r['image_id']} {r['split']}",fill='black');draw.text((x+4,y+400),'GREEN = label; RED = prediction',fill='black')
  canvas.save(out/f'positive-review-{page}.jpg',quality=85)
 (out/'positive-review-selection.json').write_text(json.dumps({'selection':'sha256(image_id) first six per evaluated non-train positive split; post-lock review only','threshold':threshold,'images':[{'image_id':r['image_id'],'split':r['split'],'path':r['path']} for r in selection]},indent=2))
 print(json.dumps({'review_images':len(selection),'pages':(len(selection)+5)//6}))
if __name__=='__main__':main()
