# Source-publication rights review — 2026-09-27

**Conclusion:** the inspected source release can be proposed with the notices and boundaries below. No definite unauthorized redistribution was identified in the inspected file set after the notice corrections. This is an evidence-based engineering license review, **not** a legal opinion, a guarantee of non-infringement, a plagiarism clearance or a patent/trademark search.

中文结论：已核对现有项目及本次比较的主要来源、固定版本、原始文件哈希、随附许可和发布范围，并修正署名及许可表述。检查没有发现本次文件集内明确无授权再分发的内容；仍有作者代码和模型权重的授权边界，不能宣称“项目绝无侵权”。

## What was inspected

- Base commit `08f1bca7d22040ee5ee4b58ea1b45c1e4c7e7684`, the complete current source/publication file list and all three commits already reachable before this change. Existing live-webcam code and the BrainCPU test fixture were included in this review, not just the new benchmark.
- All ten previously vendored mapping inputs/notices checked against their pinned upstream source bytes, plus the BrainCPU source and license. The fixture's working-copy CRLF is normalized by Git; its committed LF blobs exactly match upstream. Nothing in this review rewrites public history.
- Four additional full license texts, the imported/derived mapping data, report CSV/JSON/NPZ contents, and all three published PNGs. The PNGs are project-generated scientific plots; there are no publisher figure scans, third-party photographs, logos, paper PDFs or bundled fonts. HTML reports use local code and system fonts, with no external JavaScript/CDN assets.
- Direct runtime and benchmark dependency license metadata in the installed environments. Those packages and their transitive binary dependencies are installed separately, not redistributed in this Git source release. This is not a complete binary SBOM review.
- The consulted author notebook's model functions and MATLAB binning method against the Python implementation. The repository uses the mathematical recurrence, published parameter numbers and measurement conventions, with its own numerical implementation. The author's PyTorch model class, notebook prose/plots, custom `loadmat` helper and MATLAB source are not included. This comparison is scoped to the known sources; it is not proof of independent authorship against every possible source.

## Component decisions

| Component | Evidence and publication decision |
|---|---|
| Reiser lab body-ID/column tables, `eyemap_T4`, `visualpathways` | All three fixed repositories supply GPLv3. Original data and license bytes match upstream; derived identity/column components retain those terms, with import scripts and modifiable inputs available. |
| Arthur Zhao / Reiser Lab `eyemap-archive` | Fixed archive license explicitly distinguishes CC BY-SA 4.0 data from MIT code. Preserve the author's attribution, requested citations and original license. Changes to rays and projections are dated and described. |
| Joined mapping and benchmark spatial artifacts | Keep the two identifiable data components' terms: GPL-origin identities/columns remain GPL; archive-derived rays/projections/weights remain CC BY-SA. The collection is not dual-licensed as a free choice, and it is not all claimed as this project's original work. |
| Xenova BrainCPU fixture | Unchanged committed source at `776d115…`; original MIT application notice preserved, including its separate upstream data notices. The fixture uses a synthetic test graph; full connectome weights are excluded. |
| Dryad L2 recordings | Dataset API reports `CC0-1.0`. Included numerical response artifacts derive from that public data. Raw MAT files are optional downloads and absent from Git. |
| ClandininLab L2 author notebook/MATLAB code | **No explicit license found** in the fixed repository tree `7fa5829…`. Do not treat public visibility or citation as redistribution permission. No author notebooks, MATLAB files or mean-response MAT files are in Git. Existing optional download links are source references, not a license grant. Reuse of the author's expressive code requires permission or a separate legal assessment. |
| Flyvis / FlyDrones software | Verified MIT at pinned commits. Installed separately; full notices additionally preserved here. The benchmark invokes their actual implementations rather than relabeling them as project-owned models. |
| Flyvis pretrained archive | Official download instructions invite running the models, but no separate license was found inside the downloaded ZIP. No weight redistribution clearance is asserted. Only source download/checksum tooling and numerical predictions are published; no archive/checkpoint/config copy is committed. |
| Datamate cache compatibility code | Datamate 1.0.0 metadata supplies MIT; the full notice is preserved for the process-local Windows cache writer. Upstream model code and weights are not edited. |
| Dependencies | NumPy, SciPy, pandas, Pillow, openpyxl, matplotlib, h5py, rdata, OpenCV, librealsense/Python bindings, PyTorch, torchvision and PyYAML retain their own licenses and bundled-component notices. Source-only installation requirements do not redistribute their wheels. A container, executable installer or embedded binary release needs another review. |

## Corrections in this publication

