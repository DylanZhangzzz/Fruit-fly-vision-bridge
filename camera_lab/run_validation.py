import os
from pathlib import Path
"""Replay the fixed audit without acquiring or uploading camera frames."""
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
LAB=ROOT/'camera_lab'
CAP=Path(os.environ.get('FLYVISION_LEGACY_CAPTURE', str(LAB/'captures/legacy')))
steps=[
    [sys.executable,str(LAB/'test_encoding.py')],
    [sys.executable,str(LAB/'encode_depth.py'),str(CAP)],
    [sys.executable,str(LAB/'validate_positions.py')],
    [sys.executable,str(LAB/'validate_calibration.py')],
    [sys.executable,str(LAB/'validate_mutations.py')],
    ['node',str(LAB/'validate_network.mjs')],
    [sys.executable,str(LAB/'build_validation_report.py')],
]
for command in steps:
    subprocess.run(command,cwd=ROOT,check=True)
files=list(LAB.glob('*.py'))+list(LAB.glob('*.mjs'))+list((LAB/'data').glob('*'))
files += [CAP/name for name in ['rgb.png','depth_raw_u16.png','depth_aligned_u16.png','report.json','neural_input.json']]
files += list((LAB/'validation').glob('*.json'))+list((LAB/'validation').glob('*.csv'))
files += [LAB/'validation/local_stimulus_response.npy',LAB/'validation/index.html',ROOT/'fruit-fly-simulation/src/brain.js']
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file() and p.name!='reproducibility.json'}
(LAB/'validation/reproducibility.json').write_text(json.dumps(dict(
    completed_utc=datetime.now(timezone.utc).isoformat(),python=sys.version,platform=platform.platform(),
    node=subprocess.check_output(['node','--version'],text=True).strip(),
    commands=steps,all_commands_passed=True,sha256=hashes),indent=2),encoding='utf-8')
print('All engineering audit steps passed. Biological visual-field calibration remains UNVERIFIED.')
