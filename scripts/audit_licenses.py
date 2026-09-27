"""Check the reviewed publication boundary, not legal non-infringement.

Works offline on a checkout. --online also rechecks pinned upstream copies.
This cannot detect every copied fragment or prove an author's chain of title.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def digest(data, normalize_lf=False):
    if normalize_lf:
        data=data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def inspect(root, paths, inventory, online=False):
    failures=[]
    for entry in inventory['preserved_files']:
        path=root/entry['path']
        if not path.is_file():
            failures.append(f'Missing reviewed source/notice: {entry["path"]}')
            continue
        if digest(path.read_bytes(),entry.get('normalize_lf',False))!=entry['sha256']:
            failures.append(f'Reviewed source/notice changed: {entry["path"]}')
        if online and entry.get('source_url'):
            request=urllib.request.Request(entry['source_url'],headers={'User-Agent':'Fruit-fly-vision-bridge-license-audit'})
            with urllib.request.urlopen(request,timeout=45) as response:
                actual=digest(response.read(),entry.get('normalize_lf',False))
            if actual!=entry['sha256']:
                failures.append(f'Upstream source mismatch: {entry["path"]}')
    required=['LICENSE','THIRD_PARTY_NOTICES.md','docs/license-review.md',
              'reports/benchmark/THIRD_PARTY_NOTICES.md','reports/benchmark/LICENSE',
              'reports/benchmark/LICENSES/eyemap-archive.txt']
    failures += [f'Missing publication notice: {p}' for p in required if not (root/p).is_file()]
    report_copies={
        'reports/benchmark/LICENSE':'LICENSE',
        'reports/benchmark/THIRD_PARTY_NOTICES.md':'THIRD_PARTY_NOTICES.md',
        'reports/benchmark/LICENSES/eyemap-archive.txt':'camera_lab/biomapping/source/eyemap_archive/LICENSE',
        **{'reports/benchmark/'+e['path']:e['path'] for e in inventory['preserved_files'] if e['path'].startswith('LICENSES/')},
    }
    for copy,source in report_copies.items():
        if not (root/copy).is_file() or not (root/source).is_file():
            failures.append(f'Missing report license copy: {copy}')
        elif digest((root/copy).read_bytes(),True)!=digest((root/source).read_bytes(),True):
            failures.append(f'Stale or altered report license copy: {copy}')
    allowed=set(inventory['reviewed_binary_files'])
    preserved={e['path'] for e in inventory['preserved_files']}
    for rel in paths:
        path=Path(rel)
        if path.suffix.lower() in {'.ipynb','.m','.mat','.pt','.pth','.onnx','.ckpt','.avi','.bag','.mp4','.zip','.whl'}:
            failures.append(f'Unreviewed source/recording/model/archive: {rel}')
        if path.suffix.lower() in {'.npz','.npy','.png','.jpg','.jpeg','.webp','.svg','.pdf','.rdata','.xlsx','.woff','.woff2'} and rel not in allowed:
            failures.append(f'Unreviewed binary/media: {rel}')
        if rel.startswith('camera_lab/biomapping/source/') and rel not in preserved and rel!='camera_lab/biomapping/source/L2_Dryad/manifest.json':
            failures.append(f'Unreviewed upstream file: {rel}')
    return failures


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--online',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    paths=sorted(set(p for p in paths if p))
    inventory=json.loads((ROOT/'data/license_inventory.json').read_text(encoding='utf8'))
    failures=inspect(ROOT,paths,inventory,args.online)
    result=dict(status='FAIL' if failures else 'PASS_REVIEWED_SOURCE_PUBLICATION_CHECKS',
                paths_checked=len(paths),preserved_files_checked=len(inventory['preserved_files']),
                upstream_rechecked=args.online,failures=failures,
                limitation='Not a legal opinion or a patent/trademark clearance; see docs/license-review.md')
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
