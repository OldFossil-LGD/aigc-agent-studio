# Contributing

1. Keep each change focused on the problem it addresses.
2. Run `python -m unittest discover -s tests -v` before submitting.
3. Do not commit routine generated outputs, snapshots or caches. Selected synthetic or cleared examples under docs/evidence may be committed with their run records, source versions and limits.
4. Follow the project rules and governance constraints. Fix a failing check at its cause.

5. After deliberate source changes, inspect source classifications, rebuild with python scripts/knowledge_catalog.py --build, then validate without --build. Do not auto-refresh a catalog during a creative task just to obtain a pass.
6. Run python scripts/fidelity_regression.py and python scripts/verify_recovery_index.py. Keep the original failed evidence alongside the corrected result.
7. Keep public examples synthetic or cleared. Review THIRD_PARTY_NOTICES.md and docs/PUBLICATION_BOUNDARIES.md before adding third-party text or data.
8. A current evidence-reviewed Final is distinct from an engineering draft. See references/delivery-review.md; test fixtures never authorize generation or establish artistic quality.
