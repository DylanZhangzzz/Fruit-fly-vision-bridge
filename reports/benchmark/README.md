# Frozen synthetic visual benchmark

Open `index.html`. This archive contains the 13 synthetic cases from protocol 1.1, run twice through L2, the official Flyvis pretrained network and the official FlyDrones sensory encoder. It contains no camera frames, camera responses, pretrained model weights or whole-brain connectome arrays.

The numerical results are predictions and engineering diagnostics, not a physiological accuracy ranking. Native units and spatial sampling differ. Reproduce using [docs/benchmark.md](../../docs/benchmark.md); the source manifest pins upstream revisions and model checksums.

`report.json` retains the hashes of the code used at execution time. A subsequent publication-only update adds attribution and license notices without recomputing responses, timings or scores. `publication.json` records the exporter and renderer hashes for that update.

This project's original report code is GPL-3.0-only. Reiser lab body-ID / column components keep their GPLv3 source terms; archive-derived directions, projected points and interpolation weights keep CC BY-SA 4.0. This is not dual-licensing: preserve both sets of notices. See the included `THIRD_PARTY_NOTICES.md`, `LICENSE` and `LICENSES/eyemap-archive.txt` when sharing this directory independently. Modifiable original mapping tables and their import scripts are available in the source repository.

Sources: Arthur Zhao / Reiser Lab, Janelia Research Campus, [eyemap-archive](https://github.com/artxz/eyemap-archive/tree/503c7f055d5491a48b60b49ade8c71798d24d8f1), with requested citations [Zhao et al.](https://doi.org/10.1101/2022.12.14.520178) and [Nern et al.](https://doi.org/10.1038/s41586-025-08746-0); [Lappalainen et al. / Flyvis](https://doi.org/10.1038/s41586-024-07939-3); [SpikeCalls / FlyDrones](https://github.com/SpikeCalls/FlyDrones); [Pang et al. / L2 equations](https://doi.org/10.1016/j.cub.2024.11.064). Changes made 2026-09-27: right-eye selection, exact column join, angle convention conversion, image projection, interpolation, model predictions and benchmark summaries. No source-author endorsement is claimed.
