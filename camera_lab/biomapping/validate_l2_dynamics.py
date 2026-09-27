"""Reproduce published L2 flash model, then evaluate a held-out luminance condition.

Equations/parameters: Yang et al., A recurrent neural circuit in Drosophila
deblurs visual inputs (2024), PMC11071408. Data: ClandininLab/L1L2-deblur
7fa5829e37d566e02beaaa87efd6a0f1de4e48c0. This is a voltage-indicator response
model; outputs are NOT spikes or Hz. No new fit of dynamical parameters.
"""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.io import loadmat
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE=Path(__file__).resolve().parent
SRC=BASE/'source/L1L2-deblur/computational-model'
PARAMS=dict(tv=.0131,ty=.5613,w=12.7118,g=.1686,
            input_light=5.6441,input_dark=3.4075,bias=.2574,scale=1.0586)


def simulate(stimulus,dt,initial_v=0.,feedback=True,substeps=1):
    """Author Euler recurrence; stimulus already includes the acquisition delay.

    Internal v is signed effective voltage, positive depolarizing. The returned
    observable follows the author's inverted voltage-indicator sign convention.
    """
    s=np.asarray(stimulus,float)
    if not np.isfinite(s).all() or not 0<dt/substeps<=PARAMS['tv']:
        raise ValueError('Invalid stimulus or unsafe Euler integration step')
    p=PARAMS;v=float(initial_v);y=0.;out=np.empty(len(s));out[0]=-v
    for i in range(1,len(s)):
        drive=s[i]*(p['input_light'] if s[i]>0 else p['input_dark'])
        for _ in range(substeps):
            dy=(-y+v*((1-p['g']) if v>0 else p['g']))/p['ty']
            dv=(-v-(p['w']*y if feedback else 0)-drive)/p['tv']
            v+=dv*dt/substeps
            y=y+dy*dt/substeps if feedback else 0.
        out[i]=-p['scale']*(v+p['bias'])
    return out


def metrics(truth,pred):
    return dict(rmse=float(np.sqrt(np.mean((truth-pred)**2))),
                correlation=float(np.corrcoef(truth.ravel(),pred.ravel())[0,1]))


