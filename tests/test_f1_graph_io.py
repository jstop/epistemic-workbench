"""F1 — authoring + import/export round-trip tests."""
import json
from pathlib import Path

import pytest

from epist.store import Store
from epist.graph_io import (
    add_claim, add_argument, link, export_graph, import_graph,
)
from epist.engine import compute_atms


def _build_sample(store):
    """A small graph exercising every authoring primitive and edge relation."""
    thesis = add_claim(store, "Hardware attestation can serve as a personhood signal.",
                       node_type="thesis", confidence=0.6)
    sub = add_claim(store, "C2PA binds capture events to device identity.", confidence=0.78)
    ev = store.add_evidence(__import__("epist.model", fromlist=["Evidence"]).Evidence(
        title="C2PA spec", description="Open provenance spec.", source="c2pa.org",
        reliability=0.82))
    obj = add_claim(store, "TEE oligopoly reconcentrates trust.",
                    node_type="objection", confidence=0.7)
    older = add_claim(store, "Attestation fully substitutes institutional identity.",
                      confidence=0.4)

    arg = add_argument(store, thesis.id, [sub.id], label="C2PA supports thesis",
                       support_mode="conjunctive")
    link(store, ev.id, sub.id, "grounds")
    link(store, obj.id, thesis.id, "refutes")
    link(store, thesis.id, older.id, "supersedes")
    link(store, obj.id, thesis.id, "narrows")
    return {"thesis": thesis, "sub": sub, "ev": ev, "obj": obj,
            "older": older, "arg": arg}


def _norm(graph):
    """Canonicalize an export for comparison (order-independent)."""
    out = {}
    for k in ("claims", "evidence", "arguments", "evaluations", "predictions", "edges"):
        out[k] = sorted(
            (json.dumps(d, sort_keys=True, default=str) for d in graph.get(k, []))
        )
    return out


def test_internal_round_trip_is_lossless(tmp_path):
    a = Store(tmp_path / "a")
    _build_sample(a)
    exported = export_graph(a)

    b = Store(tmp_path / "b")
    import_graph(b, exported, mode="replace")
    reexported = export_graph(b)

    assert _norm(exported) == _norm(reexported), "import(export(W)) lost or changed data"


def test_round_trip_preserves_ids_and_fields(tmp_path):
    a = Store(tmp_path / "a")
    ids = _build_sample(a)
    exported = export_graph(a)

    b = Store(tmp_path / "b")
    import_graph(b, exported, mode="replace")

    assert set(b.claims) == set(a.claims)
    assert set(b.edges) == set(a.edges)
    # superseded node carries its lifecycle metadata through the round-trip
    older = b.claims[ids["older"].id]
    assert older.status == "superseded"
    assert older.killed_by == ids["thesis"].id
    # support_mode survives
    assert b.arguments[ids["arg"].id].support_mode == "conjunctive"


def test_authored_graph_is_analyzed_by_atms(tmp_path):
    s = Store(tmp_path / "ws")
    ids = _build_sample(s)
    atms = compute_atms(s)
    # The thesis must receive a status from the same engine generated graphs use.
    assert atms.get(ids["thesis"].id) in ("accepted", "provisional", "defeated")
    # The 'refutes' edge created a defeater on the thesis's supporting argument.
    assert any(d for arg in s.arguments.values() for d in arg.defeaters)


def test_link_validation_and_supersede(tmp_path):
    s = Store(tmp_path / "ws")
    c1 = add_claim(s, "old claim")
    c2 = add_claim(s, "new claim")
    with pytest.raises(ValueError):
        link(s, c1.id, c2.id, "bogus-relation")
    link(s, c2.id, c1.id, "supersedes")
    assert s.claims[c1.id].status == "superseded"
    assert s.claims[c1.id].killed_by == c2.id


