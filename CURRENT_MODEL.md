# CURRENT_MODEL.md — what the workbench actually is

> **Addendum 2026-09-15.** The recall integration described in §1 and §8 below
> was replaced: the living library (`~/workspace/epistemic/memory`) is now the
> one provenance substrate. `recall_client.py` is gone; `library_client.py`
> registers evidence, snapshots workspaces, and grounds beliefs. Recall retires
> in a later phase. See README "The living library is the substrate" and the
> design memo linked there. The rest of this file is the as-built record of
> F1–F5 and still describes the object model accurately.

Reconstructed by reading the source (`epist/model.py`, `engine.py`, `store.py`,
`llm.py`, `agent.py`, `compare.py`, `cli.py`, `mcp_server.py`) and sample
workspace JSON. This is the ground truth to reconcile the feature brief (§4)
against. Where the brief and the code disagree, the code is described here and
the divergence is called out.

---

## 1. Where things live

- Package is **`epist/`** at the repo root (NOT `epistemic-workbench/src/...`).
  - `model.py` — dataclasses (the schema)
  - `store.py` — JSON-file persistence + all git operations
  - `engine.py` — ATMS, coherence (7 checks), blind spots, assumptions, stress test, Bayes, calibration
  - `llm.py` — single-shot `messages.create` generator + `compute_summary` (markdown)
  - `agent.py` — Agent-SDK tool-calling generator + enhance/synthesize
  - `compare.py` — semantic-key structural diff between two branch stores
  - `cli.py` — `epist` Click CLI (full surface, incl. `claim/argument/evidence new`)
  - `mcp_server.py` — FastMCP server (the tool surface Claude Desktop sees)
- Workspaces: `workspaces/<name>/` — one directory per workspace, **each its own git repo**.
  - Files: `claims.json`, `arguments.json`, `evidence.json`, `evaluations.json`,
    `predictions.json`, `foundations.json` (each a JSON **array** of serialized
    dataclasses; foundations is an object), plus `thesis.md` and `summary.md`.
  - Forks = git **branches**; versions = git **commits** tagged
    `[init] / [generate] / [enhance] / [analysis] / [manual] / [fork] / [merge]`.
  - `compare_forks` / `merge_forks` read other branches via `git show <branch>:file.json`
    without checking them out (`Store.load_branch_store`).
- `recall` sibling server is at **`/Users/jstein/workspace/recall/recall`** (+ a
  SQLite db at `~/.recall/recall.db`). Its exact tool signatures are **not yet
  confirmed** — deferred to F2 per the brief.
- Deps confirmed available in `~/python/global`: `mcp`, `anthropic`,
  `claude_agent_sdk`, `pytest 8.4.1`. **No `pyproject.toml`, no existing tests.**

---

## 2. The object model (the real schema)

Five top-level **node** dataclasses, all content-addressed by `id =
sha256(canonical_json_of_a_few_fields)`:

| Object | Key fields | Notes |
|---|---|---|
| `Claim` | `subject, predicate, object` (hyphenated triple), `confidence: Confidence`, `modality`, `scope`, `identity`, `assumes: [claim_id]`, `is_root`, `previous_version`, `version_meta`, `notes`, `created_at`, `id` | `notes` holds the natural-language text. ID hashes subject/predicate/object/created_at. |
| `Evidence` | `title, description, evidence_type, source: str, reliability: float`, `identity`, `notes`, `created_at`, `id` | `source` is a **free string** — no provenance structure (this is the F2 hole). |
| `Argument` | `conclusion: id`, `premises: [id]`, `pattern`, `label`, `confidence: Confidence`, `defeaters: [Defeater]`, `identity`, `notes`, `created_at`, `id` | An argument **is a node**. Defeaters are embedded, not separate nodes. |
| `Evaluation` | `target: id`, `judgment` (accept/reject/suspend/needs_work), `reasoning` | Forces ATMS status on its target. |
| `Prediction` | `subject/predicate/object`, `confidence`, `resolution_date`, `resolved`, `outcome` | For calibration; orthogonal to argument graphs. |

Embedded / value types: `Defeater(type, description, status, response)`,
`Confidence(level: float, decomposition: dict?)`, `Scope`, `Identity`.

