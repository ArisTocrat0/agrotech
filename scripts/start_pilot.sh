#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python scripts/local_db.py
pilot_port="${ECOKINEU_PORT:-8010}"
if .venv/bin/python - "$pilot_port" <<'PY'
import json,sys,urllib.request
try:
    base='http://127.0.0.1:'+str(int(sys.argv[1]))
    with urllib.request.urlopen(base+'/api/pilot/status',timeout=2) as r:status=json.load(r)
    with urllib.request.urlopen(base+'/api/pilot/photos',timeout=2) as r:json.load(r)
    sys.exit(0 if status.get('name')=='Экокинеу' else 1)
except Exception:sys.exit(1)
PY
then
    printf 'Экокинеу уже доступен: http://127.0.0.1:%s/\n' "$pilot_port"
    exit 0
fi
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
exec .venv/bin/python web_pilot.py --port "$pilot_port"
