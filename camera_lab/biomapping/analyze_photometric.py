"""Same-location screen-code/camera transfer audit, not a radiance calibration.

Gray-code phase labels are optically read and transition samples excluded.
Training, withheld midpoints and repeats are assigned in the stimulus BEFORE
capture. Monotone LUTs only use training levels. No physical gamma assumption.
"""
import csv
import hashlib
import html
import json
from pathlib import Path
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from analyze_screen import screen_transform,BASE
from geometry import project_rays,sample_rgb
from import_author_map import STATUS


def render_report(out,report):
    """Readable artifact, regenerated independently of raw-video analysis."""
    out=Path(out);channels=report['channels'];summary={k:v for k,v in report.items() if k not in ['channels','uncertainty']}
    passed=report['status']=='PASS'
    percent=lambda v:'—' if v is None else f'{100*v:.2f}%'
    channel_rows=''.join('<tr><td>'+html.escape(name)+'</td><td>'+html.escape(c['status'])+'</td><td>'+percent(c.get('holdout_max_fraction_range'))+'</td><td>'+percent(c.get('repeat_max_fraction_range'))+'</td><td>'+html.escape(str(c.get('near_flat_intervals',[])))+'</td></tr>' for name,c in channels.items())
    groups=[]
    for prefix,label in [('ROI','屏幕检查区域'),('L2','L2 神经元采样位置')]:
        part=[v for k,v in channels.items() if k.startswith(prefix) and v.get('holdout_max_fraction_range') is not None]
        if part:groups.append(f'<tr><td>{label}</td><td>{len(part)}</td><td>{percent(max(v["holdout_max_fraction_range"] for v in part))}</td><td>{percent(max(v["repeat_max_fraction_range"] for v in part))}</td></tr>')
    meta=json.loads((out/'capture.json').read_text());frame_metadata=any('actual_exposure' in t for t in meta['frames_timing'])
    text='''<!doctype html><meta charset="utf-8"><title>灰阶标定与独立验收结果</title>
<style>body{font:17px system-ui;line-height:1.7;max-width:1100px;margin:30px auto;padding:15px;background:#101923;color:#eef4fa}img{width:100%}a{color:#8bd8fa}pre{white-space:pre-wrap}table{border-collapse:collapse;width:100%;font-size:15px}th,td{border-bottom:1px solid #395064;padding:9px;text-align:left}details{margin:22px 0}.tag{color:#86ecbd}</style>
<h1>同一位置的灰阶标定与独立验收</h1>'''
    text+=f'<p class="tag">{"工程验收通过" if passed else "尚未通过验收"} · {report["frames"]:,} 帧 · {report["median_fps"]:.2f} fps · {report["duration_s"]:.2f} 秒</p>'
    text+='<p>32 档灰阶建立响应表，另外 16 档检验预测，8 次重复检查稳定性。全部误差以每个位置各自测得的黑白量程为分母；预设最大误差限为 5%。</p><table><tr><th>位置</th><th>数量</th><th>独立验收最大误差</th><th>重复测量最大偏差</th></tr>'+''.join(groups)+'</table>'
    text+='<p><strong>有效范围：</strong>这次验证的是当前屏幕与相机的数字灰阶关系。低灰阶段存在近乎平坦的区间，不能可靠反推；结果尚不代表真实光强或真实果蝇神经响应。</p>'
    text+='<img src="photometric.png" alt="训练响应曲线、保留灰阶与重复测量，以及实际采集序列">'
    text+=f'<p>光学阶段识别有效率 {report["valid_optical_fraction"]*100:.2f}%，剔除 {report["rejected_phase_frames"]} 帧不确定标签。另保存 {len(meta.get("depth_frames",[]))} 帧深度、{meta["imu_samples"]:,} 条 IMU 数据。</p>'
    text+='<p>相机设置已记录并锁定；'+('保留了逐帧曝光元数据。' if frame_metadata else '设备未提供逐帧曝光元数据，因此不能用该字段独立核对每帧曝光。')+'改变屏幕亮度、相机设置或位置后，需要重新验收。</p>'
    text+='<details><summary>逐个位置的验收数据与暗部不可可靠反推区间</summary><table><tr><th>位置 / 神经元 ID</th><th>状态</th><th>独立验收</th><th>重复偏差</th><th>近乎平坦的屏幕灰阶区间</th></tr>'+channel_rows+'</table></details>'
    text+='<details><summary>采样位置示意</summary><img src="sampling_overlay.jpg" alt="首个成功定位画面中的 L2 采样位置"></details>'
    text+='<details><summary>采集检查与范围说明</summary><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre></details>'
    text+='<p>没有用本次结果替换全脑输入，也没有把数字灰度换算为光子数或放电频率。</p><p><a href="photometric_report.json">完整报告</a> · <a href="response_lut.json">响应查表</a> · <a href="photometric_phase_samples.csv">逐阶段观测</a> · <a href="/photometric.html">重新实验</a></p>'
    (out/'index.html').write_text(text,encoding='utf8')


