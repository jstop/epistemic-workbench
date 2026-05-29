"""
Epistemic analysis engine.
- ATMS (Assumption-based Truth Maintenance)
- Coherence checking (7 checks)
- Bayesian updating
- Blind spot detection
- Assumption surfacing
- Stress testing
"""
import math
from .model import (
    Claim, Evidence, Argument, Evaluation, Prediction,
    Modality, InferencePattern, DefeaterStatus, EvaluationJudgment,
    PATTERN_METADATA,
)


# ── ATMS ──────────────────────────────────────────────────────────────

class ATMSStatus:
    ACCEPTED = "accepted"
    PROVISIONAL = "provisional"
    DEFEATED = "defeated"
    UNKNOWN = "unknown"


def compute_atms(store):
    """
    Compute ATMS status for every object.
    Returns dict of {id: status}.
    """
    status = {}

    # Evidence starts as accepted (grounded)
    for eid, ev in store.evidence.items():
        status[eid] = ATMSStatus.ACCEPTED

    # Claims start as provisional
    for cid in store.claims:
        status[cid] = ATMSStatus.PROVISIONAL

    # Process arguments: if all premises accepted/provisional and
    # no active defeaters → conclusion gets promoted
    changed = True
    iterations = 0
    while changed and iterations < 20:
        changed = False
        iterations += 1
        for aid, arg in store.arguments.items():
            # Check premises
            premise_ok = all(
                status.get(p, ATMSStatus.UNKNOWN) in (ATMSStatus.ACCEPTED, ATMSStatus.PROVISIONAL)
                for p in arg.premises
            )
            has_defeated_premise = any(
                status.get(p) == ATMSStatus.DEFEATED for p in arg.premises
            )
            # Defeaters that still defeat the argument:
            # - ACTIVE: unaddressed objection
            # - CONCEDED: explicitly accepted as a valid criticism
            # ANSWERED and WITHDRAWN do not defeat.
            has_defeating_defeater = any(
                d.status in (DefeaterStatus.ACTIVE, DefeaterStatus.CONCEDED)
                for d in arg.defeaters
            )

            if has_defeating_defeater or has_defeated_premise:
                new_status = ATMSStatus.DEFEATED
            elif premise_ok and len(arg.premises) > 0:
                new_status = ATMSStatus.ACCEPTED
            else:
                new_status = ATMSStatus.PROVISIONAL

            status[aid] = new_status

            # Propagate to conclusion
            if new_status == ATMSStatus.ACCEPTED:
                if status.get(arg.conclusion) != ATMSStatus.ACCEPTED:
                    status[arg.conclusion] = ATMSStatus.ACCEPTED
                    changed = True
            elif new_status == ATMSStatus.DEFEATED:
                # Only defeat conclusion if this was its only support
                other_supports = [
                    a for a in store.arguments.values()
                    if a.conclusion == arg.conclusion and a.id != aid
                    and status.get(a.id) != ATMSStatus.DEFEATED
                ]
                if not other_supports:
                    if status.get(arg.conclusion) != ATMSStatus.DEFEATED:
                        status[arg.conclusion] = ATMSStatus.DEFEATED
                        changed = True

    # Apply evaluations
    for eid, ev in store.evaluations.items():
        if ev.judgment == EvaluationJudgment.REJECT:
            status[ev.target] = ATMSStatus.DEFEATED
        elif ev.judgment == EvaluationJudgment.ACCEPT:
            status[ev.target] = ATMSStatus.ACCEPTED

    # Predictions inherit from their evidence
    for pid in store.predictions:
        status[pid] = ATMSStatus.PROVISIONAL

    return status


# ── Coherence Checker ─────────────────────────────────────────────────

