"""Build a self-contained, per-neuron engineering audit viewer."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'validation'

def main():
    rows = list(csv.DictReader((OUT/'neurons.csv').open(encoding='utf-8-sig')))
    network = {r['bodyId']: r for r in json.loads((OUT/'network_neurons.json').read_text())}
    assert len(rows) == len(network) == 893
    for r in rows:
        r['network'] = network[r['bodyId']]
    payload = json.dumps(rows).replace('<', '\\u003c')
    html = '''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>893 个 L2 · 位置验证</title><style>
*{box-sizing:border-box}body{margin:0;background:#101923;color:#e6eef6;font:16px system-ui;padding:28px;max-width:1500px;margin:auto}h1{font-size:30px}p{line-height:1.7;color:#bfd0df}.warning{border-left:4px solid #f8c777;padding:12px;background:#26303a}input,select,button{font:inherit;padding:10px;border-radius:6px;border:1px solid #6a8299;background:#182738;color:white}main{display:grid;grid-template-columns:1.4fr 1fr;gap:24px;margin-top:24px}svg{width:100%;background:#192b39;border-radius:10px}circle{cursor:pointer;stroke:#101923;stroke-width:.8}circle:hover{stroke:white;stroke-width:3}.card{background:#1a2937;border-radius:12px;padding:20px}dt{color:#aac2d4;margin-top:10px}dd{margin:3px 0}a{color:#8ad9ff}#list{max-height:220px;overflow:auto;display:flex;flex-wrap:wrap;gap:5px}#list button{font-size:13px}.legend{font-size:14px}@media(max-width:900px){main{grid-template-columns:1fr}body{padding:16px}}</style>
<h1>893 个右眼 L2 · 逐个位置验证</h1>
<p>891 个位置可独立区分 · 2 个共用视柱 · 893 个网络地址通过 · 887 个观察到下游传播 · 当前快照 742 个具有有效深度</p>
<p class="warning">工程验证已完成；生物视野角度标定：未验证。图中坐标是我们设定的相机网格，不能据此声称果蝇真实视野方向正确。亮度到 L2 刺激也属于工程假设。</p>
<label>查找 body ID <input id="search" placeholder="例如 56150" aria-label="查找 body ID"></label>
<label>筛选 <select id="filter"><option value="all">全部</option><option value="shared">共用视柱</option><option value="silent">未观察到下游传播</option><option value="depth">快照无有效深度</option></select></label><p id="count"></p>
<main><section><svg id="map" viewBox="0 0 640 480" aria-label="逐神经元空间分布图"></svg><p class="legend">青色：可独立区分；橙色：共用视柱；灰色：当前快照无有效深度。点击点或下面的 ID 查看记录。重叠点可从 ID 列表分别选择。</p><div id="list"></div></section><section class="card"><h2 id="title"></h2><dl id="detail"></dl></section></main>
<h2>如何解读</h2><p>输入层：893 次独立 3×3 暗点刺激，调用实际 13×13 采样器；白背景和无效深度零输入。43130 与 56150 在源表共用 (25,10)，无法用本映射分开刺激。网络层另用每个神经元 120 Hz / 100 ms、seed=1 的单点注入，逐个比较连接开启/关闭；这是独立的地址及传播测试，未把局部暗点刺激当作生物反应证据。</p>
<p>RGB-D：原始深度反投影 → 外参变换 → 彩色图采样 → 平移 3 cm 的台架虚拟视点 → 最近点遮挡 → 视柱采样。SDK 投影交叉核对最大差异约 0.0000593 像素，只代表软件计算一致；不是物理测距精度。帧间约 9.44 ms 时间差、透明物体的错误深度、真实视野角度均有待专门标定。</p>
<p>独立几何面积公式核对全部 893² 响应；左右/上下翻转、缩放、平移和打乱故障均可相对当前约定被检测。它们不能判定生物学正确的朝向。</p>
<p><a href="neurons.csv">逐神经元 CSV</a> · <a href="network_neurons.json">网络原始记录</a> · <a href="summary.json">位置汇总</a> · <a href="calibration_summary.json">几何审计</a> · <a href="mutation_summary.json">故障注入</a> · <a href="SOURCES_AND_LIMITS.md">来源与限制</a> · <a href="reproducibility.json">重跑与文件指纹</a></p>
<script>const rows=PAYLOAD;const $=id=>document.getElementById(id);let selected=rows[0].bodyId;
function show(r){selected=r.bodyId;$('title').textContent='L2 · '+r.bodyId;const n=r.network;const fields={'模型索引':r.index,'源表 hex 坐标':r.hex1+', '+r.hex2,'相机网格像素':Number(r.u).toFixed(2)+', '+Number(r.v).toFixed(2),'身份 / 边界':r.identity_ok+' / '+r.inside_image,'局部刺激定位':r.isolated_position==='True'?'可独立区分':'共用位置；不能独立区分','峰值并列 ID':r.tied_bodyIds,'暗点输入率':Number(r.target_rate_hz).toFixed(4)+' Hz','当前快照有效深度':r.camera_depth_available==='True'?'有':'无','连接开启：目标 / 下游放电':n.connected.target_spikes+' / '+n.connected.downstream_spikes,'连接关闭：目标 / 下游放电':n.disconnected.target_spikes+' / '+n.disconnected.downstream_spikes,'下游传播':n.propagation_observed?'本条件下已观察到':'本条件下未观察到，不等于没有连接','生物视野标定':'UNVERIFIED'};$('detail').replaceChildren();for(const [k,v]of Object.entries(fields)){let dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=k;dd.textContent=v;$('detail').append(dt,dd)}document.querySelectorAll('circle').forEach(c=>{c.style.stroke=c.dataset.id===selected?'white':'';c.style.strokeWidth=c.dataset.id===selected?'3':''})}
function render(){let q=$('search').value.trim(),f=$('filter').value;let visible=rows.filter(r=>r.bodyId.includes(q)&&(f==='all'||f==='shared'&&r.isolated_position!=='True'||f==='silent'&&!r.network.propagation_observed||f==='depth'&&r.camera_depth_available!=='True'));$('count').textContent=visible.length+' / 893 个神经元';$('map').replaceChildren();$('list').replaceChildren();for(const r of visible){let c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('cx',r.u);c.setAttribute('cy',r.v);c.setAttribute('r',4);c.setAttribute('fill',r.isolated_position!=='True'?'#ffb75b':r.camera_depth_available==='True'?'#58d9d2':'#728397');c.dataset.id=r.bodyId;c.onclick=()=>show(r);$('map').append(c);let b=document.createElement('button');b.textContent=r.bodyId;b.onclick=()=>show(r);$('list').append(b)}if(visible.length)show(visible.find(r=>r.bodyId===selected)||visible[0]);else{$('title').textContent='没有匹配结果';$('detail').replaceChildren()}}
$('search').oninput=render;$('filter').onchange=render;render();</script></html>'''.replace('PAYLOAD',payload)
    (OUT/'index.html').write_text(html,encoding='utf-8')
    print(OUT/'index.html')

if __name__ == '__main__':
    main()
