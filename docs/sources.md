# Source ledger

| Resource | Fixed version | Contribution |
|---|---|---|
| [Male visual-system connectome code](https://github.com/reiserlab/male-drosophila-visual-system-connectome-code/tree/dbafc73124b5c96e96429cdf2a89d067cae841bc) | `dbafc73124b5c96e96429cdf2a89d067cae841bc` | `ME_assigned_columns.csv`, body IDs and columns |
| [eyemap_T4](https://github.com/reiserlab/eyemap_T4/tree/99d2a43123db636cedb55af9ff31a59657e7d17e) | `99d2a43123db636cedb55af9ff31a59657e7d17e` | 778-ray reference product |
| [visualpathways](https://github.com/reiserlab/visualpathways/tree/23f6ac131529b5f56894c6eeb9b88b17894fc00d) | `23f6ac131529b5f56894c6eeb9b88b17894fc00d` | Independent ID/column workbook |
| [eyemap-archive](https://github.com/artxz/eyemap-archive/tree/503c7f055d5491a48b60b49ade8c71798d24d8f1) | `503c7f055d5491a48b60b49ade8c71798d24d8f1` | Exact MaleCNS column-to-ray XLSX and CSV |
| [L1L2 recurrent feedback](https://github.com/ClandininLab/L1L2-recurrent-feedback/tree/7fa5829e37d566e02beaaa87efd6a0f1de4e48c0) | `7fa5829e37d566e02beaaa87efd6a0f1de4e48c0` | Temporal equation family, fitted parameters, mean-response files |
| [Dryad physiology](https://datadryad.org/dataset/doi:10.5061/dryad.ngf1vhj4c) | Version `335185`; file IDs in manifest | Per-ROI processed time series, stimuli and metadata |
| [Xenova fruit-fly simulation](https://huggingface.co/spaces/Xenova/fruit-fly-simulation/tree/776d115ee5aa934578a87fd6d260d138084f59c1) | `776d115ee5aa934578a87fd6d260d138084f59c1` | Optional unchanged BrainCPU engine and connectome assets |

Mapping background: [Zhao et al., Nature 2025](https://www.nature.com/articles/s41586-025-09276-5). Physiology: [A recurrent neural circuit in Drosophila temporally sharpens visual inputs](https://doi.org/10.1016/j.cub.2024.11.064), Current Biology (2025). The historical temporal script also cites the earlier preprint title; the current dataset README and findings use the final paper title.

`data/vendored_checksums.json` identifies the exact included source bytes. `data/downloads.json` identifies optional public files. `camera_lab/biomapping/source/L2_Dryad/manifest.json` preserves official Dryad file metadata. Derived mapping reports record import conventions and source hashes. Historical `reports/physiology/report.json` contains hashes of the original analysis scripts, which may differ from this packaged, portable release; rerunning produces a new code-hash record. This distinction is intentional.

The included GPL source license and archive data license accompany the original mapping inputs. Original MATLAB notebooks and analysis code are **not bundled**; the Python benchmark reimplements documented equations and numerical binning, with source attribution. Source acknowledgments are not endorsements by those authors.