def check_coherence(store):
    """
    Run coherence checks. Returns list of {check, severity, message, objects}.
    """
    issues = []
    status = compute_atms(store)

    # 1. Probabilistic coherence: conclusion confidence > weakest premise
    for aid, arg in store.arguments.items():
        conclusion = store.get(arg.conclusion)
        if not conclusion:
            continue
        conc_conf = conclusion.confidence.level if hasattr(conclusion, 'confidence') else 0

        for pid in arg.premises:
            premise = store.get(pid)
            if not premise:
                continue
            prem_conf = (premise.confidence.level if hasattr(premise, 'confidence')
                         else premise.reliability if hasattr(premise, 'reliability') else 1.0)
            if conc_conf > prem_conf + 0.05:
                issues.append({
                    "check": "probabilistic_coherence",
                    "severity": "warning",
                    "message": f"Conclusion confidence ({conc_conf:.0%}) exceeds weakest premise ({prem_conf:.0%})",
                    "objects": [arg.conclusion, pid],
                })

    # 2. Hume's guillotine: normative conclusion from purely empirical premises
    for aid, arg in store.arguments.items():
        conclusion = store.claims.get(arg.conclusion)
        if not conclusion or conclusion.modality != Modality.NORMATIVE:
            continue
        premise_modalities = set()
        for pid in arg.premises:
            p = store.claims.get(pid)
            if p:
                premise_modalities.add(p.modality)
        if premise_modalities and Modality.NORMATIVE not in premise_modalities:
            issues.append({
                "check": "humes_guillotine",
                "severity": "warning",
                "message": f"Normative conclusion derived from purely empirical premises (is→ought gap)",
                "objects": [arg.conclusion, aid],
            })

    # 3. Unsupported claims: claims with no supporting argument
    supported = set()
    for arg in store.arguments.values():
        supported.add(arg.conclusion)
    for cid, claim in store.claims.items():
        if cid not in supported:
            issues.append({
                "check": "unsupported_claim",
                "severity": "info",
                "message": f"Claim '{claim.subject} {claim.predicate} {claim.object}' has no supporting argument",
                "objects": [cid],
            })

    # 4. Orphaned evidence: evidence not used in any argument
    used_evidence = set()
    for arg in store.arguments.values():
        for pid in arg.premises:
            if pid in store.evidence:
                used_evidence.add(pid)
    for eid in store.evidence:
        if eid not in used_evidence:
            issues.append({
                "check": "orphaned_evidence",
                "severity": "info",
                "message": f"Evidence '{store.evidence[eid].title}' not connected to any argument",
                "objects": [eid],
            })

    # 5. Circular dependencies
    acyclic = set()  # memoize nodes known to be cycle-free

    def find_cycles(start, path=None):
        if start in acyclic:
            return False
        if path is None:
            path = set()
        if start in path:
            return True
        path.add(start)
        for arg in store.arguments.values():
            if arg.conclusion == start:
                for pid in arg.premises:
                    if pid in store.claims and find_cycles(pid, path):
                        return True
        path.discard(start)
        acyclic.add(start)
        return False

    for cid in store.claims:
        if find_cycles(cid):
            issues.append({
                "check": "circular_dependency",
                "severity": "error",
                "message": f"Circular dependency detected involving claim {cid[:12]}",
                "objects": [cid],
            })
            break  # only report once

    # 6. Pattern validity: check inference pattern requirements
    for aid, arg in store.arguments.items():
        meta = PATTERN_METADATA.get(arg.pattern, {})
        min_p = meta.get("min_premises", 1)
        if len(arg.premises) < min_p:
            issues.append({
                "check": "pattern_validity",
                "severity": "warning",
                "message": f"Argument '{arg.label or aid[:12]}' uses {arg.pattern.value} but has {len(arg.premises)} premises (needs {min_p})",
                "objects": [aid],
            })

    # 7. Defeated but relied upon: object is defeated but used as premise elsewhere
    for arg in store.arguments.values():
        for pid in arg.premises:
            if status.get(pid) == ATMSStatus.DEFEATED:
                issues.append({
                    "check": "defeated_premise",
                    "severity": "error",
                    "message": f"Argument '{arg.label or arg.id[:12]}' relies on defeated premise {pid[:12]}",
                    "objects": [arg.id, pid],
                })

    return issues


