"""Same-study, fly-held-out L2 response benchmark. Never infer MaleCNS IDs.

Run with the project's analysis dependencies installed. Downloaded data are read only.
The primary outcome is continuous out-of-fold error, not an invented cell pass rate.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares
from scipy.io import loadmat
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from l2_physiology_data import BASE, DATA, read_records
from validate_l2_dynamics import PARAMS, SRC, simulate

OUT = BASE / 'physiology_validation'
PROTOCOL = BASE / 'l2_physiology_protocol.json'
BIN_WIDTH = 1 / 120
DURATION = .020


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False), encoding='utf8')


def metrics(truth, pred):
    a, b = np.asarray(truth).ravel(), np.asarray(pred).ravel()
    valid = np.isfinite(a) & np.isfinite(b)
    a, b = a[valid], b[valid]
    if not len(a):
        return dict(rmse=None, r2=None, correlation=None, n=0)
    mse = np.mean((a-b)**2)
    var = np.mean((a-a.mean())**2)
    corr = np.corrcoef(a, b)[0, 1] if np.std(a)>1e-12 and np.std(b)>1e-12 else None
    return dict(rmse=float(np.sqrt(mse)), r2=float(1-mse/var) if var>1e-20 else None,
                correlation=float(corr) if corr is not None else None, n=len(a))


def binned_response(p, t, feedback=True, rtol=2e-6):
    """Integral-average fluorescence proxy over the author's trailing time bins.

    p: tv, ty, w, g, light drive, dark drive, offset, latency.
    Piecewise forcing is split exactly at delayed onset and offset. Resting
    initial state is shared, independent of the tested cell's observed response.
    """
    tv, ty, w, g, light, dark, offset, delay = p
    t = np.asarray(t, float)
    end = float(t.max())
    edges = np.r_[delay, delay+DURATION, end]
    states = np.zeros(6)
    solutions = []
    for k in range(2):
        drive = np.array([-dark, light]) if k == 0 else np.zeros(2)
        def rhs(_, a):
            v, y = a[:2], a[2:4]
            dv = (-v-(w*y if feedback else 0)-drive)/tv
            dy = (-y+v*np.where(v>0, 1-g, g))/ty if feedback else np.zeros(2)
            return np.r_[dv, dy, -v]
        sol = solve_ivp(rhs, (edges[k], edges[k+1]), states,
                        rtol=rtol, atol=rtol*.01, dense_output=True,
                        method='DOP853')
        if not sol.success or not np.isfinite(sol.y).all():
            raise ValueError('ODE integration failed')
        states = sol.y[:, -1]
        solutions.append(sol)
    def integral(x):
        out = np.zeros((2, len(x)))
        for k, sol in enumerate(solutions):
            mask = (x>=edges[k]) & (x<=edges[k+1])
            if np.any(mask):
                out[:, mask] = sol.sol(x[mask])[4:6]
        return out
    return (integral(t)-integral(t-BIN_WIDTH))/BIN_WIDTH + offset


def fit_model(train_fly_means, t, feedback=True):
    """Only training arrays enter this function, including scale and lag fitting."""
    target = np.mean(train_fly_means, axis=0)
    scale = float(np.std(target))
    if scale <= 1e-12:
        raise ValueError('Degenerate training scale')
    target_n = target/scale
    spec = json.loads(PROTOCOL.read_text(encoding='utf8'))
    bounds = np.array(list(spec['bounds'].values())).T
    active = np.arange(8) if feedback else np.array([0,4,5,6,7])
    def expand(x):
        if feedback:
            return x
        p = np.array([.02,.3,0,.5,4,2,0,.01], dtype=float)
        p[active] = x
        return p
    def residual(x):
        return (binned_response(expand(x), t, feedback)-target_n).ravel()
    fits = []
    for start in spec['initializations']:
        fit = least_squares(residual, np.asarray(start)[active],
                            bounds=(bounds[0,active],bounds[1,active]),
                            x_scale='jac', diff_step=1e-4,
                            ftol=1e-7, xtol=1e-7, gtol=1e-7, max_nfev=180)
        fits.append(fit)
    best = min(fits,key=lambda f:np.sum(f.fun**2))
    p = expand(best.x)
    pred = binned_response(p, t, feedback)*scale
    return pred, dict(parameters=p.tolist(), training_scale=scale,
                      training_rmse=float(np.sqrt(np.mean(best.fun**2))*scale),
                      success=bool(best.success), nfev=best.nfev,
                      boundary_parameters=[int(active[i]) for i in range(len(active))
                        if min((best.x[i]-bounds[0,active[i]]),
                               (bounds[1,active[i]]-best.x[i])) < .001*(bounds[1,active[i]]-bounds[0,active[i]])],
                      train_fly_count=len(train_fly_means))


def training_fold(records, held_fly):
    """All records from the held-out fly are excluded before any normalization."""
    ids = sorted({int(r['flyID']) for r in records if r['author_selected'] and int(r['flyID'])!=held_fly})
    means = np.array([np.mean([r['rats'] for r in records
        if r['author_selected'] and int(r['flyID'])==f], axis=0) for f in ids])
    return ids, means


def rebinned_halves(record, t):
    """Reproduce source bin edges; split by chronological flash repetition.

    Source code selects the closest onset among onsets >= frame_time-bin_width
    when looking forward, or the latest earlier onset otherwise. A frame may
    contribute to each polarity's separately constructed alignment.
    """
    ft = np.asarray(record['imFrameStartTimes'])
    df = np.asarray(record['dFF'])
    st = record['pStimDat']
    onset_all = np.asarray(st['stimEpochStartTimes']).ravel()
    labels = np.asarray(st['rcStimInd']).ravel()
    halves = np.full((2,2,len(t)), np.nan)
    total = np.full((2,len(t)), np.nan)
    counts = []
    for polarity in range(2):
        onsets = onset_all[labels==polarity+1]
        counts.append(len(onsets))
        idx = np.searchsorted(onsets, ft+BIN_WIDTH, side='right')-1
        valid = idx>=0
        idx_safe = np.maximum(idx,0)
        rel = ft-onsets[idx_safe]
        valid &= (rel>=-BIN_WIDTH) & (rel<=DURATION+.5) & np.isfinite(df)
        for j in range(len(t)):
            # Match the source's precise floating-point edge expressions;
            # ceil(rel/dt) changes membership for timestamps exactly on edges.
            center = j*BIN_WIDTH-BIN_WIDTH/2
            start, end = center-BIN_WIDTH/2, center+BIN_WIDTH/2
            use = valid & (rel>start) & (rel<=end)
            if np.any(use):
                total[polarity,j] = np.mean(df[use])
            for half in range(2):
                pick = use & (idx%2==half)
                if np.any(pick):
                    halves[half,polarity,j] = np.mean(df[pick])
    return total, halves, counts


def features(a, t, polarity):
    sign = -1 if polarity==0 else 1  # ASAP2f fluorescence sign, NOT voltage sign
    early = (t>=0)&(t<=.08)
    late = (t>=.08)&(t<=.3)
    baseline = float(np.mean(a[t<=BIN_WIDTH]))
    signal = (a-baseline)*sign
    peak_index = np.flatnonzero(early)[np.argmax(signal[early])]
    return dict(peak=float(signal[peak_index]), peak_time_s=float(t[peak_index]),
                rebound=float(-np.min(signal[late])),
                baseline=baseline)


def bootstrap_ci(values):
    a = np.asarray(values,float)
    rng = np.random.default_rng(20260927)
    boot = np.mean(a[rng.integers(0,len(a),(5000,len(a)))],axis=1)
    return [float(v) for v in np.quantile(boot,[.025,.975])]


def main():
    sys.stdout.reconfigure(encoding='utf8')
    OUT.mkdir(exist_ok=True)
    protocol_hash = sha(PROTOCOL)
    save_json(OUT/'protocol.json',json.loads(PROTOCOL.read_text(encoding='utf8')))
    manifest = json.loads((DATA/'manifest.json').read_text())
    for name, source in manifest.items():
        assert sha(DATA/name)==source['digest'], f'Source checksum changed: {name}'
    records, settings = read_records(include_timeseries=True)
    metadata = pd.read_excel(DATA/'L1L2_Metadata.xlsx', sheet_name='All Metadata')
    metadata['Time Series ID'] = metadata['Time Series ID'].astype(str).str.strip()
    t = np.asarray(records[0]['t'])[0]
    selected = [r for r in records if r['author_selected']]
    high = loadmat(SRC/'data/L2_highLum.mat',simplify_cells=True)
    mean_response = np.mean([r['rats'] for r in selected],axis=0)
    leakage_error = float(np.max(abs(mean_response-high['meanResp'])))
    assert leakage_error<1e-12, 'Source reconciliation changed: audit before evaluating'
    assert settings['interpFrameRate']==120 and settings['binWidthMult']==1
    observed = np.asarray([r['rats'] for r in records])
    half_records=[]
    inventory=[]
    for r in records:
        np.testing.assert_allclose(r['t'],np.array([t,t]))
        np.testing.assert_allclose(r['stimDat']['FlashDuration'],[DURATION,DURATION])
        original_matches = metadata[metadata['Time Series ID']==r['seriesID']]
        # Published processed MAT files retain legacy fly names. Exact series
        # strings can collide with a different genotype in the later workbook.
        # Require date, LDM suffix, z depth, genotype AND stimulus to agree.
        date = r['seriesID'].split('_')[0]
        suffix = r['seriesID'].split('_LDM')[1]
        matches = metadata[
            metadata['Time Series ID'].str.startswith(date+'_') &
            metadata['Time Series ID'].str.endswith('_LDM'+suffix) &
            (metadata['Fly Genotype'].astype(str).str.strip()==r['genotype'].strip()) &
            (metadata['Stimulus'].astype(str).str.strip()==r['stimcode'].strip()) &
            np.isclose(pd.to_numeric(metadata['Z-depth'],errors='coerce'),r['zdepth'],rtol=0,atol=1e-5)]
        info = matches.iloc[0].to_dict() if len(matches)==1 else {}
        join_kind = ('exact_consistent' if info and str(info['Time Series ID'])==r['seriesID']
                     else 'unique_date_sequence_depth_genotype_match' if info else 'unresolved')
        if r['author_selected'] and not info:
            raise AssertionError('Unresolved primary metadata identity: '+r['seriesID'])
        total, halves, counts = rebinned_halves(r,t)
        err = float(np.nanmax(abs(total-np.asarray(r['rats']))))
        half_records.append(halves)
        inv = dict(row_matlab=r['row_matlab'],series_id=r['seriesID'],
            fly_id=int(r['flyID']),roi_mask=int(r['roiMask']),zdepth=float(r['zdepth']),
            author_selected=r['author_selected'],search_series_id=r['search_seriesID'],
            metadata_matches=len(matches), metadata_join=join_kind,
            metadata_series_id=str(info.get('Time Series ID','unknown')),
            metadata_fly_id=int(info['Fly ID']) if info else None,
            direct_name_genotype_conflict=bool(len(original_matches)==1 and
                str(original_matches.iloc[0]['Fly Genotype']).strip()!=r['genotype'].strip()),
            metadata_sex=str(info.get('Sex','unknown')),
            dark_repeats=counts[0],light_repeats=counts[1],
            trace_rebin_max_abs_error=err,
            split_half_correlation=metrics(halves[0],halves[1])['correlation'])
        inventory.append(inv)
    max_rebin = max(r['trace_rebin_max_abs_error'] for r in inventory)
    canonical_by_mat = {}
    for r in inventory:
        if r['author_selected']:
            canonical_by_mat.setdefault(r['fly_id'],set()).add(r['metadata_fly_id'])
    assert all(len(ids)==1 for ids in canonical_by_mat.values())
    assert len({next(iter(ids)) for ids in canonical_by_mat.values()})==len(canonical_by_mat)
    crosswalk = pd.DataFrame(inventory)[['series_id','fly_id','search_series_id',
        'metadata_series_id','metadata_fly_id','metadata_join','metadata_matches',
        'direct_name_genotype_conflict','metadata_sex']].drop_duplicates()
    crosswalk.to_csv(OUT/'metadata_crosswalk.csv',index=False,encoding='utf-8-sig')
    print('DATA_AUDIT',json.dumps(dict(total=len(records),selected=len(selected),
          training_mean_max_error=leakage_error,max_rebin_error=max_rebin)),flush=True)
    if max_rebin>1e-8:
        save_json(OUT/'data_audit_diagnostic.json',inventory)
        raise AssertionError('Re-binning differs from released data. Repair alignment before fitting.')
    # Strict reproduction of the already-used source implementation.
    mean, std = float(high['meanResp'].mean()),float(high['meanResp'].std())
    target = (high['meanResp']-mean)/std
    stim = np.zeros_like(target);stim[0,2:5]=-1;stim[1,2:5]=1
    published = np.array([simulate(s,BIN_WIDTH,-target[j,0]) for j,s in enumerate(stim)])*std+mean
    predictions = {k:np.zeros_like(observed) for k in ['recurrent','feedback_free','constant','template']}
    folds=[]
    for fly in sorted({int(r['flyID']) for r in records}):
        train_ids, train = training_fold(records,fly)
        assert fly not in train_ids
        pred, fit = fit_model(train,t,True)
        control, control_fit = fit_model(train,t,False)
        test = [i for i,r in enumerate(records) if int(r['flyID'])==fly]
        for name,value in [('recurrent',pred),('feedback_free',control),
                           ('constant',np.full_like(pred,train.mean())),
                           ('template',train.mean(axis=0))]:
            predictions[name][test]=value
        fold=dict(held_fly=fly,train_flies=train_ids,test_rows=[i+1 for i in test],
                  fit=fit,feedback_free_fit=control_fit)
        folds.append(fold)
        save_json(OUT/'folds_in_progress.json',folds)
        print('FOLD',fly,'training-only RMSE',round(fit['training_rmse'],6),
              'converged',fit['success'],control_fit['success'],flush=True)
    # Post-fit outcomes: no model selection or refitting uses this section.
    rows=[]
    for i,r in enumerate(records):
        row=inventory[i].copy()
        row['evaluation_role']='primary_selected' if r['author_selected'] else 'secondary_author_excluded'
        for name,pred in [('published_reproduction',published)]+[(k,v[i]) for k,v in predictions.items()]:
            row.update({name+'_'+k:v for k,v in metrics(observed[i],pred).items() if k!='n'})
        for j,pol in enumerate(['dark','light']):
            row.update({f'{pol}_recurrent_{k}':v for k,v in
                metrics(observed[i,j],predictions['recurrent'][i,j]).items() if k!='n'})
            actual=features(observed[i,j],t,j);predicted=features(predictions['recurrent'][i,j],t,j)
            for key,value in actual.items():row[f'{pol}_observed_{key}']=value
            for key,value in predicted.items():row[f'{pol}_predicted_{key}']=value
            row[f'{pol}_peak_time_error_ms']=1000*(predicted['peak_time_s']-actual['peak_time_s'])
            row[f'{pol}_peak_amplitude_error']=predicted['peak']-actual['peak']
            row[f'{pol}_rebound_amplitude_error']=predicted['rebound']-actual['rebound']
        rows.append(row)
    primary=[r for r in rows if r['author_selected']]
    fly_summary=[]
    for fly in sorted({r['fly_id'] for r in primary}):
        items=[r for r in primary if r['fly_id']==fly]
        sm=dict(fly_id=fly,selected_roi_records=len(items))
        for key in ['recurrent_rmse','recurrent_r2','recurrent_correlation','feedback_free_rmse','constant_rmse','template_rmse','split_half_correlation']:
            sm[key]=float(np.mean([r[key] for r in items if r[key] is not None]))
        sm['feedback_rmse_improvement']=sm['feedback_free_rmse']-sm['recurrent_rmse']
        fly_summary.append(sm)
    improvement=[s['feedback_rmse_improvement'] for s in fly_summary]
    ci=bootstrap_ci(improvement)
    template_diff=[s['template_rmse']-s['recurrent_rmse'] for s in fly_summary]
    report=dict(status='SAME_STUDY_LEAVE_ONE_FLY_OUT_EVALUATED',
        biological_response_validated=False,independent_study_validation=False,
        malecns_identity_validation=False,spike_rate_calibration=False,
        protocol_sha256=protocol_hash,source_manifest=manifest,
        data=dict(total_roi_records=len(records),author_selected_roi_records=len(selected),
          total_flies=len({int(r['flyID']) for r in records}),
          primary_flies=len(fly_summary),stimulus='20 ms full-field dark/light flashes, 500 ms gray intervals',
          observable='ASAP2f dF/F, fractional units; fluorescence opposite to depolarization',
          selected_mean_equals_author_training_data_max_error=leakage_error,
          rebin_max_abs_error=max_rebin,metadata_matched_rows=sum(r['metadata_matches']==1 for r in rows),
          metadata_renamed_records=sum(r['metadata_join']=='unique_date_sequence_depth_genotype_match' for r in rows),
          direct_name_genotype_conflicts=sum(r['direct_name_genotype_conflict'] for r in rows),
          author_excluded_records=len(records)-len(selected)),
        implementation_checks=dict(checksums=True,source_mean_reconciled=True,
          timeseries_rebin_reconciled=True,whole_fly_disjoint=True,
          primary_fly_metadata_bijection=True,
          no_test_gain_or_lag_fit=True,protocol_unchanged=sha(PROTOCOL)==protocol_hash,
          all_optimizers_converged=all(f['fit']['success'] and f['feedback_free_fit']['success'] for f in folds)),
        primary_summary={key:dict(fly_equal_weight_mean=float(np.mean([f[key] for f in fly_summary])),
          fly_bootstrap_95pct=bootstrap_ci([f[key] for f in fly_summary]))
          for key in ['recurrent_rmse','recurrent_r2','recurrent_correlation','feedback_free_rmse','constant_rmse','template_rmse','split_half_correlation']},
        feedback_advantage=dict(mean_rmse_improvement=float(np.mean(improvement)),
          fly_bootstrap_95pct=ci,supported_by_predeclared_criterion=ci[0]>0,
          improving_flies=sum(v>0 for v in improvement),total_flies=len(fly_summary)),
        template_comparison=dict(mean_rmse_improvement=float(np.mean(template_diff)),
          fly_bootstrap_95pct=bootstrap_ci(template_diff),
          interpretation='Descriptive same-stimulus waveform template baseline, not a new-stimulus generalization test'),
        parameter_identifiability=dict(folds_with_boundary_parameters=sum(bool(f['fit']['boundary_parameters']) for f in folds),
          total_folds=len(folds),warning='Boundary-hitting feedback gains and compensating time constants prevent claiming unique biological parameter estimates'),
        primary_counts=dict(positive_r2=sum(r['recurrent_r2']>0 for r in primary),
          nonpositive_r2=sum(r['recurrent_r2']<=0 for r in primary),
          dark_positive_r2=sum(r['dark_recurrent_r2']>0 for r in primary),
          light_positive_r2=sum(r['light_recurrent_r2']>0 for r in primary)),
        primary_peak_timing=dict(dark_median_absolute_error_ms=float(np.median([abs(r['dark_peak_time_error_ms']) for r in primary])),
          light_median_absolute_error_ms=float(np.median([abs(r['light_peak_time_error_ms']) for r in primary]))),
        folds=folds,flies=fly_summary,
        limitations=json.loads(PROTOCOL.read_text(encoding='utf8'))['limitations'],
        source_code_sha256={p.name:sha(p) for p in [Path(__file__),BASE/'l2_physiology_data.py',BASE/'validate_l2_dynamics.py']})
    save_json(OUT/'report.json',report)
    save_json(OUT/'cells.json',rows)
    save_json(OUT/'folds.json',folds)
    with (OUT/'cells.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    np.savez_compressed(OUT/'response_traces.npz',time_s=t,observed=observed,
        split_halves=np.asarray(half_records),published_reproduction=published,
        selected=np.array([r['author_selected'] for r in records]),
        row_matlab=np.arange(1,len(records)+1),**predictions)
    make_report(report,rows,t,observed,predictions)
    print(json.dumps({'data':report['data'],'primary_summary':report['primary_summary'],
                      'feedback_advantage':report['feedback_advantage']},indent=2),flush=True)


def make_report(report,rows,t,obs,preds):
    ids=[i for i,r in enumerate(rows) if r['author_selected']]
    fly_ids=sorted({rows[i]['fly_id'] for i in ids})
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for j,pol in enumerate(['Dark flash','Light flash']):
        byfly=np.array([obs[[i for i in ids if rows[i]['fly_id']==f],j].mean(axis=0) for f in fly_ids])
        avg=byfly.mean(axis=0);sem=byfly.std(axis=0,ddof=1)/np.sqrt(len(byfly))
        ax=axs[j];ax.plot(t,avg,color='black',label='Measured (flies equally weighted)')
        ax.fill_between(t,avg-sem,avg+sem,color='black',alpha=.12,label='Across-fly SEM')
        for name,color in [('recurrent','#118b88'),('feedback_free','#df713b')]:
            arr=np.array([preds[name][[i for i in ids if rows[i]['fly_id']==f],j].mean(axis=0) for f in fly_ids])
            ax.plot(t,arr.mean(axis=0),color=color,label='Out-of-fold '+name)
        ax.set(title=pol,xlabel='Time after flash onset (s)',ylabel='ASAP2f dF/F (fraction)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(OUT/'population.png',dpi=160);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    f=report['flies'];x=np.arange(len(f))
    for name,label,shift in [('recurrent_rmse','Recurrent',-.2),('feedback_free_rmse','Feedback free',.2)]:
        axs[0].bar(x+shift,[a[name] for a in f],.4,label=label)
    axs[0].set_xticks(x,[a['fly_id'] for a in f],rotation=45);axs[0].set(xlabel='Held-out fly ID',ylabel='Mean ROI RMSE (dF/F)');axs[0].legend()
    corr=[rows[i]['recurrent_correlation'] for i in ids];r2=[rows[i]['recurrent_r2'] for i in ids]
    axs[1].scatter(corr,r2,alpha=.7,s=23);axs[1].axhline(0,color='grey',ls='--');axs[1].set(xlabel='Out-of-fold Pearson r',ylabel='Out-of-fold R2',title='Each point is a selected ROI record')
    fig.savefig(OUT/'per_fly.png',dpi=160);plt.close(fig)
    # Every ROI is inspectable; interactive page uses local data, no CDN or upload.
    plot_data=[dict(row=r['row_matlab'],time=t.tolist(),observed=obs[i].tolist(),
        predicted=preds['recurrent'][i].tolist(),feedback_free=preds['feedback_free'][i].tolist()) for i,r in enumerate(rows)]
    save_json(OUT/'plot_data.json',plot_data)
    payload=json.dumps(dict(rows=rows,traces=plot_data),ensure_ascii=False).replace('</','<\\/')
    summary=report['primary_summary'];adv=report['feedback_advantage']
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>L2 逐细胞生理验证</title>
<style>body{margin:0;background:#101923;color:#eef4fa;font:16px system-ui;line-height:1.7}main{max-width:1180px;margin:auto;padding:30px 22px}h1{font-size:30px}a{color:#82d9e1}.notice{border-left:4px solid #e4aa54;padding:15px;background:#223041}.cards{display:flex;gap:15px;flex-wrap:wrap}.card{padding:18px;background:#1c2b3b;flex:1;min-width:150px}.big{font-size:28px;font-weight:bold}img{width:100%;background:white;border-radius:5px;margin:14px 0}select,input,button{padding:9px;background:#23394b;color:white;border:1px solid #688396;max-width:100%}.scroll{overflow:auto;max-height:400px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:7px;border-bottom:1px solid #344659;white-space:nowrap;text-align:left}th{position:sticky;top:0;background:#223041}canvas{display:block;background:white;width:100%;height:auto;margin-top:14px}pre{white-space:pre-wrap}small{color:#acbacc}</style><main>
<p>公开活体生理记录 · 20 ms 全屏明暗闪光 · 同研究留一果蝇验证</p><h1>L2 逐细胞响应：模型能预测到什么程度？</h1>
<div class="notice"><b>已完成有边界的生理对照，未宣称所有神经元通过。</b>103 个作者选中 ROI 的平均值与模型训练曲线完全一致，因此“作者固定参数”结果属于复现。本报告另用每次留出整只果蝇的方法重新拟合；归一化、响应幅度、延迟和模型参数均只由训练果蝇确定。模型结构仍来自同一研究，不能称为独立研究验证。</div>
<div class="cards"><div class="card"><div class="big">103 / 13</div>主要分析 ROI 记录 / 果蝇</div><div class="card"><div class="big">214 / 14</div>全部 ROI 记录 / 果蝇</div><div class="card"><div class="big">__CORR__</div>逐蝇等权平均相关系数</div><div class="card"><div class="big">__RMSE__</div>逐蝇等权 RMSE · ΔF/F</div></div>
<p>荧光单位是相对变化量 ΔF/F（0.01 = 1%），不是 mV 或 Hz。ASAP2f 荧光下降对应去极化。ROI 是成像记录区域，不是 MaleCNS 神经元 ID，跨视野的细胞唯一性未获确认。</p>
<img src="population.png" alt="独立于测试果蝇拟合的预测与实测均值"><img src="per_fly.png" alt="逐果蝇误差与逐细胞相关性">
<p>反馈模型相对单独拟合的无反馈模型，逐蝇平均 RMSE 改善为 <b>__ADV__</b>，95% 描述性 bootstrap 区间 __CI__；__SUPPORT__。103 个主要记录中有 __NEGATIVE__ 个 R² ≤ 0。相关性不能替代幅度误差，全部失败记录保留。</p>
<p>训练果蝇平均波形模板的 RMSE 为 __TEMPLATE__，与循环模型接近；模型对该模板的误差改善区间为 __TEMPLATE_CI__。这次仅检验同一种闪光跨果蝇预测，不能据此断言模型能泛化到其他刺激。__BOUNDARIES__ / 14 折的参数触及预设边界，因此不能把拟合参数当成唯一的真实生理参数。</p>
<h2>逐个查看记录</h2><label>筛选 <select id="filter"><option value="primary">作者选中的 103 个</option><option value="all">全部 214 个</option><option value="excluded">作者未选中的 111 个</option></select></label> <label>记录 <select id="cell"></select></label>
<p id="detail"></p><canvas id="trace" width="1100" height="430"></canvas><small>黑色：实测；青色：留一果蝇模型；橙色：训练集拟合的无反馈对照。左侧暗闪光，右侧亮闪光。时序误差按 8.33 ms 分箱报告，不宣称亚毫秒测量精度。</small>
<div class="scroll"><table><thead><tr><th>记录</th><th>果蝇</th><th>系列 / ROI</th><th>r</th><th>R²</th><th>RMSE</th><th>重复可靠性 r</th></tr></thead><tbody id="rows"></tbody></table></div>
<h2>来源与计算检查</h2><ul><li>官方 3 个文件 SHA-256 校验通过；逐时间序列重新分箱与发布曲线一致（误差 __REBIN__）。</li><li>103 个作者选中记录都已核对元数据。全部记录中 35 个记录的系列名称曾重排；按日期、序列后缀、成像深度、基因型及刺激联合匹配。28 个记录若只按名称连接，会接到不同基因型。13 个作者未选中记录仍无元数据匹配，只进入次要分析。</li><li>作者响应筛选依据单独的搜索刺激；主要分析沿用该筛选，111 个其余记录提供敏感性分析。</li><li>主模型使用原循环方程族，对名义 20 ms 刺激做数值积分，再按作者代码的尾随 1/120 s 时间窗平均；延迟仅在训练果蝇上拟合。旧模型复现单独保存在 CSV。</li><li>奇偶闪光重复独立分箱估计重复可靠性；按果蝇汇总与 bootstrap，避免把同一果蝇的细胞当作独立动物。bootstrap 区间描述这组果蝇的差异，交叉验证训练集合有重叠，并非外部验证。</li><li>优化器是否全部收敛：__CONVERGED__。触及参数边界和每折训练集合均保留在 folds.json。</li></ul>
<p class="notice">范围：同研究、同一刺激类型、其他雌蝇的 L2 电压指示器信号。尚未验证空间感受野、光谱、相机绝对光强、自然场景泛化、MaleCNS 单细胞身份或全脑动态。本次未替换全脑输入。</p>
<p><a href="cells.csv">全部逐记录 CSV</a> · <a href="metadata_crosswalk.csv">元数据对应审计</a> · <a href="report.json">完整结果与来源哈希</a> · <a href="folds.json">每折参数与训练/测试划分</a> · <a href="protocol.json">冻结分析协议</a> · <a href="response_traces.npz">完整预测与实测数组</a> · <a href="https://datadryad.org/dataset/doi:10.5061/dryad.ngf1vhj4c">官方数据</a> · <a href="../../../reports/screen/README.md">此前相机工程验收</a></p>
<script>const data=__DATA__;const filter=document.querySelector('#filter'),sel=document.querySelector('#cell');function fmt(x,n=3){return x==null?'—':x.toFixed(n)}
function refresh(){let rows=data.rows.filter(r=>filter.value==='all'||(filter.value==='primary'?r.author_selected:!r.author_selected));sel.innerHTML=rows.map(r=>`<option value="${r.row_matlab}">#${r.row_matlab} · Fly ${r.fly_id} · ROI ${r.roi_mask}</option>`).join('');document.querySelector('#rows').innerHTML=rows.map(r=>`<tr><td><button data-row="${r.row_matlab}">${r.row_matlab}</button></td><td>${r.fly_id}</td><td>${r.series_id} / ${r.roi_mask}</td><td>${fmt(r.recurrent_correlation)}</td><td>${fmt(r.recurrent_r2)}</td><td>${fmt(r.recurrent_rmse,5)}</td><td>${fmt(r.split_half_correlation)}</td></tr>`).join('');draw()}
function draw(){const n=Number(sel.value),r=data.rows[n-1],d=data.traces[n-1];document.querySelector('#detail').textContent=`${r.series_id} / ROI ${r.roi_mask} · ${r.author_selected?'主要分析':'作者未选中，次要分析'} · r=${fmt(r.recurrent_correlation)} · R²=${fmt(r.recurrent_r2)} · RMSE=${fmt(r.recurrent_rmse,5)} · 暗/亮峰值时间误差 ${fmt(r.dark_peak_time_error_ms,1)} / ${fmt(r.light_peak_time_error_ms,1)} ms`;const c=document.querySelector('#trace'),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);for(let p=0;p<2;p++){const arrays=[d.observed[p],d.predicted[p],d.feedback_free[p]],values=arrays.flat();let lo=Math.min(...values),hi=Math.max(...values),pad=(hi-lo)*.15||.01;lo-=pad;hi+=pad;let left=60+p*540,top=45,w=450,h=315;ctx.strokeStyle='#cad4df';ctx.strokeRect(left,top,w,h);ctx.fillStyle='#162b3c';ctx.font='16px system-ui';ctx.fillText(p?'Light flash':'Dark flash',left,25);for(let a=0;a<3;a++){ctx.strokeStyle=['#222','#118b88','#df713b'][a];ctx.lineWidth=2;ctx.beginPath();arrays[a].forEach((v,i)=>{const x=left+d.time[i]/.52*w,y=top+(hi-v)/(hi-lo)*h;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()}ctx.fillText(hi.toFixed(3),left-55,top+10);ctx.fillText(lo.toFixed(3),left-55,top+h);ctx.fillText('0 s',left,top+h+24);ctx.fillText('0.52 s',left+w-45,top+h+24)}}
filter.onchange=refresh;sel.onchange=draw;document.querySelector('#rows').onclick=e=>{if(e.target.dataset.row){sel.value=e.target.dataset.row;draw()}};refresh();</script></main></html>'''
    repl={'__CORR__':f"{summary['recurrent_correlation']['fly_equal_weight_mean']:.3f}",
          '__RMSE__':f"{summary['recurrent_rmse']['fly_equal_weight_mean']:.5f}",
          '__ADV__':f"{adv['mean_rmse_improvement']:.5f}",
          '__CI__':str([round(v,6) for v in adv['fly_bootstrap_95pct']]),
          '__SUPPORT__':'支持反馈模型降低误差' if adv['supported_by_predeclared_criterion'] else '未达到预先约定的反馈优势证据标准',
          '__REBIN__':f"{report['data']['rebin_max_abs_error']:.2g}",
          '__NEGATIVE__':str(report['primary_counts']['nonpositive_r2']),
          '__TEMPLATE__':f"{summary['template_rmse']['fly_equal_weight_mean']:.5f}",
          '__TEMPLATE_CI__':str([round(v,6) for v in report['template_comparison']['fly_bootstrap_95pct']]),
          '__BOUNDARIES__':str(report['parameter_identifiability']['folds_with_boundary_parameters']),
          '__CONVERGED__':str(report['implementation_checks']['all_optimizers_converged']),
          '__DATA__':payload}
    for key,value in repl.items():page=page.replace(key,value)
    (OUT/'index.html').write_text(page,encoding='utf8')


if __name__=='__main__':
    main()
