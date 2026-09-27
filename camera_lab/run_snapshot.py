"""Capture -> depth-aware spatial encoding -> whole-network replay and report."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from encode_depth import encode

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent


def write_report(capture):
    data=json.loads((capture/'neural_input.json').read_text())
    brain=json.loads((capture/'brain_report.json').read_text())
    spikes={r['bodyId']:r['spikes'] for r in json.loads((capture/'camera_spikes.json').read_text())}
    def plot(kind):
        parts=['<svg viewBox="0 0 640 480" role="img" aria-label="Right-eye L2 spatial channels">',
               '<rect width="640" height="480" fill="#111827"/>']
        for c in data['channels']:
            value=c['rate_hz']/120 if kind=='input' else min(1,spikes.get(c['bodyId'],0)/10)
            color=f'rgb({int(255*value)},{int(100+120*value)},180)' if c['luminance'] is not None else '#374151'
            label=f"ID {c['bodyId']} / input {c['rate_hz']:.1f} Hz / spikes {spikes.get(c['bodyId'],0)} / depth {c['depth_m']} m"
            parts.append(f'<circle cx="{c["u"]:.2f}" cy="{c["v"]:.2f}" r="5" fill="{color}"><title>{label}</title></circle>')
        parts.append('</svg>')
        return ''.join(parts)
    table=''.join(f'<tr><td>{name}</td><td>{r["total_spikes"]}</td><td>{r["active_neurons"]}</td><td>{r["downstream_spikes"]}</td></tr>' for name,r in brain['runs'].items())
    html='''<!doctype html><meta charset="utf-8"><title>D435i → MaleCNS 实验</title>
<style>body{font:16px system-ui;background:#0d1420;color:#e5edf5;max-width:1200px;margin:36px auto;padding:20px}h1{font-size:28px}p{line-height:1.7}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}img,svg{width:100%;border-radius:10px}section{background:#172333;padding:18px;border-radius:12px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:10px;border-bottom:1px solid #405060}a{color:#9edfff}</style>
<h1>D435i → 空间编码 → MaleCNS 神经活动</h1>
<p>单帧回放实验 · 右眼 L2 注入 · 非实时直播 · 尚未验证生物视觉功能</p>
<div class="grid"><section><h2>相机 RGB</h2><img src="rgb.png"></section>
<section><h2>深度对齐预览</h2><img src="preview.png"><p>右半为深度；黑色为无效深度。</p></section>
<section><h2>逐视柱输入（0–120 Hz）</h2>'''+plot('input')+'''<p>灰色：采样不足；蓝到粉：刺激增强。悬停查看神经元 ID、深度和输入。</p></section>
<section><h2>L2 放电数（50 ms）</h2>'''+plot('output')+'''<p>逐位置显示模型计算出的放电，不是按输入直接绘制的活动。</p></section></div>
<h2>传播对照</h2><table><tr><th>条件</th><th>总放电</th><th>活跃神经元</th><th>非注入神经元放电</th></tr>'''+table+'''</table>
<p>完整加载 166,700 神经元与 25,582,938 条有向连接；每个条件从相同初态重置，使用相同随机种子。</p>
<p>深度用于反投影、虚拟视点偏移和遮挡处理，不直接作为刺激强度。虚拟视点沿相机 X 轴偏移 3 cm 是实验设置，并非果蝇双眼间距。视柱 ID 与位置来自公开表；视野方向、范围及亮度到 L2 输入映射仍是假设。没有使用胞体坐标冒充视野坐标。</p>
<p>本实验绕过感光细胞，仅验证空间编码能进入连接网络并传播；不能证明模型认识瓶子、杯子或理解远近。透明瓶身可能产生错误的非零深度。</p>
<a href="brain_report.json">计算报告</a> · <a href="neural_input.json">逐神经元输入</a>'''
    (capture/'experiment.html').write_text(html,encoding='utf-8')


def main():
    if len(sys.argv)>1:
        capture=Path(sys.argv[1]).resolve()
    else:
        result=subprocess.run([sys.executable,str(HERE/'probe_camera.py')],check=True,capture_output=True,text=True)
        capture=Path(json.loads(result.stdout)['output'])
    encode(capture)
    node=shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required on PATH to run the existing BrainCPU model')
    subprocess.run([node,str(HERE/'run_brain.mjs'),str(capture/'neural_input.json')],check=True)
    write_report(capture)
    print('REPORT:',capture/'experiment.html')


if __name__=='__main__':
    main()