1. Clarify mixed-source mapping components instead of applying CC BY-SA to the whole joined result or implying a blanket GPL license over every original data file. Package metadata states `MIT AND GPL-3.0-only AND CC-BY-SA-4.0 AND CC-BY-4.0` to describe the bundled collection; original project code and documentation use MIT following main PR #2. Third-party data terms remain unchanged.
2. Preserve full Flyvis, FlyDrones, datamate and CC BY-SA notices. Carry applicable notices with the stand-alone synthetic report and display source attribution, license links, modification date and no-warranty information in its HTML.
3. Correct the archived physiology README's implication that author MATLAB code ships with this repository. Identify the missing author-code license and unresolved separate weight-archive license explicitly.
4. Add `data/license_inventory.json` and an offline CI guard against changed/missing notices, unreviewed upstream files, raw recordings, weight archives and unreviewed media. `--online` rechecks the source URLs. A passing guard does not itself prove lawful origin.
5. Keep original numerical benchmark results and execution hashes. The publication renderer adds notices only; `reports/benchmark/publication.json` records that distinction.

## Recheck

From a Git checkout:

```powershell
python scripts/verify_sources.py
python scripts/audit_licenses.py --online
python scripts/audit_release.py
python scripts/run_checks.py
```

The initial review recorded 16 preserved source/notice files and nine reviewed binary/data artifacts. After the binocular integration below, the inventory records 21 and eleven respectively. Unlicensed author source, model weights, full connectome assets and personal RGB/depth/IMU captures are outside the publication boundary. Adding one requires a new source/rights review rather than weakening the check.

## Same-day binocular integration addendum

PR #1 incorporates main commit `d0aed8a`, preserving the left-eye and live-binocular implementation alongside the frozen right-eye benchmark. Three new left-eye original files (column workbook, ray workbook and CSV) match pinned upstream bytes. The fourth addition is a derived subset: all 1,779 L2 body IDs, types and sides were checked against the hash-verified Xenova/MaleCNS metadata; no connectivity weights are included. `data/license_inventory.json` records these four files and the additional full CC BY 4.0 license text, without relaxing the publication guard.

The subset adds **CC BY 4.0** attribution obligations. Left-eye joined data preserves GPL column assignments, CC BY identity metadata and CC BY-SA direction components. Together with the later MIT code update below, the package collection is described as `MIT AND GPL-3.0-only AND CC-BY-SA-4.0 AND CC-BY-4.0`. Report notice copies are refreshed, while all frozen benchmark inputs, outputs and scores remain unchanged. The author's original notices and license evidence are the same pinned sources as above; this addendum makes no new legal-clearance claim.

## Same-day original-code MIT integration

Main commit `2aaff46` (PR #2) changes original project code and documentation to MIT. This publication preserves that change, including the copyright notice and contribution policy. Benchmark code and report documentation use MIT; GPL, CC BY-SA and CC BY components retain their original terms. The stand-alone report carries a separate full GPLv3 notice for its mapping components, in addition to the root MIT notice. No source-specific license bytes, frozen numerical results or original execution hashes are changed. This integration does not extend the scope of the source review or establish new rights over third-party work.

## Limits and primary references

- Permission from an upstream repository is evidence of a license offered by that repository; this review cannot prove every upstream contributor owned all rights. No author was contacted and no bespoke permission was obtained.
- Identifying separate license-bearing components is intentional. Creative Commons lists [GPLv3 as one-way compatible with CC BY-SA 4.0](https://creativecommons.org/compatible-licenses/) and provides [specific cautions](https://wiki.creativecommons.org/wiki/ShareAlike_compatibility:_GPLv3). We do not use that mechanism to erase source notices or relicense GPL material as CC BY-SA.
- [CC BY-SA 4.0 legal code](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en) governs attribution, changes and share-alike. Software permissions and data permissions must both be preserved.
- [GitHub's license guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) explains that a public repository without a license is not a general reuse grant. The [US Copyright Office's software guidance](https://www.copyright.gov/circs/circ61.pdf) distinguishes functional methods from copyrightable expression; that distinction is not a worldwide legal clearance of this implementation.
- [Dryad dataset](https://datadryad.org/dataset/doi:10.5061/dryad.ngf1vhj4c); [dataset license metadata](https://datadryad.org/api/v2/datasets/doi%3A10.5061%2Fdryad.ngf1vhj4c); pinned source/license URLs are in the machine-readable inventory.
- No patent freedom-to-operate, trademark registry, contractual restriction or worldwide jurisdiction review was performed. Source-project names are used for attribution/comparison without logos or endorsement claims. Commercial distribution or a request for a legal guarantee needs qualified legal review.
