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
    s = Store(tmp_path / "ws")
    t = add_claim(s, "t", node_type="thesis", confidence=0.5)
    p = add_claim(s, "p", confidence=0.9)
    arg = add_argument(s, t.id, [p.id], confidence=1.0)
    # attach an active defeater → ATMS defeats the argument
    s.arguments[arg.id].defeaters.append(
        Defeater(type=DefeaterType.REBUTTING, description="x", status=DefeaterStatus.ACTIVE))
    s.save()
    d = propagate_confidence(s)
    # sole support defeated → derived falls back to stored (no live support)
    assert d[t.id] == 0.0 or _approx(d[t.id], 0.5)


def test_cycle_does_not_hang(tmp_path):
    s = Store(tmp_path / "ws")
    a = add_claim(s, "a", confidence=0.5)
    b = add_claim(s, "b", confidence=0.5)
    add_argument(s, a.id, [b.id], confidence=1.0)
    add_argument(s, b.id, [a.id], confidence=1.0)
    d = propagate_confidence(s)  # must terminate
    assert a.id in d and b.id in d


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
