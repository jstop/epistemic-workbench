"""F5 — corpus ingestion: propose-then-curate, with source-span provenance."""
import pytest

from epist.store import Store
from epist import ingest, provenance, library_client


DOC = (
    "Proof of work achieves Sybil resistance by substituting cost for identity. "
    "However, an authority that can issue personhood can also deny it, "
    "reintroducing the chokepoint PoW removes."
)


def _stub_extractor(text):
    """Pretend-LLM: returns two grounded nodes + one edge. Spans are verbatim."""
    return {
        "nodes": [
            {"id": "n0", "type": "claim", "confidence": 0.7,
             "text": "PoW achieves Sybil resistance by substituting cost for identity.",
             "span": "Proof of work achieves Sybil resistance by substituting cost for identity."},
            {"id": "n1", "type": "objection", "confidence": 0.6,
             "text": "An authority that issues personhood can deny it.",
             "span": "an authority that can issue personhood can also deny it"},
        ],
        "edges": [{"from": "n1", "rel": "refutes", "to": "n0"}],
    }


def test_ingest_proposes_without_committing(tmp_path):
    s = Store(tmp_path / "ws")
    s.init_workspace()
    res = ingest.ingest_document(s, source_text=DOC, extractor=_stub_extractor,
                                 title="one regress excerpt")
    pid = res["proposal_id"]
    # nothing in the live graph yet
    assert not s.claims and not s.edges
    # proposal persisted and reviewable
    pr = ingest.review_proposal(s, pid)
    assert pr["status"] == "pending"
    assert len(pr["nodes"]) == 2
    assert all(n["span"] in DOC for n in pr["nodes"])  # every node grounded in a span


def test_commit_only_accepted_nodes(tmp_path):
    s = Store(tmp_path / "ws")
    s.init_workspace()
    pid = ingest.ingest_document(s, source_text=DOC, extractor=_stub_extractor)["proposal_id"]
    # accept only n0
    result = ingest.commit_proposal(s, pid, ["n0"])
    assert result["committed"]["claims"] == 1
    assert len(s.claims) == 1
    # the n1→n0 edge is dropped because n1 was not accepted
    assert len(s.edges) == 0
    # proposal marked committed; re-commit refused
    with pytest.raises(ValueError):
        ingest.commit_proposal(s, pid, ["n1"])


def test_commit_all_brings_edges(tmp_path):
    s = Store(tmp_path / "ws")
    s.init_workspace()
    pid = ingest.ingest_document(s, source_text=DOC, extractor=_stub_extractor)["proposal_id"]
    result = ingest.commit_proposal(s, pid, ["n0", "n1"])
    assert result["committed"]["claims"] == 2
    assert result["committed"]["edges"] == 1
    # the refutes edge produced a defeater on n0's analysis path (engine-visible)
    from epist.engine import compute_atms
    atms = compute_atms(s)
    assert isinstance(atms, dict)


def test_llm_extractor_drops_ungrounded_spans(monkeypatch):
    """A node whose span is NOT in the document is discarded — anti-confabulation."""
    import epist.llm as llm

    fake = {
        "nodes": [
            {"id": "n0", "type": "claim", "text": "grounded", "span": "Proof of work"},
            {"id": "n1", "type": "claim", "text": "hallucinated",
             "span": "THIS PHRASE IS NOT IN THE DOCUMENT"},
        ],
        "edges": [{"from": "n1", "rel": "supports", "to": "n0"}],
    }

    class _Msgs:
        def create(self, **k):
            return type("R", (), {"content": [type("b", (), {"text": __import__("json").dumps(fake)})()]})()

    monkeypatch.setattr(llm, "get_client", lambda: type("C", (), {"messages": _Msgs()})())
    out = ingest.llm_extractor(DOC)
    ids = {n["id"] for n in out["nodes"]}
    assert ids == {"n0"}          # ungrounded n1 dropped
    assert out["edges"] == []     # edge referencing dropped node removed


# ── real library provenance on commit ────────────────────────────────