# ── Confidence propagation (F3) ───────────────────────────────────────
#
# The engine historically did NOT propagate confidence: a claim's level was a
# stored number and the only aggregate was the *average* of argument strengths
# (overstating a conjunction badly — the ~62% vs ~7% bug). This pass computes a
# DERIVED confidence bottom-up so a multi-premise, all-required argument is
# scored by the conjunction of its premises, not their average.
#
# Combination per argument support_mode (over premise DERIVED confidences):
#   conjunctive  → product   (all premises required; the honest AND)
#   disjunctive  → max       (premises are alternatives; any one suffices)
#   independent  → noisy-OR  (each premise independently lends support)
# A single-premise argument is identical under every mode.
# The argument's own `confidence` scales the result (inferential strength).
# An ATMS-defeated argument contributes 0 (its support is broken).
# A claim with multiple supporting arguments combines them by noisy-OR
# (independent lines of support). A claim with no supporting argument keeps its
# stored confidence (it is a leaf / assumption / premise).
#
# OBJECTIONS BIND ON THE CONCLUSION. Support alone is not the whole story: a
# claim targeted by `refutes`/`rebuts` edges in the generic edge layer has its
# derived confidence pulled DOWN multiplicatively —
#   derived(C) = support_term(C) × ∏ over objections O→C of (1 - derived(O))
# Without this, a multiply-supported thesis noisy-ORs up toward 1.0 while its
# objections (each only able to defeat one parallel support via ATMS) barely
# register — the 97%-with-five-live-defeaters bug. `narrows` is deliberately
# EXCLUDED: it qualifies a thesis's scope, it does not reduce its truth-
# confidence, so it is surfaced as a scope note, not a numeric penalty.

# Generic-edge relations that reduce a target claim's derived confidence.
OBJECTION_RELS = {"refutes", "rebuts"}

# Embedded defeaters synthesized from an objection edge are tagged with this
# prefix (see graph_io._apply_edge_side_effects) so the derived pass counts the
# objection once — via the edge — instead of double-counting the mirror.
EDGE_DEFEATER_PREFIX = "[edge:"

# Embedded defeaters carry no numeric strength, so an objection expressed only as
# a defeater (the generated-graph channel) reduces its target by this fixed
# factor. Heuristic, and only feeds the ADVISORY derived estimate.
DEFAULT_OBJECTION_STRENGTH = 0.7

# Stored node statuses under which an objection no longer stands, so it must NOT
# pull its target's confidence down (a rebutted/withdrawn/superseded/defeated
# objection has itself been answered).
_NON_STANDING = {"rebutted", "withdrawn", "superseded", "defeated"}


def _objection_stands(store, atms, src_id) -> bool:
    """True iff an objecting node still stands (and so should bind)."""
    obj = store.claims.get(src_id)
    if obj is not None and getattr(obj, "status", None) in _NON_STANDING:
        return False
    return atms.get(src_id) != ATMSStatus.DEFEATED


def _product(xs):
    p = 1.0
    for x in xs:
        p *= x
    return p


def _noisy_or(xs):
    """Probabilistic OR: 1 - ∏(1 - x). 0 for empty."""
    q = 1.0
    for x in xs:
        q *= (1.0 - x)
    return 1.0 - q


def _combine_premises(values, mode):
    if not values:
        return 0.0
    if mode == "disjunctive":
        return max(values)
    if mode == "independent":
        return _noisy_or(values)
    # default + "conjunctive": product (the all-required AND)
    return _product(values)


def _stored_conf(obj):
    if hasattr(obj, "confidence"):
        return obj.confidence.level
    return getattr(obj, "reliability", 1.0)


