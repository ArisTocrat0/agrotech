"""Replay real photographs through the same local HTTP ingest endpoint.

Never assigns coordinates/timestamps. Re-running is idempotent within a mission.
These are public benchmark/demo images, not observations from Kazakhstan.
"""
import argparse,base64,json,time,urllib.request,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def call(base,path,payload=None):
    body=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(base+path,data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
def main():
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8010');p.add_argument('--mission',default='public-demo-2026-10-21');p.add_argument('--weeds',action='store_true');p.add_argument('--piles',action='store_true');a=p.parse_args()
    files=sorted((ROOT/'datasets/fire-candidates-v1/images').glob('*.jpg'))
    files+=sorted((ROOT/'datasets/uavvaste-pilot-v1/images/test').glob('*.jpg'))[:3]
    if a.piles:
        files=sorted((ROOT/'datasets/fire-candidates-v1/images').glob('*.jpg'))+sorted((ROOT/'datasets/dronewaste500-v1/images/test').glob('*.png'))[:3]
    mode='environment'
    if a.weeds:
        files=sorted((ROOT/'data/Сорняки').rglob('*.jpg'))[:1];mode='weeds'
    if not files:raise ValueError('No existing demo photographs')
    ids=[]
    for path in files:
        response=call(a.base,'/api/pilot/photos',{'mission':a.mission,'name':path.name,'analysis_mode':mode,
            'photo':base64.b64encode(path.read_bytes()).decode(),'metadata':{'demo':True,'source_path':str(path.relative_to(ROOT)),
            'notice':'Public example / existing local reference; not a drone observation in Kazakhstan; no GPS invented'}})
        ids.append(response['photo']['id']);print(path.name,'duplicate' if response['duplicate'] else 'accepted',flush=True)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        rows=[r for r in call(a.base,'/api/pilot/photos')['photos'] if r['id'] in ids]
        if len(rows)==len(ids) and all(r['state'] in ('done','error') for r in rows):
            for r in rows:print(r['name'],r['state'],len((r['result'] or {}).get('events',[])),'hypotheses',r.get('error'))
            if any(r['state']=='error' for r in rows):raise RuntimeError('Demo processing failed')
            return
        time.sleep(.5)
    raise TimeoutError('Demo deadline; inspect queue')
if __name__=='__main__':main()
