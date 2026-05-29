"""
F2 — evidence provenance: the anti-confabulation layer.

The invariant (the whole point of F2): anything not backed by a real recorded
source renders as UNVERIFIED. A `source` citation string proves nothing — only a
provenance record pointing at a recall source counts as `recorded`.

Two provenance kinds:
  • "asserted" — LLM-invented or hand-typed; UNVERIFIED. This is the default for
    everything `generate_thesis` produces.
  • "recorded" — backed by a recall `record_source` id (or an explicit url/quote
    that we registered in recall). Auditable via recall's derivation graph.

This module is pure logic over the store + the recall adapter; the MCP/CLI layers
are thin wrappers over it.
"""
from . import recall_client


def provenance_kind(evidence) -> str:
    """Return 'recorded' or 'asserted' for an Evidence object.

    Recorded requires an explicit provenance dict that says so AND carries a
    source pointer (a recall source_id, or an explicit url). Absent that — even
    with a populated `source` citation string — it is asserted (unverified)."""
    p = getattr(evidence, "provenance", None)
    if isinstance(p, dict) and p.get("kind") == "recorded":
        if p.get("source_id") is not None or p.get("url"):
            return "recorded"
    return "asserted"


def is_recorded(evidence) -> bool:
    return provenance_kind(evidence) == "recorded"


def attach_source(store, node_id, source_id=None, url=None, quote=None,
                  source_type="document", retrieved_at=None) -> dict:
    """Attach a real source to an evidence node, flipping it to `recorded`.

    Accepts either a recall `source_id` or an explicit `{url, quote}` (which we
    register in recall to obtain a source_id). If recall is unreachable, or a
    given source_id doesn't exist, the node stays `asserted` and we say so —
    we never fake `recorded`.

    Returns a result dict {ok, kind, source_id, reason}.
    """
    ev = store.get(node_id)
    if ev is None:
        return {"ok": False, "reason": f"node not found: {node_id}"}
    if not hasattr(ev, "reliability"):  # not an Evidence node
        return {"ok": False,
                "reason": "attach_source targets an evidence node; "
                          f"{type(ev).__name__} {node_id[:12]} is not evidence"}

    claim_text = (ev.title or "") + (f" — {ev.description}" if ev.description else "")
    claim_text = claim_text.strip() or ev.id

    resolved_id = None
    used_url = url

    if source_id is not None:
        if recall_client.source_exists(source_id):
            resolved_id = int(source_id)
        else:
            return {"ok": False, "kind": "asserted",
                    "reason": f"recall has no source with id {source_id} "
                              "(or recall is unreachable) — left as asserted"}
    elif url:
        # Register the explicit url/quote as a recall source to earn a source_id.
        resolved_id = recall_client.record_source(
            content=quote or url, source_type=source_type, url=url,
            summary=(quote[:200] if quote else None),
        )
        if resolved_id is None:
            # recall down: keep the url on the node but DO NOT claim recorded.
            ev.provenance = {"kind": "asserted", "url": url, "quote": quote,
                             "note": "recall unreachable; unverified"}
            store.save()
            return {"ok": False, "kind": "asserted",
                    "reason": "recall unreachable — url stored but evidence "
                              "remains asserted (unverified)"}
    else:
        return {"ok": False, "reason": "provide a source_id or a url"}

    # Record the grounding derivation in recall (best-effort).
    recall_client.record_derivation(
        claim_text=claim_text, source_record_id=resolved_id, edge_type="inference",
        context="epistemic-workbench evidence", notes=f"evidence_id={ev.id}",
    )

    ev.provenance = {
        "kind": "recorded",
        "source_id": resolved_id,
        "url": used_url,
        "quote": quote,
        "retrieved_at": retrieved_at,
    }
    store.save()
    return {"ok": True, "kind": "recorded", "source_id": resolved_id}


def mark_asserted(evidence, recall_text=None):
    """Stamp an evidence node as explicitly asserted (unverified). Used by the
    generate path so invented citations are never mistaken for recorded ones.
    Best-effort records a pattern_match (orphan) derivation in recall."""
    evidence.provenance = {"kind": "asserted"}
    if recall_text:
        recall_client.record_derivation(
            claim_text=recall_text, source_record_id=None, edge_type="pattern_match",
            context="epistemic-workbench generated evidence",
        )


def list_unsourced(store) -> list[dict]:
    """Evidence nodes lacking a recorded source — the workbench mirror of
    recall.list_orphan_derivations. These are exactly the asserted nodes."""
    out = []
    for eid, ev in store.evidence.items():
        if not is_recorded(ev):
            out.append({
                "id": eid,
                "title": ev.title,
                "source": ev.source or "(none)",
                "kind": "asserted",
            })
    return out


def provenance_counts(store) -> dict:
    """{recorded, asserted, total} over evidence — for get_summary."""
    recorded = sum(1 for ev in store.evidence.values() if is_recorded(ev))
    total = len(store.evidence)
    return {"recorded": recorded, "asserted": total - recorded, "total": total}
