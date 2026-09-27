"""Read numeric/struct MATLAB v7.3 physiology data without executing MATLAB code."""
from pathlib import Path
import h5py
import numpy as np

BASE = Path(__file__).resolve().parent
DATA = BASE / 'source/L2_Dryad'


def decode(f, obj):
    if isinstance(obj, h5py.Reference):
        return decode(f, f[obj]) if obj else None
    if isinstance(obj, h5py.Group):
        return {k: decode(f, v) for k, v in obj.items()}
    if obj.attrs.get('MATLAB_empty', 0):
        return np.array([])
    arr = obj[()]
    if obj.attrs.get('MATLAB_class', b'') == b'char':
        return ''.join(chr(int(v)) for v in arr.flatten())
    if h5py.check_dtype(ref=obj.dtype):
        # h5py exposes MATLAB dimensions in reverse order.
        values = [decode(f, r) for r in arr.T.flat]
        return values[0] if arr.size == 1 else values
    arr = np.asarray(arr).T.squeeze()
    return arr.item() if arr.ndim == 0 else arr


def read_records(include_timeseries=False):
    fields = ['seriesID', 'flyID', 'roiMask', 'genotype', 'stimcode',
              'zdepth', 't', 'rats', 'stdErrs', 'BIN_SHIFT', 'stimDat']
    if include_timeseries:
        fields += ['dFF', 'imFrameStartTimes', 'imIFI', 'pStimDat']
    with h5py.File(DATA / 'L2_ASAP2f.mat', 'r') as f:
        g = f['roiDataMat']
        selected = set(np.asarray(f['iResp']).ravel().astype(int).tolist())
        records = []
        for i in range(g['seriesID'].shape[1]):
            record = {key: decode(f, g[key][1, i]) for key in fields}
            record.update(row_matlab=i+1, author_selected=i+1 in selected)
            record['search_seriesID'] = decode(f, g['seriesID'][0, i])
            records.append(record)
        settings = {k: decode(f, f[k]) for k in ['interpFrameRate','binWidthMult','inv']}
    return records, settings
