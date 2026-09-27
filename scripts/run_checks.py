"""Run hardware-free implementation and source checks from a checkout."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([sys.executable,*args],cwd=ROOT,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-only',action='store_true',help='NumPy/Pillow bridge tests only')
    args=parser.parse_args()
    run('scripts/verify_sources.py')
    run('-m','unittest','discover','-s','tests','-p','test_*.py','-v')
    if args.core_only:return
    run('camera_lab/calibrate.py','target')
    run('camera_lab/test_encoding.py')
    run('camera_lab/test_calibration.py')
    run('-m','unittest','discover','-s','camera_lab/biomapping','-p','test_*.py','-v')
    print('All implementation checks passed. This does not certify biological validity.')


if __name__=='__main__':main()
