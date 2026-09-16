#!/usr/bin/env python3
"""Episteme — one MCP server over the whole epistemic pipeline (phase 5).

Four lenses on one substrate, served to every Claude surface alike:

  belief_*   what do I believe, and how much should I rely on it?   (living library)
  argue_*    does this argument hold up?                             (workbench)
  trace_*    where did this come from, and what produced it?         (evidence, spans,
                                                                       interpretations, runs)
  pattern_*  where do people disagree?                               (mapper — dormant;
                                                                       reserved, not served)

The server composes the two existing servers' tools under namespaces rather
than reimplementing them, and adds the trace lens, which neither had. It runs
against whatever library branch EPISTEMIC_BRANCH names (default main), so a
dev build can be served side by side with main under a different server name.

Channel: this process is an AI surface's door. Everything it writes is
attributed to agent:<EPISTEMIC_AGENT> (default "episteme") in both the library
and the workspaces — never to the owner.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── channel + paths, before anything that reads them at import ───────
os.environ.setdefault("EPISTEMIC_AGENT", "episteme")
os.environ.setdefault("EPIST_AGENT", os.environ["EPISTEMIC_AGENT"])
os.environ.setdefault("EPIST_WORKSPACES", str(Path.home() / "workspace" / "epistemic" / "workspaces"))
_MEMORY = Path(os.environ.get("EPIST_MEMORY_PATH", Path.home() / "workspace" / "epistemic" / "memory"))
_HERE = Path(__file__).resolve().parent
for p in (str(_MEMORY), str(_HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from mcp.server.fastmcp import FastMCP  # noqa: E402

import engine as library  # noqa: E402  (the library's engine, on the selected branch)
import server as library_server  # noqa: E402  (its MCP tools; declares the channel at import)
from epist import mcp_server as workbench  # noqa: E402  (declares its channel at import)
from epist import library_client  # noqa: E402
from epist import actor as _wb_actor  # noqa: E402

# Declare the channel explicitly (the imports above declare it too, but only on
# first import; this server must be the channel whenever it is the process).
library.CHANNEL_ACTOR = library.agent_actor(os.environ["EPISTEMIC_AGENT"])
_wb_actor.declare_channel(_wb_actor.agent_actor(os.environ["EPISTEMIC_AGENT"]))

mcp = FastMCP("episteme")

# ── belief lens: the library's tools, namespaced ─────────────────────
_BELIEF_TOOLS = {
    "belief_recall": library_server.memory_recall,
    "belief_capture": library_server.memory_capture,
    "belief_verify": library_server.memory_verify,
    "belief_reconcile": library_server.memory_reconcile,
    "belief_why": library_server.memory_why,
    "belief_health": library_server.memory_health,
    "belief_reindex": library_server.memory_reindex,
    "belief_reconcile_pass": library_server.memory_reconcile_pass,
    "belief_reconcile_apply": library_server.memory_reconcile_apply,
    "belief_ingest_pass": library_server.memory_ingest_pass,
    "belief_ingest_apply": library_server.memory_ingest_apply,
}
for _name, _fn in _BELIEF_TOOLS.items():
    mcp.tool(name=_name)(_fn)

# ── argue lens: the workbench's tools, namespaced ────────────────────
_ARGUE_TOOLS = [
    "list_workspaces", "generate_thesis", "job_status", "get_summary", "suggest_enhancement",
    "enhance_and_accept", "get_versions", "get_workspace_stats", "show_graph",
    "respond_to_defeater", "concede_defeater", "add_evidence_to_claim", "challenge_claim",
    "set_confidence", "supersede", "add_claim", "add_argument", "link", "set_support_mode",
    "export_graph", "import_graph", "attach_source", "list_unsourced", "ingest_document",
    "review_proposal", "commit_proposal", "fork_workspace", "list_forks", "switch_fork",
    "compare_forks", "merge_forks", "server_status",
]
for _name in _ARGUE_TOOLS:
    mcp.tool(name=f"argue_{_name}")(getattr(workbench, _name))


# ── trace lens: where did this come from, and what produced it ───────

def _state():
    return library.get_log().state()


def _short_evidence(e: dict) -> dict:
    return {"evidence_id": e.get("evidence_id"), "uri": e.get("uri"), "media_type": e.get("media_type"),
            "durability": e.get("durability"), "recorded_at": e.get("recorded_at"), "actor": e.get("actor"),
            "kind": (e.get("metadata") or {}).get("kind")}


@mcp.tool()
def trace_claim(text: str = "", claim_hash: str = "", limit: int = 20) -> dict:
    """Trace a claim across the whole pipeline by its content hash (sha256 of the
    exact text, unnormalised — the join key) or by substring of its text: which
    library beliefs carry it, which interpretations state it (proposed claims,
    recall derivations, attestations), which workbench workspaces argue it, and
    which runs produced any of those. Paraphrases are different claims by design."""
    if not text and not claim_hash:
        return {"error": "give text or claim_hash"}
    h = claim_hash or library_client.claim_hash(text)
    q = text.lower()
    st = _state()
    out = {"claim_hash": h, "text": text, "beliefs": [], "interpretations": [], "workspaces": [], "runs": []}
    import datetime as dt
    ref = dt.date.today()
    by_id = library.all_views_by_id()
    for b, _ in library.load_all(include_retired=True):
        bh = library_client.claim_hash(b.get("claim") or "")
        if bh == h or (q and q in (b.get("claim") or "").lower()):
            s = library.stamped(b, ref, by_id=by_id)
            out["beliefs"].append({"id": s["id"], "claim": s["claim"], "stance": s["stance"], "method": s["method"],
                                   "exact": bh == h, "stood_behind_by": (s.get("authorship") or {}).get("stood_behind_by"),
                                   "evidence_ids": b.get("evidence_ids", [])})
    for i in st["interpretations"].values():
        ih = (i.get("metadata") or {}).get("claim_hash") or library_client.claim_hash(i.get("statement") or "")
        if ih == h or (q and q in (i.get("statement") or "").lower()):
            out["interpretations"].append({"id": i["interpretation_id"], "kind": i["kind"], "statement": i["statement"],
                                           "interpreter": i["interpreter"], "exact": ih == h,
                                           "grounding": [{"evidence_id": g["evidence_id"], "quote": (g.get("quote") or "")[:120]}
                                                         for g in i.get("grounding", [])],
                                           "run_id": (i.get("metadata") or {}).get("run_id"),
                                           "superseded_by": i.get("superseded_by")})
    # workspaces: scan claims by hash/text (cheap: 43 small json files)
    from epist.store import Store
    ws_root = Path(os.environ["EPIST_WORKSPACES"])
    if ws_root.exists():
        for d in sorted(ws_root.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            try:
                s = Store(d)
            except Exception:
                continue
            for c in s.claims.values():
                ctext = (c.notes or f"{c.subject} {c.predicate} {c.object}").strip()
                ch = library_client.claim_hash(ctext)
                if ch == h or (q and q in ctext.lower()):
                    out["workspaces"].append({"workspace": d.name, "claim_id": c.id, "text": ctext[:160],
                                              "node_type": getattr(c, "node_type", "claim"), "is_root": c.is_root,
                                              "status": getattr(c, "status", None), "exact": ch == h})
    run_ids = {x.get("run_id") for x in out["interpretations"] if x.get("run_id")}
    for r in st["runs"].values():
        if r["run_id"] in run_ids or any(o.get("id") in {b["id"] for b in out["beliefs"]} for o in r.get("outputs", [])):
            out["runs"].append({"run_id": r["run_id"], "kind": r["kind"], "interpreter": r["interpreter"],
                                "recorded_at": r.get("recorded_at"), "actor": r.get("actor")})
    for k in ("beliefs", "interpretations", "workspaces", "runs"):
        out[k] = out[k][:limit]
    return out


@mcp.tool()
def trace_evidence(evidence_id: str) -> dict:
    """Everything that rests on one piece of evidence: the beliefs and
    interpretations grounded in it (with their spans), the runs that read it,
    whether its content is present, and how it was archived."""
    st = _state()
    e = st["evidence"].get(evidence_id)
    if not e:
        return {"error": f"no evidence {evidence_id}"}
    log = library.get_log()
    out = dict(_short_evidence(e), metadata=e.get("metadata") or {}, size=e.get("size"),
               content_available=bool(e.get("digest") and log.store.has(e["digest"])),
               beliefs=[], interpretations=[], runs=[])
    for bid, b in st["beliefs"].items():
        if evidence_id in b.get("evidence_ids", []):
            spans = [g for g in b.get("grounding", []) if g.get("evidence_id") == evidence_id]
            out["beliefs"].append({"id": bid, "claim": b["claim"], "spans": [(g.get("quote") or "")[:120] for g in spans]})
    for i in st["interpretations"].values():
        spans = [g for g in i.get("grounding", []) if g.get("evidence_id") == evidence_id]
        if spans:
            out["interpretations"].append({"id": i["interpretation_id"], "kind": i["kind"], "statement": i["statement"][:160],
                                           "interpreter": i["interpreter"], "spans": [(g.get("quote") or "")[:120] for g in spans]})
    for r in st["runs"].values():
        if evidence_id in r.get("inputs", []) or any(o.get("id") == evidence_id for o in r.get("outputs", [])):
            out["runs"].append({"run_id": r["run_id"], "kind": r["kind"], "interpreter": r["interpreter"], "recorded_at": r.get("recorded_at")})
    return out


@mcp.tool()
def trace_workspace(workspace: str) -> dict:
    """A workspace's place in the pipeline: the library beliefs grounded in it,
    the snapshots of it the library holds, and the interpreter runs
    (generate / extract / curate) recorded against it."""
    return {"workspace": workspace,
            "beliefs": library_client.beliefs_citing(workspace),
            "runs": library_client.runs_for_workspace(workspace),
            "anchor_command": library_client.anchor_command(workspace)}


@mcp.tool()
def trace_runs(kind: str = "", interpreter: str = "", limit: int = 30) -> list[dict]:
    """Interpreter runs recorded in the substrate (run identity): kind, interpreter
    name@version, actor, inputs, outputs, code revisions. Filter by kind
    (generate / extract / curate / ingest-apply / import-recall) or interpreter prefix."""
    rs = library.runs(kind or None, interpreter or None)
    return [{"run_id": r["run_id"], "kind": r["kind"], "interpreter": r["interpreter"], "actor": r.get("actor"),
             "recorded_at": r.get("recorded_at"), "inputs": len(r.get("inputs", [])),
             "outputs": len(r.get("outputs", [])), "params": r.get("params", {})} for r in rs[-limit:]]


@mcp.tool()
def episteme_status() -> dict:
    """Which build is being served and its shape: branch, code revisions, counts of
    beliefs / evidence / interpretations / runs, workspaces, and what this channel
    writes as. Run `engine.py check` for the promotion gate; this is the cheap view."""
    st = _state()
    ws_root = Path(os.environ["EPIST_WORKSPACES"])
    return {
        "branch": library.branch(), "db": library.db_path(),
        "library_code": library.code_version(), "workbench_code": library_client.code_version(),
        "writes_as": {"library": library.resolve_actor(), "workspaces": __import__("epist.actor", fromlist=["resolve_actor"]).resolve_actor()},
        "counts": {"beliefs": len(st["beliefs"]), "evidence": len(st["evidence"]),
                   "interpretations": len(st["interpretations"]), "runs": len(st["runs"]),
                   "relationships": len(st["relationships"]),
                   "workspaces": sum(1 for d in ws_root.iterdir() if d.is_dir() and not d.name.startswith(".")) if ws_root.exists() else 0},
        "lenses": {"belief": sorted(_BELIEF_TOOLS), "argue": [f"argue_{n}" for n in _ARGUE_TOOLS],
                   "trace": ["trace_claim", "trace_evidence", "trace_workspace", "trace_runs"],
                   "pattern": "reserved (mapper dormant)"},
    }


if __name__ == "__main__":
    mcp.run()
