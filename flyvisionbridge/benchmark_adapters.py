"""Optional upstream adapters. No downstream brain or actuator is invoked."""
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile
import numpy as np
from .benchmark_core import sha_file

SOURCES=json.loads(Path(__file__).with_name('benchmark_sources.json').read_text())


def verified_revision(package,module_path):
    """Require the pinned revision, whether installed through VCS or editable."""
    expected=SOURCES[package]['commit']
    direct=importlib.metadata.distribution(package).read_text('direct_url.json')
    if direct:
        vcs=json.loads(direct).get('vcs_info',{})
        if vcs.get('commit_id')==expected:return expected
    for parent in Path(module_path).resolve().parents:
        if (parent/'.git').exists():
            actual=subprocess.check_output(['git','-C',str(parent),'rev-parse','HEAD'],text=True).strip()
            changed=subprocess.check_output(['git','-C',str(parent),'status','--porcelain','--untracked-files=no'],text=True).strip()
            if actual==expected and not changed:return expected
            break
    raise RuntimeError(f'{package} must be the clean pinned revision from requirements-benchmark.txt')


def windows_datamate_compat():
    """datamate 1.0.0 unlinks an open HDF5 file on every new write on Windows.

    Replace only the cache writer, within this process. No upstream files or
    model equations are changed. Linux retains its upstream implementation.
    """
    if os.name != 'nt' or importlib.metadata.version('datamate') != '1.0.0':
        return None
    import datamate.directory as directory
    import datamate.io as io
    import h5py
    def write_h5(path, val):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        with h5py.File(path, 'w', libver='latest') as f:
            f.create_dataset('data', data=np.asarray(val))
            f.swmr_mode=True
    io._write_h5=directory._write_h5=write_h5
    return 'datamate-1.0.0 Windows process-local context-managed HDF5 cache writer'


