# Findings as of 2026-09-27

## Contributions

The project provides an executable connection between published visual-column anatomy and camera observations, a pipeline that explicitly preserves unknown data, controlled screen/camera checks, and an auditable public-physiology benchmark. It integrates existing scientific resources and exposes their limits. It does not claim discovery of a new eye map or proof of whole-brain visual intelligence.

The [FlyDrones L2 adapter](flydrones.md) now makes that spatial mapping reusable in a second runtime. A matched-L2 comparison checks body-ID invariance under reordering, observation status, and screen-bar passage order. The [spatial report](../reports/flydrones/README.md) separates synthetic checks and retrospective private camera replay. A subsequent [full native network qualification](../reports/flydrones-full-network/README.md) runs 166,700 neurons / 10,520,377 connections, confirms downstream propagation and finds a raw-annotation side-selection compatibility issue. Its default motor-output groups remain silent with tonic bias disabled; flight and physiological validity are not established.

## Anatomy and engineering

- Exact author-column joins resolve 847 of 893 L2 IDs, across 846 unique columns. Missing 46 directions are not extrapolated. Two IDs share one ray.
- Official reference-eye rays and MaleCNS body IDs are different products. The author's separate MaleCNS output supplies the bridge; the reference indices are not substituted for neuron identities.
- D435i screen run `20260927-142451-807004` retained 1,728 RGB frames at 59.527 frames/s with no detected frame/queue gaps. 21 L2 IDs / 20 columns and 9 screen regions passed the fixed criteria.
- Worst L2 static error: 3.828 camera-equivalent gray codes. Minimum sine R²: 0.99551. Maximum sine amplitude relative error: 5.57%. All eight flashes and both motion directions passed.
- This required fixed optical reference patches and the frozen LUT from a preceding separate calibration. It is not validation of arbitrary scenes without references.

Earlier runs failed. One moved the screen markers by 22.23 pixels (p95), invalidating calibration reuse. A later run kept geometry stable but still had brightness drift and failed static gray decoding. Those observations motivated independent black/white reference correction; the accepted result used a **fresh prospective recording**, with thresholds unchanged. [Archived screen summary](../reports/screen/README.md).

## Physiological evidence

The official public dataset contains 214 ROI records grouped under 14 MAT fly IDs. The author's separate search-stimulus selection identifies 103 records from 13 flies for the primary analysis. The remaining 111 records remain available as a secondary sensitivity analysis. Records are not guaranteed unique cells across imaging fields.

An audit found:

- The mean of the 103 selected records exactly equals the previously used author high-luminance training curve. Its good match to author parameters cannot count as independent validation.
- 35 records required series-name reconciliation; joining by the literal series name would match a different genotype for 28 records. The compound date/sequence/depth/genotype/stimulus join resolves all primary records, with a bijective primary fly grouping.
- Thirteen author-excluded records have no metadata match and remain marked unresolved, outside the primary analysis.
- Rebinning all 214 released processed time series reproduces the published curves to maximum absolute error 5.55e-17.

The replacement evaluation leaves out an entire fly each time. Primary scores (mean within each fly, then equal weight across 13 flies):

| Measure | Result |
|---|---:|
| Pearson correlation | 0.75039 |
| R² (not correlation squared) | 0.44727 |
| Recurrent-model RMSE | 0.0066306 ΔF/F |
| Feedback-free model RMSE | 0.0071955 ΔF/F |
| Training-mean waveform RMSE | 0.0066460 ΔF/F |
| Constant baseline RMSE | 0.0096343 ΔF/F |
| Flies improved by feedback | 11/13 |
| Primary records with R²≤0 | 5/103 |
| Median absolute peak-time error | 8.33 ms for each polarity |

The mean feedback-free-to-recurrent RMSE improvement is approximately 7.85%. Its fly-bootstrap improvement interval is positive under the frozen descriptive criterion. The improvement over a training-mean waveform template is approximately 0.0000154 ΔF/F, with an interval spanning zero: **no clear advantage over that template is established**.

Feedback parameters touch a preset boundary in 10 of 14 total folds (the 14th fly only has secondary records), limiting parameter identification. The response resolution is 8.33 ms, not sub-millisecond. ASAP2f fluorescence has the opposite sign to depolarization and is not a firing rate. This is a same-study, same-20-ms-flash cross-fly check, not independent-study, natural-scene, spatial receptive-field, male/female transfer or whole-brain validation.

[Interactive per-record results](../reports/physiology/index.html) · [All records CSV](../reports/physiology/cells.csv) · [Full report](../reports/physiology/report.json).

## Reproducibility boundary

Public physiology inputs are available separately with verified hashes, so the numerical analysis can be rerun. Small mapping inputs are included with provenance. Private raw camera recordings are not distributed; their archived engineering summaries and plots can be inspected, and the acquisition protocol can be repeated on a new setup. A camera summary alone cannot independently reproduce the underlying pixel measurements.
