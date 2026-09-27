"""Prospective temporal validation of a frozen screen-code/camera LUT.

All acceptance limits below are engineering limits fixed before acquisition.
Equivalent screen-code contrast is not physical luminance contrast. The L2
outputs are conditional model predictions, never recorded neural responses.
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
from analyze_screen import BASE,CENTERS,screen_transform,recurrent_prediction
from analyze_photometric import decode_dualrail,stable_indices
from geometry import project_rays,sample_rgb
from import_author_map import STATUS

LIMITS=dict(static_max_code_error=5.,sine_min_r2=.95,sine_max_amplitude_relative_error=.10,
            flash_duration_error_s=.06,motion_min_signed_correlation=.9,motion_max_residual_s=.1,
            pose_p95_pixel_shift=3.,gyro_p95_residual_rad_s=.04,accel_p95_residual_m_s2=.25)


def reference_correct(values,black,white,reference):
    """Causal affine correction from independent patches, never test targets."""
    v=np.asarray(values,float);black=np.asarray(black,float);white=np.asarray(white,float)
    span=reference['white_camera']-reference['black_camera'];delta=white-black
    scale=np.divide(span,delta,out=np.full_like(delta,np.nan),where=delta>20)
    valid=np.isfinite(scale)&(scale>=.8)&(scale<=1.25)
    corrected=reference['black_camera']+(v-black[:,None])*scale[:,None]
    corrected[~valid]=np.nan
    return corrected,scale


def inverse_lookup(values,channel):
    """No extrapolation, clipping or invented recovery of near-flat intervals."""
    v=np.asarray(values,float);x=np.asarray(channel['gray_codes'],float);y=np.asarray(channel['monotone_camera_values'],float)
    interval=np.clip(np.searchsorted(y,v,side='right')-1,0,len(y)-2)
    delta=y[interval+1]-y[interval]
    valid=np.isfinite(v)&(v>=y[0])&(v<=y[-1])&(delta>=1.)
    out=np.full(v.shape,np.nan);out[valid]=x[interval[valid]]+(v[valid]-y[interval[valid]])/delta[valid]*(x[interval[valid]+1]-x[interval[valid]])
    return out


def sine_metrics(times,values,frequency):
    good=np.isfinite(values);t=np.asarray(times)[good];v=np.asarray(values)[good]
    if len(t)<30 or np.std(v)<1:return dict(pass_check=False,samples=len(t))
    X=np.c_[np.sin(2*np.pi*frequency*t),np.cos(2*np.pi*frequency*t),np.ones(len(t))]
    c=np.linalg.lstsq(X,v,rcond=None)[0];res=v-X@c
    r2=float(1-np.sum(res**2)/np.sum((v-v.mean())**2));amplitude=float(np.linalg.norm(c[:2]))
    error=abs(amplitude/48-1)
    return dict(samples=len(t),r2=r2,amplitude_code=amplitude,amplitude_relative_error=error,
                fitted_mean_code=float(c[2]),offset_error_code=float(c[2]-160),
                phase_rad=float(np.arctan2(c[1],c[0])),pass_check=bool(r2>=LIMITS['sine_min_r2'] and error<=LIMITS['sine_max_amplitude_relative_error']))


def motion_metrics(times,values,screen_x,direction):
    """Order of dark-bar passages, not neuronal direction selectivity."""
    passages=[];xs=[];amplitudes=[]
    for j,x in enumerate(screen_x):
        if not np.isfinite(x):continue
        v=values[:,j];good=np.isfinite(v)
        if good.sum()<30:continue
        weights=np.maximum(160-v[good]-8,0)
        if weights.sum()<60:continue
        passages.append(float(np.sum(times[good]*weights)/weights.sum()));xs.append(float(x))
        amplitudes.append(float(160-np.nanpercentile(v,5)))
    if len(xs)<6 or np.ptp(xs)<150:return dict(pass_check=False,channels=len(xs))
    xs=np.array(xs);passages=np.array(passages);sign=1 if direction=='move_right' else -1
    predicted=sign*xs/(520/3);offset=float(np.mean(passages-predicted));res=passages-predicted-offset
    signed_r=float(sign*np.corrcoef(xs,passages)[0,1]);rmse=float(np.sqrt(np.mean(res**2)))
    return dict(channels=len(xs),signed_correlation=signed_r,residual_rmse_s=rmse,
                screen_x=xs.tolist(),passage_camera_times_s=passages.tolist(),
                common_time_offset_s=offset,min_dark_amplitude_code=min(amplitudes),
                mirrored_coordinates_would_fail=bool(-signed_r<LIMITS['motion_min_signed_correlation']),
                pass_check=bool(signed_r>=LIMITS['motion_min_signed_correlation'] and rmse<=LIMITS['motion_max_residual_s'] and min(amplitudes)>30))


def marker_reference(directory):
    cap=cv2.VideoCapture(str(Path(directory)/'rgb.avi'));points=[]
    try:
        for frame in [60,90,120,150]:
            cap.set(cv2.CAP_PROP_POS_FRAMES,frame);ok,bgr=cap.read()
            if not ok:continue
            H,_=screen_transform(cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY))
            if H is not None:points.append(cv2.perspectiveTransform(CENTERS.astype(np.float32)[None],np.linalg.inv(H))[0])
    finally:cap.release()
    if not points:raise ValueError('Cannot recover calibration screen pose')
    return np.median(points,axis=0)


def imu_metrics(meta,directory,t_start,t_end):
    motion=json.loads((Path(directory)/'imu.json').read_text());result={}
    # Host receipt time is only used for a coarse stability interval, not precise sensor synchronization.
    for name,threshold in [('gyro',LIMITS['gyro_p95_residual_rad_s']),('accel',LIMITS['accel_p95_residual_m_s2'])]:
        a=np.array([r['xyz'] for r in motion if name in r['stream'] and t_start<=r['host_receipt_ms']<=t_end])
        if len(a)<30:result[name]={'samples':len(a),'pass_check':False};continue
        center=np.median(a,axis=0);residual=np.linalg.norm(a-center,axis=1);p95=float(np.percentile(residual,95))
        result[name]=dict(samples=len(a),median_xyz=center.tolist(),residual_p95=p95,pass_check=p95<=threshold)
    result['scope']='Stationarity audit using coarse host-receipt interval; not calibrated orientation or exact sensor timing'
    result['depth_frames_saved']=len(meta.get('depth_frames',[]))
    return result


def analyze(directory):
    out=Path(directory);meta=json.loads((out/'capture.json').read_text());display=json.loads((out/'display_log.json').read_text())
    if display.get('protocol')!='calibrated_temporal_v1' or display.get('bit_encoding')!='gray_dualrail_v2':raise ValueError('Wrong temporal protocol')
    lut_bytes=(out/'frozen_response_lut.json').read_bytes();lut=json.loads(lut_bytes)
    if hashlib.sha256(lut_bytes).hexdigest()!=meta['frozen_lut_sha256']:raise ValueError('Frozen LUT hash mismatch')
    source=out.parent/meta['calibration_run'];reference=marker_reference(source)
    channels=lut['channels'];roi_names=[k for k in channels if k.startswith('ROI_')]
    neural_names=[k for k in channels if k.startswith('L2_')];names=roi_names+neural_names
    rows={r['bodyId']:r for r in json.loads((BASE/'data/malecns_author_crosswalk.json').read_text()) if r['status']==STATUS}
    uv,visible=project_rays([rows[k[3:]]['ray_head_xyz'] for k in neural_names],meta['color_intrinsics'])
    phases=display['phases'];valid_ids={p['id'] for p in phases};observations=[];labels=[];timings=[];pose_shift=[];positions=[];reference_values=[]
    cap=cv2.VideoCapture(str(out/'rgb.avi'))
    try:
        for i,timing in enumerate(meta['frames_timing']):
            ok,bgr=cap.read()
            if not ok:break
            H,n=screen_transform(cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY));v=np.full(len(names),np.nan);phase=-1;shift=np.nan;xy=np.full((len(neural_names),2),np.nan);refs=[np.nan,np.nan]
            if H is not None:
                gray=cv2.warpPerspective(cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY),H,(1000,700));phase,_=decode_dualrail(gray,valid_ids)
                rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB).astype(float);intensity=rgb@np.array([.2126,.7152,.0722]);plane=cv2.warpPerspective(intensity,H,(1000,700))
                refs=[float(np.mean(plane[112:143,309:351])),float(np.mean(plane[112:143,399:441]))]
                for j,name in enumerate(roi_names):
                    _,x,y=name.split('_');x=int(x);y=int(y);v[j]=np.mean(plane[y-20:y+20,x-20:x+20])
                xy=cv2.perspectiveTransform(uv.astype(np.float32)[None],H)[0]
                inside=visible&(xy[:,0]>225)&(xy[:,0]<775)&(xy[:,1]>205)&(xy[:,1]<495)
                rv=sample_rgb(rgb,uv,visible)@np.array([.2126,.7152,.0722]);v[len(roi_names):][inside]=rv[inside]
                screenpoints=cv2.perspectiveTransform(CENTERS.astype(np.float32)[None],np.linalg.inv(H))[0]
                shift=float(np.sqrt(np.mean(np.sum((screenpoints-reference)**2,axis=1))))
                if i==90:
                    overlay=bgr.copy()
                    for (x,y),yes in zip(uv,inside):
                        if yes:cv2.circle(overlay,(round(x),round(y)),4,(0,200,255),1)
                    cv2.imwrite(str(out/'sampling_overlay.jpg'),overlay)
            observations.append(v);labels.append(phase);timings.append(timing);pose_shift.append(shift);positions.append(xy);reference_values.append(refs)
    finally:cap.release()
    if len(timings)<100:raise ValueError('Too few video frames')
    raw=np.array(observations);labels=np.array(labels);xy=np.array(positions);times=np.array([t['color_ms'] for t in timings])/1000;times-=times[0]
    reference_values=np.array(reference_values);aligned=raw;scale=np.ones(len(raw))
    correction=meta.get('reference_correction')
    if correction:
        if correction!='dual_patch_affine_v1' or 'optical_reference' not in lut:raise ValueError('Missing preregistered optical reference')
        aligned,scale=reference_correct(raw,reference_values[:,0],reference_values[:,1],lut['optical_reference'])
    codes=np.column_stack([inverse_lookup(aligned[:,j],channels[name]) for j,name in enumerate(names)])
    # Ignore startup settling only, consistently defined before acquisition.
    evaluation=times>=.5
    per_channel={};static_entries=[]
    for j,name in enumerate(names):
        static=[];sines=[]
        for p in phases:
            if p['kind'].startswith('move_'):continue
            index=stable_indices(labels,p['id'],trim=1 if p['kind'].endswith('_flash') else 4);index=index[times[index]>=.5]
            if p['kind']=='sine':
                m=sine_metrics(times[index],codes[index,j],p['frequency']);m.update(phase_id=p['id'],frequency_hz=p['frequency']);sines.append(m)
            else:
                v=codes[index,j];v=v[np.isfinite(v)];minimum=4 if p['kind'].endswith('_flash') else 10
                m=dict(channel=name,phase_id=p['id'],kind=p['kind'],target_code=p['level'],samples=len(v),median_code=float(np.median(v)) if len(v) else None,
                       error_code=float(np.median(v)-p['level']) if len(v) else None,pass_check=bool(len(v)>=minimum and abs(np.median(v)-p['level'])<=LIMITS['static_max_code_error']))
                static.append(m);static_entries.append(m)
        error=max([abs(m['error_code']) for m in static if m['error_code'] is not None],default=None)
        finite=float(np.mean(np.isfinite(codes[evaluation,j])))
        per_channel[name]=dict(pass_check=bool(finite>.95 and static and all(m['pass_check'] for m in static) and len(sines)==3 and all(m['pass_check'] for m in sines)),
                               valid_fraction=finite,static_max_abs_code_error=error,sines=sines)
    central=names.index('ROI_500_350');flashes=[];moves=[]
    neural_codes=codes[:,len(roi_names):]
    for p in phases:
        index=np.flatnonzero(labels==p['id'])
        if p['kind'].endswith('_flash'):
            m=dict(phase_id=p['id'],kind=p['kind'],samples=len(index),pass_check=False)
            if len(index)>=4:
                window=(times>=times[index[0]]-.12)&(times<=times[index[-1]]+.12);t=times[window];v=codes[window,central]
                hit=v<136 if p['kind']=='dark_flash' else v>184
                hits=np.flatnonzero(hit);groups=np.split(hits,np.flatnonzero(np.diff(hits)>1)+1)
                group=max(groups,key=len)
                if len(group):
                    duration=float(t[group[-1]]-t[group[0]]+np.median(np.diff(times)));error=abs(duration-.2)
                    m.update(observed_duration_s=duration,duration_error_s=error,pass_check=bool(error<=LIMITS['flash_duration_error_s']))
            flashes.append(m)
        if p['kind'].startswith('move_'):
            x=np.nanmedian(xy[index,:,0],axis=0) if len(index) else np.full(len(neural_names),np.nan)
            m=motion_metrics(times[index],neural_codes[index],x,p['kind']);m.update(phase_id=p['id'],direction=p['kind']);moves.append(m)
    contrast=(neural_codes-160)/160
    predictions=recurrent_prediction(times,contrast);polarity={}
    for p in phases:
        if p['kind'] not in ['dark_step','light_step']:continue
        index=np.flatnonzero(labels==p['id'])
        if not len(index):continue
        start=times[index[0]];before=(times>=start-.15)&(times<start-.025);during=(times>=start+.04)&(times<=start+.2)
        delta=np.nanmean(predictions[during],axis=0)-np.nanmean(predictions[before],axis=0)
        polarity[p['kind']]=dict(channels=len(delta),delta_effective_voltage=[float(d) if np.isfinite(d) else None for d in delta],pass_check=bool(np.isfinite(delta).all() and (np.all(delta>0) if p['kind']=='dark_step' else np.all(delta<0))))
    active_indices=np.flatnonzero(evaluation);imu=imu_metrics(meta,out,timings[active_indices[0]]['host_receipt_ms'],timings[-1]['host_receipt_ms'])
    pose=np.array(pose_shift);pose_p95=float(np.nanpercentile(pose[evaluation],95)) if np.isfinite(pose[evaluation]).any() else 1e9
    comparable=dict(camera_intrinsics_unchanged=meta['color_intrinsics']==lut['capture_intrinsics'],camera_settings_unchanged=meta['exposure_settings']==lut['capture_settings'],
                    screen_pose_within_3px=pose_p95<=LIMITS['pose_p95_pixel_shift'])
    frameids=np.array([t['color_frame_number'] for t in timings]);acquisition=dict(no_frame_gaps=bool(np.all(np.diff(frameids)==1)),no_queue_drops=meta['queue_drops']==0,
        all_video_frames_present=len(timings)==len(meta['frames_timing']),optical_labels_over_95pct=float(np.mean(labels>=0))>.95,
        all_phases_observed=all(np.sum(labels==p['id'])>=4 for p in phases),display_visible=bool(display['frames']) and all(f['visibility']=='visible' for f in display['frames']),
        not_aborted=not display.get('aborted',False),gyro_stationary=imu['gyro']['pass_check'],accel_stationary=imu['accel']['pass_check'])
    engineering=dict(all_calibrated_channels_pass=bool(per_channel) and all(v['pass_check'] for v in per_channel.values()),
                     all_eight_200ms_flashes_pass=len(flashes)==8 and all(v['pass_check'] for v in flashes),
                     both_bar_directions_pass=len(moves)==2 and all(v['pass_check'] for v in moves),
                     conditional_model_step_polarity=len(polarity)==2 and all(v['pass_check'] for v in polarity.values()))
    accepted=all(comparable.values()) and all(acquisition.values()) and all(engineering.values())
    report=dict(status='PASS_ENGINEERING_TEMPORAL' if accepted else 'CHECK_FAILURES',frames=len(timings),duration_s=float(times[-1]),median_fps=float(1/np.median(np.diff(times))),
                frozen_calibration=meta['calibration_run'],frozen_lut_sha256=meta['frozen_lut_sha256'],lut_refitted=False,
                reference_correction=correction,reference_gain_median=float(np.nanmedian(scale)),reference_gain_p05_p95=np.nanpercentile(scale,[5,95]).tolist(),
                calibrated_L2=len(neural_names),passing_L2=sum(v['pass_check'] for k,v in per_channel.items() if k.startswith('L2_')),
                calibrated_ROIs=len(roi_names),passing_ROIs=sum(v['pass_check'] for k,v in per_channel.items() if k.startswith('ROI_')),
                screen_pose_shift_p95_px=pose_p95,valid_optical_fraction=float(np.mean(labels>=0)),
                comparability_checks=comparable,acquisition_checks=acquisition,temporal_checks=engineering,
                channels=per_channel,flashes=flashes,motion=moves,conditional_model_polarity=polarity,imu_stability=imu,thresholds=LIMITS,
                model_input='(equivalent_screen_code - 160) / 160; an engineering proxy, NOT physical luminance contrast',
                model_output='Conditional effective voltage in arbitrary units; NOT measured physiology, mV or Hz',
                biological_response_validated=False,physical_luminance_calibrated=False,brain_input_replaced=False,
                limitations=['Fixed LUTs are not refitted on this recording; near-flat and out-of-range inverse queries remain NaN',
                  'Sine fits allow an independent phase offset; they do not establish absolute display/camera latency',
                  'Optical phase bits and stimulus occur at different image rows; transitions remain temporally uncertain',
                  'IMU uses coarse host-receipt intervals for stationarity only; depth retained, not used as screen radiometry',
                  'Same-column L2 neurons cannot be distinguished by this visual stimulation',
                  'No recorded neurons; model polarity checks are conditional on published parameters and code-contrast proxy'])
    if correction:report['limitations'].append('Independent black/white patches correct per-frame affine drift; this requires those fixed references in view and is not validated for arbitrary natural scenes')
    np.savez_compressed(out/'calibrated_temporal_samples.npz',times_s=times,phase_id=labels,channels=np.array(names),camera_values=raw,equivalent_screen_codes=codes,
                        L2_bodyIds=np.array([k[3:] for k in neural_names]),code_contrast=contrast,effective_voltage=predictions,screen_xy=xy,pose_shift_px=pose,
                        camera_values_reference_aligned=aligned,optical_reference_values=reference_values,reference_gain=scale)
    with (out/'static_validation.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=static_entries[0]);writer.writeheader();writer.writerows(static_entries)
    (out/'calibrated_temporal_report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    plot_report(out,report,times,codes,predictions,labels,phases,names)
    render_report(out,report)
    return {k:v for k,v in report.items() if k not in ['channels','flashes','motion','conditional_model_polarity','limitations']}


def plot_report(out,report,times,codes,predictions,labels,phases,names):
    fig,axes=plt.subplots(3,1,figsize=(12,10),layout='constrained')
    axes[0].plot(times,codes[:,names.index('ROI_500_350')],label='Frozen LUT -> equivalent screen code')
    for p in phases:
        if p['kind']=='sine':
            index=labels==p['id'];m=report['channels']['ROI_500_350']['sines'][[1,2,4].index(p['frequency'])]
            if 'phase_rad' in m:axes[0].plot(times[index],160+48*np.sin(2*np.pi*p['frequency']*times[index]+m['phase_rad']),':',color='black',lw=1)
    axes[0].set(ylabel='Equivalent screen code',title='Independent new camera data; calibration NOT refitted');axes[0].legend()
    for m in report['motion']:
        if 'screen_x' in m:axes[1].scatter(m['screen_x'],m['passage_camera_times_s'],label=m['direction'])
    axes[1].set(xlabel='Screen x (canonical pixels)',ylabel='Dark passage camera time (s)',title='Order across mapped L2 positions; not neuronal direction tuning');axes[1].legend()
    neural=[k for k in names if k.startswith('L2')]
    for j in np.linspace(0,len(neural)-1,min(5,len(neural))).astype(int):axes[2].plot(times,predictions[:,j],label=neural[j],alpha=.7)
    axes[2].set(xlabel='Camera time (s)',ylabel='Effective voltage (arbitrary units)',title='Conditional L2 predictions from equivalent-code contrast, not measured neurons');axes[2].legend(ncol=3,fontsize=8)
    fig.savefig(out/'calibrated_temporal.png',dpi=140);plt.close(fig)


def render_report(out,r):
    good=r['status']=='PASS_ENGINEERING_TEMPORAL';failed=[k for group in ['comparability_checks','acquisition_checks','temporal_checks'] for k,v in r[group].items() if not v]
    text='''<!doctype html><meta charset="utf-8"><title>固定标定 · 独立时序验收</title><style>body{font:17px system-ui;line-height:1.7;background:#101923;color:#eef4fa;max-width:1100px;margin:30px auto;padding:15px}img{width:100%}a{color:#8bd8fa}pre{white-space:pre-wrap}table{width:100%;border-collapse:collapse;font-size:15px}td,th{padding:8px;border-bottom:1px solid #395064;text-align:left}details{margin:20px 0}</style><h1>固定灰阶标定后的独立时序验收</h1>'''
    text+=f'<p><strong>{"工程验收通过" if good else "尚有未通过项"}</strong> · {r["frames"]:,} 帧 · {r["median_fps"]:.2f} fps</p><p>上轮响应表固定使用，没有用本轮数据重新拟合。L2 采样位置通过 {r["passing_L2"]}/{r["calibrated_L2"]}；屏幕检查区域通过 {r["passing_ROIs"]}/{r["calibrated_ROIs"]}。</p>'
    if failed:text+='<p>未通过：'+html.escape(', '.join(failed))+'</p>'
    text+='<p>检查灰阶还原、1 / 2 / 4 Hz 幅度与波形、8 次 200 ms 闪烁，以及左右运动在各个位置的先后顺序。误差门限在采集前确定。</p><img src="calibrated_temporal.png" alt="独立时序采集、运动通过顺序与条件 L2 模型预测">'
    if r.get('reference_correction'):text+='<p>本轮先用画面中独立的黑白参考块逐帧校正亮度漂移，再查询固定响应表；没有用测试刺激的目标灰阶拟合修正量。此方法要求参考块持续可见，尚未验证任意自然场景。</p>'
    text+='<p><strong>范围：</strong>解码得到的是等效屏幕数字灰阶。下方 L2 曲线以这种灰阶对比度作为模型输入，尚未证明它等于真实光强对比度，也没有记录真实神经元。</p>'
    text+='<details><summary>逐个 L2 与屏幕位置</summary><table><tr><th>位置</th><th>通过</th><th>最大静态灰阶误差</th><th>1 / 2 / 4 Hz R²</th></tr>'
    for name,c in r['channels'].items():
        error='不可用' if c['static_max_abs_code_error'] is None else f'{c["static_max_abs_code_error"]:.2f}'
        text+=f'<tr><td>{html.escape(name)}</td><td>{c["pass_check"]}</td><td>{error}</td><td>'+', '.join(f'{s["r2"]:.4f}' if 'r2' in s else '不可用' for s in c['sines'])+'</td></tr>'
    text+='</table></details><details><summary>完整验收数据、IMU 稳定性与限制</summary><pre>'+html.escape(json.dumps(r,ensure_ascii=False,indent=2))+'</pre></details>'
    text+='<p><a href="calibrated_temporal_report.json">完整报告</a> · <a href="static_validation.csv">逐阶段静态误差</a> · <a href="calibrated_temporal_samples.npz">逐帧输入与条件模型预测</a> · <a href="frozen_response_lut.json">本轮固定响应表</a> · <a href="/continuous_validation.html">重新实验</a></p>'
    (Path(out)/'index.html').write_text(text,encoding='utf8')


if __name__=='__main__':
    import sys
    print(json.dumps(analyze(sys.argv[1]),indent=2))
