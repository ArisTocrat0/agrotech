"""Retrain a versioned reference head from unchanged, SHA-verified local photos."""
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    import torch
    torch.set_num_threads(2)
    from src.recognition.autolearn import train_head,split_records
    index=torch.load(ROOT/'artifacts/reference_index.pt',weights_only=True,map_location='cpu')
    records=index['metadata']['records']
    for r in records:
        if hashlib.sha256(Path(r['image_path']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Photo changed; rebuild embeddings explicitly')
    run=ROOT/'artifacts/weed-runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');run.mkdir(parents=True)
    classifier=train_head(index,run/'classifier.pt');train,val,test,excluded=split_records(records)
    (run/'report.json').write_text(json.dumps(classifier.report,ensure_ascii=False,indent=2))
    (run/'split-manifest.json').write_text(json.dumps({'scope':'Reference photo classification; no field detection metric',
        'reference_index_sha256':hashlib.sha256((ROOT/'artifacts/reference_index.pt').read_bytes()).hexdigest(),
        'split':{k:[{a:records[i][a] for a in ('sha256','species','stage','kind')} for i in ids] for k,ids in [('train',train),('validation',val),('test',test)]}},ensure_ascii=False,indent=2))
    print(run);print(json.dumps(classifier.report,ensure_ascii=False))
if __name__=='__main__':main()
