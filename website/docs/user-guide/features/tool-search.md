---
title: Tool Search
sidebar_position: 95
---

# Tool Search

Tool schemas can consume a substantial fraction of the context window on
every turn even when only a few are relevant. This includes large MCP and
plugin surfaces plus built-in tools that are useful only after a specific
event.

**Tool Search** is Hermes' opt-in progressive-disclosure layer for that
problem. When activated, MCP tools, non-core plugin tools, and a curated set
of event-triggered built-ins are replaced in the model-visible tools array by
three bridge tools. The model loads each specific schema on demand.

:::info The normal working set stays direct
High-frequency tools such as `terminal`, file operations, skill discovery,
and `memory` remain directly visible. The default curated deferred set is
`todo`, `session_search`, `clarify`, `process`, `cronjob`, `computer_use`,
`image_generate`, `read_terminal`, and `skill_manage`. Session toolset scope
still applies: deferral never grants a tool the session did not already have.
:::

## How it works

When Tool Search activates for a turn, the model sees three new tools in
place of the deferred ones:

```
tool_search(query, limit?)     — search the deferred-tool catalog
tool_describe(name)            — load the full schema for one tool
tool_call(name, arguments)     — invoke a deferred tool
```

A typical interaction looks like:

```
Model: tool_search("create a github issue")
  → { matches: [{ name: "mcp_github_create_issue", ... }, ...] }
Model: tool_describe("mcp_github_create_issue")
  → { parameters: { type: "object", properties: { ... } } }
Model: tool_call("mcp_github_create_issue", { title: "...", body: "..." })
  → { ok: true, issue_number: 42 }
```

When the model invokes `tool_call`, Hermes **unwraps the bridge** and
dispatches the underlying tool exactly as if the model had called it
directly. Pre-tool-call hooks, guardrails, approval prompts, and
post-tool-call hooks all run against the real tool name — not against
`tool_call`. The activity feed in the CLI and gateway also unwraps so you
see the underlying tool, not the bridge.

## When does it activate?

By default Tool Search runs in `auto` mode and activates whenever at least one
deferrable tool is present. `on` currently has the same activation behavior;
`auto` remains the compatibility default. `threshold_pct` is retained for
configuration compatibility and future catalog budgeting.

This decision is re-evaluated every time the tools array is built, so:

- A normal core session activates because its curated event-triggered tools
  are deferred.
- A session with many MCP tools avoids loading every MCP schema directly.
- Removing MCP servers mid-session correctly returns to direct exposure
  on the next assembly.

## Configuration

```yaml
tools:
  tool_search:
    enabled: auto       # auto (default), on, or off
    threshold_pct: 10   # compatibility field; reserved for future budgeting
    search_default_limit: 5
    max_search_limit: 20
    # defer: []          # optional explicit set; [] keeps all core tools direct
```

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `auto` | `auto` and `on` activate when at least one tool is deferrable; `off` disables Tool Search. |
| `threshold_pct` | `10` | Compatibility field retained for future catalog budgeting. Range 0–100. |
| `search_default_limit` | `5` | Hits returned when the model calls `tool_search` without a `limit`. |
| `max_search_limit` | `20` | Hard upper bound the model can request via `limit`. Range 1–50. |
| `defer` | curated set | Optional explicit list of built-in names to defer. `[]` restores direct exposure for every core tool. |

You can also flip the legacy boolean shape:

```yaml
tools:
  tool_search: true   # equivalent to {enabled: auto}
```

## When NOT to use it

Tool Search trades a fixed per-turn token cost (the three bridge tool
schemas, ~300 tokens) and at least one extra round trip (search →
describe → call) for the savings on the deferred schemas. It's a clear
win when you have many tools and use few per turn; it's overhead when
you have few tools total.

Set `enabled: off` or `defer: []` when direct exposure is preferable for a
small, fixed toolset.

## Trade-offs that don't go away

These come from the prompt-cache integrity invariant — they are inherent
to any progressive-disclosure design, not specific to this implementation:

- **One extra round trip on cold tools.** The first time the model needs
  a deferred tool, it spends one or two extra model calls to find and
  load the schema. The token savings on the static side are real, but a
  portion is paid back at runtime.
- **No cache benefit on deferred schemas.** A loaded `tool_describe`
  result enters the conversation history (so it does get cached on
  subsequent turns) but it never benefits from the system-prompt cache
  prefix.
- **Model-quality dependence.** Tool Search assumes the model can write a
  reasonable search query for the tool it wants. Smaller models do this
  less well; the published Anthropic numbers (49% → 74% on Opus 4 with
  vs. without tool search) show the upside but also that ~26 points of
  accuracy is still retrieval failure.
- **Toolset edits invalidate cache.** Adding or removing a tool mid-
  session changes the bridge tools' descriptions (which include the
  count of deferred tools) and the catalog, so the prompt cache is
  invalidated. This is the same trade-off as any toolset edit.

## Implementation details

- **Retrieval:** BM25 over tokenized tool name + description + parameter
  names. Falls back to a literal substring match on the tool name when
  BM25 returns no positive-score hits, which protects against
  zero-IDF degenerate cases (e.g. searching `"github"` against a
  catalog where every tool name contains "github").
- **Catalog is stateless across turns.** It rebuilds from the current
  tool-defs list every assembly — no session-keyed `Map`. This avoids
  the class of bug where a stored catalog drifts out of sync with the
  live tool registry.
- **The catalog is scoped to the session's toolsets.** `tool_search`,
  `tool_describe`, and `tool_call` only ever see and invoke tools the
  session was actually granted. A subagent, kanban worker, or gateway
  session restricted to a subset of toolsets cannot use the bridge to
  discover or call a tool outside that subset — the deferred catalog is
  the deferrable slice of the session's own enabled/disabled toolsets,
  not the whole process registry.
- **No JS sandbox.** Hermes uses the simpler "structured tools" mode
  (search / describe / call as plain functions). The JS-sandbox "code
  mode" some other implementations offer is a large surface area; we
  skip it.

## See also

- `tools/tool_search.py` — the implementation
- `tests/tools/test_tool_search.py` — the regression suite
- The `openclaw-tool-search-report` PDF in the original implementation
  PR for the research that shaped the design
