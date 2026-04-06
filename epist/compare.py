"""
Structural diff between two argument graphs.

Claims across forks have different content-addressed IDs (created_at differs),
so we match by semantic key instead:
- Claims: (subject, predicate, object) triple
- Evidence: title
- Arguments: (conclusion_key, frozenset(premise_keys), pattern)
"""
from epist.engine import compute_atms, check_coherence, find_blind_spots
from epist.llm import compute_summary


# ── Semantic identity ────────────────────────────────────────────────

def semantic_key_claim(claim) -> tuple:
    return (claim.subject, claim.predicate, claim.object)


def semantic_key_evidence(ev) -> tuple:
    return (ev.title,)


def semantic_key_argument(argument, claim_key_index: dict, ev_key_index: dict) -> tuple:
    """Argument key uses semantic keys of conclusion + premises (not raw IDs)."""
    conc_key = claim_key_index.get(argument.conclusion) or ev_key_index.get(argument.conclusion)
    premise_keys = []
    for pid in argument.premises:
        k = claim_key_index.get(pid) or ev_key_index.get(pid)
        if k is not None:
            premise_keys.append(k)
    return (conc_key, frozenset(premise_keys), argument.pattern.value)


def build_semantic_index(store) -> dict:
    """Build {type: {semantic_key: object}} for a store.
    Also returns id->key reverse maps for arguments."""
    claim_by_key = {}
    claim_id_to_key = {}
    for cid, c in store.claims.items():
        k = semantic_key_claim(c)
        claim_by_key[k] = c
        claim_id_to_key[cid] = k

    ev_by_key = {}
    ev_id_to_key = {}
    for eid, e in store.evidence.items():
        k = semantic_key_evidence(e)
        ev_by_key[k] = e
        ev_id_to_key[eid] = k

    arg_by_key = {}
    arg_id_to_key = {}
    for aid, a in store.arguments.items():
        k = semantic_key_argument(a, claim_id_to_key, ev_id_to_key)
        arg_by_key[k] = a
        arg_id_to_key[aid] = k

    return {
        "claims": claim_by_key,
        "evidence": ev_by_key,
        "arguments": arg_by_key,
        "claim_id_to_key": claim_id_to_key,
        "ev_id_to_key": ev_id_to_key,
        "arg_id_to_key": arg_id_to_key,
    }


# ── Diff computation ─────────────────────────────────────────────────

def _claim_changes(a, b) -> list[str]:
    changes = []
    if abs(a.confidence.level - b.confidence.level) > 0.01:
        changes.append(f"confidence {a.confidence.level:.0%} -> {b.confidence.level:.0%}")
    if a.modality != b.modality:
        changes.append(f"modality {a.modality.value} -> {b.modality.value}")
    if (a.notes or "") != (b.notes or ""):
        changes.append("notes changed")
    if a.is_root != b.is_root:
        changes.append(f"is_root {a.is_root} -> {b.is_root}")
    return changes


def _evidence_changes(a, b) -> list[str]:
    changes = []
    if abs(a.reliability - b.reliability) > 0.01:
        changes.append(f"reliability {a.reliability:.0%} -> {b.reliability:.0%}")
    if a.evidence_type != b.evidence_type:
        changes.append(f"type {a.evidence_type.value} -> {b.evidence_type.value}")
    if (a.source or "") != (b.source or ""):
        changes.append("source changed")
    if (a.description or "") != (b.description or ""):
        changes.append("description changed")
    return changes


def _argument_changes(a, b) -> list[str]:
    changes = []
    if abs(a.confidence.level - b.confidence.level) > 0.01:
        changes.append(f"confidence {a.confidence.level:.0%} -> {b.confidence.level:.0%}")
    a_active = sum(1 for d in a.defeaters if d.status.value == "active")
    b_active = sum(1 for d in b.defeaters if d.status.value == "active")
    a_answered = sum(1 for d in a.defeaters if d.status.value == "answered")
    b_answered = sum(1 for d in b.defeaters if d.status.value == "answered")
    if a_active != b_active:
        changes.append(f"active defeaters {a_active} -> {b_active}")
    if a_answered != b_answered:
        changes.append(f"answered defeaters {a_answered} -> {b_answered}")
    return changes


