# Extension gate v1

## Reviewed scope
Pre-import checks cover general directory plugins, pip entry points, model-provider modules, memory providers and their CLI modules, context-engine providers, and local MCP transport launch. Bundled code under this checkout's real plugins directory is the existing baseline. Remote MCP transport is unchanged. No new tool schemas, dependency updates, config changes or Desktop renderer changes.

Default behavior is deny. General plugins still also require their existing enable setting. A manifest claiming source=bundled does not grant trust to an external path. External symlinks cannot inherit bundled trust.

## Owner exception format
On macOS the policy path is `/private/etc/hermes/extension-trust.json`; on other platforms `/etc/hermes/extension-trust.json`. No environment/config override is supported. Missing/malformed policy fails closed.

```json
{"schema_version":1,"directories":[{"path":"/opt/hermes-approved/example","sha256":"REVIEWED_TREE_SHA256"}]}
```

The policy, code tree, and every ancestor must be root-owned, non-group/world-writable, and not symlinks. Hash covers all regular tree files and their relative names; special files are rejected. Compute a digest using `hermes_cli.extension_gate.tree_digest(Path(...))` after an operator has installed reviewed immutable code. The policy is written by the human operator outside the agent. No approval file was created by this implementation. The gate does not automatically grandfather user plugins.

Pip entry-point plugins and local MCP subprocess launches are blocked outright in v1. Exceptions for these are deliberately unsupported until complete dependency/launch identity is designed. A denial is permanent for that attempt, not a network error to retry.

## Important threat boundary
This is a loader gate, NOT an OS security boundary for a same-user process with arbitrary terminal access. Agent-writable Hermes source could be modified to remove the gate; root-owned policy does not fix that. Bundled code and preexisting Python dependencies remain trusted baseline; approved plugins can import that environment's dependencies. This does not sandbox package installation, scripts, cron, terminal, external agents or skill execution. Full containment and source protection remain separate work. Windows root ownership semantics are not a supported exception workflow in v1; no guarantee of Windows owner exceptions is made.

## Deployment
Implemented in checkout, not committed/pushed and not activated by restarting Desktop. New processes importing changed files use the new gate. Already loaded modules in existing processes are not retroactively unloaded. Backend-only controlled restart and runtime verification are needed for Desktop activation; no Electron rebuild is required for these Python changes. Do not announce full containment after restart.

## Tests
`venv/bin/python -m pytest -o addopts='' tests/hermes_cli/test_extension_gate.py tests/hermes_cli/test_project_plugin_rce_bypass.py tests/tools/test_osv_check.py tests/tools/test_mcp_tool.py -q`

Dedicated tests exercise denied marker payloads through actual loaders, policy absence/malformed content, writable policy rejection, content changes, bundle compatibility, symlink rejection, pip denial before entry-point discovery and local MCP denial before OSV/spawn. Approval-path ownership is mocked only for content-identity unit tests; no privileged policy changes occur in tests. Legacy mocked stdio transport lifecycle tests mock the gate locally to exercise retained transport machinery; separate gate integration tests do not mock denial.