class FlyvisAdapter:
    unit='native model voltage-state, arbitrary units; not mV, Hz or dF/F'
    def __init__(self, root, p):
        import yaml
        import torch
        self.torch=torch;self.p=p
        os.environ['FLYVIS_ROOT_DIR']=str(Path(root).resolve()/'bridge-cache')
        self.compat=windows_datamate_compat()
        import flyvis
        from flyvis.datasets.rendering import BoxEye
        revision=verified_revision('flyvis',flyvis.__file__)
        torch.set_default_device('cpu')
        flyvis.device=torch.device('cpu')
        torch.set_num_threads(p['torch_threads'])
        torch.manual_seed(p['seed'])
        model=Path(root)/'results'/p['flyvis']['model_id']
        archive=Path(root)/SOURCES['pretrained_archive']['name']
        if sha_file(archive)!=SOURCES['pretrained_archive']['sha256']:
            raise ValueError('Pretrained archive differs from author checksum')
        with zipfile.ZipFile(archive) as z:
            for name in ['best_chkpt','_meta.yaml']:
                if (model/name).read_bytes()!=z.read('results/'+p['flyvis']['model_id']+'/'+name):
                    raise ValueError('Extracted pretrained model differs from verified archive')
        cfg=yaml.safe_load((model/'_meta.yaml').read_text())['config']['network']
        self.net=flyvis.Network(**cfg)
        # State tensors only; never load arbitrary pickle objects from a checkpoint.
        state=torch.load(model/'best_chkpt',map_location='cpu',weights_only=True)
        self.net.load_state_dict(state['network'],strict=True)
        self.eye=BoxEye(extent=p['flyvis']['boxeye_extent'],kernel_size=p['flyvis']['boxeye_kernel_size'])
        self.initial=self.net.steady_state(p['flyvis']['baseline_settle_s'],p['frame_dt_s'],1,value=p['background_code']/255)
        self.nodes=self.net.connectome.nodes
        types=self.nodes.type[:].astype(str)
        self.indices={typ:np.flatnonzero(types==typ) for typ in p['flyvis']['output_types']}
        uv=np.c_[self.nodes.u[:],self.nodes.v[:]]
        # Check the receptor order, do not assume that model-node indices match pixels.
        axial=[(u,v) for u in range(-15,16) for v in range(max(-15,-15-u),min(15,15-u)+1)]
        self.l2_order=np.array([np.flatnonzero((types=='L2')&(uv[:,0]==u)&(uv[:,1]==v))[0] for u,v in axial])
        self.metadata=dict(version=flyvis.__version__,revision=revision,checkpoint_sha256=sha_file(model/'best_chkpt'),
            config_sha256=sha_file(model/'_meta.yaml'),model_id=p['flyvis']['model_id'],
            node_count=self.net.n_nodes,edge_count=self.net.n_edges,unit=self.unit,
            compatibility=self.compat,device='cpu',threads=p['torch_threads'],
            source_files={name:sha_file(Path(flyvis.__file__).parent/name) for name in
                ['network/network.py','network/dynamics.py','datasets/rendering/eye.py','connectome/fib25-fib19_v2.2.json']})

    def receptor_positions(self, shape):
        h,w=shape
        if min(h,w)<int(self.eye.min_frame_size.max()):
            raise ValueError('Frame too small for native BoxEye; explicitly resize with updated intrinsics first')
        centers=self.eye.receptor_centers.cpu().numpy()+np.array([h//2,w//2])
        return centers[:,::-1].astype(float)

    def run(self, rgb):
        start=time.perf_counter()
        self.receptor_positions(rgb.shape[1:3]) # prohibit silent upstream resizing
        gray=(rgb.astype(np.float32)@np.array([.2126,.7152,.0722],np.float32))/255
        movie=self.eye(self.torch.from_numpy(gray[None]))
        response=self.net.simulate(movie,self.p['frame_dt_s'],initial_state=self.initial)[0].detach().cpu().numpy()
        traces={typ:response[:,ids].mean(axis=1) for typ,ids in self.indices.items() if len(ids)}
        # Timing includes upstream rendering/integration/readout, excludes disk writes.
        elapsed=time.perf_counter()-start
        return dict(traces=traces,l2=response[:,self.l2_order].copy(),
                    receptors=movie[0,:,0].detach().cpu().numpy(),seconds=elapsed,
                    finite_fraction=float(np.isfinite(response).mean()))


class FlyDronesAdapter:
    unit='engineered Poisson input rate Hz; not recorded neural firing'
    def __init__(self,p):
        from flydrones.config import default_config
        from flydrones.brain.synthetic import build_minifly
        from flydrones.brain.connectome import GroupSpec
        from flydrones.senses.encoder import InputEncoder
        from flydrones.senses.retina import Retina
        import flydrones
        revision=verified_revision('flydrones',flydrones.__file__)
        self.config=default_config();self.Retina=Retina
        connectome=build_minifly(seed=p['seed'])
        connectome.resolve_groups({k:GroupSpec.from_dict(k,v) for k,v in self.config['inputs'].items()})
        self.encoder=InputEncoder(connectome,self.config)
        package=Path(flydrones.__file__).parent
        self.metadata=dict(version=importlib.metadata.version('flydrones'),revision=revision,unit=self.unit,
            scope=p['flydrones']['scope'],source_files={name:sha_file(package/name) for name in
                ['senses/retina.py','senses/encoder.py','brain/synthetic.py','defaults.yaml']})

    def run(self,rgb):
        start=time.perf_counter()
        retina=self.Retina.from_config(self.config)
        records={};features={};finite=0;total=0
        for frame in rgb:
            visual=retina.encode(frame)
            rates=self.encoder.encode(visual,yaw_rate_dps=0)
            for name,values in rates.items():
                records.setdefault(name,[]).append(float(np.mean(values)))
                finite+=int(np.isfinite(values).sum());total+=values.size
            for eye,grid in visual.eyes.items():
                for name,values in grid.grids.items():
                    features.setdefault(eye+'_'+name,[]).append(float(values.mean()))
        if not records:
            raise RuntimeError('Upstream encoder resolved no input groups')
        return dict(traces={k:np.asarray(v) for k,v in records.items()},
                    features=features,seconds=time.perf_counter()-start,
                    finite_fraction=finite/total)
