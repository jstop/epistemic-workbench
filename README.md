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
  `provisional` in the ATMS, never `accepted`; only evidence registered in the
  living library (a snapshot or a referenced uri) is grounded. Generated graphs
  are asserted until you attach sources.
- **Deletion loses the dialectic.** Claims are superseded or retired, never
  removed; both stay in the graph as dimmed history with the reason kept.
- **Who wrote it is a property of the channel.** Every workspace commit carries
  the actor as its git author and an `Actor:` trailer: `owner:web` from the
  browser, `agent:claude-desktop` from the MCP server (set `EPIST_AGENT` to
  rename), `owner` from an interactive terminal, `agent:cli` from a script.
  Commits from before this rule read as `unattributed`.

## The living library is the substrate

Decided 2026-09-15: the library's canonical log (`~/workspace/epistemic/memory`)
is the one provenance substrate. The workbench is an interpreter over it and
never owns beliefs.

- Sources a workspace cites are registered in the library as evidence; the
  workspace stores the library `evidence_id`. Ingested documents are
  content-addressed snapshots there.
- A belief **grounds in** a workspace, never the reverse: `ground-belief`
  snapshots the workspace at its commit into the library
  (`epist-workspace://<name>@<commit>`), adds it under the belief with the
  thesis as a located span, and sets the belief's anchor to
  `epist verify-thesis <name>`, which exits 2 when the thesis is defeated and 3
  when its derived confidence is below `--min-derived`. The library's
  `memory_verify` then literally re-runs the argument.
- Which beliefs a workspace argues for is a query against the library (beliefs
  whose evidence includes a snapshot of it), shown in the Summary tab.
- `capture-belief` creates a new `derived` belief from the thesis, grounded and
  anchored the same way. Captures are written under the workbench's own agent
  identity and become the owner's word only when stood behind from the owner's
  terminal.
- Every claim carries its content hash (sha256 of the text, unnormalised); an
  accepted ingestion proposal records the accepted hashes in its commit.

- **Run identity.** Every interpreter run is recorded in the library with its
  identity (`epistemic-workbench/<component>@<model or version>`), its canonical
  inputs and what it produced: `generate` (output: a workspace snapshot),
  `extract` (output: the proposal plus one grounded interpretation per proposed
  node, located verbatim in the source), `curate` (output: the accepted nodes by
  content hash, with the accepting channel's actor). A proposed node is an
  interpretation until a person commits it; it is never a belief. The Summary
  tab lists the runs against a workspace.

If the library is not present (`EPIST_MEMORY_PATH`), the bridge reports
unavailable, evidence stays asserted, and runs go unrecorded (the proposal says
so). The design memo with the full decision
record: https://claude.ai/artifact/9zBDqaNorWVwLkvBKqTRMg

## Workspaces

The sidebar filters by name or thesis. Archiving a workspace writes a
`.archived` marker inside it and hides it from the list; nothing is deleted.
