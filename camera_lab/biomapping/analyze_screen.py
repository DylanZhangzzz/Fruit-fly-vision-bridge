"""Analyze optical screen timing and feed captured signals to frozen L2 dynamics.

Monitor code values / camera values are not calibrated radiance. No neuronal
measurements are made in this experiment; L2 traces remain predictions.
"""
import csv
import json
from pathlib import Path
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from geometry import project_rays,sample_rgb
from import_author_map import STATUS
from validate_l2_dynamics import PARAMS

BASE=Path(__file__).resolve().parent
CENTERS=np.array([[100,90],[900,90],[900,610],[100,610]],float)
DETECTOR=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))


def screen_transform(rgb):
    corners,ids,_=DETECTOR.detectMarkers(rgb)
    if ids is None:return None,0
    src=[];dst=[];used=[]
    for c,i in zip(corners,ids.flatten()):
        if i>3:continue
        src.extend(c[0]);x,y=CENTERS[i]
        dst.extend([[x-35,y-35],[x+35,y-35],[x+35,y+35],[x-35,y+35]])
        used.append(int(i))
    if len(set(used))<3:return None,len(set(used))
    # Threshold in 1000x700 canonical screen pixels (~2 camera pixels here).
    H,mask=cv2.findHomography(np.array(src),np.array(dst),cv2.RANSAC,6.)
    if H is None or mask.sum()<10:return None,len(set(used))
    return H,len(set(used))


def recurrent_prediction(times,contrast):
    """Fixed published parameters, small integration steps, causal sample hold.

    No extra 16.7 ms delay is claimed here; these predictions are conditional on
    observed frames. Cannot recover the unobserved signal between exposures.
    """
    p=PARAMS;v=np.zeros(contrast.shape[1]);y=v.copy();output=np.full_like(contrast,np.nan)
    output[0]=0
    for i in range(1,len(times)):
        dt=times[i]-times[i-1]
        if not 0<dt<.1:
            v[:]=0;y[:]=0;continue
        c=contrast[i-1];good=np.isfinite(c);v[~good]=0;y[~good]=0
        n=max(1,int(np.ceil(dt/.001)));h=dt/n
        drive=np.where(good,c,0)*np.where(c>0,p['input_light'],p['input_dark'])
        for _ in range(n):
            dv=(-v-p['w']*y-drive)/p['tv']
            dy=(-y+v*np.where(v>0,1-p['g'],p['g']))/p['ty']
            v+=dv*h;y+=dy*h
        output[i,good]=v[good]
    return output


