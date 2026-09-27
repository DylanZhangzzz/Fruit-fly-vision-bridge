"""Fetch only the author's small, checksum-pinned Flyvis pretrained archive.

No room data is transmitted. The public download key is read from the author's
pinned download script, never from user credentials and never printed.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def safe_extract(archive,destination):
    destination=Path(destination).resolve()
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (destination/name).resolve().is_relative_to(destination):
                raise ValueError('Archive contains path outside destination')
        z.extractall(destination)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=Path('outputs/flyvis-data'))
    args=ap.parse_args()
    sources=json.loads((ROOT/'flyvisionbridge/benchmark_sources.json').read_text())
    spec=sources['pretrained_archive'];commit=sources['flyvis']['commit']
    args.output.mkdir(parents=True,exist_ok=True)
    archive=args.output/spec['name']
    if not archive.exists():
        url=f'https://raw.githubusercontent.com/TuragaLab/flyvis/{commit}/flyvis_cli/download_pretrained_models.py'
        with urllib.request.urlopen(url,timeout=60) as r:code=r.read().decode()
        key=None
        for n in ast.walk(ast.parse(code)):
            if isinstance(n,ast.Assign) and isinstance(n.value,ast.Constant):
                if any(isinstance(t,ast.Name) and t.id=='api_key' for t in n.targets):key=n.value.value
        if key is None:raise RuntimeError('Official download script has changed')
        query=urllib.parse.urlencode({'alt':'media','key':key})
        request='https://www.googleapis.com/drive/v3/files/'+spec['file_id']+'?'+query
        partial=archive.with_suffix('.partial')
        try:
            with urllib.request.urlopen(request,timeout=90) as response,partial.open('wb') as f:
                while chunk:=response.read(1024*1024):f.write(chunk)
        except Exception:
            raise RuntimeError('Official model download failed; see Flyvis download documentation') from None
        if hashlib.sha256(partial.read_bytes()).hexdigest()!=spec['sha256']:
            raise ValueError('Archive checksum differs from pinned author checksum')
        partial.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=spec['sha256']:
        raise ValueError('Existing archive checksum mismatch')
    # Avoid overwriting existing experiment/cache files on repeated invocations.
    if not (args.output/'results/flow/0000/000/best_chkpt').exists():
        safe_extract(archive,args.output)
    print(f'Author archive verified: {spec["sha256"]}; models available in {args.output}')


if __name__=='__main__':main()
