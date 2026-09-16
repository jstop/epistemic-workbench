"""F2 — evidence provenance: sourced-vs-asserted classification + recall wiring."""
import tempfile

import pytest

from epist.store import Store
from epist.model import Evidence
from epist import provenance, library_client


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


def test_attach_source_degrades_when_library_unavailable(tmp_path, no_library):
    """If the library can't be reached, evidence must NOT be faked as recorded."""
    s = Store(tmp_path / "ws")
    ev = s.add_evidence(Evidence(title="t", description="d"))
    r = provenance.attach_source(s, ev.id, evidence_id="evd_nope")
    assert r["ok"] is False
    assert provenance.provenance_kind(s.evidence[ev.id]) == "asserted"
    # url path with library down → url stored but still asserted
    r = provenance.attach_source(s, ev.id, url="https://example.org/x")
    assert r["ok"] is False
    assert provenance.provenance_kind(s.evidence[ev.id]) == "asserted"
    assert s.evidence[ev.id].provenance["url"] == "https://example.org/x"


# ── Real library integration (temp canonical store) ──────────────────

def test_attach_real_library_evidence_flips_to_recorded(tmp_path, temp_library):
    eng = temp_library
    eid = eng.get_log().register_evidence(media_type="text/plain", content="A real consulted source.")
    s = Store(tmp_path / "ws")
    ev = s.add_evidence(Evidence(title="real", description="d"))
    assert provenance.provenance_kind(ev) == "asserted"

    r = provenance.attach_source(s, ev.id, evidence_id=eid)
    assert r["ok"] is True and r["kind"] == "recorded"
    assert provenance.provenance_kind(s.evidence[ev.id]) == "recorded"
    assert s.evidence[ev.id].provenance["evidence_id"] == eid


def test_attach_url_registers_library_evidence(tmp_path, temp_library):
    eng = temp_library
    s = Store(tmp_path / "ws")
    ev = s.add_evidence(Evidence(title="webby", description="d"))
    r = provenance.attach_source(s, ev.id, url="https://example.org/paper",
                                 quote="key finding", source_type="web_fetch")
    assert r["ok"] is True and r["kind"] == "recorded"
    e = eng.get_log().state()["evidence"][r["evidence_id"]]
    assert e["uri"] == "https://example.org/paper"
    assert e["durability"] == "SNAPSHOTTED"  # the quote is content-addressed
    assert e["metadata"]["source"] == "epistemic-workbench"


def test_legacy_recall_source_id_is_no_longer_accepted(tmp_path, temp_library):
    s = Store(tmp_path / "ws")
    ev = s.add_evidence(Evidence(title="old", description="d"))
    r = provenance.attach_source(s, ev.id, source_id=42)
    assert r["ok"] is False and "recall" in r["reason"]
    # but a legacy record already on disk still READS as recorded
    ev.provenance = {"kind": "recorded", "source_id": 42}
    assert provenance.provenance_kind(ev) == "recorded"
