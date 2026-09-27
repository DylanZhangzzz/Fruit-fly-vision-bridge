"""Obtain optional public physiology files and verify every byte by SHA-256.

Dryad may require a normal browser download. --from-directory imports those
downloads after the same checksum validation; no login or access bypass is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-directory',type=Path)
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    failures=[]
    for entry in json.loads((ROOT/'data/downloads.json').read_text(encoding='utf8')):
        dest=(ROOT/entry['path']).resolve()
        if not dest.is_relative_to(ROOT):raise ValueError('Data path escapes repository')
        if dest.exists():
            if digest(dest)!=entry['sha256']:raise ValueError(f'Existing file has unexpected SHA-256: {dest}')
            print('VERIFIED',dest.name);continue
        if args.verify_only:
            failures.append(entry['path']);continue
        dest.parent.mkdir(parents=True,exist_ok=True)
        temp=dest.with_suffix(dest.suffix+'.partial')
        if temp.exists():raise FileExistsError(f'Unfinished download exists: {temp}; inspect before retrying')
        try:
            local=args.from_directory/dest.name if args.from_directory else None
            if local and local.is_file():
                shutil.copyfile(local,temp)
            else:
                req=urllib.request.Request(entry['url'],headers={'User-Agent':'Fruit-fly-vision-bridge/0.1'})
                with urllib.request.urlopen(req,timeout=60) as response, temp.open('wb') as out:
                    shutil.copyfileobj(response,out)
            if digest(temp)!=entry['sha256']:raise ValueError('SHA-256 mismatch; response may be an HTML access page')
            temp.replace(dest);print('VERIFIED',dest.name)
        except Exception as exc:
            if temp.exists():temp.unlink()
            failures.append(entry['path'])
            print(f'Could not obtain {dest.name}: {exc}')
            print('Download the exact named file in a browser, then rerun --from-directory:')
            print(entry.get('manual_page',entry['url']))
    if failures:
        raise SystemExit(f'{len(failures)} required files unavailable. No physiology validation has run.')


if __name__=='__main__':main()
