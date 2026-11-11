# Changelog

## Unreleased

- Read node identity from either platform projection: `id`/`nodeKey` and `type`/`nodeType`. The single-node detail payload carries only the latter.
- Verify declared canvas positions by reading them back from the project payload. `position: null` means "not declared", and assets and shots are both checked.
- Reject assets without `subject`, which the asset schema requires and the node name is built from.
- Stop rendering absent prompts and coordinates as the string `None`.
- Report stacked node positions in canvas integrity output; they are reported, not treated as failures.
- Check the bundled model-schema snapshot in `lib_doctor` for duplicate keys, the declared count, and missing files. This is snapshot consistency, not a review of schema contents.
- Add a captured platform-projection fixture with a `--check` drift comparison, and a mutation case list for `mutation_check.py --cases`.
- Treat a failed mutation restore as "not verified" rather than "caught".
- Compare node parameters against both places the platform stores them (the `params` object and `params.settings`), so a storage difference alone no longer produces a false parameter mismatch when a build runs again. A real difference is still rejected.
- Reject a declared parameter whose two stored copies disagree, instead of guessing which one the platform uses.
- Compare parameter values with JSON semantics, so `true` and `1` are not treated as equal.
- Explain hash-suffixed missing node names as collision renames: a duplicate display name renames every colliding node, which orphans nodes built earlier.
- Stop repeating a unit a fact already carries (`二十岁上下岁`) and a label it already carries (`层高层高约三米`).
- Report strict-mode artifact warnings as failures, matching the exit code instead of still printing `[WARN]`.

## 1.0.1-beta.2

- Preserve the complete ordered reference list when applying multiple incoming edges.
- Give colliding asset display names stable, distinct node names and reject invalid or duplicate IDs.
- Verify that all planned assets and shots exist, including asset-only canvases.
- Read existing canvas nodes before writing and resume matching plans with an explicit project UUID.
- Isolate CLI stdin, bound CLI waits and report missing executables and connection failures.
- Add offline regressions for reference integrity, input validation and interrupted builds.

## 1.0.1-beta.1

Public Beta.

- Mark the current public version as Beta and align the package metadata.
- Link the Public Beta preview with the updated GitHub address.
- State the LibTV dependency at the start of the README and skill entry.
- Add MCP and CLI setup guidance, account authorization and read-only connection checks.
- Explain that bundled Python platform executors invoke the CLI and that the offline demo covers local compilation.

## 1.0.0

Initial product-focused public upload, subsequently classified as a Beta prerelease.

- Filmmaking skill and reference library for scripts, assets, storyboards and shot prompts.
- Offline compilers and checks for declared constraints, source evidence and delivery state.
- MIT license with project copyright attributed to jiangchenxi, plus upstream notices and recorded provenance limits.
- Synthetic examples and local regressions. Platform generation and media review use separate approval and evidence.

See THIRD_PARTY_NOTICES.md for unresolved source-version and redistribution checks.