def test_committed_nodes_get_library_provenance(tmp_path, temp_library):
    eng = temp_library
    s = Store(tmp_path / "ws")
    s.init_workspace()
    res = ingest.ingest_document(s, source_text=DOC, extractor=_stub_extractor, title="t")
    assert res["source_id"] is not None
    # the source itself is a content-addressed snapshot in the substrate
    e = eng.get_log().state()["evidence"][res["source_id"]]
    assert e["durability"] == "SNAPSHOTTED" and e["metadata"]["kind"] == "ingested-source"
    assert eng.get_log().evidence_content(res["source_id"]).decode() == DOC

    ingest.commit_proposal(s, res["proposal_id"], ["n0", "n1"])
    claim = next(c for c in s.claims.values() if c.notes.startswith("PoW achieves"))
    ing = claim.version_meta["ingested_from"]
    assert ing["evidence_id"] == res["source_id"]
    assert ing["span"].startswith("Proof of work achieves")
    assert ing["claim_hash"] == library_client.claim_hash(claim.notes)


# ── phase 3: run identity ────────────────────────────────────────────

def test_ingest_records_extract_run_and_grounded_interpretations(tmp_path, temp_library):
    eng = temp_library
    s = Store(tmp_path / "ws")
    s.init_workspace()
    res = ingest.ingest_document(s, source_text=DOC, extractor=_stub_extractor, title="t")
    assert res["run_id"] and res["run_id"].startswith("run_")
    assert res["interpreter"].startswith("epistemic-workbench/ingest-_stub_extractor@")
    state = eng.get_log().state()
    run = state["runs"][res["run_id"]]
    assert run["kind"] == "extract" and run["inputs"] == [res["source_id"]]
    assert run["params"]["workspace"] == "ws" and run["params"]["ungrounded_nodes"] == 0
    # every proposed node is an interpretation located verbatim in the source
    pr = ingest.review_proposal(s, res["proposal_id"])
    iids = [n["interpretation_id"] for n in pr["nodes"]]
    assert all(i and i.startswith("int") for i in iids)
    i0 = state["interpretations"][iids[0]]
    assert i0["kind"] == "proposed-claim" and i0["interpreter"] == res["interpreter"]
    assert i0["grounding"][0]["evidence_id"] == res["source_id"]
    assert i0["grounding"][0]["quote"].startswith("Proof of work")
    assert i0["metadata"]["run_id"] == res["run_id"]
    # nothing became a belief or a live claim
    assert not s.claims and not state["beliefs"]


def test_commit_records_curate_run_under_channel_actor(tmp_path, temp_library, monkeypatch):
    eng = temp_library
    monkeypatch.setenv("EPIST_ACTOR", "test:curator")
    s = Store(tmp_path / "ws")
    s.init_workspace()
    res = ingest.ingest_document(s, source_text=DOC, extractor=_stub_extractor, title="t")
    out = ingest.commit_proposal(s, res["proposal_id"], ["n0"])
    assert out["run_id"]
    run = eng.get_log().state()["runs"][out["run_id"]]
    assert run["kind"] == "curate"
    assert run["params"]["accepted_by"] == "test:curator"
    assert run["params"]["extract_run_id"] == res["run_id"]
    assert len(run["outputs"]) == 1 and run["outputs"][0]["node_id"] == "n0"
    assert run["outputs"][0]["claim_hash"] == library_client.claim_hash(
        "PoW achieves Sybil resistance by substituting cost for identity.")
    claim = next(iter(s.claims.values()))
    assert claim.version_meta["ingested_from"]["interpretation_id"] == run["outputs"][0]["interpretation_id"]


def test_ungrounded_span_yields_no_interpretation_but_run_says_so(tmp_path, temp_library):
    eng = temp_library
    def bad_span_extractor(text):
        return {"nodes": [{"id": "n0", "type": "claim", "text": "made up", "span": "not in the document"}],
                "edges": []}
    s = Store(tmp_path / "ws")
    s.init_workspace()
    res = ingest.ingest_document(s, source_text=DOC, extractor=bad_span_extractor)
    pr = ingest.review_proposal(s, res["proposal_id"])
    assert pr["nodes"][0]["interpretation_id"] is None
    run = eng.get_log().state()["runs"][res["run_id"]]
    assert run["params"]["ungrounded_nodes"] == 1
    assert not eng.get_log().state()["interpretations"]
