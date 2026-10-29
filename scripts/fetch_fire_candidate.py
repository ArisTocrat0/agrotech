"""Restore pinned CC BY 2.0 fire checkpoint; no activation or unsafe deserialization."""
import hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    folder=ROOT/'artifacts/fire-candidate-v6';source=json.loads((folder/'SOURCE.json').read_text());path=folder/'best.pt'
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']:print('Already verified');return
    with urllib.request.urlopen(source['url'],timeout=60) as r:data=r.read(30_000_001)
    if len(data)>30_000_000 or hashlib.sha256(data).hexdigest()!=source['sha256']:raise ValueError('Checkpoint size/hash mismatch')
    path.write_bytes(data);print('Pinned checkpoint verified. Convert with export_fire_candidate.py using weights_only.')
if __name__=='__main__':main()
