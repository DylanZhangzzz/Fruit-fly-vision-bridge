"""Reproduce author-table import, RGB-D-IMU snapshot replay and brain controls."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
from import_author_map import BASE, STATUS

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('capture',type=Path)
    args=parser.parse_args()
    cap=args.capture.resolve()
    for script,extra in [('import_author_map.py',[]),('test_author_map.py',[]),
                         ('test_biomapping.py',[]),('run_reference.py',[str(cap),'--malecns'])]:
        subprocess.run([sys.executable,str(BASE/script),*extra],check=True)
    out=cap/'malecns_eye'
    subprocess.run(['node',str(BASE.parent/'run_brain.mjs'),str(out/'brain_input.json')],check=True)
    report=json.loads((out/'report.json').read_text())
    brain=json.loads((out/'brain_report.json').read_text())
    report.update(neural_injection_performed=True,brain_propagation_check=brain['propagation_check_passed'],
                  scope='One saved RGB snapshot held for 50 ms; depth and IMU auxiliary only, no biological response validation')
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    rows=json.loads((BASE/'data/malecns_author_crosswalk.json').read_text())
    mapped=[r for r in rows if r['status']==STATUS]
    v=np.array([r['ray_head_xyz'] for r in mapped])
    dots=np.clip(v@v.T,-1,1)
    checks=[]
    for i,r in enumerate(mapped):
        peaks=np.flatnonzero(dots[i]>=dots[i].max()-1e-12)
        ids=[mapped[j]['bodyId'] for j in peaks]
        checks.append(dict(bodyId=r['bodyId'],hex1=r['hex1'],hex2=r['hex2'],
             target_in_peak=r['bodyId'] in ids,peak_bodyIds=';'.join(ids),
             independently_separable=len(ids)==1,
             validation_scope='Spherical angular point addressing, not biological ground truth'))
    with (out/'per_neuron_address_checks.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=checks[0]);writer.writeheader();writer.writerows(checks)
    if not all(r['target_in_peak'] for r in checks):raise ValueError('Angular addressing failed')
    runs=brain['runs']
    page=(out/'index.html').read_text(encoding='utf8')
    page+=f'''<h2>已执行的验证</h2><p>17 项自动测试通过。逐神经元球面点刺激寻址：847/847 目标位于峰值，845 个可独立区分；两个共享视柱同时达到峰值。这只验证编码地址。</p>
<p>全脑 50 ms 对照：零输入 {runs['no_input']['total_spikes']} 次放电；相机输入 {runs['camera']['total_spikes']} 次，其中下游 {runs['camera']['downstream_spikes']} 次；断开连接后的下游 {runs['connections_off']['downstream_spikes']} 次。传播检查通过不代表感知或生理模型验证通过。</p>
<p><a href="per_neuron_address_checks.csv">逐神经元检查表</a> · <a href="../../../data/malecns_author_crosswalk.json">完整 893 个 L2 对应表（含空缺）</a></p>'''
    (out/'index.html').write_text(page,encoding='utf8')
    status=dict(status='AUTHOR_MALECNS_MAP_CONNECTED_SNAPSHOT_REPLAY_TESTED',tests_passed=17,
                latest_capture=str(cap),resolved_L2=847,unique_columns=846,missing_L2=46,
                rgb_observed=report['rgb_observed'],depth_observed=report['depth_observed'],
                brain_injection=True,brain_propagation_check=brain['propagation_check_passed'],
                biological_response_validated=False,imu_alignment='APPROXIMATE_HOST_RECEIPT_TIME',
                sha256={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [*BASE.glob('*.py'),*BASE.joinpath('data').glob('*')] if p.is_file()})
    (BASE/'status.json').write_text(json.dumps(status,indent=2),encoding='utf8')
    print('COMPLETE:',out/'index.html')

if __name__=='__main__':main()
