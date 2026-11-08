# Publication data boundaries

- Runtime and snapshot/cache directories are excluded by .gitignore.
- Public fidelity fixtures are synthetic graphs, not a platform readback or reproduction of an original film. They test graph scale, schema and lineage failures only.
- Historical local paths are normalised to `<HOME>`; that marker is not a literal executable command. Use the current-user examples in README for real installation.
- Migration source identifiers use private-source:// aliases. Original source hashes are retained; where a distributed snapshot redacts a local path, the manifest explicitly records a changed target hash and byte_identical=false. Original private bytes stay outside this tree.
- Test fixtures and historic files named Final do not constitute a current reviewed creative delivery.
- Source attribution is not blanket ownership or redistribution permission. See THIRD_PARTY_NOTICES.md for upstream notices and outstanding provenance checks before public release.