def propagate_confidence(store, atms=None):
    """Return {object_id: derived_confidence} computed bottom-up.

    Pure: never mutates the store. Cycle-safe (a node currently being computed
    falls back to its stored confidence to break the loop)."""
    if atms is None:
        atms = compute_atms(store)

    supports = {}  # conclusion_id -> [arguments]
    for a in store.arguments.values():
        supports.setdefault(a.conclusion, []).append(a)

    # Objection edges (refutes/rebuts) grouped by the node they target.
    objections = {}  # target_id -> [source_id]
    for e in getattr(store, "edges", {}).values():
        if e.rel in OBJECTION_RELS:
            objections.setdefault(e.to, []).append(e.from_id)

    derived = {}
    in_progress = set()

    def conf(oid):
        if oid in derived:
            return derived[oid]
        obj = store.get(oid)
        if obj is None:
            return 0.0
        if oid in in_progress:
            return _stored_conf(obj)  # cycle guard
        in_progress.add(oid)

        # Support term. A supporting argument contributes 0 only when a premise
        # is genuinely broken (ATMS-defeated premise) — NOT merely because the
        # argument carries an objection defeater. Objections are applied once,
        # below, so zeroing here too would double-count them.
        args = supports.get(oid, [])
        if args and oid not in store.evidence:
            arg_contributions = []
            for a in args:
                has_defeated_premise = any(
                    atms.get(p) == ATMSStatus.DEFEATED for p in a.premises
                )
                if has_defeated_premise:
                    arg_contributions.append(0.0)
                    continue
                premise_vals = [conf(pid) for pid in a.premises]
                mode = getattr(a, "support_mode", "independent")
                combined = _combine_premises(premise_vals, mode)
                arg_contributions.append(a.confidence.level * combined)
            support_term = _noisy_or(arg_contributions)
        else:
            support_term = _stored_conf(obj)

        # Objections bind on the conclusion through ONE channel (noisy-AND of the
        # complements), counting each objection exactly once:
        #   (1) standing refutes/rebuts EDGES → reduced by the objector's derived
        #       confidence (the authored/imported channel);
        #   (2) embedded active/conceded defeaters that are NOT edge-mirrors →
        #       reduced by DEFAULT_OBJECTION_STRENGTH (the generated-graph channel).
        # `narrows` is excluded (scope qualifier, not a truth penalty).
        objection_factor = 1.0
        for src in objections.get(oid, []):
            if _objection_stands(store, atms, src):
                objection_factor *= (1.0 - conf(src))
        for a in args:
            for d in a.defeaters:
                if d.status not in (DefeaterStatus.ACTIVE, DefeaterStatus.CONCEDED):
                    continue
                if (d.description or "").startswith(EDGE_DEFEATER_PREFIX):
                    continue  # already counted via its edge in (1)
                objection_factor *= (1.0 - DEFAULT_OBJECTION_STRENGTH)

        in_progress.discard(oid)
        result = support_term * objection_factor
        derived[oid] = result
        return result

    for cid in store.claims:
        conf(cid)
    return derived


def conjunction_report(store, claim_id, atms=None):
    """Explain a claim's derived confidence vs its averaged display value.

    Returns a dict suitable for a summary note, or None if the claim has no
    multi-premise conjunctive support worth warning about."""
    if atms is None:
        atms = compute_atms(store)
    derived = propagate_confidence(store, atms)

    args = [a for a in store.arguments.values() if a.conclusion == claim_id]
    if not args:
        return None

    # Focus on the conjunctive, multi-premise supporters — the overstatement risk.
    conj = [a for a in args
            if getattr(a, "support_mode", "independent") != "disjunctive"
            and len(a.premises) >= 2]
    if not conj:
        return None

    # Pick the dominant supporting argument (most premises) for the note.
    arg = max(conj, key=lambda a: len(a.premises))
    premises = []
    for pid in arg.premises:
        p = store.get(pid)
        if not p:
            continue
        label = (f"{p.subject} {p.predicate} {p.object}" if hasattr(p, "subject")
                 else getattr(p, "title", pid[:12]))
        premises.append({"id": pid, "label": label, "confidence": derived.get(pid, _stored_conf(p))})
    premises_sorted = sorted(premises, key=lambda x: x["confidence"])
    weakest = premises_sorted[:2]

    product = _product([pp["confidence"] for pp in premises])
    average = sum(pp["confidence"] for pp in premises) / len(premises) if premises else 0.0

    return {
        "claim_id": claim_id,
        "n_premises": len(premises),
        "product": product,
        "average": average,
        "derived": derived.get(claim_id, 0.0),
        "weakest_links": weakest,
        "support_mode": getattr(arg, "support_mode", "independent"),
    }


