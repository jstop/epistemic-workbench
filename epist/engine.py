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
