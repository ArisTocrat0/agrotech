"""Finite local training/evaluation chain; no scheduler, downloads or auto-activation."""
import argparse,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args();assert a.run.replace('-','').isalnum();run=ROOT/'outputs/pilot-training'/a.run;deadline=time.time()+5*3600
    def status(state,**extra):
        tmp=run/'supervision.tmp';tmp.write_text(json.dumps({'state':state,'run':a.run,'updated_unix':time.time(),**extra},indent=2));tmp.replace(run/'supervision.json')
    status('waiting_for_training_and_export')
    while time.time()<deadline:
        if (run/'failure.json').exists():status('training_failed');return
        report=run/'quality-report.json'
        if report.exists() and json.loads(report.read_text()).get('state')=='exported_candidate_not_activated':break
        time.sleep(30)
    else:status('supervisor_timeout_no_activation');return
    status('evaluating_candidate_development_only')
    with (run/'quality-evaluation.log').open('ab') as log:
        result=subprocess.run([str(ROOT/'.venv/bin/python'),'-u',str(ROOT/'scripts/evaluate_quality_smoke.py'),'--run',a.run],cwd=ROOT,stdout=log,stderr=log,timeout=5400)
    status('evaluation_complete_not_activated' if result.returncode==0 else 'evaluation_failed_no_activation',exit_code=result.returncode)
if __name__=='__main__':main()
