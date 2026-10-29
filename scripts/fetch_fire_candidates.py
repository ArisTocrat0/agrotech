"""Restore the two pinned, unlabelled public fire examples with checksum checks."""
import hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    folder=ROOT/'datasets/fire-candidates-v1';manifest=json.loads((folder/'manifest.json').read_text())
    for row in manifest['records']:
        path=folder/row['file'];path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']:continue
        req=urllib.request.Request(row['download_url'],headers={'User-Agent':'EcokineuLocalPilot/0.1 (research dataset attribution)'})
        with urllib.request.urlopen(req,timeout=40) as r:data=r.read(5_000_001)
        if len(data)>5_000_000 or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Pinned image changed; review source before replacement')
        path.write_bytes(data);print(row['file'],'verified')
if __name__=='__main__':main()
