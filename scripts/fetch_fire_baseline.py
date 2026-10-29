"""Fetch only the pinned safe-format fire baseline and verify known SHA256.

No user photos are uploaded. Card/embedded licenses differ: read SOURCE.json.
Existing model registry is preserved; this script never auto-activates weights.
"""
import hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    source=ROOT/'artifacts/fire-openvino/SOURCE.json';manifest=json.loads(source.read_text())
    base='https://huggingface.co/zell-dev/fire-smoke-detection/resolve/'+manifest['revision']+'/best_int8_openvino_model/'
    for item in manifest['assets']:
        name=Path(item['path']).name;target=source.parent/name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']:
            print(name,'already verified');continue
        with urllib.request.urlopen(base+name,timeout=60) as response:data=response.read(30_000_001)
        if len(data)>30_000_000 or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Size/checksum mismatch: '+name)
        target.write_bytes(data);print(name,len(data),'verified')
if __name__=='__main__':main()
