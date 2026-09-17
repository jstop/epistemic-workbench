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


# ── run identity (phase 3) ───────────────────────────────────────────────
#
# Every interpreter run — an LLM extracting argumentation, an LLM generating a
# graph, a person curating a proposal — is recorded in the substrate with its
# identity (name@version), its canonical inputs and what it produced. Derived
# objects name their run; a later, better interpreter is diffed, not silently
# substituted.

def interpreter_id(component: str, model: str | None = None) -> str:
    from epist import __version__
    return f"epistemic-workbench/{component}@{model or __version__}"


def code_version() -> str:
    """The workbench code's git revision, stamped into every run's params."""
    try:
        import subprocess
        root = Path(__file__).resolve().parent.parent
        sha = subprocess.run(["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5).stdout.strip() != ""
        return f"{sha}{'+dirty' if dirty else ''}" if sha else "unknown"
    except Exception:
        return "unknown"


def record_run(*, kind: str, interpreter: str, inputs: list[str] | None = None,
               outputs: list[dict] | None = None, params: dict | None = None,
               note: str = "", run_id: str | None = None,
               started_at: str | None = None) -> str | None:
    """Record a run; returns the run id, or None if the library is unavailable
    (the run then goes unrecorded — callers say so in their own metadata)."""
    return _in_library_thread(_record_run, kind, interpreter, inputs, outputs, params, note, run_id, started_at)


def _record_run(kind, interpreter, inputs, outputs, params, note, run_id, started_at):
    eng = _load()
    if eng is None:
        return None
    params = dict(params or {})
    params.setdefault("workbench_code", code_version())
    try:
        return eng.record_run(kind=kind, interpreter=interpreter,
                              inputs=[i for i in (inputs or []) if i], outputs=outputs,
                              params=params, note=note, run_id=run_id, started_at=started_at)
    except Exception:
        return None


def new_run_id() -> str | None:
    return _in_library_thread(lambda: (_load().new_run_id() if _load() else None))


def record_interpretation(*, kind: str, statement: str, grounding: list[dict],
                          interpreter: str, note: str = "", metadata: dict | None = None) -> str | None:
    """Record a derived, grounded object (e.g. a proposed claim located in its
    source). Returns the interpretation id, or None when it cannot be grounded
    verbatim or the library is unavailable — never a fake id."""
    return _in_library_thread(_record_interpretation, kind, statement, grounding, interpreter, note, metadata)


def _record_interpretation(kind, statement, grounding, interpreter, note, metadata):
    eng = _load()
    if eng is None:
        return None
    try:
        return eng.get_log().record_interpretation(
            kind=kind, statement=statement, grounding=grounding, interpreter=interpreter,
            note=note, metadata=metadata or {})
    except Exception:
        return None


def runs_for_workspace(name: str) -> list[dict]:
    """Runs whose params name this workspace (generate, extract, curate)."""
    return _in_library_thread(_runs_for_workspace, name)


def _runs_for_workspace(name):
    eng = _load()
    if eng is None:
        return []
    out = []
    for r in eng.get_log().state()["runs"].values():
        if (r.get("params") or {}).get("workspace") == name:
            out.append({k: r.get(k) for k in ("run_id", "kind", "interpreter", "actor",
                                               "recorded_at", "inputs", "outputs", "params", "note")})
    return out


# ── lenses for the app: status, belief detail, trace ─────────────────────

def status() -> dict:
    return _in_library_thread(_status)


def _status():
    eng = _load()
    if eng is None:
        return {}
    st = eng.get_log().state()
    gates = [r for r in st["runs"].values() if r.get("kind") == "gate-check"]
    gates.sort(key=lambda r: r.get("recorded_at") or "")
    last_gate = None
    if gates:
        g = gates[-1]
        out = (g.get("outputs") or [{}])[0]
        last_gate = {"ok": out.get("ok"), "recorded_at": g.get("recorded_at"),
                     "anchors_failed": (g.get("params") or {}).get("anchors_failed"),
                     "unreviewed": (g.get("params") or {}).get("unreviewed"), "run_id": g["run_id"]}
    import datetime as dt
    ref = dt.date.today(); by_id = eng.all_views_by_id()
    stances = {}
    unreviewed = 0
    for b, _ in eng.load_all():
        s_ = eng.stamped(b, ref, by_id=by_id)
        stances[s_["stance"]] = stances.get(s_["stance"], 0) + 1
        if (s_.get("authorship") or {}).get("stood_behind_by") != "owner":
            unreviewed += 1
    return {"branch": eng.branch(), "db": eng.db_path(), "library_code": eng.code_version(),
            "workbench_code": code_version(), "writes_as": eng.resolve_actor(),
            "counts": {"beliefs": len(st["beliefs"]), "evidence": len(st["evidence"]),
                       "interpretations": len(st["interpretations"]), "runs": len(st["runs"]),
                       "unreviewed": unreviewed, "stances": stances},
            "last_gate": last_gate}


def runs_all(kind: str = "", limit: int = 50) -> list[dict]:
    return _in_library_thread(_runs_all, kind, limit)


def _runs_all(kind, limit):
    eng = _load()
    if eng is None:
        return []
    rs = eng.runs(kind or None)
    return [{"run_id": r["run_id"], "kind": r["kind"], "interpreter": r["interpreter"], "actor": r.get("actor"),
             "recorded_at": r.get("recorded_at"), "inputs": len(r.get("inputs", [])),
             "outputs": r.get("outputs", [])[:6], "n_outputs": len(r.get("outputs", [])),
             "params": r.get("params", {}), "note": r.get("note")} for r in rs[-limit:]][::-1]


def evidence_detail(evidence_id: str) -> dict | None:
    return _in_library_thread(_evidence_detail, evidence_id)


def _evidence_detail(evidence_id):
    eng = _load()
    if eng is None:
        return None
    st = eng.get_log().state(); log = eng.get_log()
    e = st["evidence"].get(evidence_id)
    if not e:
        return None
    out = {"evidence_id": evidence_id, "uri": e.get("uri"), "media_type": e.get("media_type"),
           "durability": e.get("durability"), "recorded_at": e.get("recorded_at"), "actor": e.get("actor"),
           "size": e.get("size"), "metadata": e.get("metadata") or {},
           "content_available": bool(e.get("digest") and log.store.has(e["digest"])),
           "beliefs": [], "interpretations": [], "runs": [], "excerpt": None}
    if out["content_available"] and (e.get("media_type") or "").startswith("text/"):
        raw = log.evidence_content(evidence_id) or b""
        out["excerpt"] = raw[:1200].decode("utf-8", "replace")
    for bid, b in st["beliefs"].items():
        if evidence_id in b.get("evidence_ids", []):
            out["beliefs"].append({"id": bid, "claim": b["claim"],
                                   "spans": [(g.get("quote") or "")[:160] for g in b.get("grounding", []) if g.get("evidence_id") == evidence_id]})
    for i in st["interpretations"].values():
        spans = [g for g in i.get("grounding", []) if g.get("evidence_id") == evidence_id]
        if spans:
            out["interpretations"].append({"id": i["interpretation_id"], "kind": i["kind"], "statement": i["statement"][:200],
                                           "interpreter": i["interpreter"], "spans": [(g.get("quote") or "")[:160] for g in spans]})
    for r in st["runs"].values():
        if evidence_id in r.get("inputs", []) or any(o.get("id") == evidence_id for o in r.get("outputs", [])):
            out["runs"].append({"run_id": r["run_id"], "kind": r["kind"], "interpreter": r["interpreter"], "recorded_at": r.get("recorded_at")})
    return out


def belief_detail(belief_id: str) -> dict | None:
    return _in_library_thread(_belief_detail, belief_id)


def _belief_detail(belief_id):
    eng = _load()
    if eng is None:
        return None
    v, _ = eng.find(belief_id)
    if v is None:
        return None
    import datetime as dt
    st = eng.get_log().state()
    stamped = eng.stamped(v, dt.date.today(), by_id=eng.all_views_by_id())
    raw = st["beliefs"][belief_id]
    log = eng.get_log()
    evidence = []
    for eid in raw.get("evidence_ids", []):
        e = st["evidence"].get(eid) or {}
        spans = [g for g in raw.get("grounding", []) if g.get("evidence_id") == eid]
        evidence.append({"evidence_id": eid, "uri": e.get("uri"), "media_type": e.get("media_type"),
                         "recorded_at": e.get("recorded_at"), "kind": (e.get("metadata") or {}).get("kind"),
                         "content_available": bool(e.get("digest") and log.store.has(e["digest"])),
                         "spans": [(g.get("quote") or "")[:200] for g in spans]})
    interps = [{"id": i["interpretation_id"], "kind": i["kind"], "statement": i["statement"][:200],
                "interpreter": i["interpreter"]}
               for i in st["interpretations"].values() if belief_id in (i.get("subjects") or [])]
    runs = [{"run_id": r["run_id"], "kind": r["kind"], "interpreter": r["interpreter"], "recorded_at": r.get("recorded_at")}
            for r in st["runs"].values() if any(o.get("id") == belief_id for o in r.get("outputs", []))]
    return {**_slim(stamped), "anchor_cost": stamped.get("anchor_cost"), "verified_at": stamped.get("verified_at"),
            "contested": stamped.get("contested"), "retired": v.get("retired"),
            "authorship": stamped.get("authorship"), "claim_history": raw.get("claim_history", []),
            "events": stamped.get("events", []), "evidence": evidence, "interpretations": interps, "runs": runs,
            "links": stamped.get("links", [])}


def trace_claim(text: str, claim_hash_: str, limit: int, workspaces_dir) -> dict:
    return _in_library_thread(_trace_claim, text, claim_hash_, limit, workspaces_dir)


def _trace_claim(text, claim_hash_, limit, workspaces_dir):
    eng = _load()
    if eng is None:
        return {}
    h = claim_hash_ or claim_hash(text)
    q = (text or "").lower()
    st = eng.get_log().state()
    import datetime as dt
    ref = dt.date.today(); by_id = eng.all_views_by_id()
    out = {"claim_hash": h, "text": text, "beliefs": [], "interpretations": [], "workspaces": [], "runs": []}
    for b, _ in eng.load_all(include_retired=True):
        bh = claim_hash(b.get("claim") or "")
        if bh == h or (q and q in (b.get("claim") or "").lower()):
            s = eng.stamped(b, ref, by_id=by_id)
            out["beliefs"].append({**_slim(s), "exact": bh == h})
    for i in st["interpretations"].values():
        ih = (i.get("metadata") or {}).get("claim_hash") or claim_hash(i.get("statement") or "")
        if ih == h or (q and q in (i.get("statement") or "").lower()):
            out["interpretations"].append({"id": i["interpretation_id"], "kind": i["kind"], "statement": i["statement"][:200],
                                           "interpreter": i["interpreter"], "exact": ih == h,
                                           "run_id": (i.get("metadata") or {}).get("run_id"),
                                           "grounding": [{"evidence_id": g["evidence_id"], "quote": (g.get("quote") or "")[:120]} for g in i.get("grounding", [])]})
    from epist.store import Store
    root = Path(workspaces_dir)
    if root.exists():
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            try:
                s = Store(d)
            except Exception:
                continue
            for c in s.claims.values():
                ctext = (c.notes or f"{c.subject} {c.predicate} {c.object}").strip()
                ch = claim_hash(ctext)
                if ch == h or (q and q in ctext.lower()):
                    out["workspaces"].append({"workspace": d.name, "claim_id": c.id, "text": ctext[:160],
                                              "node_type": getattr(c, "node_type", "claim"), "is_root": c.is_root,
                                              "status": getattr(c, "status", None), "exact": ch == h})
    run_ids = {x.get("run_id") for x in out["interpretations"] if x.get("run_id")}
    bids = {b["id"] for b in out["beliefs"]}
    for r in st["runs"].values():
        if r["run_id"] in run_ids or any(o.get("id") in bids for o in r.get("outputs", [])):
            out["runs"].append({"run_id": r["run_id"], "kind": r["kind"], "interpreter": r["interpreter"],
                                "recorded_at": r.get("recorded_at"), "actor": r.get("actor")})
    for k in ("beliefs", "interpretations", "workspaces", "runs"):
        out[k] = out[k][:limit]
    return out


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


def record_workspace_run(store, *, name: str, kind: str, interpreter: str,
                         inputs: list[str] | None = None, params: dict | None = None,
                         note: str = "", started_at: str | None = None) -> dict:
    """Snapshot the workspace as evidence and record a run whose output is that
    snapshot — the honest record of what an interpreter left behind in a
    workspace. Returns {run_id, evidence_id, uri} (all None if unavailable)."""
    return _in_library_thread(_record_workspace_run, store, name, kind, interpreter, inputs, params, note, started_at)


def _record_workspace_run(store, name, kind, interpreter, inputs, params, note, started_at):
    eng = _load()
    if eng is None:
        return {"run_id": None, "evidence_id": None, "uri": None, "reason": _error}
    commit = None
    if store.is_git_repo():
        log = store.git_log(max_count=1)
        commit = log[0]["hash"][:12] if log else None
    uri = f"{WORKSPACE_URI}{name}" + (f"@{commit}" if commit else "")
    thesis = next((c for c in store.claims.values() if c.is_root), None)
    thesis_text = (thesis.notes or f"{thesis.subject} {thesis.predicate} {thesis.object}").strip() if thesis else ""
    try:
        lib = eng.get_log()
        eid = lib.register_evidence(
            media_type="text/plain", uri=uri, content=snapshot_text(store, name, commit),
            metadata={"kind": "workspace-snapshot", "workspace": name, "commit": commit,
                      "thesis_hash": claim_hash(thesis_text) if thesis_text else None,
                      "source": "epistemic-workbench", "produced_by": kind})
        rid = eng.record_run(kind=kind, interpreter=interpreter,
                             inputs=[i for i in (inputs or []) if i],
                             outputs=[{"type": "workspace-snapshot", "id": eid, "uri": uri,
                                       "claims": len(store.claims), "evidence": len(store.evidence),
                                       "arguments": len(store.arguments)}],
                             params=dict(params or {}, workspace=name, commit=commit,
                                         workbench_code=code_version()),
                             note=note, started_at=started_at)
        return {"run_id": rid, "evidence_id": eid, "uri": uri}
    except Exception as e:
        return {"run_id": None, "evidence_id": None, "uri": uri, "reason": str(e)}


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