Enums:
- `Modality`: empirical / analytic / normative / modal / predictive
- `EvidenceType`: observation / experiment / testimony / document / statistical / formal_proof
- `InferencePattern`: modus_ponens, abduction, induction, analogy, testimony, causal, … (14, with `PATTERN_METADATA[min_premises, validity_conditions, strength]`)
- `DefeaterType`: **rebutting / undercutting / undermining**
- `DefeaterStatus`: **active / answered / conceded / withdrawn**
- `EvaluationJudgment`: accept / reject / suspend / needs_work

### Edges are implicit — there is no generic edge table

The only relationships that exist:
- **support** = an `Argument` (its `premises` → its `conclusion`).
- **objection** = a `Defeater` *embedded inside an Argument* (rebut/undercut/undermine + status).
- **assumes** = `Claim.assumes` list (claim → assumption claims), attached to the thesis.
- **versioning** = `Claim.previous_version` pointer + `version_meta`.

There is **no** `supports/refutes/rebuts/concedes/grounds/narrows/supersedes`
typed-edge concept and **no `{from, rel, to}` records.**

---

## 3. How status works — computed, not stored

`compute_atms(store)` recomputes status for **every** object at read time and
returns `{id: status}`. **Status is never persisted on nodes.**

- ATMS statuses: **accepted / provisional / defeated / unknown** (class
  `ATMSStatus`).
- Evidence starts `accepted`; claims start `provisional`. An argument is
  `accepted` iff **all** premises are accepted/provisional **and** it has no
  *defeating* defeater (a defeater defeats if its status is `active` **or**
  `conceded`; `answered`/`withdrawn` do not). An accepted argument promotes its
  conclusion; a defeated argument defeats its conclusion **only if it was the
  sole support**. `Evaluation` accept/reject overrides.

So the ATMS layer is **structurally conjunctive** (an argument needs all its
premises) — but it is **boolean**, not numeric.

---

## 4. How confidence works — and the F3 finding

**Confidence is NOT propagated.** This is the single most important divergence
from the brief.

- `Claim.confidence.level` and `Argument.confidence.level` are **stored values**,
  written by the LLM at generation time or by hand via `set_confidence`. Nothing
  computes a claim's confidence from its supporting arguments or an argument's
  confidence from its premises.
- The only aggregate is `average_argument_strength` in `compute_summary` = the
  **mean of argument confidence levels** — a display statistic, shown next to the
  (independently stored) thesis confidence. This is almost certainly the "~62%
  average" the brief saw.
- The nearest thing to conjunction-awareness today is a **coherence warning**
  (`probabilistic_coherence`): it flags when a conclusion's stored confidence
  exceeds its weakest premise's. It warns; it does not recompute.

⇒ **F3 is not "change an average to a product." There is no propagation to fix —
it has to be added.** A `support_mode {conjunctive|disjunctive|independent}` on
`Argument` plus a real propagation pass (product/min for conjunctive, max for
disjunctive) is a genuinely new computation, and it will change numbers shown
across `get_summary` / `show_graph` for every existing workspace. Scope is larger
than the brief implies — flagging per the "code wins" rule.

> Also note: the brief says confidence "appears to use **DF-QuAD**." **There is
> no DF-QuAD anywhere in the code.** What exists is boolean ATMS + a standalone
> `bayesian_update` CLI helper + the coherence checks. No quantitative argument
> aggregation of any kind.

---

## 5. Tool surface (MCP) vs. the brief

Present in `mcp_server.py`: `list_workspaces, generate_thesis, job_status,
get_summary, suggest_enhancement, enhance_and_accept, get_versions,
get_workspace_stats, show_graph, respond_to_defeater, concede_defeater,
add_evidence_to_claim, challenge_claim, set_confidence, fork_workspace,
list_forks, switch_fork, compare_forks, merge_forks, server_status`.

- **No** `add_claim`, `add_argument`, `link`, `import_graph`, `export_graph` at
  the MCP layer → confirms F1's gap. (The **CLI** has `claim new` /
  `argument new` / `evidence new` and an `export` command, but `export` writes a
  bespoke flat dump and there is **no import** — not a round-trip, and not
  reachable from MCP.)
- Generation invents evidence with authoritative-looking `source` strings (e.g.
  the `issuerless-identity` workspace cites real-sounding USENIX/IEEE papers and
  C2PA specs). Nothing marks them as unverified → confirms F2.