def compute_graph_diff(store_a, store_b) -> dict:
    """Compute structural diff between two argument graph stores."""
    idx_a = build_semantic_index(store_a)
    idx_b = build_semantic_index(store_b)

    def diff_collection(name, change_fn):
        keys_a = set(idx_a[name].keys())
        keys_b = set(idx_b[name].keys())
        added = sorted(keys_b - keys_a)
        removed = sorted(keys_a - keys_b)
        common = keys_a & keys_b
        modified = []
        unchanged = []
        for k in sorted(common):
            changes = change_fn(idx_a[name][k], idx_b[name][k])
            if changes:
                modified.append({"key": k, "changes": changes,
                                  "a": idx_a[name][k], "b": idx_b[name][k]})
            else:
                unchanged.append(k)
        return {
            "added": [idx_b[name][k] for k in added],
            "removed": [idx_a[name][k] for k in removed],
            "modified": modified,
            "unchanged_count": len(unchanged),
        }

    # Find root theses
    thesis_a = next((c for c in store_a.claims.values() if c.is_root), None)
    thesis_b = next((c for c in store_b.claims.values() if c.is_root), None)

    return {
        "claims": diff_collection("claims", _claim_changes),
        "evidence": diff_collection("evidence", _evidence_changes),
        "arguments": diff_collection("arguments", _argument_changes),
        "thesis_a": {
            "text": (thesis_a.notes if thesis_a else "")
                    or (f"{thesis_a.subject} {thesis_a.predicate} {thesis_a.object}" if thesis_a else "(none)"),
            "confidence": thesis_a.confidence.level if thesis_a else 0,
        },
        "thesis_b": {
            "text": (thesis_b.notes if thesis_b else "")
                    or (f"{thesis_b.subject} {thesis_b.predicate} {thesis_b.object}" if thesis_b else "(none)"),
            "confidence": thesis_b.confidence.level if thesis_b else 0,
        },
    }


# ── Analysis delta ───────────────────────────────────────────────────

def compute_analysis_delta(store_a, store_b) -> dict:
    """Run analysis on both stores and compute the delta."""
    atms_a = compute_atms(store_a)
    atms_b = compute_atms(store_b)
    coherence_a = check_coherence(store_a)
    coherence_b = check_coherence(store_b)
    blind_a = find_blind_spots(store_a)
    blind_b = find_blind_spots(store_b)

    thesis_a = next((c for c in store_a.claims.values() if c.is_root), None)
    thesis_b = next((c for c in store_b.claims.values() if c.is_root), None)

    status_a = atms_a.get(thesis_a.id, "unknown") if thesis_a else "unknown"
    status_b = atms_b.get(thesis_b.id, "unknown") if thesis_b else "unknown"

    active_def_a = sum(
        1 for arg in store_a.arguments.values()
        for d in arg.defeaters if d.status.value == "active"
    )
    active_def_b = sum(
        1 for arg in store_b.arguments.values()
        for d in arg.defeaters if d.status.value == "active"
    )

    return {
        "atms_status_a": status_a,
        "atms_status_b": status_b,
        "thesis_confidence_a": thesis_a.confidence.level if thesis_a else 0,
        "thesis_confidence_b": thesis_b.confidence.level if thesis_b else 0,
        "active_defeaters_a": active_def_a,
        "active_defeaters_b": active_def_b,
        "coherence_issues_a": len(coherence_a),
        "coherence_issues_b": len(coherence_b),
        "blind_spots_a": len([s for s in blind_a if s["risk"] == "high"]),
        "blind_spots_b": len([s for s in blind_b if s["risk"] == "high"]),
    }


