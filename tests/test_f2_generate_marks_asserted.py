"""F2 acceptance: generated evidence is marked asserted, not recorded.

The generate path runs an LLM, so we don't call it here; instead we verify the
exact construction the generate path uses (llm.generate_full_graph step 3 and
agent.create_evidence) stamps provenance=asserted even when a confident-looking
`source` string is present.
"""
from epist.store import Store
from epist.model import Evidence
from epist import provenance


def test_marked_asserted_even_with_authoritative_source(tmp_path):
    s = Store(tmp_path / "ws")
    # mimic what the generate path now does for each evidence item
    ev = Evidence(
        title="NIST IR 8214B",
        description="Authoritative-looking standard the LLM never consulted.",
        source="NIST IR 8214B, 2022",  # confident but unverified
        reliability=0.9,
    )
    provenance.mark_asserted(ev, recall_text=f"{ev.title} — {ev.description}")
    s.add_evidence(ev)

    assert provenance.provenance_kind(s.evidence[ev.id]) == "asserted"
    # and it shows up in the anti-confabulation view
    unsourced = {r["id"] for r in provenance.list_unsourced(s)}
    assert ev.id in unsourced


def test_generate_full_graph_stamps_asserted(monkeypatch, tmp_path):
    """Drive llm.generate_full_graph with a stubbed LLM response and confirm
    every evidence node it creates is asserted."""
    import epist.llm as llm

    fake = {
        "thesis": {"subject": "t", "predicate": "is", "object": "x",
                   "confidence": 0.6, "modality": "empirical", "notes": "thesis"},
        "claims": [{"subject": "c", "predicate": "is", "object": "y",
                    "confidence": 0.7, "modality": "empirical", "notes": "claim"}],
        "evidence": [
            {"title": "Fireblocks MPC-CMP", "description": "invented citation",
             "evidence_type": "document", "source": "Fireblocks whitepaper 2020",
             "reliability": 0.85},
            {"title": "Some study", "description": "another asserted item",
             "evidence_type": "statistical", "source": "", "reliability": 0.6},
        ],
        "arguments": [{"conclusion_ref": "thesis", "premise_refs": ["claim_0", "evidence_0"],
                       "pattern": "abduction", "label": "a", "confidence": 0.7}],
        "assumptions": [],
        "defeaters": [],
    }

    class _FakeMessages:
        def create(self, **kwargs):
            class _R:
                content = [type("blk", (), {"text": __import__("json").dumps(fake)})()]
            return _R()

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(llm, "get_client", lambda: _FakeClient())
    # avoid touching real recall during the unit test
    from epist import recall_client
    monkeypatch.setattr(recall_client, "record_derivation", lambda **k: None)

    s = Store(tmp_path / "ws")
    thesis_id = llm.generate_full_graph(s, "thesis")

    assert s.evidence, "generate should have created evidence"
    for ev in s.evidence.values():
        assert provenance.provenance_kind(ev) == "asserted", \
            f"generated evidence {ev.title!r} must be asserted, not recorded"
    # all generated evidence is unsourced by construction
    assert len(provenance.list_unsourced(s)) == len(s.evidence)