def gray_decode(code):
    value=int(code);shift=value>>1
    while shift:value^=shift;shift>>=1
    return value


def decode_dualrail(warp,valid_ids):
    """Local complementary pairs tolerate different brightness across the screen."""
    left=np.array([np.mean(warp[573:597,244+i*65:263+i*65]) for i in range(8)])
    right=np.array([np.mean(warp[573:597,277+i*65:296+i*65]) for i in range(8)])
    contrast=left-right;confidence=float(np.min(abs(contrast)))
    decoded=gray_decode(sum(int(b)<<i for i,b in enumerate(contrast>0)))
    return (decoded if decoded in valid_ids and confidence>20 else -1),confidence


def monotone_fit(y,weights=None):
    """Weighted pool-adjacent-violators, without using withheld samples."""
    a=np.asarray(y,float);w=np.ones(len(a)) if weights is None else np.asarray(weights,float)
    if len(a)==0 or not np.isfinite(a).all() or np.any(w<=0):raise ValueError('Bad training values')
    blocks=[]
    for i,(v,weight) in enumerate(zip(a,w)):
        blocks.append([i,i+1,float(v*weight),float(weight)])
        while len(blocks)>1 and blocks[-2][2]/blocks[-2][3]>blocks[-1][2]/blocks[-1][3]:
            b=blocks.pop();c=blocks.pop();blocks.append([c[0],b[1],c[2]+b[2],c[3]+b[3]])
    out=np.empty_like(a)
    for start,end,total,weight in blocks:out[start:end]=total/weight
    return out


def stable_indices(labels,phase_id,trim=4):
    """Use longest contiguous optical run, discarding both transition edges."""
    indices=np.flatnonzero(labels==phase_id)
    if not len(indices):return indices
    groups=np.split(indices,np.flatnonzero(np.diff(indices)>1)+1)
    group=max(groups,key=len)
    return group[trim:-trim] if len(group)>2*trim else group[:0]


def fit_channel(entries):
    train=sorted([x for x in entries if x['kind']=='train' and x['samples']>=12],key=lambda x:x['level'])
    if len(train)!=32:return {'status':'INSUFFICIENT_TRAINING_LEVELS','training_levels':len(train)}
    x=np.array([a['level'] for a in train]);raw=np.array([a['median'] for a in train]);fit=monotone_fit(raw)
    span=float(fit[-1]-fit[0])
    if span<30:return {'status':'INSUFFICIENT_CAMERA_RANGE','camera_range':span}
    tests=[a for a in entries if a['kind']=='holdout' and a['samples']>=12]
    reps=[a for a in entries if a['kind']=='repeat' and a['samples']>=12]
    errors=np.array([a['median']-np.interp(a['level'],x,fit) for a in tests])
    repeat_errors=np.array([a['median']-np.interp(a['level'],x,fit) for a in reps])
    # The inverse is only a screen-code equivalent and ambiguous on plateaus.
    vals=np.unique(fit);inverse_x=np.array([np.mean(x[fit==v]) for v in vals])
    inverse_errors=[float(np.interp(a['median'],vals,inverse_x)-a['level']) for a in tests if fit[0]<=a['median']<=fit[-1]]
    passed=len(tests)==16 and len(reps)==8 and np.max(abs(errors))/span<=.05 and np.max(abs(repeat_errors))/span<=.05
    return dict(status='PASS_ENGINEERING_TRANSFER' if passed else 'FAIL_OR_INCOMPLETE_TRANSFER',
        gray_codes=x.tolist(),camera_medians=raw.tolist(),monotone_camera_values=fit.tolist(),
        black_camera_value=float(fit[0]),white_camera_value=float(fit[-1]),camera_range=span,
        holdout_levels=len(tests),repeat_levels=len(reps),
        holdout_rmse_fraction_range=float(np.sqrt(np.mean(errors**2))/span) if len(errors) else None,
        holdout_max_fraction_range=float(np.max(abs(errors))/span) if len(errors) else None,
        repeat_max_fraction_range=float(np.max(abs(repeat_errors))/span) if len(repeat_errors) else None,
        inverse_screen_code_mae=float(np.mean(abs(np.array(inverse_errors)))) if inverse_errors else None,
        near_flat_intervals=[[int(x[i]),int(x[i+1])] for i in range(len(x)-1) if fit[i+1]-fit[i]<1.],
        monotonic_adjustment_max_camera_units=float(np.max(abs(raw-fit))),
        normalization='(camera_value - same_ROI_black) / same_ROI_range; NOT linear physical luminance',
        threshold='Predeclared engineering: held-out and repeat max errors <=5% of camera dynamic range')


