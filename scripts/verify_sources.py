"""Verify included authoritative mapping inputs without network or hardware."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    entries=json.loads((ROOT/'data/vendored_checksums.json').read_text(encoding='utf8'))
    for rel,expected in entries.items():
        actual=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
        if actual!=expected:raise ValueError(f'Source SHA-256 mismatch: {rel}')
    print(f'PASS: {len(entries)} included source files match pinned SHA-256.')


if __name__=='__main__':main()
