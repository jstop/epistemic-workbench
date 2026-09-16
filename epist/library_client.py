"""Bridge to the living library (~/workspace/epistemic/memory) — the substrate.

Decided 2026-09-15: the library's canonical log is the one provenance substrate
for every epistemic tool. The workbench is an interpreter over it:

- evidence a workspace cites is registered in the library (content-addressed
  snapshot or referenced uri) and the workspace stores the library evidence id;
- a workspace can be snapshotted into the library as evidence
  (`epist-workspace://<name>@<commit>`), and a belief can be GROUNDED in that
  snapshot — the belief's anchor then re-runs the argument;
- the workbench never owns beliefs. Which beliefs a workspace argues for is a
  query against the library, not a list the workspace keeps.

Every call runs on one dedicated thread (the library's sqlite connection has
thread affinity and FastAPI runs sync routes on a pool). If the library is not
importable, every call degrades to "unavailable" rather than raising.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_DEFAULT_PATH = Path.home() / "workspace" / "epistemic" / "memory"
_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="living-library")
_engine = None
_error: str | None = None

WORKSPACE_URI = "epist-workspace://"


def _in_library_thread(fn, *args, **kwargs):
    return _EXEC.submit(fn, *args, **kwargs).result()


def reset() -> None:
    """Forget the cached engine (tests point the library at a temp store)."""
    global _engine, _error
    _engine, _error = None, None


def _load():
    global _engine, _error
    if _engine is not None or _error is not None:
        return _engine
    path = Path(os.environ.get("EPIST_MEMORY_PATH", _DEFAULT_PATH))
    if not (path / "engine.py").exists():
        _error = f"living library not found at {path}"
        return None
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    try:
        import engine as mem_engine  # the library's engine module
        import importlib
        mem_engine = importlib.reload(mem_engine) if getattr(mem_engine, "_LOGS", None) else mem_engine
    except Exception as e:  # pragma: no cover
        _error = f"living library import failed: {e}"
        return None
    from epist.actor import resolve_actor
    actor = resolve_actor()
    # Declare this process as a channel of its own; never write as owner.
    mem_engine.CHANNEL_ACTOR = actor if actor.startswith("agent:") else f"agent:workbench-{actor.replace(':', '-')}"
    _engine = mem_engine
    return _engine


def available() -> bool:
    return _in_library_thread(_load) is not None


def unavailable_reason() -> str | None:
    _in_library_thread(_load)
    return _error


# ── claim identity (decision 3: content hash, no normalisation) ─────────

def claim_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ── evidence ────────────────────────────────────────────────────────────

def register_evidence(*, content: str | None = None, uri: str | None = None,
                      media_type: str = "text/plain", metadata: dict | None = None) -> str | None:
    """Register a source in the substrate; returns the library evidence id or
    None when the library is unavailable (callers must then stay 'asserted')."""
    return _in_library_thread(_register_evidence, content, uri, media_type, metadata)


def _register_evidence(content, uri, media_type, metadata):
    eng = _load()
    if eng is None:
        return None
    try:
        return eng.get_log().register_evidence(
            media_type=media_type, uri=uri, content=content,
            metadata=dict(metadata or {}, source="epistemic-workbench"),
        )
    except Exception as e:
        global _error
        return None


def evidence_exists(evidence_id: str) -> bool:
    return _in_library_thread(_evidence_exists, evidence_id)


def _evidence_exists(evidence_id):
    eng = _load()
    if eng is None or not evidence_id:
        return False
    try:
        return evidence_id in eng.get_log().state()["evidence"]
    except Exception:
        return False


# ── workspace snapshots ────────────────────────────────────────────────

def snapshot_text(store, name: str, commit: str | None) -> str:
    """The evidence content for a workspace snapshot: a plain-text header (so a
    thesis can be located verbatim as a span) followed by the lossless export."""
    from epist import graph_io
    thesis = next((c for c in store.claims.values() if c.is_root), None)
    thesis_text = (thesis.notes or f"{thesis.subject} {thesis.predicate} {thesis.object}").strip() if thesis else ""
    head = [f"EPISTEMIC WORKBENCH SNAPSHOT", f"workspace: {name}", f"commit: {commit or '(uncommitted)'}",
            f"thesis_hash: {claim_hash(thesis_text)}", "", f"THESIS: {thesis_text}", ""]
    return "\n".join(head) + json.dumps(graph_io.export_graph(store), indent=1, default=str, sort_keys=True)


def snapshot_workspace(store, name: str) -> dict:
    """Register the workspace at its current commit as library evidence."""
    commit = None
    if store.is_git_repo():
        log = store.git_log(max_count=1)
        commit = log[0]["hash"][:12] if log else None
    uri = f"{WORKSPACE_URI}{name}" + (f"@{commit}" if commit else "")
    thesis = next((c for c in store.claims.values() if c.is_root), None)
    thesis_text = (thesis.notes or f"{thesis.subject} {thesis.predicate} {thesis.object}").strip() if thesis else ""
    eid = register_evidence(
        content=snapshot_text(store, name, commit), uri=uri, media_type="text/plain",
        metadata={"kind": "workspace-snapshot", "workspace": name, "commit": commit,
                  "thesis_hash": claim_hash(thesis_text) if thesis_text else None},
    )
    return {"ok": eid is not None, "evidence_id": eid, "uri": uri, "commit": commit,
            "thesis_text": thesis_text, "reason": None if eid else unavailable_reason()}


def beliefs_citing(name: str) -> list[dict]:
    """Beliefs whose evidence includes a snapshot of this workspace."""
    return _in_library_thread(_beliefs_citing, name)


def _beliefs_citing(name):
    eng = _load()
    if eng is None:
        return []
    import datetime as dt
    state = eng.get_log().state()
    prefix = f"{WORKSPACE_URI}{name}"
    hits = {eid for eid, e in state["evidence"].items()
            if (e.get("uri") or "").startswith(prefix)
            and ((e.get("uri") or "")[len(prefix):] in ("",) or (e.get("uri") or "")[len(prefix)] == "@")}
    if not hits:
        return []
    ref = dt.date.today()
    by_id = eng.all_views_by_id()
    out = []
    for b, _ in eng.load_all():
        cited = [eid for eid in b.get("evidence_ids", []) if eid in hits]
        if not cited:
            continue
        st = eng.stamped(b, ref, by_id=by_id)
        row = _slim(st)
        row["snapshots"] = [{"evidence_id": eid, "uri": state["evidence"][eid].get("uri"),
                             "recorded_at": state["evidence"][eid].get("recorded_at")} for eid in cited]
        out.append(row)
    return out


# ── beliefs ────────────────────────────────────────────────────────────

def _stamped_all():
    eng = _load()
    if eng is None:
        return []
    import datetime as dt
    ref = dt.date.today()
    by_id = eng.all_views_by_id()
    return [eng.stamped(b, ref, by_id=by_id) for b, _ in eng.load_all()]


def search(query: str = "", cluster: str = "", limit: int = 30) -> list[dict]:
    return _in_library_thread(_search, query, cluster, limit)


def _search(query, cluster, limit):
    q = (query or "").lower()
    out = []
    for st in _stamped_all():
        if cluster and cluster.lower() not in (st.get("cluster") or "").lower():
            continue
        if q and q not in (st.get("claim", "") + " " + st.get("id", "")).lower():
            continue
        out.append(_slim(st))
    eng = _load()
    order = getattr(eng, "STANCE_ORDER", {}) if eng else {}
    out.sort(key=lambda s: order.get(s["stance"], 9))
    return out[:limit]


def _slim(st: dict) -> dict:
    return {
        "id": st.get("id"), "claim": st.get("claim"), "stance": st.get("stance"),
        "cluster": st.get("cluster"), "method": st.get("method"),
        "volatility": st.get("volatility"), "freshness": st.get("freshness"),
        "observed_at": st.get("observed_at"), "unsupported": st.get("unsupported"),
        "anchor": st.get("anchor"), "guidance": st.get("guidance"),
        "stood_behind_by": (st.get("authorship") or {}).get("stood_behind_by"),
        "claim_hash": claim_hash(st.get("claim") or ""),
    }


def anchor_command(name: str, min_derived: float | None = None) -> str:
    py = os.environ.get("EPIST_PYTHON", str(Path.home() / "python" / "global" / "bin" / "python"))
    root = Path(__file__).resolve().parent.parent
    cmd = f"cd {root} && {py} -m epist.cli verify-thesis {name}"
    if min_derived is not None:
        cmd += f" --min-derived {min_derived:g}"
    return cmd


def ground_belief(store, *, belief_id: str, name: str, note: str = "",
                  set_anchor: bool = True, min_derived: float | None = None) -> dict:
    """Ground an EXISTING belief in this workspace: snapshot the workspace as
    evidence, add it under the belief (with the thesis as a located span when
    the text is present), and make the argument the belief's anchor."""
    return _in_library_thread(_ground_belief, store, belief_id, name, note, set_anchor, min_derived)