- `enhance`/`enhance_and_accept` call `s.clear()` then regenerate. The old graph
  survives **only in git history**; the live graph drops every rejected position
  → confirms F4.

---

## 6. Reconciliation map (brief §4 → code)

| Brief §4 concept | Reality in code | Gap / mapping needed |
|---|---|---|
| node types thesis/claim/argument/evidence/**objection/concession** | Claim/Evidence/Argument nodes; objection & concession are **embedded Defeaters**, not nodes | objection/concession have no node identity |
| flat `text` field | Claim = subject/predicate/object + `notes`; Evidence = title/description | importer must map `text`→`notes` (and synthesize/blank the triple) |
| `status` ∈ live/defeated/superseded/conceded/rebutted/open (stored) | status is **computed** ATMS accepted/provisional/defeated/unknown, never stored | no `superseded`/`open`; storing status at all is new (F4) |
| `confidence` on node | exists (`Confidence.level`) | ok, but not propagated (F3) |
| `killed_by` | none | new field/edge (F4) |
| edges `{from, rel, to}`, 7 relations | no generic edges; only argument/defeater/assumes/previous_version | **central F1 decision** (see below) |
| content-addressed import IDs | IDs are sha256(of-fields); but deserialize **accepts an explicit `id=`** | importer can preserve given IDs (good for round-trip) |

### The central F1 decision (needs Josh)
F1's acceptance is *lossless* `import_graph(export_graph(W))` **and** importing the
`osmio_argument_graph.json` fixture (objection/concession nodes; supports / refutes
/ rebuts / concedes / grounds / narrows / supersedes edges). The current model
cannot represent `narrows`, `grounds`, or `supersedes` at all, and represents
objections as embedded defeaters rather than nodes. Two ways forward:

- **(A) Map onto existing constructs.** supports→Argument, rebuts/refutes→Defeater,
  concedes→conceded Defeater, supersedes→`previous_version`/status. Lossy/awkward
  for narrows & grounds; objection/concession lose node identity. Smaller change.
- **(B) Add a parallel generic edge layer** (`edges.json`: `{from, rel, to}`) and
  let objection/concession be real nodes, while the ATMS/argument engine keeps
  running off the existing constructs (with a thin adapter). Clean lossless
  round-trip and matches the "analyzer → editor" pivot. Bigger change.

Recommendation: **(B)** — it's the only option that meets the lossless + fixture
acceptance criteria, and the pivot is the whole point of the brief. But this is a
real architectural fork, so confirm before building.

---

## 7. Guardrail facts to preserve

- Existing workspaces (e.g. `one-regress`, `issuerless-identity`, 30+ others) load
  via `Store._load()` and must keep loading after any schema change → **all new
  fields must be optional with safe defaults** in the `_deserialize_*` functions.
- `one-regress` currently has only a `master` branch in my check (the brief
  mentioned a `narrowed-conditional` branch — not present now; worth confirming
  with Josh, may be in another copy).
- The `osmio_argument_graph.json` fixture is **not in the repo** — Josh needs to
  hand it over to complete F1's acceptance test.

---

## 8. Recall API (confirmed — for F2 / F5)

Server: `/Users/jstein/workspace/recall/mcp-server/server.py` (FastMCP name
`"recall"`); core logic in `recall/db.py` over SQLite at `~/.recall/recall.db`.
The current ("tracing") tool set we should integrate with:

- `record_source(source_type, content, external_id=None, created_at=None,
  ingesting_conversation_uuid=None, content_summary=None, metadata=None) -> int`
  Idempotent on `(source_type, external_id)`. `source_type` must be in
  `VALID_SOURCE_TYPES` (e.g. document / web_fetch / conversation_message /
  tool_use … — confirm the exact set before F2/F5). Returns the **source id (int)**.
- `record_derivation(claim_text, edge_type, source_record_id=None,
  recorded_by="claude", conversation_uuid=None, context=None, notes=None) -> int`
  `edge_type` ∈ direct_quote / paraphrase / synthesis / inference / pattern_match /
  memory_block. **Invariant: `pattern_match` ⇔ `source_record_id is None`; every
  other edge_type REQUIRES a real `source_record_id`.** This maps cleanly to F2:
  workbench `provenance.kind="recorded"` ⇒ a non-`pattern_match` derivation with a
  source id; `kind="asserted"` ⇒ a `pattern_match` (orphan) derivation.
- `trace_derivation(claim_text=None, claim_hash=None, limit=50) -> [rows]`
- `list_orphan_derivations(limit=50) -> [rows]` — the anti-confabulation view;
  F2's `list_unsourced` should mirror this.

Note these are plain Python fns in `db.py` AND `@mcp.tool()`-wrapped in the
server. Cross-process, the workbench reaches them as **MCP tools** (or, if same
host, could import `recall.db` directly). Per the brief's "don't over-couple"
guardrail: integrate through a thin adapter so that if recall is unreachable,
evidence degrades to `kind:"asserted"` instead of crashing.

---

## 9. Locked decisions (from Josh, this session)

1. **F1 edges → add a generic edge layer.** New `edges.json` with `{from, rel, to}`;
   `objection`/`concession` become first-class nodes. The ATMS/argument engine
   keeps running off the existing Argument/Defeater/assumes constructs via a thin
   adapter, so generated graphs are unaffected and imported graphs still analyze.
2. **F1 fixture → Josh will provide `osmio_argument_graph.json`.** Until then,
   round-trip is validated against a synthetic graph mirroring §4; the real
   fixture wires into the same test when it lands.
3. **F3 → build full propagation.** Add `support_mode {conjunctive|disjunctive|
   independent}` to `Argument` and a real bottom-up propagation pass
   (product/min for conjunctive, max for disjunctive). This *will* change the
   numbers shown for existing workspaces — that's intended.

### AS-BUILT schema (after F1–F4) — report to Josh

The schema as actually shipped on `feature/workbench-editor-provenance`. All
additions are optional with safe defaults, so every pre-existing workspace loads
and analyzes unchanged (guardrail test covers this).

**Claim** (in `claims.json`) — added:
- `node_type: str = "claim"` — claim | thesis | objection | concession
- `status: str|None = None` — stored status override (live/defeated/superseded/
  conceded/rebutted/open). `None` ⇒ ATMS computes it at read time.
- `killed_by: str|None = None` — id of the node that defeated/superseded this one.
(unchanged: subject/predicate/object, confidence, modality, scope, identity,
assumes, is_root, previous_version, version_meta, notes, created_at, id)

**Evidence** (in `evidence.json`) — added:
- `provenance: dict|None = None` — `{"kind":"recorded","source_id":<recall id>,
  "url","quote","retrieved_at"}` or `{"kind":"asserted"}`. **A `source` string is
  NOT provenance**; only `recorded` with a pointer is trusted. Default/None ⇒
  asserted (unverified).

**Argument** (in `arguments.json`) — added:
- `support_mode: str = "independent"` — conjunctive | disjunctive | independent.
  Authoring defaults new multi-premise args to conjunctive. Drives F3 propagation.

**Edge** (NEW collection `edges.json`) — the generic typed-edge layer:
- `{from_id, rel, to, notes, created_at, id}`; `rel` ∈ supports / refutes /
  rebuts / concedes / grounds / narrows / supersedes. Lossless source of truth;
  the ATMS-visible Argument/Defeater constructs are kept in sync by an adapter.

**Computed, not stored** (unchanged): ATMS status (accepted/provisional/defeated/
unknown). **NEW computed**: derived (propagated) confidence — F3 `propagate_
confidence(store)`; shown alongside stored confidence in get_summary, never
written to disk.

**New tools (MCP):** add_claim, add_argument, link, import_graph, export_graph,
attach_source, list_unsourced, set_support_mode, supersede. show_graph gains
`include_superseded`. (Existing tool contracts unchanged.)

### Resulting target schema additions (F1)
- `Claim`: `+ node_type: str = "claim"` (claim|thesis|objection|concession),
  `+ status: Optional[str] = None` (stored override; `None` ⇒ ATMS computes),
  `+ killed_by: Optional[str] = None`. All optional ⇒ existing workspaces load
  unchanged (and IDs are unaffected — `_hash` only uses spo+created_at).
- `Argument`: `+ support_mode: str = "independent"` (field added in F1, propagation
  wired in F3; default preserves today's behavior until F3).
- New `Edge(from_id, rel, to, notes="", id)` persisted in `edges.json`; `rel` ∈
  supports/refutes/rebuts/concedes/grounds/narrows/supersedes.
</content>
</invoke>