def analyze(directory):
    out=Path(directory);meta=json.loads((out/'capture.json').read_text())
    if not (out/'display_log.json').exists():raise ValueError('Missing actual display log; incomplete acquisition')
    display=json.loads((out/'display_log.json').read_text())
    if display.get('protocol')!='photometric' or display.get('bit_encoding') not in ['gray','gray_dualrail_v2']:raise ValueError('Wrong stimulus protocol')
    phases=display['phases'];valid_ids={p['id'] for p in phases}
    rows=[r for r in json.loads((BASE/'data/malecns_author_crosswalk.json').read_text()) if r['status']==STATUS]
    uv,visible=project_rays([r['ray_head_xyz'] for r in rows],meta['color_intrinsics'])
    ids=[r['bodyId'] for r,v in zip(rows,visible) if v];uv=uv[visible]
    positions=[(x,y) for y in [250,350,450] for x in [300,500,700]]
    names=[f'ROI_{x}_{y}' for x,y in positions]+[f'L2_{i}' for i in ids]
    cap=cv2.VideoCapture(str(out/'rgb.avi'));observations=[];labels=[];timings=[];marker_counts=[];confidence=[];unrecognized=0;reference_values=[]
    try:
        for timing in meta['frames_timing']:
            ok,bgr=cap.read()
            if not ok:break
            gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY);H,n=screen_transform(gray)
            vals=np.full(len(names),np.nan);phase=-1;conf=0.;refs=[np.nan,np.nan]
            if H is not None:
                warp=cv2.warpPerspective(gray,H,(1000,700))
                black=float(np.median(warp[112:143,309:351]));white=float(np.median(warp[112:143,399:441]))
                if white-black>20:
                    if display['bit_encoding']=='gray_dualrail_v2':phase,conf=decode_dualrail(warp,valid_ids)
                    else:
                        code_values=np.array([np.mean(warp[573:597,248+i*65:277+i*65]) for i in range(8)])
                        levels=(code_values-black)/(white-black);conf=float(np.min(abs(levels-.5)))
                        binary=sum(int(b)<<i for i,b in enumerate(levels>.5));decoded=gray_decode(binary)
                        if decoded in valid_ids and conf>.15:phase=decoded
                    if phase<0:unrecognized+=1
                    rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB).astype(float)
                    luminance=rgb@np.array([.2126,.7152,.0722]);plane=cv2.warpPerspective(luminance,H,(1000,700))
                    refs=[float(np.mean(plane[112:143,309:351])),float(np.mean(plane[112:143,399:441]))]
                    vals[:9]=[np.mean(plane[y-20:y+20,x-20:x+20]) for x,y in positions]
                    xy=cv2.perspectiveTransform(uv.astype(np.float32)[None],H)[0]
                    inside=(xy[:,0]>225)&(xy[:,0]<775)&(xy[:,1]>205)&(xy[:,1]<495)
                    rayvalues=sample_rgb(rgb,uv,np.ones(len(uv),bool))@np.array([.2126,.7152,.0722])
                    vals[9:][inside]=rayvalues[inside]
                    if not (out/'sampling_overlay.jpg').exists():
                        overlay=bgr.copy()
                        for x,y in uv[inside]:cv2.circle(overlay,(round(x),round(y)),4,(0,200,255),1)
                        cv2.imwrite(str(out/'sampling_overlay.jpg'),overlay)
            observations.append(vals);labels.append(phase);timings.append(timing);marker_counts.append(n);confidence.append(conf);reference_values.append(refs)
    finally:cap.release()
    if len(observations)<2:raise ValueError('Fewer than two recorded video frames')
    values=np.array(observations);labels=np.array(labels);times=np.array([t['color_ms'] for t in timings])/1000;times-=times[0]
    ref_median=np.nanmedian(np.array(reference_values)[(times>.5)&(labels>=0)],axis=0)
    optical_reference=dict(black_camera=float(ref_median[0]),white_camera=float(ref_median[1]),
                           method='Median of independent fixed black/white patches during calibration; Rec.709 weighted camera codes')
    eligible=np.mean(np.isfinite(values),axis=0)>.95
    table=[];channels={}
    for i,name in enumerate(names):
        if not eligible[i]:continue
        entries=[]
        for p in phases:
            if p['kind'] not in ['train','holdout','repeat']:continue
            index=stable_indices(labels,p['id']);a=values[index,i];a=a[np.isfinite(a)]
            entry=dict(channel=name,phase_id=p['id'],kind=p['kind'],level=p['level'],samples=len(a),
                       median=float(np.median(a)) if len(a) else None,
                       mad=float(np.median(abs(a-np.median(a)))) if len(a) else None)
            entries.append(entry);table.append(entry)
        channels[name]=fit_channel(entries)
    intervals=np.diff(times);frameids=np.array([r['color_frame_number'] for r in timings])
    checks=dict(all_training_and_holdout_phases_observed=all(len(stable_indices(labels,p['id']))>=12 for p in phases if p['kind'] in ['train','holdout','repeat']),
                optical_valid_over_95pct=bool(np.mean(labels>=0)>.95),no_camera_frame_gaps=bool(np.all(np.diff(frameids)==1)),
                no_queue_drops=meta['queue_drops']==0,browser_visible=all(r['visibility']=='visible' for r in display['frames']),
                not_aborted=not display.get('aborted',False),all_nine_ROIs_observed=sum(k.startswith('ROI') for k in channels)==9,
                mapped_L2_observed=any(k.startswith('L2') for k in channels))
    report=dict(status='PASS' if all(checks.values()) and channels and all(v['status']=='PASS_ENGINEERING_TRANSFER' for v in channels.values()) else 'CHECK_FAILURES',
        scope='Screen digital code to camera code response; NOT physical radiance or fly photoreceptor calibration',
        frames=len(values),median_fps=float(1/np.median(intervals)),duration_s=float(times[-1]),
        valid_optical_fraction=float(np.mean(labels>=0)),rejected_phase_frames=int(np.sum(labels<0)),unrecognized_or_low_confidence=unrecognized,
        same_location_ROIs=sum(k.startswith('ROI') for k in channels),mapped_L2=sum(k.startswith('L2') for k in channels),
        checks=checks,channels=channels,source_capture=str(out),
        biological_response_validated=False,physical_luminance_calibrated=False,brain_input_replaced=False,
        uncertainty=['Same-location black/white correction reduces spatial-reference mismatch, but combined display/camera transfer cannot identify their separate gamma curves',
                     'No photometer or radiometrically calibrated camera; inverse LUT returns equivalent screen code, not photons or true luminance',
                     'Near-flat intervals cannot be reliably inverted; no out-of-range extrapolation authorized',
                     'Model brightness-to-Hz conversion remains unvalidated; existing temporal results are not automatically relabeled',
                     'Different screen settings, exposure, pose or ambient light require revalidation'],
        protocol_sha256=hashlib.sha256((out/'display_log.json').read_bytes()).hexdigest())
    np.savez_compressed(out/'photometric_samples.npz',times_s=times,phase_id=labels,channels=np.array(names),camera_values=values)
    if table:
        with (out/'photometric_phase_samples.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=table[0]);w.writeheader();w.writerows(table)
    (out/'photometric_report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    (out/'response_lut.json').write_text(json.dumps(dict(scope=report['scope'],channels=channels,optical_reference=optical_reference,capture_settings=meta['exposure_settings'],capture_intrinsics=meta['color_intrinsics']),indent=2),encoding='utf8')
    fig,axes=plt.subplots(2,1,figsize=(11,8),layout='constrained')
    central='ROI_500_350'
    if central in channels and channels[central]['status'].startswith(('PASS','FAIL')):
        c=channels[central];axes[0].plot(c['gray_codes'],c['monotone_camera_values'],label='Training LUT')
        for kind,marker in [('holdout','o'),('repeat','x')]:
            part=[a for a in table if a['channel']==central and a['kind']==kind and a['median'] is not None]
            axes[0].scatter([a['level'] for a in part],[a['median'] for a in part],label=kind,marker=marker)
        axes[0].legend()
    axes[0].set(xlabel='Screen digital gray code',ylabel='Camera code value',title='Same central ROI: frozen training LUT vs held-out levels')
    axes[1].plot(times,values[:,4]);axes[1].set(xlabel='Camera time (s)',ylabel='Measured camera code',title='Actual randomized gray sequence')
    fig.savefig(out/'photometric.png',dpi=140);plt.close(fig)
    render_report(out,report)
    return {k:v for k,v in report.items() if k not in ['channels','uncertainty']}


if __name__=='__main__':
    import sys
    print(json.dumps(analyze(Path(sys.argv[1])),indent=2))
