# BrainCPU test fixture

`brain.js` is the unchanged upstream CPU engine from
https://huggingface.co/spaces/Xenova/fruit-fly-simulation/blob/776d115ee5aa934578a87fd6d260d138084f59c1/src/brain.js

The original MIT application notice is preserved in `LICENSE`. The data and
other-component notices in that original file describe upstream material;
no connectome data are included in this fixture. Tests generate a tiny,
explicitly synthetic graph and execute the real engine to check streaming
state, clearing input rates, identity validation, and connection controls.

Production runs load their separate model installation and verify its array
hashes. This fixture is not the whole fly brain and is not a biological test.