def test_flat_import_brief_shape(tmp_path):
    flat = {
        "meta": {"node_types": ["thesis", "claim", "objection", "concession"]},
        "nodes": [
            {"id": "T", "type": "thesis", "status": "live",
             "text": "Main thesis.", "confidence": 0.55},
            {"id": "C1", "type": "claim", "status": "superseded",
             "text": "An earlier claim.", "confidence": 0.5, "killed_by": "O_sep"},
            {"id": "O_sep", "type": "objection", "status": "live",
             "text": "Separation objection.", "confidence": 0.7},
            {"id": "K1", "type": "concession", "status": "conceded",
             "text": "Conceded limitation.", "confidence": 0.6},
            {"id": "E1", "type": "evidence", "text": "A real source.",
             "source": "https://example.org", "confidence": 0.8},
        ],
        "edges": [
            {"from": "C1", "rel": "supports", "to": "T"},
            {"from": "O_sep", "rel": "refutes", "to": "C1"},
            {"from": "E1", "rel": "grounds", "to": "C1"},
            {"from": "K1", "rel": "narrows", "to": "T"},
        ],
    }
    s = Store(tmp_path / "ws")
    summary = import_graph(s, flat, mode="replace")
    assert summary["mode"] == "flat"
    # all five nodes preserved under their original ids
    assert "T" in s.claims and "C1" in s.claims and "O_sep" in s.claims and "K1" in s.claims
    assert "E1" in s.evidence
    # killed_by / status preserved (the dialectic is held, not discarded)
    assert s.claims["C1"].status == "superseded"
    assert s.claims["C1"].killed_by == "O_sep"
    assert s.claims["K1"].node_type == "concession"
    assert len(s.edges) == 4
    # imported graph analyzes without error
    atms = compute_atms(s)
    assert atms.get("T") in ("accepted", "provisional", "defeated")


def test_existing_workspaces_still_load(tmp_path):
    """Guardrail: pre-F1 workspaces (no edges.json, no new fields) must keep
    loading and analyzing unchanged after the schema additions."""
    ws_root = Path(__file__).resolve().parent.parent / "workspaces"
    candidates = [d for d in ws_root.glob("*")
                  if (d / "claims.json").exists()] if ws_root.exists() else []
    if not candidates:
        pytest.skip("no existing workspaces to check")
    checked = 0
    for d in candidates[:5]:
        s = Store(d)  # read-only; no .save()
        if not s.claims:
            continue
        atms = compute_atms(s)  # must not raise
        assert isinstance(atms, dict)
        # new fields take safe defaults on legacy claims
        any_claim = next(iter(s.claims.values()))
        assert any_claim.node_type == "claim"
        assert any_claim.status is None
        checked += 1
    assert checked > 0


def test_osmio_fixture_imports_and_round_trips(tmp_path):
    """F1 acceptance: the canonical authored graph imports, preserves the
    rejected/superseded dialectic, and round-trips losslessly."""
    fixture = Path(__file__).resolve().parent.parent / "osmio_argument_graph.json"
    if not fixture.exists():
        pytest.skip("osmio_argument_graph.json not present")
    g = json.loads(fixture.read_text())
    nodes, edges = g["nodes"], g["edges"]
    unique_ids = {n["id"] for n in nodes}

    s = Store(tmp_path / "osmio")
    summary = import_graph(s, g, mode="replace")
    assert summary["mode"] == "flat"

    # every node landed in exactly one collection, under its own id
    stored = set(s.claims) | set(s.evidence) | set(s.arguments)
    assert unique_ids <= stored, "some fixture nodes were dropped on import"
    assert len(s.edges) == len(edges)

    # the dialectic is preserved: superseded nodes keep status + killed_by
    superseded = [n for n in nodes if n.get("status") == "superseded"]
    assert superseded, "fixture should contain superseded nodes"
    for n in superseded:
        c = s.claims.get(n["id"])
        if c is not None:  # superseded theses/claims are Claim nodes
            assert c.status == "superseded"
            assert c.killed_by == n.get("killed_by")

    # analysis runs over the imported graph without error
    atms = compute_atms(s)
    assert isinstance(atms, dict) and atms

    # lossless internal round-trip of the imported graph
    exported = export_graph(s)
    s2 = Store(tmp_path / "osmio2")
    import_graph(s2, exported, mode="replace")
    assert _norm(export_graph(s2)) == _norm(exported)


def test_flat_then_export_round_trips_internally(tmp_path):
    flat = {
        "nodes": [
            {"id": "T", "type": "thesis", "text": "t", "confidence": 0.5},
            {"id": "O", "type": "objection", "text": "o", "confidence": 0.6},
        ],
        "edges": [{"from": "O", "rel": "refutes", "to": "T"}],
    }
    s = Store(tmp_path / "ws")
    import_graph(s, flat, mode="replace")
    exported = export_graph(s)

    s2 = Store(tmp_path / "ws2")
    import_graph(s2, exported, mode="replace")
    assert _norm(export_graph(s2)) == _norm(exported)