# ── Bayesian Update ───────────────────────────────────────────────────

def bayesian_update(prior, likelihood_if_true, likelihood_if_false):
    """Simple Bayesian update. Returns posterior probability."""
    numerator = likelihood_if_true * prior
    denominator = numerator + likelihood_if_false * (1 - prior)
    if denominator == 0:
        return prior
    return numerator / denominator


# ── Blind Spot Detection ─────────────────────────────────────────────

def find_blind_spots(store):
    """
    Find high-risk blind spots: load-bearing beliefs with
    minimal structural support.
    """
    spots = []
    status = compute_atms(store)

    for cid, claim in store.claims.items():
        # How many arguments depend on this claim?
        dependents = sum(
            1 for arg in store.arguments.values()
            if cid in arg.premises
        )
        # How many arguments support this claim?
        supporters = sum(
            1 for arg in store.arguments.values()
            if arg.conclusion == cid
        )
        # Direct evidence count
        evidence_count = sum(
            1 for arg in store.arguments.values()
            if arg.conclusion == cid
            for pid in arg.premises
            if pid in store.evidence
        )

        conf = claim.confidence.level
        risk = "low"

        if conf >= 0.8 and supporters == 0:
            risk = "high"
        elif conf >= 0.6 and evidence_count == 0:
            risk = "high" if dependents > 0 else "medium"
        elif dependents > 0 and supporters == 0:
            risk = "medium"

        if risk != "low":
            spots.append({
                "risk": risk,
                "claim_id": cid,
                "label": f"{claim.subject} {claim.predicate} {claim.object}",
                "confidence": conf,
                "dependents": dependents,
                "supporters": supporters,
                "evidence": evidence_count,
                "message": (
                    f"{'HIGH' if risk == 'high' else 'MEDIUM'} RISK: "
                    f"'{claim.subject} {claim.predicate} {claim.object}' "
                    f"at {conf:.0%} confidence with {supporters} supporting arguments, "
                    f"{evidence_count} evidence, and {dependents} downstream dependents"
                ),
            })

    spots.sort(key=lambda s: (0 if s["risk"] == "high" else 1, -s["dependents"]))
    return spots


# ── Assumption Surfacer ───────────────────────────────────────────────

def surface_assumptions(store, target_id):
    """
    Trace all assumptions (explicit and implicit) that a claim depends on.
    """
    target = store.get(target_id)
    if not target:
        return []

    assumptions = []
    visited = set()

    def trace(oid, depth=0):
        if oid in visited or depth > 10:
            return
        visited.add(oid)

        obj = store.get(oid)
        if not obj:
            return

        # Explicit assumes
        if hasattr(obj, 'assumes'):
            for aid in obj.assumes:
                a = store.get(aid)
                if a:
                    assumptions.append({
                        "type": "explicit",
                        "id": aid,
                        "label": f"{a.subject} {a.predicate} {a.object}" if hasattr(a, 'subject') else str(aid[:12]),
                        "depth": depth,
                        "supported": any(arg.conclusion == aid for arg in store.arguments.values()),
                    })
                    trace(aid, depth + 1)

        # Implicit: unsupported premises of arguments that support this
        for arg in store.arguments.values():
            if arg.conclusion == oid:
                for pid in arg.premises:
                    if pid in store.claims:
                        p = store.claims[pid]
                        has_support = any(a.conclusion == pid for a in store.arguments.values())
                        if not has_support:
                            assumptions.append({
                                "type": "implicit",
                                "id": pid,
                                "label": f"{p.subject} {p.predicate} {p.object}",
                                "depth": depth + 1,
                                "supported": False,
                            })
                    trace(pid, depth + 1)

    trace(target_id)
    return assumptions


