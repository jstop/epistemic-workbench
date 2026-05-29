"""F4 — node lifecycle: rejected/superseded branches are preserved, not deleted."""
import json
from pathlib import Path

import pytest

from epist.store import Store
from epist.graph_io import add_claim, add_argument, supersede, revise_thesis, import_graph
from epist.model import NODE_STATUSES


def test_supersede_keeps_old_node_and_links(tmp_path):
    s = Store(tmp_path / "ws")
    old = add_claim(s, "original thesis", node_type="thesis", confidence=0.6)
    new = add_claim(s, "narrowed thesis", node_type="thesis", confidence=0.5)
    r = supersede(s, old.id, new.id, reason="too broad; narrowed after objection O")

    assert old.id in s.claims                       # NOT deleted
    assert s.claims[old.id].status == "superseded"
    assert s.claims[old.id].killed_by == new.id
    assert s.claims[old.id].is_root is False        # demoted
    assert s.claims[new.id].previous_version == old.id
    assert s.claims[new.id].version_meta["rationale"].startswith("too broad")
    # a supersedes edge new → old exists
    assert any(e.rel == "supersedes" and e.from_id == new.id and e.to == old.id
               for e in s.edges.values())


def test_supersede_is_first_class_status():
    assert "superseded" in NODE_STATUSES


def test_supersede_rejects_self_and_missing(tmp_path):
    s = Store(tmp_path / "ws")
    c = add_claim(s, "c")
    with pytest.raises(ValueError):
        supersede(s, c.id, c.id)
    with pytest.raises(ValueError):
        supersede(s, c.id, "nonexistent")


def test_revise_thesis_is_non_destructive(tmp_path):
    """A normal revise-flow keeps the prior claim and its subgraph instead of
    dropping them. generate_fn is stubbed to avoid invoking the LLM."""
    s = Store(tmp_path / "ws")
    old = add_claim(s, "v1 thesis", node_type="thesis", confidence=0.7)
    prem = add_claim(s, "v1 supporting premise", confidence=0.6)
    add_argument(s, old.id, [prem.id])
    old_ids_before = set(s.claims)

    def fake_generate(store, text):
        t = add_claim(store, text, node_type="thesis", confidence=0.5)
        p = add_claim(store, "v2 premise", confidence=0.6)
        add_argument(store, t.id, [p.id])
        return t.id

    rev = revise_thesis(s, old.id, "v2 narrowed thesis", fake_generate,
                        reason="incorporated objection")

    # old nodes all survive
    assert old_ids_before <= set(s.claims)
    assert s.claims[old.id].status == "superseded"
    assert s.claims[old.id].is_root is False
    # exactly one current root: the new thesis
    roots = [c for c in s.claims.values() if c.is_root]
    assert len(roots) == 1 and roots[0].id == rev["new_thesis_id"]
    assert s.claims[rev["new_thesis_id"]].previous_version == old.id


def test_osmio_fixture_preserves_rejected_branches(tmp_path):
    """F4 acceptance: importing the fixture preserves the rejected nodes with
    their killed_by / supersedes links."""
    fixture = Path(__file__).resolve().parent.parent / "osmio_argument_graph.json"
    if not fixture.exists():
        pytest.skip("osmio fixture not present")
    g = json.loads(fixture.read_text())
    rejected_in_fixture = [n for n in g["nodes"]
                           if n.get("status") in ("superseded", "defeated", "rebutted")]
    killed_in_fixture = [n for n in g["nodes"] if n.get("killed_by")]

    s = Store(tmp_path / "ws")
    import_graph(s, g, mode="replace")

    # every rejected node is still present with its status
    for n in rejected_in_fixture:
        assert n["id"] in s.claims
        assert s.claims[n["id"]].status == n["status"]
    # every killed_by pointer is preserved
    for n in killed_in_fixture:
        assert s.claims[n["id"]].killed_by == n["killed_by"]

    assert len(rejected_in_fixture) >= 6  # the rejected dialectic is non-trivial
