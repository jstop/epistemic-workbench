"""F3 — conjunction-aware confidence propagation. Math tested directly."""
import math

import pytest

from epist.store import Store
from epist.model import Claim, Argument, Confidence, InferencePattern
from epist.engine import (
    propagate_confidence, conjunction_report,
    _product, _noisy_or, _combine_premises,
)
from epist.graph_io import add_claim, add_argument


def _approx(a, b, tol=1e-9):
    return abs(a - b) < tol


# ── pure combiners ───────────────────────────────────────────────────

def test_combiners():
    assert _approx(_product([0.5, 0.5, 0.5]), 0.125)
    assert _approx(_combine_premises([0.5, 0.5, 0.5], "conjunctive"), 0.125)
    assert _approx(_combine_premises([0.5, 0.9, 0.3], "disjunctive"), 0.9)
    assert _approx(_combine_premises([0.5, 0.5], "independent"), 1 - 0.25)  # noisy-OR
    assert _combine_premises([], "conjunctive") == 0.0


# ── the headline bug: five entangled premises ────────────────────────

def test_five_premise_conjunction_is_product_not_average(tmp_path):
    """The narrowed-thesis case: 5 all-required premises at ~0.6 each.
    Average ≈ 62%; honest conjunction ≈ 7%."""
    s = Store(tmp_path / "ws")
    thesis = add_claim(s, "narrowed thesis", node_type="thesis", confidence=0.62)
    levels = [0.55, 0.6, 0.6, 0.65, 0.6]
    pids = []
    for i, lv in enumerate(levels):
        c = add_claim(s, f"premise {i}", confidence=lv)
        pids.append(c.id)
    # inference strength 1.0 so we isolate the premise conjunction
    add_argument(s, thesis.id, pids, support_mode="conjunctive", confidence=1.0)

    derived = propagate_confidence(s)
    expected = _product(levels)  # ≈ 0.0708
    assert _approx(derived[thesis.id], expected)
    assert derived[thesis.id] < 0.10          # low double digits / single digit
    avg = sum(levels) / len(levels)
    assert avg > 0.55                          # the misleading average
    assert derived[thesis.id] < avg / 3        # product is dramatically lower


def test_single_premise_unchanged(tmp_path):
    """A single-premise argument is unaffected by support_mode."""
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis", confidence=0.9)
    p = add_claim(s, "p", confidence=0.8)
    add_argument(s, t.id, [p.id], support_mode="conjunctive", confidence=1.0)
    d = propagate_confidence(s)
    assert _approx(d[t.id], 0.8)


def test_disjunctive_takes_max(tmp_path):
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis", confidence=0.5)
    a = add_claim(s, "a", confidence=0.3)
    b = add_claim(s, "b", confidence=0.85)
    c = add_claim(s, "c", confidence=0.4)
    add_argument(s, t.id, [a.id, b.id, c.id], support_mode="disjunctive", confidence=1.0)
    d = propagate_confidence(s)
    assert _approx(d[t.id], 0.85)


def test_multiple_arguments_combine_noisy_or(tmp_path):
    """Two independent supporting arguments raise confidence above either alone."""
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis", confidence=0.5)
    p1 = add_claim(s, "p1", confidence=0.6)
    p2 = add_claim(s, "p2", confidence=0.6)
    add_argument(s, t.id, [p1.id], confidence=1.0)
    add_argument(s, t.id, [p2.id], confidence=1.0)
    d = propagate_confidence(s)
    assert _approx(d[t.id], 1 - (1 - 0.6) * (1 - 0.6))  # 0.84
    assert d[t.id] > 0.6


def test_defeated_argument_contributes_zero(tmp_path):
    from epist.model import Defeater, DefeaterType, DefeaterStatus
    from epist.engine import DEFAULT_OBJECTION_STRENGTH
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis", confidence=0.5)
    p = add_claim(s, "p", confidence=0.9)
    arg = add_argument(s, t.id, [p.id], confidence=1.0)
    base = propagate_confidence(s)[t.id]  # 0.9, no objection yet
    # A manual (non-edge) active defeater reduces the conclusion by the default
    # objection strength — once. The premise itself is not defeated, so the
    # support strand is intact; the penalty comes through the objection channel.
    s.arguments[arg.id].defeaters.append(
        Defeater(type=DefeaterType.REBUTTING, description="x", status=DefeaterStatus.ACTIVE))
    s.save()
    d = propagate_confidence(s)
    assert _approx(base, 0.9)
    assert _approx(d[t.id], 0.9 * (1 - DEFAULT_OBJECTION_STRENGTH))  # 0.27


