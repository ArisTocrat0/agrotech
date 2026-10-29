"""HTTP transport integration on an isolated test table, no real model metrics."""
import json,threading,urllib.request,urllib.error,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.test_pilot import MariaIntegration
from web_pilot import make_handler
from http.server import ThreadingHTTPServer
class HTTPTests(MariaIntegration):
    def test_http_ingest_and_boundaries(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def call(path,payload=None,headers=None):
            req=urllib.request.Request(base+path,data=None if payload is None else json.dumps(payload).encode(),
                                       headers={'Content-Type':'application/json',**(headers or {})})
            return urllib.request.urlopen(req,timeout=5)
        try:
            with call('/') as r:self.assertIn('Экокинеу',r.read().decode())
            for headers in [{'Origin':'https://outside.invalid'},{'Host':'outside.invalid'}]:
                with self.assertRaises(urllib.error.HTTPError) as failure:call('/api/pilot/photos',self.payload(),headers)
                self.assertEqual(failure.exception.code,403);failure.exception.close()
            with call('/api/pilot/photos',self.payload()) as r:key=json.load(r)['photo']['id']
            self.keys.append(key);row=self.wait(key);self.assertEqual(row['state'],'done')
            with call('/api/pilot/events.geojson') as r:
                rows=json.load(r)['features'];self.assertTrue(any(f['properties']['photo_id']==key and f['geometry'] is None for f in rows))
            with call('/api/pilot/evidence/'+key+'/annotated.jpg') as r:self.assertEqual(r.headers['Content-Type'],'image/jpeg')
            with self.assertRaises(urllib.error.HTTPError) as failure:call('/api/pilot/evidence/'+key+'/../../client.json')
            self.assertEqual(failure.exception.code,404);failure.exception.close()
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main(verbosity=2)