def analyze(out):
    out=Path(out);meta=json.loads((out/'capture.json').read_text())
    display=json.loads((out/'display_log.json').read_text()) if (out/'display_log.json').exists() else None
    rows=json.loads((BASE/'data/malecns_author_crosswalk.json').read_text())
    rows=[r for r in rows if r['status']==STATUS]
    rays=np.array([r['ray_head_xyz'] for r in rows]);uv,visible=project_rays(rays,meta['color_intrinsics'])
    sample_idx=np.flatnonzero(visible);uv=uv[visible];ids=[rows[i]['bodyId'] for i in sample_idx]
    cap=cv2.VideoCapture(str(out/'rgb.avi'));records=[];samples=[];Hs=[];annotated=False
    try:
        for timing in meta['frames_timing']:
            ok,bgr=cap.read()
            if not ok:break
            gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
            H,nmarks=screen_transform(gray)
            record=dict(**timing,markers=nmarks,phase_id=None,center=None,black=None,white=None)
            neural=np.full(len(ids),np.nan)
            if H is not None:
                warp=cv2.warpPerspective(gray,H,(1000,700))
                black=float(np.median(warp[112:143,309:351]));white=float(np.median(warp[112:143,399:441]))
                if white-black>20:
                    normalize=lambda a:(float(np.mean(a))-black)/(white-black)
                    bits=[np.mean(warp[573:597,248+i*65:277+i*65])>(black+white)/2 for i in range(8)]
                    phase_id=sum(int(b)<<i for i,b in enumerate(bits))
                    record.update(phase_id=phase_id,center=normalize(warp[280:420,400:600]),black=black,white=white)
                    for j,x in enumerate([300,500,700]):record[f'position_{j}']=normalize(warp[310:390,x-15:x+15])
                    pixels=cv2.perspectiveTransform(uv.astype(np.float32)[None],H)[0]
                    inside=(pixels[:,0]>215)&(pixels[:,0]<785)&(pixels[:,1]>195)&(pixels[:,1]<505)
                    luminance=sample_rgb(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB).astype(float),uv,np.ones(len(uv),bool))@np.array([.2126,.7152,.0722])
                    # Reference patches normalize camera intensity range only;
                    # they do not linearize display gamma or spectral response.
                    neural[inside]=(luminance[inside]-black)/(white-black)
                    if not annotated:
                        frame=bgr.copy()
                        for x,y in uv[inside]:cv2.circle(frame,(round(x),round(y)),4,(0,200,255),1)
                        cv2.imwrite(str(out/'sampling_overlay.jpg'),frame)
                        cv2.imwrite(str(out/'rectified_screen.png'),warp);annotated=True
            records.append(record);samples.append(neural);Hs.append(H is not None)
    finally:cap.release()
    if not records:raise ValueError('No decoded video frames')
    times=np.array([r['color_ms'] for r in records])/1000;times-=times[0]
    spacing=np.diff(times);positive=spacing[spacing>0]
    signal=np.array([r['center'] if r['center'] is not None else np.nan for r in records])
    phases=np.array([r['phase_id'] if r['phase_id'] is not None else -1 for r in records])
    valid=np.isfinite(signal)
    values=np.array(samples);baseline_mask=valid&(phases==0)
    enough=bool(baseline_mask.sum()>=15)
    baseline=np.full(len(ids),np.nan)
    for j in range(len(ids)):
        a=values[baseline_mask,j];a=a[np.isfinite(a)]
        if len(a)>=15:baseline[j]=np.median(a)
    eligible=np.isfinite(baseline)&(baseline>.05)&(np.mean(np.isfinite(values),axis=0)>.90)
    contrast=(values[:,eligible]-baseline[eligible])/baseline[eligible]
    predictions=recurrent_prediction(times,contrast) if eligible.any() else np.empty((len(times),0))
    np.savez_compressed(out/'l2_predictions.npz',times_s=times,bodyIds=np.array(ids)[eligible],
                        contrast=contrast,effective_voltage=predictions,source_pixel_values=values[:,eligible])
    metrics=[]
    # Presentation quality comes from RAF requests, not monitor emission times.
    raf_times=np.array([f['elapsed_s'] for f in display['frames']]) if display else np.array([])
    raf_intervals=np.diff(raf_times)
    hidden_frames=sum(f.get('visibility')!='visible' for f in display['frames']) if display else None
    if display:
        for p in display['phases']:
            mask=valid&(phases==p['id']);tt=times[mask];ss=signal[mask]
            m=dict(phase_id=p['id'],kind=p['kind'],samples=len(tt))
            if len(tt)>2:
                m.update(observed_span_s=float(tt[-1]-tt[0]),mean=float(ss.mean()),std=float(ss.std()))
                if p['kind']=='sine':
                    f=p['frequency'];X=np.c_[np.sin(2*np.pi*f*tt),np.cos(2*np.pi*f*tt),np.ones(len(tt))]
                    coeff=np.linalg.lstsq(X,ss,rcond=None)[0];fit=X@coeff
                    m.update(frequency_hz=f,amplitude=float(np.linalg.norm(coeff[:2])),
                             r2=float(1-np.sum((ss-fit)**2)/np.sum((ss-ss.mean())**2)) if ss.std()>1e-8 else None)
                if p['kind'].startswith('move_'):
                    positions=np.array([[r.get(f'position_{j}',np.nan) for j in range(3)] for r in records])[mask]
                    minima=[float(tt[np.nanargmin(positions[:,j])]) for j in range(3)]
                    m.update(dark_passage_times_s=minima,ordered=bool(np.all(np.diff(minima)>0) if p['kind']=='move_right' else np.all(np.diff(minima)<0)))
            metrics.append(m)
    fps=float(1/np.median(positive)) if len(positive) else 0
    frame_numbers=np.array([r['color_frame_number'] for r in records])
    report=dict(recorded_frames=len(records),duration_s=float(times[-1]),median_fps=fps,
        frame_interval_p95_ms=float(np.percentile(positive,95)*1000) if len(positive) else None,
        unique_frame_gaps=int(np.maximum(np.diff(frame_numbers)-1,0).sum()),queue_drops=meta['queue_drops'],
        screen_localized_fraction=float(np.mean(Hs)),optically_decoded_fraction=float(valid.mean()),
        browser_raf_median_fps=float(1/np.median(raf_intervals)) if len(raf_intervals) and np.median(raf_intervals)>0 else None,
        browser_raf_gap_p95_ms=float(np.percentile(raf_intervals,95)*1000) if len(raf_intervals) else None,
        browser_hidden_frames=hidden_frames,
        observed_phase_ids=np.unique(phases[phases>=0]).tolist(),display_log_present=display is not None,
        mapped_L2_in_screen=int(eligible.sum()),baseline_available=enough,
        acquisition_checks=dict(rgb_over_50fps=fps>50,screen_over_90pct=float(valid.mean())>.9,
             no_queue_drops=meta['queue_drops']==0,display_sequence_logged=display is not None,
             display_remained_visible=hidden_frames==0,
             sufficient_screen_L2=bool(eligible.any()),all_phases_seen=bool(display and all(m['samples']>=3 for m in metrics))),
        phases=metrics,depth_frames_saved=len(meta.get('depth_frames',[])),imu_samples=meta['imu_samples'],
        model='Frozen published L2 recurrent parameters, causal camera sample hold, integration <=1 ms',
        model_parameters=PARAMS,physiology_validated=False,brain_injection_performed=False,
        limitations=['RGB code values are not calibrated photons or Drosophila spectral sensitivity',
          '60 Hz cannot establish 13 ms L2 dynamics or reliably reproduce 20 ms flashes',
          'Screen optical phase labels are sampled at a different image row than stimulus; rolling shutter and panel scanout remain',
          'Camera frame timestamps and browser RAF clock are not equated; no absolute latency claim',
          'L2 model outputs are predictions, not measured neurons, mV or Hz; no spike conversion',
          'Spatial surround and adaptive luminance encoding remain unmodeled',
          'Depth/IMU retained as auxiliary records; screen depth and multimodal timing not certified'])
    report['optical_stimulus_checks']={
        'sine_fits_r2_over_0_8':bool(len([m for m in metrics if m.get('r2',0) is not None and m.get('r2',0)>.8])==3),
        'both_bar_directions_ordered':bool(len([m for m in metrics if m.get('ordered')])==2),
        'all_eight_100ms_flashes_observed':bool(len([m for m in metrics if m['kind'].endswith('_flash') and m['samples']>=3])==8)}
    report['status']='ACQUISITION_CHECKS_PASSED_MODEL_PREDICTIONS_ONLY' if all(report['acquisition_checks'].values()) else 'INCOMPLETE_OR_FAILED_ACQUISITION_CHECKS'
    (out/'analysis.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    keys=list(records[0])+['position_0','position_1','position_2']
    keys=list(dict.fromkeys(keys))
    with (out/'optical_samples.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(records)
    fig,axes=plt.subplots(3,1,figsize=(12,9),layout='constrained')
    axes[0].plot(times,signal,color='#166aab');axes[0].set(ylabel='Normalized camera intensity',title='Physical camera observations (not calibrated radiance)')
    axes[1].plot(times,phases,'.',ms=1);axes[1].set(ylabel='Optical phase ID')
    if eligible.any():
        selected=np.linspace(0,predictions.shape[1]-1,min(6,predictions.shape[1])).astype(int)
        for j in selected:axes[2].plot(times,predictions[:,j],label=f'L2 {np.array(ids)[eligible][j]}',alpha=.8)
        axes[2].legend(ncol=3,fontsize=8)
    axes[2].set(xlabel='Camera time (s)',ylabel='Effective voltage (a.u.)',title='Frozen model predictions; not biological recordings')
    fig.savefig(out/'temporal.png',dpi=140);plt.close(fig)
    summary={k:v for k,v in report.items() if k not in ['phases','limitations','model_parameters']}
    (out/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>拍屏幕验证结果</title>
<style>body{background:#101923;color:#eef4fa;font:17px system-ui;line-height:1.7;max-width:1100px;margin:30px auto;padding:15px}img{max-width:100%}a{color:#8bd8fa}pre{white-space:pre-wrap}</style>
<h1>屏幕 → 相机 → L2 动态预测</h1><p>这是传感器与模型链路实验，没有记录真实神经元。下方显示实际采集检查，未通过项不能算作验证成功。</p>
<pre>'''+json.dumps(summary,ensure_ascii=False,indent=2)+'''</pre><img src="temporal.png">
<p>黄色点是当前落在刺激区域内的 MaleCNS L2 视线。</p><img src="sampling_overlay.jpg">
<p>60 fps 与未做辐射标定的 RGB 值，只支持本轮较慢刺激的链路检查，不能宣称复现毫秒级生理精度。</p>
<p><a href="analysis.json">完整报告</a> · <a href="optical_samples.csv">逐帧实际观测</a> · <a href="l2_predictions.npz">逐 L2 模型预测</a> · <a href="display_log.json">屏幕渲染日志</a> · <a href="/">返回实验页</a></p>''',encoding='utf8')
    return summary


if __name__=='__main__':
    import sys
    print(json.dumps(analyze(Path(sys.argv[1])),indent=2))
