"""Check the Git publication file set for recordings, large files and private paths."""
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    paths=sorted(set(p for p in paths if p))
    forbidden=['.venv','outputs/','fruit-fly-simulation/','camera_lab/captures/',
        'camera_lab/imu/','camera_lab/biomapping/captures/',
        'camera_lab/biomapping/screen_experiment/runs/','camera_lab/biomapping/source/L1L2-deblur/']
    failures=[];total=0
    for rel in paths:
        path=ROOT/rel
        if not path.is_file():continue
        total+=path.stat().st_size
        if any(rel.startswith(p) for p in forbidden) or path.suffix.lower() in ['.avi','.bag']:
            failures.append((rel,'unpublished input/output'))
        if path.stat().st_size>10_000_000:failures.append((rel,'file exceeds 10 MB release limit'))
        if path.suffix.lower() in ['.py','.md','.json','.html','.yml','.yaml','.mjs','.toml','.csv']:
            text=path.read_text(encoding='utf-8-sig')
            # Construct patterns to avoid the audit's own source matching itself.
            if re.search(r'[A-Z]:[\\/]+(?:Users|Fun Project)[\\/]',text):
                failures.append((rel,'private absolute path'))
            if re.search(r'"serial(?:_number)?"\s*:\s*"[0-9]{8,}"',text):
                failures.append((rel,'device serial in an artifact'))
            if re.search('-----BEGIN '+'(?:OPENSSH|RSA|EC) PRIVATE KEY-----',text):
                failures.append((rel,'private key'))
    if failures:raise SystemExit(str(failures))
    print(f'Publication audit passed: {len(paths)} files, {total/1e6:.2f} MB. Review the diff as well.')


if __name__=='__main__':main()
