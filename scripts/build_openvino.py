"""Build standalone C++ inference against the installed OpenVINO wheel SDK."""
from pathlib import Path
import subprocess
import openvino
ROOT=Path(__file__).resolve().parents[1]
sdk=Path(openvino.__file__).parent
library=next((sdk/'libs').glob('libopenvino.so.*'))
out=ROOT/'artifacts/native/infer_openvino';out.parent.mkdir(parents=True,exist_ok=True)
subprocess.run(['g++','-std=c++17','-O3',str(ROOT/'native/infer_openvino.cpp'),'-I'+str(sdk/'include'),
                str(library),'-Wl,-rpath,'+str(sdk/'libs'),'-o',str(out)],check=True)
print(out)
