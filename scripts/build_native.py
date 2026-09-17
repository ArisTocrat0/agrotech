"""Build the optional C++ NMS kernel; the app has a Python fallback."""
from pathlib import Path
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]

def build():
    output = ROOT / 'artifacts/native/libagro_nms.so'
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a complete library; a running server may have the old one mapped.
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        compiled = Path(temporary) / output.name
        subprocess.run(['g++', '-O3', '-std=c++17', '-Wall', '-Wextra', '-shared', '-fPIC',
                        str(ROOT/'native/nms.cpp'), '-o', str(compiled)], check=True)
        compiled.replace(output)
    return output

if __name__ == '__main__':
    print(build())
