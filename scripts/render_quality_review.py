"""Render local, explicitly labelled candidate diagnostics; never changes originals or labels."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    from PIL import Image,ImageDraw,ImageOps
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();assert a.run.replace('-','').isalnum()
    run=ROOT/'outputs/pilot-training'/a.run;report=json.loads((run/'development-evaluation.json').read_text());out=run/'quality-evaluation';threshold=report['threshold']
    src=Path(json.loads((ROOT/'datasets/dronewaste-v2-binary-strict/manifest.json').read_text())['source_root']);records=[json.loads(s) for s in (src/'manifest.jsonl').read_text().splitlines()];lookup={r['source_image_id']:r for r in records};pred=json.loads((out/'candidate-predictions.json').read_text());gt={}
    for split in ('val_development','test_development'):
        for box in json.loads((src/'annotations/binary_strict'/f'{split}.json').read_text())['annotations']:
            x,y,w,h=box['bbox'];gt.setdefault(box['image_id'],[]).append([x,y,x+w,y+h])
    def annotated(image_id,ground_truth=False):
        image=Image.open(src/lookup[image_id]['path']).convert('RGB');draw=ImageDraw.Draw(image)
        if ground_truth:
            for box in gt.get(image_id,[]):draw.rectangle(box,outline='#00dd66',width=3)
        for box in pred[str(image_id)]:
            if box['confidence']>=threshold:
                draw.rectangle(box['bbox'],outline='#ff3322',width=3);draw.text(box['bbox'][:2],f"{box['confidence']:.2f}",fill='white',stroke_width=1,stroke_fill='black')
        return image
    groups={
        'positive-misses':([r['id'] for r in sorted(report['test_development']['per_image'],key=lambda r:-r['fn']) if r['gt']][:6],True),
        'stone-soil-road':([r['source_image_id'] for r in report['diagnostics']['stone_soil_road_examples']],False),
        'positive-matches':([r['id'] for r in sorted(report['test_development']['per_image'],key=lambda r:-r['tp']) if r['tp']][:6],True)}
    for name,(ids,show_gt) in groups.items():
        for start in range(0,len(ids),6):
            canvas=Image.new('RGB',(960,770),'white');draw=ImageDraw.Draw(canvas)
            draw.text((8,8),'DEVELOPMENT ONLY / red: candidate / green: source target annotation',fill='black')
            for n,key in enumerate(ids[start:start+6]):
                r=lookup[key];image=annotated(key,show_gt).resize((320,320));x=n%3*320;y=n//3*370+30;canvas.paste(image,(x,y));draw.text((x+4,y+323),r['source_file_name']+' / '+r['split'],fill='black')
            canvas.save(out/f'{name}-{start//6}.jpg')
    operator=[]
    for item in report.get('operator_diagnostics',[]):
        image=ImageOps.exif_transpose(Image.open(ROOT/'outputs/pilot'/item['photo_id']/'original')).convert('RGB');draw=ImageDraw.Draw(image);boxes=[b for b in item['candidate_predictions_at_min_threshold'] if b['confidence']>=threshold]
        for box in boxes:
            draw.rectangle(box['bbox'],outline='#ff3322',width=3);draw.text(box['bbox'][:2],f"candidate {box['confidence']:.2f}",fill='white',stroke_width=1,stroke_fill='black')
        path=out/(item['photo_id']+'-operator-candidate.jpg');image.save(path)
        operator.append({'photo_id':item['photo_id'],'candidate_detections':len(boxes),'threshold':threshold,'evidence':str(path.relative_to(ROOT)),'scope':'unlabelled local diagnostic; not training or independent evaluation'})
    (out/'operator-review.json').write_text(json.dumps(operator,indent=2));print(json.dumps({'output':str(out),'operator':operator},indent=2))
if __name__=='__main__':main()
