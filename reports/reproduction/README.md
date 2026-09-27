# Release reproduction

The project was installed into a fresh Windows Python 3.12 virtual environment, without inherited system packages. The installation's package versions are recorded in `environment.json`.

Verified in that environment:

- All 10 included authoritative mapping-input checksums.
- All 57 implementation tests (9 bridge, 4 projection, 6 calibration, 38 mapping/screen/physiology).
- Regeneration of the reference product and exact MaleCNS author-column join.
- Import/download and checksum verification of all five optional physiology inputs.
- A complete rerun of the whole-fly-held-out physiology benchmark: the seven primary summary means matched the archived results exactly on this machine; the explicit comparison tolerance was 1e-9.
- `pip check` and building a distributable Python wheel.

`verification.json` records comparison differences, protocol hash, current analysis-code hashes and scope. This is a packaging/public-data reproduction. It does not repeat the physical camera experiment, test a living fly, or perform new-stimulus validation. GitHub CI status is separate from these local results.
