# Third-party notices and data terms

The top-level GPL-3.0-only license applies to this project's code and documentation unless otherwise identified. Preserve the following source-specific notices; a software license does not replace a dataset's license.

| Paths / material | Source and terms |
|---|---|
| `camera_lab/data/ME_assigned_columns.csv` | Reiser lab male visual-system connectome code; source repository GPL-3.0. Exact commit and hash in `camera_lab/data/provenance.json`. |
| `camera_lab/biomapping/source/eyemap.RData`, `med_ixy.RData` | Reiser lab `eyemap_T4`; GPL-3.0, license preserved at `source/LICENSE`. |
| `camera_lab/biomapping/source/visualpathways/ME_columnar-cells_location.xlsx` | Reiser lab `visualpathways`; GPL-3.0, original license preserved alongside it. |
| `camera_lab/biomapping/source/visualpathways/ME_L_columnar-cells_location.xlsx` | Reiser lab `visualpathways`, commit `23f6ac131529b5f56894c6eeb9b88b17894fc00d`; published left-eye ID/column assignments; GPL-3.0 notice preserved alongside it. |
| `camera_lab/biomapping/source/malecns_l2_inventory.json` | Derived subset of pinned Xenova model metadata: L2 body IDs, type and side only. MaleCNS data: CC BY 4.0. Credit: FlyEM / HHMI Janelia, University of Cambridge, MRC LMB, Google Research. Original source: https://male-cns.janelia.org/download/ ; compressed metadata URL and SHA-256 are recorded in this subset. No connectivity weights are included. |
| `camera_lab/biomapping/source/eyemap_archive/maps/`, `docs/data/` | Arthur Zhao / Reiser Lab, Janelia Research Campus; CC BY-SA 4.0. Original `eyemap_archive/LICENSE` is included. |
| `camera_lab/biomapping/data/reference_rays.csv`, `malecns_crosswalk.json` | Derived from the identified GPL mapping resources; retain source provenance and terms. |
| Direction fields and exact-join result in `malecns_author_crosswalk.json` | Derived from the CC BY-SA 4.0 archive direction table with attributed column identities; preserve that share-alike data license and all source attribution. No ownership claim over the upstream anatomy. |
| `malecns_left_crosswalk.json` direction fields and left exact join | Derived from Arthur Zhao's published left-eye archive output, CC BY-SA 4.0; preserve this attribution and data license. The ID/column workbook and metadata inventory retain the distinct source terms above. Seven unassigned IDs and 32 absent direction entries are explicitly unresolved. |
| Optional Dryad recordings and metadata | DOI `10.5061/dryad.ngf1vhj4c`, CC0 1.0; not stored in Git. The archived per-record numerical response results derive from these public records. |
| Optional mean-response MAT files / author code | Referenced at a pinned ClandininLab commit; not redistributed here. Retrieve from the original source and follow its applicable terms. |
| `tests/fixtures/brain_cpu/brain.js` | Unmodified Xenova BrainCPU source at commit `776d115ee5aa934578a87fd6d260d138084f59c1`; its original MIT notice and upstream LICENSE are preserved alongside the fixture. Tests construct a tiny synthetic graph; no connectome weights are bundled here. |
| Optional `fruit-fly-simulation/` | External, ignored checkout with its own MIT application notice, CC BY 4.0 MaleCNS data attribution and other notices. See that checkout's LICENSE; not included or relicensed here. |

The archive requests citation of Zhao et al. 2022 [bioRxiv](https://doi.org/10.1101/2022.12.14.520178) and Nern et al. 2025 [Nature](https://doi.org/10.1038/s41586-025-08746-0). The current project also cites the final eye-map and physiology papers in [docs/sources.md](docs/sources.md).

Changes to upstream data: selected right-eye records; exact joins by body ID and column; added validity/provenance fields; converted angles to a left-positive convention; preserved missing directions; computed response predictions and benchmark scores. Original included source bytes remain unchanged and are checked by SHA-256. Consult upstream licenses when redistributing datasets independently.
