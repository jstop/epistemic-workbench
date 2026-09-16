"""Thin, read-mostly bridge to the living library (~/workspace/epistemic/memory).

The two stores stay separate: the library holds beliefs about a person with
stance and provenance; the workbench holds argument graphs for a thesis. The
bridge is links, not copies:

- a workspace records which library beliefs it argues for (`foundations.json`
  → `library_beliefs`), and the UI shows those beliefs with their live stance;
- a thesis can be captured INTO the library as a `derived` belief whose
  evidence is the workspace itself (name + commit), written under this
  process's own agent identity — never as the owner.

If the library is not importable, every call degrades to "unavailable" rather
than raising; the workbench must never depend on it to function.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# The library's engine keeps one sqlite connection per process, and sqlite
# objects may only be used from the thread that created them. FastAPI runs
# sync routes on a threadpool, so every library call is funnelled through a
# single dedicated thread.
_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="living-library")


def _in_library_thread(fn, *args, **kwargs):
    return _EXEC.submit(fn, *args, **kwargs).result()

_DEFAULT_PATH = Path.home() / "workspace" / "epistemic" / "memory"
_engine = None
_error: str | None = None


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
    except Exception as e:  # pragma: no cover
        _error = f"living library import failed: {e}"
        return None
    # Declare this process as a channel of its own. The library resolves the
    # actor from the channel, and a web/MCP process must never write as owner.
    from epist.actor import resolve_actor
    actor = resolve_actor()
    mem_engine.CHANNEL_ACTOR = actor if actor.startswith("agent:") else f"agent:workbench-{actor.replace(':', '-')}"
    _engine = mem_engine
    return _engine


def available() -> bool:
    return _in_library_thread(_load) is not None


def unavailable_reason() -> str | None:
    _in_library_thread(_load)
    return _error


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


def _search(query: str, cluster: str, limit: int) -> list[dict]:
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


def get_many(ids: list[str]) -> list[dict]:
    return _in_library_thread(_get_many, ids)


def _get_many(ids: list[str]) -> list[dict]:
    want = set(ids)
    return [_slim(st) for st in _stamped_all() if st.get("id") in want]


def _slim(st: dict) -> dict:
    return {
        "id": st.get("id"),
        "claim": st.get("claim"),
        "stance": st.get("stance"),
        "cluster": st.get("cluster"),
        "method": st.get("method"),
        "volatility": st.get("volatility"),
        "freshness": st.get("freshness"),
        "observed_at": st.get("observed_at"),
        "unsupported": st.get("unsupported"),
        "guidance": st.get("guidance"),
        "stood_behind_by": (st.get("authorship") or {}).get("stood_behind_by"),
    }


def capture_thesis(**kw) -> dict:
    """Capture a thesis into the library as a `derived` belief grounded in the
    workspace. Method is `derived` because the claim is the conclusion of an
    argument graph, not an observation; the graph is its grounding."""
    return _in_library_thread(_capture_thesis, **kw)


def _capture_thesis(*, belief_id: str, claim: str, cluster: str, workspace: str,
                    commit: str | None, note: str = "", links: list[str] | None = None,
                    volatility: str = "preference") -> dict:
    eng = _load()
    if eng is None:
        return {"ok": False, "reason": _error}
    uri = f"epist-workspace://{workspace}" + (f"@{commit}" if commit else "")
    belief = {
        "id": belief_id, "claim": claim, "method": "derived", "volatility": volatility,
        "cluster": cluster, "kind": "project", "note": note, "links": links or [],
    }
    try:
        result = eng.capture(
            belief,
            evidence_uri=uri,
            evidence_content=f"Thesis of workbench workspace '{workspace}'"
                             + (f" at commit {commit}" if commit else "") + f":\n\n{claim}",
            grounding=[{"kind": "workspace", "uri": uri}],
        )
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    return {"ok": True, "belief": _slim(result), "warning": result.get("warning")}
