"""Bounded, reproducible UAVVaste subset, CC BY 4.0 (Zenodo 8214061).

Uses HTTP Range to avoid downloading the 3GB archive. Source batches never cross
splits; this is a proxy for capture sessions, not verified location independence.
"""
import concurrent.futures,hashlib,io,json,re,struct,sys,urllib.request,zipfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
URL='https://zenodo.org/api/records/8214061/files/UAVVasteDataset.zip/content'
SIZE=3010727259
OUT=ROOT/'datasets/uavvaste-pilot-v1'
MAX_TOTAL=400_000_000
class Remote(io.RawIOBase):
    def __init__(self):self.pos=0
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,n,whence=0):self.pos=n if whence==0 else self.pos+n if whence==1 else SIZE+n;return self.pos
    def read(self,n=-1):
        n=SIZE-self.pos if n<0 else min(n,SIZE-self.pos)
        if n<=0:return b''
        data=fetch(self.pos,n);self.pos+=len(data);return data

def fetch(start,n):
    if n>20_000_000:raise ValueError('Range exceeds budget')
    req=urllib.request.Request(URL,headers={'Range':f'bytes={start}-{start+n-1}'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=45) as r:
                if r.status!=206:raise ValueError('Server ignored Range; aborting large download')
                d=r.read(n+1)
                if len(d)!=n:raise ValueError('Wrong Range length')
                return d
        except (OSError,ValueError):
            if attempt==2:raise

def main():
    from PIL import Image,ImageOps
    if (OUT/'manifest.json').exists():raise ValueError('Version exists; preserve it and choose a new version')
    OUT.mkdir(parents=True,exist_ok=True)
    z=zipfile.ZipFile(Remote());a=json.loads(z.read('annotations/annotations.json'))
    records=[]
    def group(name):return re.sub(r'(?:img_|frame_|img)\d+.*','',name).lower()
    groups={'train':{'batch_s01_','batch_d06_','batch_01_'},'val':{'batch_02_'},'test':{'batch_03_'}}
    for split,gs in groups.items():
        candidates=sorted([r for r in a['images'] if group(r['file_name']) in gs],key=lambda r:hashlib.sha256(r['file_name'].encode()).hexdigest())
        records.extend((split,r) for r in candidates[:48 if split=='train' else 12])
    infos={r['file_name']:z.getinfo('images/'+r['file_name']) for _,r in records}
    if sum(i.compress_size for i in infos.values())>MAX_TOTAL:raise ValueError('Subset exceeds total budget')
    labels={}
    for ann in a['annotations']:labels.setdefault(ann['image_id'],[]).append(ann)
    def download(item):
        split,row=item;info=infos[row['file_name']]
        header=fetch(info.header_offset,30);fields=struct.unpack('<4s5H3I2H',header)
        nname,nextra=fields[-2:];start=info.header_offset+30+nname+nextra
        compressed=fetch(start,info.compress_size)
        raw=zlib.decompress(compressed,-15) if info.compress_type==8 else compressed
        if len(raw)!=info.file_size or (zlib.crc32(raw)&0xffffffff)!=info.CRC:raise ValueError('ZIP CRC mismatch')
        key=Path(row['file_name']).stem.lower();image=Image.open(io.BytesIO(raw));image.load()
        if image.size!=(row['width'],row['height']):raise ValueError('COCO dimensions mismatch')
        image=image.convert('RGB');image.thumbnail((1280,1280))
        folder=OUT/'images'/split;folder.mkdir(parents=True,exist_ok=True);dest=folder/(key+'.jpg');image.save(dest,quality=92)
        lines=[]
        for ann in labels.get(row['id'],[]):
            x,y,w,h=ann['bbox'];iw,ih=row['width'],row['height']
            if w<=0 or h<=0 or min(x,y)<0 or x+w>iw+1 or y+h>ih+1:raise ValueError('Invalid bbox')
            lines.append(f'0 {(x+w/2)/iw:.8f} {(y+h/2)/ih:.8f} {w/iw:.8f} {h/ih:.8f}')
        labeldir=OUT/'labels'/split;labeldir.mkdir(parents=True,exist_ok=True);(labeldir/(key+'.txt')).write_text('\n'.join(lines)+'\n')
        return {'file':str(dest.relative_to(OUT)),'source_file':row['file_name'],'batch':group(row['file_name']),'split':split,
                'source_sha256':hashlib.sha256(raw).hexdigest(),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
                'source_url':row.get('flickr_url'),'annotations':len(lines),'license':'CC BY 4.0 / Zenodo 8214061'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result=[]
        for r in pool.map(download,records):result.append(r);print(len(result),r['file'],flush=True)
    if len({r['source_sha256'] for r in result})!=len(result):raise ValueError('Duplicate image; abort split')
    manifest={'version':'uavvaste-pilot-v1','source':URL,'record':'https://zenodo.org/records/8214061','license':'CC BY 4.0',
              'attribution':'Kraft, Piechocki, Ptak, Walas (2021), Remote Sensing 13(5), 965. doi:10.3390/rs13050965',
              'selection':'sha256(filename) order; 48 train / 12 validation / 12 test; disjoint source batches',
              'limitation':'Batches are a session proxy; same-location independence not verified. Small experimental subset, no production accuracy claim.',
              'records':result}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (OUT/'LICENSE.txt').write_text('UAVVaste Dataset. CC BY 4.0. https://creativecommons.org/licenses/by/4.0/\n'+manifest['attribution']+'\nSource: '+manifest['record']+'\nImages resized to <=1280px; COCO boxes converted to normalized YOLO.\n')
    (OUT/'dataset.yaml').write_text('path: '+str(OUT)+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames: [trash]\n')
    (OUT/'annotations-original.json').write_text(json.dumps(a))
    print('Complete',len(result),'photos; source compressed bytes',sum(i.compress_size for i in infos.values()))
if __name__=='__main__':main()
