# Epistemic Workbench

An argument-graph analyzer and editor. Each workspace holds one thesis with its
claims, arguments, evidence, objections and concessions, versioned as its own git
repo (forks are branches, every change is a tagged commit). The engine computes
ATMS status, coherence checks, blind spots, and conjunction-aware confidence
propagation; nothing derived is ever persisted.

Two surfaces share the same engine and workspaces:

- **MCP server** — `epist/mcp_server.py`, wired into Claude Desktop as
  `epistemic-workbench` (32 tools).
- **Web UI** — `web/server.py` (FastAPI) serving the React app in `web/frontend`.

```bash
make web      # build the frontend and serve on http://127.0.0.1:8111
make serve    # serve only
make test
```

Workspaces live in `~/workspace/epistemic/workspaces` (override with
`EPIST_WORKSPACES`). The CLI is `epist/cli.py`.

## Web UI tabs

| Tab | What it does |
|---|---|
| Summary | Thesis, supporting arguments, objections, confidence assessment with stored vs derived confidence, confidence gap, conjunction weakest links, evidence recorded/asserted |
| Graph | Force-directed graph. Roles: ◉ thesis, ● claim, ◆ objection, ◇ concession, ■ evidence (dashed = asserted, unverified). Typed edges: supports, grounds, rebuts/refutes, concedes, narrows, supersedes. Rejected/superseded positions stay visible, dimmed. `→n%` marks a derived confidence that differs from the stored one |
| Inspect | A node's stored and derived confidence, provenance (attach a real source to flip asserted → recorded), support mode per supporting argument, defeaters, manual interventions, lifecycle (supersede, typed links) |
| Add | Plain-text nodes with a dialectical role; structured claim/evidence/argument forms (argument gets a support mode); typed links; import/export of the lossless `epist-graph/v1` JSON or a flat `{nodes, edges}` document |
| Sources | Unsourced-evidence audit; document ingestion (LLM proposes claims/arguments/objections grounded in verbatim spans; nothing is committed until you accept nodes) |
| Analysis | Coherence checks, blind spots, stress test and assumptions for the selected node |

`CURRENT_MODEL.md` is the as-built description of the object model and the
F1–F5 decisions.