# ── Stress Tester ─────────────────────────────────────────────────────

def stress_test(store, target_id):
    """
    Generate attack surface for a claim.
    Returns structured prompts for challenging the claim.
    """
    target = store.get(target_id)
    if not target:
        return None

    label = f"{target.subject} {target.predicate} {target.object}" if hasattr(target, 'subject') else str(target_id[:12])
    modality = target.modality.value if hasattr(target, 'modality') else "empirical"

    # Gather supporting arguments
    supports = [a for a in store.arguments.values() if a.conclusion == target_id]
    assumptions = surface_assumptions(store, target_id)
    blind_spots = [s for s in find_blind_spots(store) if s["claim_id"] == target_id]

    challenges = {
        "target": label,
        "modality": modality,
        "attack_surfaces": [],
        "crux_questions": [],
        "steelman_prompts": [],
        "alternative_explanations": [],
    }

    # Modality-specific attacks
    if modality == "empirical":
        challenges["attack_surfaces"].append("What counter-evidence exists?")
        challenges["attack_surfaces"].append("Is the sample representative?")
        challenges["attack_surfaces"].append("Could a confounding variable explain this?")
    elif modality == "normative":
        challenges["attack_surfaces"].append("What competing values would this violate?")
        challenges["attack_surfaces"].append("Does this generalize or is it context-dependent?")
    elif modality == "analytic":
        challenges["attack_surfaces"].append("Are the definitions precise enough?")
        challenges["attack_surfaces"].append("Does the logic actually follow?")

    # Assumption-based attacks
    unsupported = [a for a in assumptions if not a["supported"]]
    for ua in unsupported:
        challenges["attack_surfaces"].append(
            f"Unsupported assumption: '{ua['label']}' — what if this is wrong?"
        )

    # Crux questions
    challenges["crux_questions"].append(
        f"What single piece of evidence would make you abandon '{label}'?"
    )
    challenges["crux_questions"].append(
        f"If you had to bet your salary on this, would you?"
    )
    if supports:
        weakest = min(supports, key=lambda a: a.confidence.level)
        challenges["crux_questions"].append(
            f"Your weakest supporting argument is '{weakest.label or weakest.id[:12]}' at {weakest.confidence.level:.0%}. Is this the real crux?"
        )

    # Steelman the opposite
    challenges["steelman_prompts"].append(
        f"Make the strongest possible case that '{target.subject} does NOT {target.predicate} {target.object}'"
    )

    # Alternative explanations
    challenges["alternative_explanations"].append(
        f"What if {target.subject} {target.predicate} something else entirely?"
    )
    challenges["alternative_explanations"].append(
        f"What if the causation runs in the opposite direction?"
    )

    return challenges


# ── Calibration ───────────────────────────────────────────────────────

def compute_calibration(store):
    """Compute prediction calibration from resolved predictions."""
    resolved = [p for p in store.predictions.values() if p.resolved]
    if not resolved:
        return None

    # Bin by confidence
    bins = {}
    for p in resolved:
        bucket = round(p.confidence.level * 10) / 10  # round to nearest 0.1
        if bucket not in bins:
            bins[bucket] = {"total": 0, "correct": 0}
        bins[bucket]["total"] += 1
        if p.outcome:
            bins[bucket]["correct"] += 1

    calibration = []
    for conf, data in sorted(bins.items()):
        calibration.append({
            "predicted": conf,
            "actual": data["correct"] / data["total"] if data["total"] > 0 else 0,
            "n": data["total"],
        })

    return calibration
