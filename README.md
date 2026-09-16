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
| Summary | Thesis, supporting arguments, objections, confidence assessment with stored vs derived confidence, confidence gap (adopt derived), conjunction weakest links, evidence recorded/asserted; linked living-library beliefs with their live stance; recent history with who wrote each change |
| Graph | Layered layout by default (thesis on top, premises below, evidence at the bottom, objections beside what they attack); switch to a free force layout in the corner. Roles: ◉ thesis, ● claim, ◆ objection, ◇ concession, ■ evidence (dashed = asserted, unverified). Typed edges: supports, grounds, rebuts/refutes, concedes, narrows, supersedes. Superseded/retired positions stay visible, dimmed. `→n%` marks a derived confidence that differs from the stored one |
| Inspect | A node's stored and derived confidence (with one-click adopt), provenance (attach a real source to flip asserted → recorded), support mode per supporting argument, defeaters, manual interventions, lifecycle (supersede, retire, typed links). Hard delete is offered only for nodes nothing references |
| Add | Plain-text nodes with a dialectical role; structured claim/evidence/argument forms (argument gets a support mode); typed links; import/export of the lossless `epist-graph/v1` JSON or a flat `{nodes, edges}` document |
| Sources | Unsourced-evidence audit; document ingestion (LLM proposes claims/arguments/objections grounded in verbatim spans; nothing is committed until you accept nodes) |
| Analysis | Coherence checks, blind spots, stress test and assumptions for the selected node |

`CURRENT_MODEL.md` is the as-built description of the object model and the
F1–F5 decisions.

## Rules the engine now enforces

- **A source string is not provenance.** Evidence that is merely asserted starts
  `provisional` in the ATMS, never `accepted`; only evidence with a recorded
  source (attached through recall) is grounded. Generated graphs are asserted
  until you attach sources.
- **Deletion loses the dialectic.** Claims are superseded or retired, never
  removed; both stay in the graph as dimmed history with the reason kept.
- **Who wrote it is a property of the channel.** Every workspace commit carries
  the actor as its git author and an `Actor:` trailer: `owner:web` from the
  browser, `agent:claude-desktop` from the MCP server (set `EPIST_AGENT` to
  rename), `owner` from an interactive terminal, `agent:cli` from a script.
  Commits from before this rule read as `unattributed`.

## Living-library bridge

The workbench and the living library (`~/workspace/epistemic/memory`) stay
separate stores. A workspace can link the beliefs it argues for (shown in the
Summary with their stance), and a thesis can be captured into the library as a
`derived` belief whose evidence is the workspace at its current commit. Captures
are written under the workbench's own agent identity; they become the owner's
word only when stood behind from the owner's terminal. If the library is not
present (`EPIST_MEMORY_PATH`), the bridge reports unavailable and nothing else
is affected.

## Workspaces

The sidebar filters by name or thesis. Archiving a workspace writes a
`.archived` marker inside it and hides it from the list; nothing is deleted.
