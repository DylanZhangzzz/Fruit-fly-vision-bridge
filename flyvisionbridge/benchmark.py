"""Frozen offline L2 / FlyDrones sensory encoder / pretrained Flyvis comparison.

python -m flyvisionbridge.benchmark --flyvis-root outputs/flyvis-data --output outputs/benchmark
"""
import argparse
import csv
import importlib.metadata
import json
from pathlib import Path
import platform
import time
import numpy as np
from .benchmark_core import (PROTOCOL, protocol, sha_file, stimulus, synthetic_intrinsics,
    sample_columns, l2_response, interpolation_map, interpolate_responses)
from .bridge import MAPPING

ROOT=Path(__file__).resolve().parents[1]


def write_json(path,obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')


def capture_movie(folder, seconds, start, dt):
    """Explicit local screen-capture replay. No serials/room frames in public reports."""
    import cv2
    folder=Path(folder)
    meta=json.loads((folder/'capture.json').read_text(encoding='utf8'))
    k=meta['color_intrinsics']
    if any(k.get('coeffs',[])):
        raise ValueError('Capture RGB must first be rectified; distortion cannot be ignored')
    timing=meta['frames_timing']
    if len({x['color_clock'] for x in timing})!=1:
        raise ValueError('Mixed camera timestamp domains')
    src=np.array([x['color_ms'] for x in timing])/1000
    src-=src[0]
    if not np.all(np.diff(src)>0):raise ValueError('Nonmonotonic capture timestamps')
    target=start+np.arange(round(seconds/dt))*dt
    if start<0 or target[-1]>src[-1]:raise ValueError('Replay interval outside recording')
    indices=np.searchsorted(src,target,side='right')-1
    if np.any(target-src[indices]>.05):raise ValueError('Source gap exceeds 50ms; refusing silent hold')
    cap=cv2.VideoCapture(str(folder/'rgb.avi'));selected={}
    wanted=set(indices.tolist())
    try:
        for i in range(int(indices.max())+1):
            ok,bgr=cap.read()
            if not ok:raise RuntimeError('Video shorter than timestamps')
            if i in wanted:selected[i]=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
    finally:cap.release()
    frames=np.stack([selected[i] for i in indices])
    provenance=dict(kind='LOCAL_CAMERA_CODE_REPLAY',rgb_sha256=sha_file(folder/'rgb.avi'),
        timing_sha256=sha_file(folder/'capture.json'),start_s=start,duration_s=seconds,
        source_clock=timing[0]['color_clock'],resampling='causal zero-order hold at 50 Hz',
        maximum_hold_age_s=float(np.max(target-src[indices])),
        photometry='Uncorrected weighted camera code, no physical radiance or physiology claim',
        initialization='Model starts from protocol gray state; unrecorded prior adaptation unknown')
    return target-start,frames,k,provenance


def trace_metrics(trace,t,p):
    trace=np.asarray(trace,float)
    if not np.isfinite(trace).all():return dict(status='NONFINITE')
    baseline=trace[t<p['onset_s']].mean() if np.any(t<p['onset_s']) else trace[0]
    delta=trace-baseline
    active=(t>=p['onset_s'])&(t<p['offset_s'])
    peak_ids=np.flatnonzero(t>=p['onset_s'])
    peak=int(peak_ids[np.argmax(abs(delta[peak_ids]))]) if len(peak_ids) else 0
    return dict(status='FINITE',baseline=float(baseline),minimum=float(trace.min()),maximum=float(trace.max()),
        peak_delta=float(delta[peak]),peak_sample_time_s=float(t[peak]),
        mean_abs_active_delta=float(np.mean(abs(delta[active]))) if active.any() else 0.)


def repeated(run,frames,count):
    results=[run(frames) for _ in range(count)]
    first=results[0]
    diffs=[]
    for other in results[1:]:
        for key,val in first['traces'].items():
            diffs.append(float(np.max(abs(val-other['traces'][key]))))
        if 'l2' in first:
            good=np.isfinite(first['l2'])
            if not np.array_equal(good,np.isfinite(other['l2'])):
                raise RuntimeError('Repeat spatial support changed')
            if good.any():diffs.append(float(np.max(abs(first['l2'][good]-other['l2'][good]))))
    return first,dict(wall_seconds=[r['seconds'] for r in results],
        mean_wall_seconds=float(np.mean([r['seconds'] for r in results])),
        repeat_max_absolute_difference=max(diffs,default=0),finite_fraction=first['finite_fraction'])


def render_report(out,report,plot):
    from html import escape
    rows=''.join(f"<tr><td>{escape(c['case'])}</td><td>{escape(m)}</td><td>{v['mean_wall_seconds']:.3f}</td><td>{v['finite_fraction']:.3f}</td><td>{v['repeat_max_absolute_difference']:.3g}</td></tr>"
        for c in report['cases'] for m,v in c['models'].items())
    payload=json.dumps(plot,ensure_ascii=False,allow_nan=False).replace('</','<\\/')
    support={}
    for c in report['cases']:
        key='真实相机录像' if c['case']=='camera_replay' else '合成虚拟相机'
        support[key]=(c['camera_observed_columns'],c['flyvis_interpolated_columns'])
    support_rows=''.join(f'<tr><td>{k}</td><td>{a}</td><td>{b}</td></tr>' for k,(a,b) in support.items())
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>统一视觉输入基准</title>
<style>body{background:#101923;color:#eef4fa;font:16px system-ui;line-height:1.7;margin:0}main{max-width:1120px;margin:auto;padding:28px}a{color:#83d7e0}.note{background:#223041;border-left:4px solid #e5ac58;padding:16px}.cards{display:flex;gap:12px;flex-wrap:wrap}.card{background:#1c2b3b;padding:16px;flex:1}select{padding:9px;background:#203448;color:white;max-width:100%}canvas{display:block;background:white;width:100%;margin:15px 0}.scroll{max-height:450px;overflow:auto}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #3b5064;padding:8px;text-align:left}small{color:#b1c4d6}</style><main>
<p>Fruit-fly-vision-bridge · 固定参数 · 离线输入 · 协议 __VERSION__</p><h1>同一批图像，三种视觉响应方法</h1>
<div class="note"><b>这是工程基准和响应预测，未新增真实神经响应验证。</b>三者共享 RGB 帧与时间轴，保留各自采样网格和输出单位。FlyDrones 测的是官方感觉编码器；Flyvis 运行官方预训练网络；L2 使用固定论文参数。未模拟全脑或输出控制指令。</div>
<div class="cards"><div class="card">__COUNT__ 组输入<br>每组重复 __REPEATS__ 次</div><div class="card">Flyvis<br>45,669 神经元 / 模型 000</div><div class="card">空间桥接<br>保留全部 893 个 MaleCNS ID</div></div>
<p>L2：有效电压状态代理，任意单位；Flyvis：网络原生电压状态，任意单位；FlyDrones：工程设定的 Poisson 输入率 Hz。没有跨模型原始幅度误差排名。运行耗时不等于神经反应延迟，也不代表全脑性能比较。</p>
<p>Flyvis L2 可读出到同一图像位置，但这只是<b>图像空间插值</b>，不是 Flyvis 细胞和 MaleCNS ID 的生物身份对应。超出相机、缺失方向、超出 Flyvis 网格的位置均保留未知。</p>
<table><thead><tr><th>输入几何</th><th>相机内 L2 ID</th><th>同时支持 Flyvis 图像插值的 ID</th></tr></thead><tbody>__SUPPORT__</tbody></table>
<label>刺激 <select id="case"></select></label> <label>通道 <select id="channel"></select></label>
<p id="detail"></p><canvas id="trace" width="1100" height="460"></canvas><small>每次只显示一种方法的原生单位。时间点按各方法约定显示；闪光峰值只具备本基准 20 ms 采样精度。平均值仅覆盖该方法有效采样点。</small>
<h2>运行与重复性</h2><div class="scroll"><table><thead><tr><th>输入</th><th>方法</th><th>平均耗时 / s</th><th>有效输出有限值比例</th><th>重复最大差异</th></tr></thead><tbody>__ROWS__</tbody></table></div>
<h2>如何解读</h2><ul><li>移动边缘和条纹用于观察方向通道，逼近刺激用于观察编码响应。未实现的能力不记为“失败”。</li><li>L2 不提供运动方向/逼近检测通道；FlyDrones 编码器不提供 L2 生理响应；Flyvis 本次仅导出指定视觉细胞类型。</li><li>方向对比保存在 direction_diagnostics.json；这是各通道的相对响应，不是依据结果训练的分类器或跨模型准确率。</li><li>模型 000 在看结果前固定；没有选择最好模型、拟合增益、对齐峰值或训练新权重。</li><li>真实录像回放若存在，输入是相机码值。未测光子数；IMU/深度未用于本轮评分。其曲线不能视为生理实测。</li></ul>
<p><a href="report.json">完整报告</a> · <a href="protocol.json">冻结协议</a> · <a href="metrics.csv">通道指标</a> · <a href="spatial_columns.csv">逐 ID 空间支持</a> · <a href="spatial_weights.npz">空间插值权重</a> · <a href="direction_diagnostics.json">方向对比</a></p>
<footer><h2>来源与许可</h2><p>本项目贡献 © 2026 Fruit-fly-vision-bridge contributors；原创代码采用 <a href="https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge/blob/main/LICENSE">MIT</a>，无担保，可依许可复制、修改和再分发。<a href="https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge">可修改源代码</a>与 <a href="https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge/blob/main/THIRD_PARTY_NOTICES.md">完整署名</a>。</p><p>MaleCNS 视柱来源：Reiser lab（GPLv3）；视线来源：Arthur Zhao / Reiser Lab, Janelia Research Campus，<a href="https://github.com/artxz/eyemap-archive/tree/503c7f055d5491a48b60b49ade8c71798d24d8f1">eyemap-archive</a>（<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>）。2026-09-27 修改：右眼筛选、ID/视柱连接、角度转换、图像投影、插值及预测。两类数据各保留来源许可；无作者背书。</p><p>引用：<a href="https://doi.org/10.1101/2022.12.14.520178">Zhao et al.</a>；<a href="https://doi.org/10.1038/s41586-025-08746-0">Nern et al. 2025</a>；<a href="https://doi.org/10.1038/s41586-024-07939-3">Lappalainen et al. 2024 / Flyvis</a>；<a href="https://doi.org/10.1016/j.cub.2024.11.064">Pang et al. 2025 / L2 方程</a>；<a href="https://github.com/SpikeCalls/FlyDrones">SpikeCalls / FlyDrones</a>。Flyvis 和 FlyDrones 软件为 MIT，单独安装；权重与原始录像不包含在可分享报告中。</p></footer>
<script>const d=__DATA__;const c=document.querySelector('#case'),ch=document.querySelector('#channel');c.innerHTML=d.map((x,i)=>`<option value="${i}">${x.name}</option>`).join('');function refresh(){ch.innerHTML=Object.keys(d[+c.value].traces).map(k=>`<option>${k}</option>`).join('');draw()}function draw(){const s=d[+c.value],a=s.traces[ch.value],t=s.times[ch.value.split(' / ')[0]],canvas=document.querySelector('#trace'),ctx=canvas.getContext('2d');document.querySelector('#detail').textContent=s.name+' · '+ch.value+' · '+s.units[ch.value.split(' / ')[0]];ctx.clearRect(0,0,1100,460);let lo=Math.min(...a),hi=Math.max(...a),pad=(hi-lo)*.12||.01;lo-=pad;hi+=pad;ctx.strokeStyle='#c7d5df';ctx.strokeRect(85,40,960,340);ctx.fillStyle='#172b3b';ctx.font='16px system-ui';ctx.fillText(hi.toPrecision(4),5,52);ctx.fillText(lo.toPrecision(4),5,382);ctx.fillText('0 s',85,410);ctx.fillText(t.at(-1).toFixed(2)+' s',1000,410);ctx.strokeStyle='#138d91';ctx.lineWidth=2;ctx.beginPath();a.forEach((v,i)=>{const x=85+t[i]/t.at(-1)*960,y=40+(hi-v)/(hi-lo)*340;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()}c.onchange=refresh;ch.onchange=draw;refresh();</script></main></html>'''
    for key,value in {'__DATA__':payload,'__ROWS__':rows,'__SUPPORT__':support_rows,'__VERSION__':report['protocol']['version'],'__COUNT__':str(len(report['cases'])),'__REPEATS__':str(report['protocol']['repeat_runs'])}.items():html=html.replace(key,value)
    (out/'index.html').write_text(html,encoding='utf8')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--flyvis-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--cases',nargs='+',help='Explicit subset; logged as a protocol override')
    ap.add_argument('--capture-run',type=Path)
    ap.add_argument('--replay-seconds',type=float,default=4.)
    ap.add_argument('--replay-start',type=float,default=0.)
    args=ap.parse_args()
    if args.output.exists():ap.error('Output exists; choose a new directory')
    if args.replay_seconds<=0 or args.replay_start<0:ap.error('Replay duration must be positive and start nonnegative')
    p=protocol()
    if args.cases:
        if any(c not in p['cases'] for c in args.cases):ap.error('Unknown case')
        p['requested_subset']=args.cases
    args.output.mkdir(parents=True)
    try:
        execute(args,p)
    except Exception as error:
        path=args.output/'report.json'
        report=json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
        report.update(status='FAILED',error_type=type(error).__name__,error=str(error))
        write_json(path,report)
        raise


def execute(args,p):
    # Save before obtaining any test response, including on a failed run.
    write_json(args.output/'protocol.json',p)
    report=dict(status='RUNNING',protocol=p,protocol_sha256=sha_file(PROTOCOL),run_protocol_sha256=sha_file(args.output/'protocol.json'),
        mapping_sha256=sha_file(MAPPING),sources=json.loads(Path(__file__).with_name('benchmark_sources.json').read_text()),
        runtime=dict(python=platform.python_version(),platform=platform.system(),processor=platform.processor()),
        models={},cases=[],biological_validation=False,brain_input_replaced=False)
    write_json(args.output/'report.json',report)
    from .benchmark_adapters import FlyvisAdapter,FlyDronesAdapter
    print('Initializing pinned upstream models',flush=True)
    flyvis=FlyvisAdapter(args.flyvis_root,p);drones=FlyDronesAdapter(p)
    report['models']=dict(flyvis=flyvis.metadata,flydrones=drones.metadata,l2=p['l2'])
    report['runtime']['packages']={n:importlib.metadata.version(n) for n in ['numpy','scipy','torch','torchvision','flyvis','flydrones','datamate','h5py']}
    metrics=[];plot=[];column_rows=[];weights={};outputs={}
    names=list(args.cases or p['cases'])+(['camera_replay'] if args.capture_run else [])
    for name in names:
        print('Running',name,flush=True)
        if name=='camera_replay':
            t,rgb,k,source=capture_movie(args.capture_run,args.replay_seconds,args.replay_start,p['frame_dt_s'])
        else:
            t,rgb=stimulus(name,p);k=synthetic_intrinsics(p);source=dict(kind='SYNTHETIC')
        frame_hash=__import__('hashlib').sha256(rgb.tobytes()).hexdigest()
        def run_l2(frames):
            start=time.perf_counter();rows,uv,samples=sample_columns(frames,k)
            response=l2_response(samples,p['frame_dt_s'],p['l2'])
            valid=np.isfinite(samples).all(axis=0)
            if not valid.any():raise ValueError('No mapped rays in camera view')
            return dict(traces={'L2':response[:,valid].mean(axis=1)},l2=response,samples=samples,uv=uv,rows=rows,
                finite_fraction=float(np.isfinite(response[:,valid]).mean()),seconds=time.perf_counter()-start)
        l2,lm=repeated(run_l2,rgb,p['repeat_runs'])
        fv,fm=repeated(flyvis.run,rgb,p['repeat_runs'])
        fd,dm=repeated(drones.run,rgb,p['repeat_runs'])
        receptor_uv=flyvis.receptor_positions(rgb.shape[1:3])
        vertices,bary=interpolation_map(receptor_uv,l2['uv'])
        mapped=interpolate_responses(fv['l2'],vertices,bary)
        geometry_key='camera' if name=='camera_replay' else 'synthetic'
        if geometry_key+'_vertices' not in weights:
            weights[geometry_key+'_vertices']=vertices;weights[geometry_key+'_weights']=bary
            weights[geometry_key+'_receptor_uv']=receptor_uv;weights[geometry_key+'_target_uv']=l2['uv']
            for i,row in enumerate(l2['rows']):
                column_rows.append(dict(geometry=geometry_key,bodyId=row['bodyId'],reference_id=row.get('reference_id'),
                    mapping_status=row['status'],camera_observed=bool(np.isfinite(l2['uv'][i]).all()),
                    flyvis_image_interpolation_supported=bool(np.isfinite(bary[i]).all()),
                    pixel_x=float(l2['uv'][i,0]) if np.isfinite(l2['uv'][i,0]) else None,
                    pixel_y=float(l2['uv'][i,1]) if np.isfinite(l2['uv'][i,1]) else None,
                    identity_claim='NONE: image-space readout only'))
        np.savez_compressed(args.output/(name+'.npz'),frame_time_s=t,response_time_s=t+p['frame_dt_s'],
            body_ids=np.asarray([str(r['bodyId']) for r in l2['rows']]),camera_code_samples=l2['samples'],
            l2_effective_state=l2['l2'],flyvis_L2_native=fv['l2'],flyvis_receptor_input=fv['receptors'],
            flyvis_L2_at_body_image_positions=mapped,**{'flydrones_'+key:val for key,val in fd['traces'].items()})
        if name!='camera_replay': # public artifact never includes room images
            from PIL import Image
            Image.fromarray(rgb[int(.6/p['frame_dt_s'])]).save(args.output/(name+'.png'))
        case=dict(case=name,input_rgb_sha256=frame_hash,input_shape=list(rgb.shape),source=source,intrinsics=k,
            camera_observed_columns=int(np.isfinite(l2['uv']).all(axis=1).sum()),
            flyvis_interpolated_columns=int(np.isfinite(bary).all(axis=1).sum()),
            models=dict(l2=lm,flyvis=fm,flydrones=dm))
        report['cases'].append(case)
        signals=dict(l2=l2['traces'],flyvis=fv['traces'],flydrones=fd['traces'])
        units=dict(l2=p['l2']['output'],flyvis=flyvis.unit,flydrones=drones.unit)
        times=dict(l2=t+p['frame_dt_s'],flyvis=t+p['frame_dt_s'],flydrones=t)
        for model,traces in signals.items():
            for channel,a in traces.items():
                m=trace_metrics(a,times[model],p)
                if name=='camera_replay':m['status']='DESCRIPTIVE_REPLAY_NO_STIMULUS_LABELS'
                metrics.append(dict(case=name,model=model,channel=channel,unit=units[model],**m))
        plot_traces={m+' / '+key:v.tolist() for m,traces in signals.items() for key,v in traces.items()}
        common=np.flatnonzero(np.isfinite(bary).all(axis=1))
        # Three image-central examples are a display choice, never response-selected.
        center=np.array([k['ppx'],k['ppy']])
        example_ids=common[np.argsort(np.linalg.norm(l2['uv'][common]-center,axis=1))[:3]]
        for i in example_ids:
            body=str(l2['rows'][i]['bodyId'])
            plot_traces['l2 / body '+body]=l2['l2'][:,i].tolist()
            plot_traces['flyvis / image readout at body '+body]=mapped[:,i].tolist()
        plot.append(dict(name=name,units=units,times={m:v.tolist() for m,v in times.items()},
            traces=plot_traces,spatial_examples=[dict(bodyId=str(l2['rows'][i]['bodyId']),pixel_uv=l2['uv'][i].tolist()) for i in example_ids]))
        outputs[name]=signals
        write_json(args.output/'report.json',report)
        print('  supported camera/Flyvis:',case['camera_observed_columns'],case['flyvis_interpolated_columns'],flush=True)
    for filename,rows in [('metrics.csv',metrics),('spatial_columns.csv',column_rows)]:
        with (args.output/filename).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    np.savez_compressed(args.output/'spatial_weights.npz',**weights)
    diagnostics=[]
    for forward,reverse in [('grating_right','grating_left'),('edge_right','edge_left'),('edge_down','edge_up'),('loom','recede')]:
        if forward not in outputs or reverse not in outputs:continue
        for model in ['flyvis','flydrones']:
            for channel,a in outputs[forward][model].items():
                def magnitude(x):
                    start=int(p['onset_s']/p['frame_dt_s']);end=int(p['offset_s']/p['frame_dt_s'])
                    return float(np.mean(abs(x[start:end]-np.mean(x[:start]))))
                x,y=magnitude(a),magnitude(outputs[reverse][model][channel])
                diagnostics.append(dict(pair=forward+'/'+reverse,model=model,channel=channel,
                    response_first=x,response_second=y,contrast=(x-y)/(x+y) if x+y>1e-12 else None))
    write_json(args.output/'direction_diagnostics.json',diagnostics)
    report['status']='COMPLETED_PREDICTIONS_AND_ENGINEERING_DIAGNOSTICS'
    report['code_sha256']={f.name:sha_file(f) for f in Path(__file__).parent.glob('benchmark*.py')}
    write_json(args.output/'report.json',report);write_json(args.output/'plot_data.json',plot)
    render_report(args.output,report,plot)
    print('Report:',args.output/'index.html',flush=True)


if __name__=='__main__':main()
