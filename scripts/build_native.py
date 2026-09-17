"""Build the optional C++ NMS kernel; the app has a Python fallback."""
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]

def build():
    output = ROOT / 'artifacts/native/libagro_nms.so'
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['g++', '-O3', '-std=c++17', '-shared', '-fPIC',
                    str(ROOT/'native/nms.cpp'), '-o', str(output)], check=True)
    return output

if __name__ == '__main__':
    print(build())
