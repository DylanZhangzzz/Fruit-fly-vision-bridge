# Contributing

Questions and contributions in English or Chinese are welcome. Use [Issues](https://github.com/DylanZhangzzz/Fruit-fly-vision-bridge/issues) for reproduction failures, camera adapters, dataset suggestions and scientific objections. The roadmap lists experiments that would most improve the evidence.

## Development

```sh
python -m venv .venv
# Activate the environment, then:
python -m pip install -e ".[analysis,camera]"
python scripts/run_checks.py
```

Keep changes focused. A PR should explain the user-visible or scientific behavior, how it was checked, and what remains unverified. Add a meaningful test for an adapter, coordinate convention, unit conversion, invalid-data policy, or train/test leakage risk you change. Do not add tests that simply repeat implementation arithmetic as their supposed independent oracle.

## Scientific claims and data

- Specify what is measured, modeled or assumed; state units and clock domains.
- Preserve unknown/out-of-view samples. Do not turn missing depth/direction into black visual input.
- Cite original sources with a fixed version and hash. Include original license notices. Do not replace an upstream dataset silently.
- Keep animal-level grouping and train/test separation explicit. Freeze protocols before evaluating held-out outcomes. Keep negative R², failed runs and parameter-boundary cases visible.
- A synthetic test, network spike, or good training fit does not establish biological correctness. Predictions without independent recordings must be labeled predictions.
- Never equate camera code, physical radiance, effective voltage, ΔF/F and firing Hz without an independently supported conversion.

## Sharing recordings

Do not commit raw room recordings, faces, device serials, private paths, credentials or large weights. Prefer a small synthetic reproduction. If a new public recording is necessary, establish its sharing permission and license, remove private information, and publish it as a separately versioned dataset with a manifest. The existing `.gitignore` is a convenience, not a substitute for reviewing a diff.

## Licensing contributions

Original code and documentation contributions are submitted under the project's [MIT License](LICENSE). Submit only material you have the right to contribute. For third-party code or data, preserve the original license and attribution, and add its path and terms to [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Mapping data and derivatives retain their source-specific terms; do not label them MIT simply because they are stored in this repository.

All issue discussions should address evidence and code respectfully. Upstream authors and contributors may disagree with an interpretation; document the evidence rather than presenting their work as endorsing this bridge.