def _ground_belief(store, belief_id, name, note, set_anchor, min_derived):
    eng = _load()
    if eng is None:
        return {"ok": False, "reason": _error}
    snap = snapshot_workspace(store, name) if False else None  # placeholder (see below)
    # snapshot_workspace itself hops threads; call the inner pieces directly here.
    commit = None
    if store.is_git_repo():
        log = store.git_log(max_count=1)
        commit = log[0]["hash"][:12] if log else None
    uri = f"{WORKSPACE_URI}{name}" + (f"@{commit}" if commit else "")
    content = snapshot_text(store, name, commit)
    thesis = next((c for c in store.claims.values() if c.is_root), None)
    thesis_text = (thesis.notes or f"{thesis.subject} {thesis.predicate} {thesis.object}").strip() if thesis else ""
    try:
        log = eng.get_log()
        eid = log.register_evidence(
            media_type="text/plain", uri=uri, content=content,
            metadata={"kind": "workspace-snapshot", "workspace": name, "commit": commit,
                      "thesis_hash": claim_hash(thesis_text) if thesis_text else None,
                      "source": "epistemic-workbench"})
        grounding = [{"evidence_id": eid, "quote": f"THESIS: {thesis_text}"}] if thesis_text else None
        eng.ground(belief_id, evidence_ids=[eid], grounding=grounding,
                   note=note or f"argued in workbench workspace {name}" + (f" @ {commit}" if commit else ""))
        if set_anchor:
            eng.set_anchor(belief_id, anchor_command(name, min_derived), anchor_cost="cheap",
                           note=f"re-check by re-running the argument in workspace {name}")
        v, _ = eng.find(belief_id)
        import datetime as dt
        st = eng.stamped(v, dt.date.today(), by_id=eng.all_views_by_id())
        return {"ok": True, "belief": _slim(st), "evidence_id": eid, "uri": uri, "commit": commit}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def capture_thesis(**kw) -> dict:
    """Capture a thesis as a NEW belief grounded in this workspace (derived:
    the claim is the conclusion of an argument). Also anchors it to the argument."""
    return _in_library_thread(_capture_thesis, **kw)


