"""
F2 — evidence provenance: the anti-confabulation layer.

The invariant: anything not backed by a real recorded source renders as
UNVERIFIED. A `source` citation string proves nothing — only a provenance record
pointing at evidence registered in the living library (the substrate) counts as
`recorded`.

Two provenance kinds:
  • "asserted" — LLM-invented or hand-typed; UNVERIFIED. This is the default for
    everything `generate_thesis` produces.
  • "recorded" — backed by a library `evidence_id` (a snapshot or a referenced
    uri registered there). Legacy records carrying a recall `source_id` are
    still read as recorded; new ones are never written that way.
"""
from . import library_client


def provenance_kind(evidence) -> str:
    """Return 'recorded' or 'asserted' for an Evidence object."""
    p = getattr(evidence, "provenance", None)
    if isinstance(p, dict) and p.get("kind") == "recorded":
        if p.get("evidence_id") or p.get("source_id") is not None or p.get("url"):
            return "recorded"
    return "asserted"


def is_recorded(evidence) -> bool:
    return provenance_kind(evidence) == "recorded"


def attach_source(store, node_id, evidence_id=None, url=None, quote=None,
                  source_type="document", retrieved_at=None, source_id=None) -> dict:
    """Attach a real source to an evidence node, flipping it to `recorded`.

    Accepts either an existing library `evidence_id` or an explicit `{url, quote}`
    (registered in the library as evidence: the quote is snapshotted content, the
    url the reference). If the library is unreachable, or the evidence_id does
    not exist, the node stays `asserted` and we say so — never fake `recorded`.

    `source_id` (a legacy recall id) is accepted for API compatibility but no
    longer resolves anything; use evidence_id.
    """
    ev = store.get(node_id)
    if ev is None:
        return {"ok": False, "reason": f"node not found: {node_id}"}
    if not hasattr(ev, "reliability"):  # not an Evidence node
        return {"ok": False,
                "reason": "attach_source targets an evidence node; "
                          f"{type(ev).__name__} {node_id[:12]} is not evidence"}

    resolved = None
    if evidence_id:
        if library_client.evidence_exists(evidence_id):
            resolved = evidence_id
        else:
            return {"ok": False, "kind": "asserted",
                    "reason": f"the library has no evidence {evidence_id} "
                              "(or is unreachable) — left as asserted"}
    elif url:
        resolved = library_client.register_evidence(
            content=(quote or None), uri=url,
            media_type=("text/plain" if quote else "text/uri-list"),
            metadata={"kind": "attached-source", "source_type": source_type,
                      "workbench_evidence": ev.id, "title": ev.title},
        )
        if resolved is None:
            ev.provenance = {"kind": "asserted", "url": url, "quote": quote,
                             "note": "library unreachable; unverified"}
            store.save()
            return {"ok": False, "kind": "asserted",
                    "reason": "living library unreachable — url stored but evidence "
                              "remains asserted (unverified)"}
    elif source_id is not None:
        return {"ok": False, "kind": "asserted",
                "reason": "recall source ids are no longer a source of record; "
                          "attach a library evidence_id or a url"}
    else:
        return {"ok": False, "reason": "provide an evidence_id or a url"}

    ev.provenance = {
        "kind": "recorded",
        "evidence_id": resolved,
        "url": url,
        "quote": quote,
        "retrieved_at": retrieved_at,
    }
    store.save()
    return {"ok": True, "kind": "recorded", "evidence_id": resolved}


def mark_asserted(evidence, recall_text=None):
    """Stamp an evidence node as explicitly asserted (unverified). Used by the
    generate path so invented citations are never mistaken for recorded ones.
    (`recall_text` is accepted for compatibility and ignored: the workbench
    itself is the anti-confabulation view for asserted evidence.)"""
    evidence.provenance = {"kind": "asserted"}


def list_unsourced(store) -> list[dict]:
    """Evidence nodes lacking a recorded source — exactly the asserted nodes."""
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