# ── Markdown formatting ──────────────────────────────────────────────

def format_diff_markdown(diff: dict, delta: dict, label_a: str, label_b: str) -> str:
    """Render a structural diff as markdown."""
    lines = []
    lines.append(f"# Comparison: {label_a} vs {label_b}\n")

    lines.append("## Theses\n")
    lines.append(f"**{label_a}** ({delta['thesis_confidence_a']:.0%}, {delta['atms_status_a']}):")
    lines.append(f"> {diff['thesis_a']['text']}\n")
    lines.append(f"**{label_b}** ({delta['thesis_confidence_b']:.0%}, {delta['atms_status_b']}):")
    lines.append(f"> {diff['thesis_b']['text']}\n")

    lines.append("## Analysis Delta\n")
    lines.append(f"| Metric | {label_a} | {label_b} | Δ |")
    lines.append("|---|---|---|---|")
    conf_delta = delta["thesis_confidence_b"] - delta["thesis_confidence_a"]
    lines.append(
        f"| Thesis confidence | {delta['thesis_confidence_a']:.0%} | "
        f"{delta['thesis_confidence_b']:.0%} | {conf_delta:+.0%} |"
    )
    lines.append(
        f"| ATMS status | {delta['atms_status_a']} | {delta['atms_status_b']} | — |"
    )
    lines.append(
        f"| Active defeaters | {delta['active_defeaters_a']} | "
        f"{delta['active_defeaters_b']} | "
        f"{delta['active_defeaters_b'] - delta['active_defeaters_a']:+d} |"
    )
    lines.append(
        f"| Coherence issues | {delta['coherence_issues_a']} | "
        f"{delta['coherence_issues_b']} | "
        f"{delta['coherence_issues_b'] - delta['coherence_issues_a']:+d} |"
    )
    lines.append(
        f"| High-risk blind spots | {delta['blind_spots_a']} | "
        f"{delta['blind_spots_b']} | "
        f"{delta['blind_spots_b'] - delta['blind_spots_a']:+d} |"
    )
    lines.append("")

    for label, key in [("Claims", "claims"), ("Evidence", "evidence"), ("Arguments", "arguments")]:
        section = diff[key]
        added = section["added"]
        removed = section["removed"]
        modified = section["modified"]
        unchanged = section["unchanged_count"]
        if not (added or removed or modified):
            lines.append(f"## {label}\n")
            lines.append(f"_No changes ({unchanged} unchanged)_\n")
            continue

        lines.append(f"## {label}\n")
        lines.append(f"_{len(added)} added · {len(removed)} removed · {len(modified)} modified · {unchanged} unchanged_\n")

        if added:
            lines.append(f"### Added in {label_b}\n")
            for obj in added:
                if hasattr(obj, "subject"):
                    lines.append(f"- **{obj.subject} {obj.predicate} {obj.object}** ({obj.confidence.level:.0%})")
                elif hasattr(obj, "title"):
                    lines.append(f"- **{obj.title}** ({obj.reliability:.0%})  \n  _{obj.source or 'no source'}_")
                else:
                    lines.append(f"- **{obj.label or '(argument)'}** ({obj.pattern.value}, {obj.confidence.level:.0%})")
            lines.append("")

        if removed:
            lines.append(f"### Removed from {label_a}\n")
            for obj in removed:
                if hasattr(obj, "subject"):
                    lines.append(f"- ~~{obj.subject} {obj.predicate} {obj.object}~~")
                elif hasattr(obj, "title"):
                    lines.append(f"- ~~{obj.title}~~")
                else:
                    lines.append(f"- ~~{obj.label or '(argument)'}~~")
            lines.append("")

        if modified:
            lines.append(f"### Modified\n")
            for m in modified:
                key_text = " ".join(str(p) for p in m["key"] if p)
                lines.append(f"- **{key_text}**")
                for ch in m["changes"]:
                    lines.append(f"  - {ch}")
            lines.append("")

    return "\n".join(lines)
