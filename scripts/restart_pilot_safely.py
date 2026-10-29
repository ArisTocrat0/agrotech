"""Restart only this project's known idle local server, preserving the journal."""
import json,os,signal,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    url='http://127.0.0.1:8010';rows=json.load(urllib.request.urlopen(url+'/api/pilot/photos'))['photos']
    assert not any(p['state'] in ('queued','running') for p in rows),'Queue active: retry restart after processing completes'
    pid=int((ROOT/'outputs/pilot/server.pid').read_text());cmd=Path('/proc')/str(pid)/'cmdline'
    assert str(ROOT/'web_pilot.py').encode() in cmd.read_bytes(),'PID does not belong to this app'
    os.kill(pid,signal.SIGINT)
    for _ in range(300):
        if not cmd.exists():break
        time.sleep(.1)
    else:raise RuntimeError('Old server still running; no second process started')
    log=open(ROOT/'outputs/pilot/server.log','ab');proc=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'web_pilot.py'),'--port','8010'],cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
    (ROOT/'outputs/pilot/server.pid').write_text(str(proc.pid))
    for _ in range(150):
        try:
            after=json.load(urllib.request.urlopen(url+'/api/pilot/photos'))['photos'];assert {p['id'] for p in rows}<={p['id'] for p in after};print(json.dumps({'pid':proc.pid,'saved_photos':len(after)}));return
        except OSError:time.sleep(.1)
    raise RuntimeError('New server healthcheck failed')
if __name__=='__main__':main()
