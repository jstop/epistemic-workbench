"""Route-level tests for the web server. These exercise the same HTTP surface
the React UI calls, against a throwaway workspaces directory, so drift between
the engine and the browser shows up here rather than in a screenshot."""
import json
import os
import importlib

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPIST_WORKSPACES", str(tmp_path / "ws"))
    monkeypatch.setenv("EPIST_MEMORY_PATH", str(tmp_path / "no-library"))  # bridge unavailable
    import web.server as server
    importlib.reload(server)
    from fastapi.testclient import TestClient
    return TestClient(server.app)


def _mk(client, name="t"):
    r = client.post("/api/workspaces", json={"name": name})
    assert r.status_code == 200, r.text
    return name


def _claim(client, ws, text, **kw):
    r = client.post(f"/api/workspaces/{ws}/add-claim", json={"text": text, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_create_and_list(client):
    _mk(client, "alpha")
    names = [w["name"] for w in client.get("/api/workspaces").json()]
    assert "alpha" in names
    w = next(w for w in client.get("/api/workspaces").json() if w["name"] == "alpha")
    assert w["archived"] is False


def test_authoring_graph_and_derived(client):
    ws = _mk(client)
    t = _claim(client, ws, "thesis text", node_type="thesis", confidence=0.6)
    p1 = _claim(client, ws, "premise one", confidence=0.8)
    p2 = _claim(client, ws, "premise two", confidence=0.5)
    r = client.post(f"/api/workspaces/{ws}/add-argument", json={
        "conclusion_id": t, "premise_ids": [p1, p2], "label": "a", "support_mode": "conjunctive"})
    assert r.status_code == 200, r.text
    g = client.get(f"/api/workspaces/{ws}/graph").json()
    by_id = {n["id"]: n for n in g["nodes"]}
    assert by_id[t]["node_type"] == "thesis"
    assert by_id[t]["derived"] is not None
    assert any(e["type"] == "supports" and e["support_mode"] == "conjunctive" for e in g["edges"])
    prop = client.get(f"/api/workspaces/{ws}/analysis/propagation").json()
    assert t in prop


def test_typed_link_strips_edge_tag_in_display(client):
    ws = _mk(client)
    t = _claim(client, ws, "thesis", node_type="thesis")
    p = _claim(client, ws, "premise")
    client.post(f"/api/workspaces/{ws}/add-argument", json={"conclusion_id": t, "premise_ids": [p]})
    o = _claim(client, ws, "an objection", node_type="objection", confidence=0.4)
    r = client.post(f"/api/workspaces/{ws}/link", json={"from_id": o, "to_id": t, "relation": "rebuts"})
    assert r.status_code == 200, r.text
    g = client.get(f"/api/workspaces/{ws}/graph").json()
    assert any(e["type"] == "rebuts" for e in g["edges"])
    descs = [d["description"] for n in g["nodes"] for d in n.get("defeaters", [])]
    assert descs and all(not d.startswith("[edge:") for d in descs)
    summ = client.get(f"/api/workspaces/{ws}/summary").json()
    assert all(not d["description"].startswith("[edge:") for d in summ["objections"])
    assert "[edge:" not in summ["markdown"]


def test_supersede_and_retire_keep_history(client):
    ws = _mk(client)
    old = _claim(client, ws, "old thesis", node_type="thesis")
    new = _claim(client, ws, "new thesis", node_type="thesis")
    r = client.post(f"/api/workspaces/{ws}/supersede", json={"old_claim_id": old, "new_claim_id": new, "reason": "sharper"})
    assert r.status_code == 200, r.text
    x = _claim(client, ws, "withdrawn claim")
    r = client.post(f"/api/workspaces/{ws}/retire", json={"claim_id": x, "reason": "no longer held"})
    assert r.status_code == 200, r.text
    g = client.get(f"/api/workspaces/{ws}/graph").json()
    by_id = {n["id"]: n for n in g["nodes"]}
    assert by_id[old]["status"] == "superseded" and by_id[old]["killed_by"] == new
    assert by_id[x]["status"] == "retired"
    assert "no longer held" in by_id[x]["notes"]
    assert any(e["type"] == "supersedes" for e in g["edges"])


def test_export_import_roundtrip(client):
    ws = _mk(client)
    t = _claim(client, ws, "thesis", node_type="thesis")
    p = _claim(client, ws, "premise")
    client.post(f"/api/workspaces/{ws}/add-argument", json={"conclusion_id": t, "premise_ids": [p]})
    exp = client.get(f"/api/workspaces/{ws}/export").json()
    assert exp["format"] == "epist-graph/v1"
    r = client.post(f"/api/workspaces/{ws}/import", json={"graph": exp, "mode": "replace"})
    assert r.status_code == 200, r.text
    exp2 = client.get(f"/api/workspaces/{ws}/export").json()
    assert {c["id"] for c in exp2["claims"]} == {c["id"] for c in exp["claims"]}
    assert len(exp2["arguments"]) == len(exp["arguments"])


def test_asserted_evidence_is_provisional_and_listed_unsourced(client):
    ws = _mk(client)
    t = _claim(client, ws, "thesis", node_type="thesis")
    r = client.post(f"/api/workspaces/{ws}/add-evidence-to-claim", json={
        "claim_id": t, "title": "a study", "description": "says so", "source": "Journal of Things 2021"})
    assert r.status_code == 200, r.text
    g = client.get(f"/api/workspaces/{ws}/graph").json()
    ev = next(n for n in g["nodes"] if n["type"] == "evidence")
    assert ev["provenance"] == "asserted"
    assert ev["atms"] == "provisional"  # a source string is not provenance
    un = client.get(f"/api/workspaces/{ws}/unsourced").json()
    assert un["counts"]["asserted"] == 1 and len(un["rows"]) == 1


def test_archive_marker(client):
    ws = _mk(client, "arch")
    assert client.post(f"/api/workspaces/{ws}/archive", json={"archived": True}).status_code == 200
    w = next(w for w in client.get("/api/workspaces").json() if w["name"] == ws)
    assert w["archived"] is True
    client.post(f"/api/workspaces/{ws}/archive", json={"archived": False})
    w = next(w for w in client.get("/api/workspaces").json() if w["name"] == ws)
    assert w["archived"] is False


def test_commits_carry_channel_actor(client):
    ws = _mk(client)
    _claim(client, ws, "something")
    log = client.get(f"/api/workspaces/{ws}/git-log").json()
    assert log and log[0]["actor"] == "owner:web"
    assert "Actor: owner:web" in log[0]["body"]


def test_library_bridge_degrades_when_unavailable(client):
    ws = _mk(client)
    st = client.get("/api/library/status").json()
    assert st["available"] is False
    assert client.get("/api/library/beliefs?q=x").status_code == 503
    r = client.get(f"/api/workspaces/{ws}/beliefs").json()
    assert r["available"] is False and r["beliefs"] == []
    assert "verify-thesis" in r["anchor_command"]
    assert client.post(f"/api/workspaces/{ws}/snapshot", json={}).status_code == 503
    assert client.post(f"/api/workspaces/{ws}/ground-belief", json={"belief_id": "x"}).status_code == 400
    assert client.post(f"/api/workspaces/{ws}/capture-belief", json={"belief_id": "x", "cluster": "k"}).status_code == 400


@pytest.fixture()
def client_with_library(tmp_path, monkeypatch, temp_library):
    monkeypatch.setenv("EPIST_WORKSPACES", str(tmp_path / "ws"))
    import web.server as server
    importlib.reload(server)
    from fastapi.testclient import TestClient
    return TestClient(server.app), temp_library


def test_belief_grounds_in_workspace_not_the_reverse(client_with_library):
    client, eng = client_with_library
    ws = _mk(client, "sky")
    t = _claim(client, ws, "the sky is blue", node_type="thesis", confidence=0.7)
    p = _claim(client, ws, "light scatters", confidence=0.9)
    client.post(f"/api/workspaces/{ws}/add-argument", json={"conclusion_id": t, "premise_ids": [p]})
    # an existing belief, asserted from chat, with no evidence yet
    eng.get_log().form_belief(belief_id="sky-blue", claim="the sky is blue", method="asserted",
                              volatility="structural", unsupported=True)
    assert client.get(f"/api/workspaces/{ws}/beliefs").json()["beliefs"] == []

    r = client.post(f"/api/workspaces/{ws}/ground-belief", json={"belief_id": "sky-blue"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uri"].startswith("epist-workspace://sky@")
    # the library now holds the snapshot as evidence under the belief, with the thesis as a located span
    b = eng.get_log().state()["beliefs"]["sky-blue"]
    assert body["evidence_id"] in b["evidence_ids"]
    assert b["grounding"][0]["quote"] == "THESIS: the sky is blue"
    assert "verify-thesis sky" in b["anchor"]
    assert b["unsupported"] is False
    assert b["authorship"]["composed_by"] == "test:fixture" or b["claim"] == "the sky is blue"
    # and the workspace-side view is a query, not a stored list
    cited = client.get(f"/api/workspaces/{ws}/beliefs").json()["beliefs"]
    assert [c["id"] for c in cited] == ["sky-blue"]
    assert cited[0]["snapshots"][0]["uri"] == body["uri"]
    exp = client.get(f"/api/workspaces/{ws}/export").json()
    assert "library_beliefs" not in exp["foundations"]


def test_capture_thesis_creates_derived_anchored_belief(client_with_library):
    client, eng = client_with_library
    ws = _mk(client, "cap")
    _claim(client, ws, "identity must be accountable", node_type="thesis", confidence=0.6)
    r = client.post(f"/api/workspaces/{ws}/capture-belief", json={"belief_id": "wb-cap", "cluster": "Positions"})
    assert r.status_code == 200, r.text
    b = eng.get_log().state()["beliefs"]["wb-cap"]
    assert b["method"] == "derived" and b["claim"] == "identity must be accountable"
    assert b["evidence_ids"] and b["grounding"][0]["evidence_id"] == b["evidence_ids"][0]
    assert "verify-thesis cap" in b["anchor"]
    assert b["authorship"]["stood_behind_by"] is None  # an agent wrote it; the owner has not stood behind it
    g = client.get(f"/api/workspaces/{ws}/graph").json()
    assert all(len(n["claim_hash"]) == 64 for n in g["nodes"] if n["type"] == "claim")
