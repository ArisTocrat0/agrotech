"""Экокинеу local photo pilot. Starts only on loopback."""
import argparse,json,mimetypes,re
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from src.pilot.service import Pilot
ROOT=Path(__file__).resolve().parent

def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def send(self,status,data,mime='application/json; charset=utf-8'):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob: data: https://tile.openstreetmap.org; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if not re.fullmatch(r'(?:localhost|127\.0\.0\.1)(?::[0-9]+)?',self.headers.get('Host','')):
                return self.send(403,{'error':'Только локальный доступ.'})
            path=urlparse(self.path).path
            try:
                if path=='/api/pilot/status':return self.send(200,app.status())
                if path=='/api/pilot/photos':return self.send(200,{'photos':app.photos()})
                if path=='/api/pilot/events.geojson':return self.send(200,app.geojson())
                if path=='/api/pilot/training':
                    files={}
                    for name in ('learning_report','benchmark_nms','pilot_validation','pilot_training'):
                        p=ROOT/'artifacts'/(name+'.json')
                        files[name]=json.loads(p.read_text()) if p.exists() else None
                    return self.send(200,files)
                match=re.fullmatch(r'/api/pilot/evidence/([a-f0-9]{32})/(source|annotated)\.jpg',path)
                if match:
                    app.store.get(match[1]);return self.send(200,(app.base/match[1]/(match[2]+'.jpg')).read_bytes(),'image/jpeg')
                name={'/':'pilot.html'}.get(path,path.lstrip('/'))
                if name not in ('pilot.html','pilot.js','pilot.css','map.js','world.geojson','vendor/leaflet/leaflet.js','vendor/leaflet/leaflet.css','vendor/leaflet/LICENSE','vendor/leaflet/images/layers.png','vendor/leaflet/images/layers-2x.png','vendor/leaflet/images/marker-icon.png','vendor/leaflet/images/marker-icon-2x.png','vendor/leaflet/images/marker-shadow.png'):return self.send(404,{'error':'Не найдено'})
                return self.send(200,(ROOT/'web'/name).read_bytes(),mimetypes.guess_type(name)[0] or 'application/json')
            except (OSError,ValueError): self.send(404,{'error':'Не найдено'})
        def do_POST(self):
            if not re.fullmatch(r'(?:localhost|127\.0\.0\.1)(?::[0-9]+)?',self.headers.get('Host','')):
                return self.send(403,{'error':'Только локальный доступ.'})
            try:
                if self.headers.get('Origin') and self.headers['Origin'] != 'http://'+self.headers.get('Host',''):
                    return self.send(403,{'error':'Разрешён только локальный интерфейс.'})
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Нужен application/json.')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=15_000_000:return self.send(413,{'error':'Слишком большой запрос.'})
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):raise ValueError('Нужен JSON объект.')
                path=urlparse(self.path).path
                if path=='/api/pilot/photos':return self.send(200,app.ingest(payload))
                m=re.fullmatch(r'/api/pilot/photos/([a-f0-9]{32})/diagnose-public',path)
                if m:return self.send(200,app.diagnose_public_photo(m[1]))
                m=re.fullmatch(r'/api/pilot/photos/([a-f0-9]{32})/reprocess',path)
                if m:return self.send(200,app.reprocess(m[1],payload.get('expected_registry_sha256')))
                m=re.fullmatch(r'/api/pilot/photos/([a-f0-9]{32})/retry',path)
                if m:return self.send(200,app.retry(m[1]))
                m=re.fullmatch(r'/api/pilot/photos/([a-f0-9]{32})/review',path)
                if m:return self.send(200,app.review(m[1],payload.get('event_id'),payload.get('status')))
                self.send(404,{'error':'Не найдено'})
            except (ValueError,TypeError,KeyError) as exc:self.send(400,{'error':str(exc)})
            except Exception:
                import traceback;traceback.print_exc();self.send(500,{'error':'Ошибка хранилища. Проверьте журнал сервера.'})
    return Handler

def main():
    p=argparse.ArgumentParser(description='Экокинеу: очередь отдельных фотографий');p.add_argument('--port',type=int,default=8010);a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),BaseHTTPRequestHandler)
    try:app=Pilot(ROOT)
    except Exception:server.server_close();raise
    server.RequestHandlerClass=make_handler(app)
    print(f'Экокинеу: http://127.0.0.1:{a.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();app.close()
if __name__=='__main__':main()
