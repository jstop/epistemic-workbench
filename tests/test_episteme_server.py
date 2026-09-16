"""The unified server composes both lenses and adds trace, on the selected branch."""
import asyncio
import importlib
import os
import sys

import pytest


@pytest.fixture()
def episteme(temp_library, tmp_path, monkeypatch):
    monkeypatch.setenv("EPIST_WORKSPACES", str(tmp_path / "ws"))
    monkeypatch.setenv("EPISTEMIC_AGENT", "episteme-test")
    monkeypatch.setenv("EPIST_AGENT", "episteme-test")
    (tmp_path / "ws").mkdir()
    from epist import actor
    monkeypatch.setattr(actor, "CHANNEL_ACTOR", None)  # importing the server declares a channel; undo after
    sys.modules.pop("episteme_server", None)
    sys.modules.pop("server", None)  # the library's MCP module declares its channel at import; re-import it
    import episteme_server
    importlib.reload(episteme_server)
    yield episteme_server, temp_library
    actor.CHANNEL_ACTOR = None


def test_tools_are_namespaced_and_complete(episteme):
    srv, _ = episteme
    names = sorted(t.name for t in asyncio.run(srv.mcp.list_tools()))
    assert "belief_recall" in names and "belief_capture" in names
    assert "argue_show_graph" in names and "argue_ground" not in names
    assert {"trace_claim", "trace_evidence", "trace_workspace", "trace_runs", "episteme_status"} <= set(names)
    assert len([n for n in names if n.startswith("argue_")]) == 32
    assert len([n for n in names if n.startswith("belief_")]) == 11


def test_status_reports_branch_and_channel(episteme):
    srv, _ = episteme
    st = srv.episteme_status()
    assert st["counts"]["beliefs"] == 0 and st["counts"]["workspaces"] == 0
    assert st["writes_as"]["library"] == "agent:episteme-test"
    assert st["writes_as"]["workspaces"] == "agent:episteme-test"
    assert st["lenses"]["pattern"].startswith("reserved")


def test_trace_claim_joins_belief_interpretation_and_workspace(episteme, tmp_path):
    srv, lib = episteme
    from epist.store import Store
    from epist import graph_io, library_client
    text = "Accountable identity is a global primitive."
    # a workspace claim
    s = Store(tmp_path / "ws" / "trace-ws"); s.init_workspace()
    graph_io.add_claim(s, text, node_type="thesis")
    # a library belief with the same exact text, and an interpretation stating it
    eid = lib.get_log().register_evidence(media_type="text/plain", content=f"THESIS: {text}")
    lib.get_log().form_belief(belief_id="ai-primitive", claim=text, method="asserted",
                              volatility="structural", evidence_ids=[eid])
    lib.get_log().record_interpretation(kind="proposed-claim", statement=text,
                                        grounding=[{"evidence_id": eid, "quote": text}],
                                        interpreter="test@1", metadata={"claim_hash": library_client.claim_hash(text), "run_id": "run_x"})
    out = srv.trace_claim(text=text)
    assert out["claim_hash"] == library_client.claim_hash(text)
    assert [b["id"] for b in out["beliefs"]] == ["ai-primitive"] and out["beliefs"][0]["exact"]
    assert len(out["interpretations"]) == 1 and out["interpretations"][0]["exact"]
    assert out["workspaces"][0]["workspace"] == "trace-ws" and out["workspaces"][0]["is_root"]
    # substring search finds paraphrase-ish text too, marked inexact
    out2 = srv.trace_claim(text="global primitive")
    assert out2["beliefs"] and not out2["beliefs"][0]["exact"]
    ev = srv.trace_evidence(eid)
    assert [b["id"] for b in ev["beliefs"]] == ["ai-primitive"] and ev["content_available"]
    assert len(ev["interpretations"]) == 1
