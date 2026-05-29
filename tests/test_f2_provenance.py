"""F2 — evidence provenance: sourced-vs-asserted classification + recall wiring."""
import tempfile

import pytest

from epist.store import Store
from epist.model import Evidence
from epist import provenance, recall_client


# ── Pure classification (no recall needed) ───────────────────────────

def test_new_evidence_is_asserted_by_default():
    """Generated/hand-typed evidence is UNVERIFIED until a real source attaches —
    a `source` citation string alone does NOT make it recorded."""
    e = Evidence(title="NIST IR 8214B", description="authoritative-looking",
                 source="NIST IR 8214B")  # plausible but unconsulted
    assert provenance.provenance_kind(e) == "asserted"
    assert not provenance.is_recorded(e)


def test_recorded_requires_source_pointer():
    e_recorded = Evidence(title="x", description="y",
                          provenance={"kind": "recorded", "source_id": 42})
    assert provenance.provenance_kind(e_recorded) == "recorded"
    # A 'recorded' label without any pointer is not trusted.
    e_fake = Evidence(title="x", description="y", provenance={"kind": "recorded"})
    assert provenance.provenance_kind(e_fake) == "asserted"


def test_list_unsourced_returns_exactly_the_asserted(tmp_path):
    s = Store(tmp_path / "ws")
    a1 = s.add_evidence(Evidence(title="asserted-1", description="d"))
    a2 = s.add_evidence(Evidence(title="asserted-2", description="d", source="cite"))
    rec = s.add_evidence(Evidence(title="recorded-1", description="d",
                                  provenance={"kind": "recorded", "source_id": 7}))
    unsourced_ids = {r["id"] for r in provenance.list_unsourced(s)}
    assert unsourced_ids == {a1.id, a2.id}
    assert rec.id not in unsourced_ids
    counts = provenance.provenance_counts(s)
    assert counts == {"recorded": 1, "asserted": 2, "total": 3}


def test_attach_source_degrades_when_recall_unavailable(tmp_path, monkeypatch):
    """If recall can't be reached, evidence must NOT be faked as recorded."""
    monkeypatch.setattr(recall_client, "source_exists", lambda sid: False)
    monkeypatch.setattr(recall_client, "record_source", lambda **k: None)
    s = Store(tmp_path / "ws")
    ev = s.add_evidence(Evidence(title="x", description="d"))
    # bad/unknown source id → stays asserted
    r1 = provenance.attach_source(s, ev.id, source_id=999)
    assert r1["ok"] is False
    assert provenance.provenance_kind(s.evidence[ev.id]) == "asserted"
    # url path with recall down → url stored but still asserted
    r2 = provenance.attach_source(s, ev.id, url="https://example.org", quote="q")
    assert r2["ok"] is False
    assert provenance.provenance_kind(s.evidence[ev.id]) == "asserted"


def test_attach_source_rejects_non_evidence(tmp_path):
    from epist.graph_io import add_claim
    s = Store(tmp_path / "ws")
    c = add_claim(s, "a claim")
    r = provenance.attach_source(s, c.id, source_id=1)
    assert r["ok"] is False
    assert "evidence" in r["reason"].lower()


# ── Real recall integration (temp db; skips if recall not importable) ──

@pytest.fixture
def recall_db(monkeypatch):
    """Point recall at a throwaway db and hand the test the live module.
    Uses a tempfile dir (not pytest's tmp_path, which is subject to mid-session
    retention cleanup that races with the long-lived sqlite file)."""
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("RECALL_DB", str(__import__("os").path.join(d, "recall.db")))
        recall_client.reset_cache()
        db = recall_client._db()
        if db is None:
            pytest.skip("recall package not importable")
        yield db
        recall_client.reset_cache()


def test_attach_real_recall_source_flips_to_recorded(tmp_path, recall_db):
    db = recall_db
    sid = db.record_source(source_type="document", content="A real consulted source.")
    s = Store(tmp_path / "ws")
    ev = s.add_evidence(Evidence(title="real", description="d"))
    assert provenance.provenance_kind(ev) == "asserted"

    r = provenance.attach_source(s, ev.id, source_id=sid)
    assert r["ok"] is True and r["kind"] == "recorded"
    assert provenance.provenance_kind(s.evidence[ev.id]) == "recorded"
    assert s.evidence[ev.id].provenance["source_id"] == sid


def test_attach_url_registers_recall_source(tmp_path, recall_db):
    db = recall_db
    s = Store(tmp_path / "ws")
    ev = s.add_evidence(Evidence(title="webby", description="d"))
    r = provenance.attach_source(s, ev.id, url="https://example.org/paper",
                                 quote="key finding", source_type="web_fetch")
    assert r["ok"] is True and r["kind"] == "recorded"
    assert isinstance(r["source_id"], int)
    # the evidence's claim text now traces back to a real recall source
    traced = db.trace_derivation(claim_text=(ev.title + " — " + ev.description))
    assert any(row["source_record_id"] is not None for row in traced)


def test_asserted_evidence_shows_as_orphan_in_recall(tmp_path, recall_db):
    """mark_asserted records a pattern_match (orphan) — recall's anti-confab view."""
    db = recall_db
    ev = Evidence(title="invented", description="confabulated citation")
    provenance.mark_asserted(ev, recall_text="invented — confabulated citation")
    orphans = db.list_orphan_derivations()
    assert any("invented" in (o.get("claim_text") or "") for o in orphans)
