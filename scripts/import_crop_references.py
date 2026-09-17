"""User-triggered Commons import. Retains originals, provenance and license metadata."""
from pathlib import Path
import hashlib
import html
import json
import re
from io import BytesIO
from urllib.parse import urlencode, quote, urlparse
from urllib.request import Request, urlopen
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]


def fetch(url):
    if urlparse(url).scheme != 'https' or urlparse(url).hostname not in {'commons.wikimedia.org','upload.wikimedia.org'}:
        raise ValueError('Unexpected image host')
    request = Request(url,headers={'User-Agent':'OlzhaAgroReferenceImporter/1.0 (local research prototype)'})
    with urlopen(request,timeout=30) as response:
        data = response.read(25*1024*1024+1)
    if len(data) > 25*1024*1024:
        raise ValueError('Image exceeds 25 MB')
    return data


def import_references():
    sources = json.loads((ROOT/'datasets/crop_sources.json').read_text())['sources']
    folder = ROOT/'data/Культуры'
    folder.mkdir(parents=True,exist_ok=True)
    manifest = folder/'sources.json'
    records = json.loads(manifest.read_text()) if manifest.exists() else []
    failures = []
    for source in sources:
        try:
            if any(r['title']==source['title'] and (ROOT/r['file']).exists() for r in records):
                print('Already imported:',source['title'],flush=True)
                continue
            query = urlencode({'action':'query','format':'json','prop':'imageinfo','iiprop':'url|extmetadata','titles':source['title']})
            page = next(iter(json.loads(fetch('https://commons.wikimedia.org/w/api.php?'+query))['query']['pages'].values()))
            info = page['imageinfo'][0]
            meta = info['extmetadata']
            clean = lambda key: html.unescape(re.sub('<[^>]+>','',meta.get(key,{}).get('value','')))
            license_name = clean('LicenseShortName')
            if not any(key in license_name.lower() for key in ['cc by','cc0','public domain']):
                raise ValueError('No supported open license found: '+license_name)
            raw = fetch(info['url'])
            with Image.open(BytesIO(raw)) as image:
                image.verify()
            digest = hashlib.sha256(raw).hexdigest()
            target = folder/source['species']/source['stage']/(digest[:20]+'.jpg')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            records.append({**source,'file':str(target.relative_to(ROOT)),'sha256':digest,
                            'author':clean('Artist'),'license':license_name,'license_url':clean('LicenseUrl'),
                            'page':'https://commons.wikimedia.org/wiki/'+quote(source['title']),
                            'download_url':info['url'],'changes':'none','field_validated':False})
            temp = manifest.with_suffix('.tmp')
            temp.write_text(json.dumps(records,ensure_ascii=False,indent=2));temp.replace(manifest)
            print('Imported:',source['species'],source['title'],flush=True)
        except Exception as exc:
            failures.append(source['title']);print('ERROR:',source['title'],str(exc),flush=True)
    print(f'Imported references: {len(records)}; failed: {len(failures)}',flush=True)
    if failures:
        raise RuntimeError('Some references could not be imported. See the log; already imported photos are preserved.')


if __name__ == '__main__':
    import_references()
