"""Export only synthetic results; private camera arrays/video are never copied."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import numpy as np
from flyvisionbridge.benchmark import render_report,write_json
from flyvisionbridge.benchmark_core import sha_file

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
    args=p.parse_args()
    if args.destination.exists():p.error('Destination exists; preserve previous report')
    report=json.loads((args.source/'report.json').read_text(encoding='utf8'))
    if report['status']!='COMPLETED_PREDICTIONS_AND_ENGINEERING_DIAGNOSTICS':
        raise ValueError('Cannot export incomplete benchmark')
    report['cases']=[c for c in report['cases'] if c['source']['kind']=='SYNTHETIC']
    report['export_scope']='Synthetic cases only; no camera frames, timestamps or response arrays copied'
    names={c['case'] for c in report['cases']}
    plot=[x for x in json.loads((args.source/'plot_data.json').read_text(encoding='utf8')) if x['name'] in names]
    args.destination.mkdir(parents=True)
    # Carry notices with a stand-alone report; do not rely on a repository parent.
    for name in ['LICENSE','THIRD_PARTY_NOTICES.md']:
        shutil.copyfile(ROOT/name,args.destination/name)
    shutil.copytree(ROOT/'LICENSES',args.destination/'LICENSES')
    (args.destination/'LICENSES'/'eyemap-archive.txt').write_bytes(
        (ROOT/'camera_lab/biomapping/source/eyemap_archive/LICENSE').read_bytes())
    (args.destination/'LICENSES'/'mapping-GPL-3.0.txt').write_bytes(
        (ROOT/'camera_lab/biomapping/source/LICENSE').read_bytes())
    write_json(args.destination/'publication.json',dict(
        scope='Synthetic-only source/report publication; no model weights or camera recording',
        numerical_report_preserved=True,
        original_execution_code_sha256=report.get('code_sha256',{}),
        export_code_sha256=sha_file(Path(__file__)),
        render_code_sha256=sha_file(ROOT/'flyvisionbridge/benchmark.py'),
        licensing='Original project code MIT; source-specific GPL-3.0 and CC-BY-SA-4.0 mapping components; additional CC-BY-4.0 identity data in the repository; see THIRD_PARTY_NOTICES.md'))
    write_json(args.destination/'report.json',report);write_json(args.destination/'plot_data.json',plot)
    for name in ['protocol.json','direction_diagnostics.json']:
        shutil.copyfile(args.source/name,args.destination/name)
    for filename,column,allowed in [('metrics.csv','case',names),('spatial_columns.csv','geometry',{'synthetic'})]:
        with (args.source/filename).open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;rows=[r for r in reader if r[column] in allowed]
        with (args.destination/filename).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    with np.load(args.source/'spatial_weights.npz',allow_pickle=False) as z:
        np.savez_compressed(args.destination/'spatial_weights.npz',**{k:z[k] for k in z.files if k.startswith('synthetic_')})
    render_report(args.destination,report,plot)
    print('Synthetic-only report exported to',args.destination)


if __name__=='__main__':main()