def test_cycle_does_not_hang(tmp_path):
    s = Store(tmp_path / "ws")
    a = add_claim(s, "a", confidence=0.5)
    b = add_claim(s, "b", confidence=0.5)
    add_argument(s, a.id, [b.id], confidence=1.0)
    add_argument(s, b.id, [a.id], confidence=1.0)
    d = propagate_confidence(s)  # must terminate
    assert a.id in d and b.id in d


def test_osmio_thesis_not_inflated_by_parallel_supports(tmp_path):
    """Regression (Desktop session): the osmio thesis has 7 parallel `supports`
    edges and several `refutes` objections. It must NOT noisy-OR up toward 1.0 —
    objections bind on the conclusion. Honest target is low (a conceded five-link
    conjunction)."""
    import json
    from pathlib import Path
    from epist.graph_io import import_graph
    fixture = Path(__file__).resolve().parent.parent / "osmio_argument_graph.json"
    if not fixture.exists():
        pytest.skip("osmio fixture not present")
    s = Store(tmp_path / "ws")
    import_graph(s, json.loads(fixture.read_text()), mode="replace")
    derived = propagate_confidence(s)
    assert derived["I_claim"] < 0.20, f"thesis inflated to {derived['I_claim']:.2%}"


def test_legacy_edge_defeaters_not_double_counted(tmp_path):
    """A workspace imported before the [edge:] dedup tag carries edge-mirror
    defeaters as 'refutes: …'. The pass must recognize those as edge-mirrors so
    a stale workspace doesn't double-count without a re-import."""
    from epist.graph_io import add_claim, link
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis")
    p = add_claim(s, "p", confidence=0.8)
    link(s, p.id, t.id, "supports")
    o = add_claim(s, "o", node_type="objection", confidence=0.7)
    link(s, o.id, t.id, "refutes")
    tagged = propagate_confidence(s)[t.id]
    # rewrite the synthesized defeater to the OLD untagged format and reload
    for a in s.arguments.values():
        for d in a.defeaters:
            if d.description.startswith("[edge:"):
                rel = d.description[len("[edge:"):].split("]", 1)[0]
                d.description = f"{rel}: {d.description.split('] ', 1)[1]}"
    s.save()
    legacy = propagate_confidence(Store(tmp_path / "ws"))[t.id]
    assert _approx(tagged, legacy), f"legacy {legacy} != tagged {tagged} (double-count)"


def test_objection_not_double_counted(tmp_path):
    """Regression: a refutes edge must reduce the conclusion exactly once, not
    both via its synthesized ATMS defeater AND via the objection factor."""
    from epist.graph_io import add_claim, link
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis")
    p = add_claim(s, "p", confidence=0.8)
    link(s, p.id, t.id, "supports")
    base = propagate_confidence(s)[t.id]            # 0.8 (arg) × 0.8 (premise)
    o = add_claim(s, "o", node_type="objection", confidence=0.7)
    link(s, o.id, t.id, "refutes")
    after = propagate_confidence(s)[t.id]
    assert _approx(after, base * (1 - 0.7))         # single penalty, not zeroed
    assert after > 0.0


def test_narrows_does_not_penalize(tmp_path):
    from epist.graph_io import add_claim, link
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis")
    p = add_claim(s, "p", confidence=0.8)
    link(s, p.id, t.id, "supports")
    before = propagate_confidence(s)[t.id]
    n = add_claim(s, "n", node_type="objection", confidence=0.9)
    link(s, n.id, t.id, "narrows")
    assert _approx(propagate_confidence(s)[t.id], before)


def test_answered_objection_does_not_bind(tmp_path):
    from epist.graph_io import add_claim, link
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis")
    p = add_claim(s, "p", confidence=0.8)
    link(s, p.id, t.id, "supports")
    before = propagate_confidence(s)[t.id]
    o = add_claim(s, "o", node_type="objection", confidence=0.7, status="rebutted")
    link(s, o.id, t.id, "refutes")
    assert _approx(propagate_confidence(s)[t.id], before)


def test_conjunction_report_names_weakest_links(tmp_path):
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis", confidence=0.62)
    weak = add_claim(s, "weakest", confidence=0.3)
    weak2 = add_claim(s, "second weakest", confidence=0.4)
    strong = add_claim(s, "strong", confidence=0.95)
    add_argument(s, t.id, [weak.id, weak2.id, strong.id],
                 support_mode="conjunctive", confidence=1.0)
    rep = conjunction_report(s, t.id)
    assert rep is not None
    assert rep["n_premises"] == 3
    assert rep["product"] < rep["average"]
    assert {w["id"] for w in rep["weakest_links"]} == {weak.id, weak2.id}
