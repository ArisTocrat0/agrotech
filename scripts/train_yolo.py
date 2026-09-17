"""Small local YOLO trial, also launched and monitored by the web dashboard."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
TRAINING = ROOT / 'outputs' / 'yolo_training'
STATUS = TRAINING / 'status.json'


def save_status(state):
    temporary = STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(STATUS)


def training_status():
    if not STATUS.exists():
        return {'status': 'idle', 'epoch': 0, 'epochs': 5,
                'full_ready': (ROOT/'yolo_dataset/verified/dataset.yaml').exists()}
    state = json.loads(STATUS.read_text(encoding='utf-8'))
    if state['status'] == 'running':
        # The lock survives parent/server restarts and does not depend on PID namespaces.
        with (TRAINING / 'training.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                state['status'] = 'error'
                state['error'] = 'Обучение остановлено. Можно запустить повторно.'
    log = TRAINING / state['run'] / 'training.log'
    if log.exists():
        with log.open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 12000))
            state['log'] = stream.read().decode('utf-8', errors='replace')
            import re
            state['log'] = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', state['log']).replace('\r', '\n')
    state['weights_ready'] = state['status'] == 'done' and (TRAINING / state['run'] / 'weights' / 'best.pt').exists()
    state['percent'] = round(100 * state.get('epoch', 0) / max(1, state.get('epochs', 1)))
    state['full_ready'] = (ROOT/'yolo_dataset/verified/dataset.yaml').exists()
    return state


def start_training():
    if not (ROOT / 'yolo_dataset/trial/dataset.yaml').exists():
        raise ValueError('Не найден подготовленный датасет YOLO.')
    if not (ROOT / 'artifacts/yolo11n.pt').exists():
        raise ValueError('Не найдены исходные веса YOLO11n.')
    TRAINING.mkdir(parents=True, exist_ok=True)
    with (TRAINING / 'training.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Обучение уже выполняется.') from exc
        run = 'trial_' + uuid.uuid4().hex[:12]
        folder = TRAINING / run
        folder.mkdir()
        save_status({'status':'running', 'run':run, 'epoch':0, 'epochs':5, 'device':'cpu'})
        try:
            with (folder / 'training.log').open('w') as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                    '--run', run, '--lock-fd', str(lock.fileno())], cwd=ROOT,
                    stdout=log, stderr=subprocess.STDOUT, pass_fds=(lock.fileno(),), start_new_session=True)
        except Exception as exc:
            save_status({'status':'error', 'run':run, 'epoch':0, 'epochs':5, 'error':str(exc)})
            raise
    return process


def start_full_training():
    dataset = ROOT/'yolo_dataset/verified/dataset.yaml'
    if not dataset.exists():
        raise ValueError('Полное обучение не готово: нет yolo_dataset/verified/dataset.yaml.')
    from scripts.train_yolo_full import validate_dataset
    validate_dataset(dataset)
    if not (ROOT/'artifacts/yolo11n.pt').exists():
        raise ValueError('Не найдены исходные веса YOLO11n.')
    TRAINING.mkdir(parents=True, exist_ok=True)
    with (TRAINING/'training.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Обучение уже выполняется.') from exc
        run='full_'+uuid.uuid4().hex[:12]
        folder=TRAINING/run
        folder.mkdir()
        save_status({'status':'running','mode':'full','run':run,'epoch':0,'epochs':150,'percent':0,'device':'cuda'})
        with (folder/'training.log').open('w') as log:
            process=subprocess.Popen([sys.executable,str(ROOT/'scripts/train_yolo_full.py'),
                '--data',str(dataset),'--model',str(ROOT/'artifacts/yolo11n.pt'),
                '--epochs','150','--imgsz','640','--batch','-1','--device','0',
                '--workers','2','--patience','30','--name',run,'--status',str(STATUS),
                '--lock-fd',str(lock.fileno()),'--exist-ok'],cwd=ROOT,stdout=log,
                stderr=subprocess.STDOUT,pass_fds=(lock.fileno(),),start_new_session=True)
    return process


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    parser.add_argument('--lock-fd', type=int, required=True)
    args = parser.parse_args()
    state = {'status':'running', 'run':args.run, 'pid':os.getpid(), 'epoch':0, 'epochs':5, 'device':'cpu'}
    save_status(state)
    try:
        config_dir = ROOT / 'outputs' / 'yolo_config'
        config_dir.mkdir(parents=True, exist_ok=True)
        os.environ['YOLO_CONFIG_DIR'] = str(config_dir)
        os.environ['MPLCONFIGDIR'] = str(config_dir / 'matplotlib')
        os.environ['YOLO_OFFLINE'] = 'true'
        os.environ['YOLO_AUTOINSTALL'] = 'false'
        os.environ['OMP_NUM_THREADS'] = '4'
        # Use an installed Unicode font; training does not need font downloads.
        import shutil
        from matplotlib import font_manager
        font = font_manager.findfont('DejaVu Sans')
        import torch
        torch.set_num_threads(4)
        from ultralytics import YOLO, settings
        from ultralytics.utils import USER_CONFIG_DIR
        for name in ['Arial.ttf', 'Arial.Unicode.ttf']:
            shutil.copyfile(font, USER_CONFIG_DIR / name)
        integrations = ['sync', 'wandb', 'mlflow', 'clearml', 'comet', 'neptune', 'tensorboard']
        settings.update({key: False for key in integrations if key in settings})
        model = YOLO(str(ROOT / 'artifacts/yolo11n.pt'))

        def progress(trainer):
            state['epoch'] = min(trainer.epoch + 1, state['epochs'])
            state['metrics'] = {key: float(value) for key, value in trainer.metrics.items()}
            save_status(state)

        model.add_callback('on_fit_epoch_end', progress)
        model.train(data=str(ROOT / 'yolo_dataset/trial/dataset.yaml'),
                    epochs=5, imgsz=320, batch=4, device='cpu', workers=0,
                    project=str(TRAINING), name=args.run, exist_ok=True,
                    seed=42, deterministic=True, plots=False, cache=False,
                    amp=False, pretrained=True, save=True, val=True, close_mosaic=0)
        state['status'] = 'done'
        save_status(state)
    except BaseException as exc:
        state.update(status='error', error=str(exc))
        save_status(state)
        raise
    finally:
        os.close(args.lock_fd)


if __name__ == '__main__':
    main()