def _capture_thesis(*, store, belief_id: str, cluster: str, name: str, note: str = "",
                    links: list[str] | None = None, volatility: str = "preference",
                    min_derived: float | None = None) -> dict:
    eng = _load()
    if eng is None:
        return {"ok": False, "reason": _error}
    thesis = next((c for c in store.claims.values() if c.is_root), None)
    if thesis is None:
        return {"ok": False, "reason": "workspace has no thesis"}
    claim = (thesis.notes or f"{thesis.subject} {thesis.predicate} {thesis.object}").strip()
    commit = None
    if store.is_git_repo():
        log = store.git_log(max_count=1)
        commit = log[0]["hash"][:12] if log else None
    uri = f"{WORKSPACE_URI}{name}" + (f"@{commit}" if commit else "")
    belief = {"id": belief_id, "claim": claim, "method": "derived", "volatility": volatility,
              "cluster": cluster, "kind": "project", "note": note, "links": links or [],
              "anchor": anchor_command(name, min_derived), "anchor_cost": "cheap"}
    try:
        log = eng.get_log()
        eid = log.register_evidence(
            media_type="text/plain", uri=uri, content=snapshot_text(store, name, commit),
            metadata={"kind": "workspace-snapshot", "workspace": name, "commit": commit,
                      "thesis_hash": claim_hash(claim), "source": "epistemic-workbench"})
        result = eng.capture(belief, grounding=[{"evidence_id": eid, "quote": f"THESIS: {claim}"}])
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    return {"ok": True, "belief": _slim(result), "evidence_id": eid, "uri": uri,
            "commit": commit, "warning": result.get("warning")}