def main():
    out=BASE/'temporal_validation';out.mkdir(exist_ok=True)
    high=loadmat(SRC/'data/L2_highLum.mat',simplify_cells=True)
    low=loadmat(SRC/'data/L2_lowLum.mat',simplify_cells=True)
    t=np.asarray(high['t']);dt=float(np.diff(t).mean())
    np.testing.assert_allclose(t,low['t'])
    data=np.asarray(high['meanResp']);test=np.asarray(low['meanResp'])
    mean=float(data.mean());std=float(data.std());target=(data-mean)/std
    stimuli=np.zeros_like(data);stimuli[0,2:5]=-1;stimuli[1,2:5]=1
    # Published notebook uses target[0] for initialization. Low-luminance test
    # deliberately reuses HIGH initial state/scaling, avoiding test refitting.
    pred=np.array([simulate(s,dt,-target[j,0]) for j,s in enumerate(stimuli)])*std+mean
    nofeedback=np.array([simulate(s,dt,-target[j,0],False) for j,s in enumerate(stimuli)])*std+mean
    # Fair static control: affine contrast response, fitted on HIGH only.
    X=np.c_[stimuli.ravel(),np.ones(stimuli.size)]
    coef=np.linalg.lstsq(X,data.ravel(),rcond=None)[0]
    static=(X@coef).reshape(data.shape)
    results={}
    for name,truth in [('high_reproduction',data),('low_no_refit',test)]:
        results[name]={k:metrics(truth,v) for k,v in [('published_feedback',pred),('feedback_off',nofeedback),('static_control',static)]}
    # Compare polarity and rebound against the actual released mean traces.
    checks={}
    for name,a in [('data',data),('model',pred)]:
        voltage=-(a-a[:,:2].mean(axis=1)[:,None])
        checks[name+'_dark_depolarizes']=bool(voltage[0,2:6].max()>0)
        checks[name+'_light_hyperpolarizes']=bool(voltage[1,2:6].min()<0)
        checks[name+'_dark_opposite_rebound']=bool(voltage[0,6:25].min()<0)
        checks[name+'_light_opposite_rebound']=bool(voltage[1,6:25].max()>0)
    # Frozen parameter simulations: step, frequency sweep, moving dark bar
    # across five columns. These are predictions, not measured validation.
    ts=np.arange(0,2,.001);step=np.where((ts>=.4)&(ts<1.2),-1.,0.)
    flashes=np.where((ts>=.4)&(ts<.42),-1.,0.)
    sweep={}
    for f in [0.5,1,2,4,8,16,32]:
        st=np.sin(2*np.pi*f*ts);v=simulate(st,.001)
        sweep[str(f)]=float(np.std(v[1000:]))
    moving=[]
    for j in range(5):
        onset=.3+j*.15
        stim=np.where((ts>=onset)&(ts<onset+.1),-1.,0.)
        moving.append(-simulate(stim,.001))
    fine=simulate(flashes,.001,substeps=4)
    finer=simulate(flashes,.001,substeps=8)
    convergence=float(np.max(abs(fine-finer)))
    checks['finite_moving_predictions']=bool(np.isfinite(moving).all())
    report=dict(status='PUBLISHED_MODEL_REPRODUCTION_AND_CROSS_LUMINANCE_CHECK',
        source='https://github.com/ClandininLab/L1L2-deblur/tree/7fa5829e37d566e02beaaa87efd6a0f1de4e48c0',
        paper='https://pmc.ncbi.nlm.nih.gov/articles/PMC11071408/',parameters=PARAMS,
        parameter_origin='Rounded fitted parameters printed in author notebook; frozen, not refitted here',
        stimulus='Author notebook indices 2:5 at 120 Hz; approximates delayed 20 ms experimental flash',
        data_units='Released mean voltage-indicator fluorescence, NOT mV or firing Hz',
        results=results,qualitative_checks=checks,numerical_max_difference_025_vs_0125_ms=convergence,
        predicted_frequency_response_std=sweep,
        limitations=['High condition was used by original authors for parameter fitting; reproduction is not independent validation',
         'Low condition not used here for fitting; same published study, not independent specimen validation',
         'Initial high-condition baseline and normalization follow author notebook; all reused unchanged for low condition',
         'Notebook undefined natsti_res names corrected to the loaded MAT t arrays; no optimizer rerun',
         'Mean traces only; no per-fly uncertainty/significance estimate',
         'Spatial surround, adaptation across luminance, spectral sensitivity and camera radiometry are not modeled',
         'Existing saved camera frames approximately 5 Hz cannot resolve these 13 ms dynamics or 20 ms flashes',
         'No conversion to BrainCPU Poisson Hz validated; existing brain input not replaced'],
        source_sha256={str(p.relative_to(SRC)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SRC.rglob('*') if p.is_file()})
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    with (out/'flash_comparison.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['time_s','polarity','high_data','low_data','published_model','feedback_off','static'])
        for j,label in enumerate(['dark','light']):
            for i,x in enumerate(t):w.writerow([x,label,data[j,i],test[j,i],pred[j,i],nofeedback[j,i],static[j,i]])
    fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    for j,label in enumerate(['Dark flash','Light flash']):
        for col,truth in enumerate([data,test]):
            ax=axs[j,col];ax.plot(t,truth[j],label='Published mean data',color='black')
            ax.plot(t,pred[j],label='Frozen recurrent model');ax.plot(t,static[j],label='Static control',alpha=.7)
            ax.set(title=label+(' / high: reproduction' if col==0 else ' / low: no refit'),xlabel='Time (s)',ylabel='Indicator response (source units)')
            ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.savefig(out/'flash_comparison.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
    for j,v in enumerate(moving):ax.plot(ts,v,label=f'Column {j+1}')
    ax.set(title='Moving dark bar: model prediction only',xlabel='Time (s)',ylabel='Effective voltage proxy (arbitrary units)');ax.legend()
    fig.savefig(out/'moving_prediction.png',dpi=140);plt.close(fig)
    (out/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>L2 时间响应验证</title>
<style>body{font:17px system-ui;max-width:1100px;margin:30px auto;line-height:1.7;padding:20px;background:#101923;color:#eef4fa}img{width:100%}a{color:#8bd8fa}pre{white-space:pre-wrap}</style>
<h1>L2 时间响应：作者模型与实验曲线</h1><p>冻结作者模型参数；高亮度条件复现，低亮度条件不重新拟合。曲线单位是电压指示器信号，不是 Hz，也不是直接测得的 mV。</p>
<img src="flash_comparison.png"><h2>定量比较</h2><pre>'''+json.dumps(results,indent=2)+'''</pre>
<p>高亮度数据曾参与作者拟合，不能作为独立验证。低亮度结果反映条件迁移的误差；没有逐蝇原始数据的置信区间。</p>
<img src="moving_prediction.png"><p>移动条纹图仅为模型预测。已有约 5 Hz 相机存档不足以验证毫秒级响应。本次没有将模型信号擅自换算为全脑放电率。</p>
<p><a href="report.json">全部指标、参数和限制</a> · <a href="flash_comparison.csv">逐时间点数据</a> · <a href="https://github.com/ClandininLab/L1L2-deblur">作者代码和数据</a></p>''',encoding='utf8')
    print(json.dumps(dict(results=results,checks=checks),indent=2))
    if not all(checks.values()):raise AssertionError('Qualitative checks failed; inspect report')

if __name__=='__main__':main()
