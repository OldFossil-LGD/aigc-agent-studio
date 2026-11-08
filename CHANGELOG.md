# Changelog

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
