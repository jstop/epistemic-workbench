"""
F5 — corpus ingestion (propose-then-curate).

Turn an existing document/transcript into a *proposed* set of claims, arguments,
and objections — each carrying a provenance pointer back to the source span it
came from — for human review before anything touches the live graph.

Flow:
  ingest_document(store, text, extractor) -> proposal_id
     • registers the document in recall (record_source) — best-effort
     • runs `extractor(text)` to get proposed nodes/edges with source spans
     • persists the proposal as a pending file under <ws>/proposals/<id>.json
       (NOT in the live claims/arguments/edges collections)
  review_proposal(store, proposal_id) -> the proposal dict (read-only)
  commit_proposal(store, proposal_id, accepted_node_ids) -> summary
     • only the accepted nodes (and edges between accepted nodes) enter the graph
     • accepted claims get provenance recorded in recall (a real derivation to
       the source); evidence is created `recorded` when it has a span, else
       asserted. Nothing is committed without explicit acceptance.

The `extractor` is injected (an LLM call in production, a stub in tests) so this
module is pure orchestration + persistence and fully testable offline.
"""
import json
import time
import uuid
from pathlib import Path

from .model import Claim, Evidence, Argument, Edge, Confidence
from . import library_client


PROPOSAL_DIR = "proposals"
_CLAIM_TYPES = {"claim", "thesis", "objection", "concession"}


INGEST_PROMPT = """\
You are an epistemic analyst. Extract the argumentation ALREADY PRESENT in the \
document below — do not invent new arguments. Identify the claims, the thesis (if \
any), supporting arguments, and objections actually made in the text.

Return ONLY a JSON object:
{
  "nodes": [
    {"id": "n0", "type": "claim|thesis|objection|concession",
     "text": "the claim as stated/paraphrased",
     "confidence": 0.5,
     "span": "a short VERBATIM quote from the document that this node came from"}
  ],
  "edges": [
    {"from": "n1", "rel": "supports|refutes|rebuts|concedes|grounds|narrows", "to": "n0"}
  ]
}

Rules:
- Every node's `span` MUST be a verbatim substring of the document — it is the
  provenance pointer. If you cannot ground a node in a span, do not emit it.
- Use stable local ids (n0, n1, …) referenced by edges.
- Extract only what the text argues; mark counter-positions as objection nodes.
- Do NOT fabricate citations or evidence not in the document.
"""


def llm_extractor(text: str) -> dict:
    """Production extractor: ask the LLM to surface the argumentation present in
    `text`, each node grounded in a verbatim span. Returns {nodes, edges}."""
    from .llm import get_client, _parse_llm_json
    client = get_client()
    resp = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        messages=[{"role": "user",
                   "content": f"{INGEST_PROMPT}\n\n=== DOCUMENT ===\n{text}"}],
    )
    data = _parse_llm_json(resp.content[0].text)
    # Drop any node whose span is not actually in the document (anti-confabulation).
    kept = []
    for n in data.get("nodes", []):
        span = n.get("span")
        if span and isinstance(span, str) and span.strip() and span in text:
            kept.append(n)
    kept_ids = {n["id"] for n in kept if n.get("id")}
    edges = [e for e in data.get("edges", [])
             if (e.get("from") in kept_ids and e.get("to") in kept_ids)]
    return {"nodes": kept, "edges": edges}


def _proposals_path(store) -> Path:
    return Path(store.home) / PROPOSAL_DIR


def _proposal_file(store, proposal_id) -> Path:
    return _proposals_path(store) / f"{proposal_id}.json"


def ingest_document(store, source_text=None, source_ref=None, extractor=None,
                    source_type="document", title=None) -> dict:
    """Ingest a document and produce a PROPOSED graph (nothing committed).

    Provide `source_text` (raw content) or `source_ref` (a {url, ...} pointer);
    `extractor(text) -> {nodes, edges}` does the argumentation extraction. Each
    proposed node SHOULD carry `span` ({start,end} or a quote) into the source.

    Returns {proposal_id, source_id, counts}.
    """
    if extractor is None:
        raise ValueError("an extractor(text)->{nodes,edges} must be provided")
    text = source_text
    if text is None and isinstance(source_ref, dict):
        text = source_ref.get("content") or source_ref.get("url") or ""
    if not text:
        raise ValueError("provide source_text or a source_ref with content/url")

    url = source_ref.get("url") if isinstance(source_ref, dict) else None
    # The source is registered in the substrate (content-addressed snapshot);
    # `source_id` is the library evidence id, or None if the library is down —
    # in which case nothing derived from it can be marked recorded.
    source_id = library_client.register_evidence(
        content=text, uri=url, media_type="text/plain",
        metadata={"kind": "ingested-source", "source_type": source_type,
                  "title": (title or text[:200])},
    )

    proposed = extractor(text) or {}
    nodes = proposed.get("nodes", [])
    edges = proposed.get("edges", [])

    proposal_id = f"prop-{uuid.uuid4().hex[:8]}"
    proposal = {
        "proposal_id": proposal_id,
        "created_at": time.time(),
        "status": "pending",
        "source_id": source_id,
        "source_type": source_type,
        "source_url": url,
        "title": title,
        "nodes": nodes,
        "edges": edges,
    }
    p = _proposals_path(store)
    p.mkdir(parents=True, exist_ok=True)
    _proposal_file(store, proposal_id).write_text(json.dumps(proposal, indent=2, default=str))

    return {"proposal_id": proposal_id, "source_id": source_id,
            "counts": {"nodes": len(nodes), "edges": len(edges)}}


def list_proposals(store) -> list[dict]:
    d = _proposals_path(store)
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("prop-*.json")):
        try:
            pr = json.loads(f.read_text())
            out.append({"proposal_id": pr["proposal_id"], "status": pr.get("status"),
                        "source_id": pr.get("source_id"),
                        "nodes": len(pr.get("nodes", [])),
                        "title": pr.get("title")})
        except (json.JSONDecodeError, KeyError):
            continue
    return out


def review_proposal(store, proposal_id) -> dict:
    f = _proposal_file(store, proposal_id)
    if not f.exists():
        raise ValueError(f"no such proposal: {proposal_id}")
    return json.loads(f.read_text())


def commit_proposal(store, proposal_id, accepted_node_ids) -> dict:
    """Commit only the accepted proposed nodes (and edges among them) into the
    live graph. Accepted claims/evidence get real provenance in recall.

    Returns {committed: {...}, skipped: int, source_id}.
    """
    proposal = review_proposal(store, proposal_id)
    if proposal.get("status") == "committed":
        raise ValueError(f"proposal {proposal_id} already committed")

    accepted = set(accepted_node_ids or [])
    source_id = proposal.get("source_id")
    counts = {"claims": 0, "evidence": 0, "arguments": 0, "edges": 0}
    skipped = 0
    # map proposal-local node id -> real store id
    id_map = {}

    # First pass: create the accepted claim/evidence nodes.
    for n in proposal.get("nodes", []):
        nid = n.get("id")
        if nid not in accepted:
            skipped += 1
            continue
        ntype = n.get("type", "claim")
        text = n.get("text", "")
        span = n.get("span")  # {start,end} or quote string
        quote = span if isinstance(span, str) else (n.get("quote"))

        if ntype in _CLAIM_TYPES:
            c = Claim(subject=text or nid, predicate="", object="",
                      confidence=Confidence(n.get("confidence", 0.6)),
                      node_type=ntype, notes=text, is_root=(ntype == "thesis"))
            store.claims[c.id] = c
            id_map[nid] = c.id
            counts["claims"] += 1
            # Provenance for an accepted claim is the proposal itself (kept on
            # disk with its spans) plus the library evidence it came from. A
            # per-claim interpretation event with run identity is phase 3.
            c.version_meta = dict(c.version_meta or {}, ingested_from={
                "evidence_id": source_id, "proposal_id": proposal_id,
                "span": span, "claim_hash": library_client.claim_hash(text or "")})
        elif ntype == "evidence":
            recorded = source_id is not None
            ev = Evidence(title=(text[:80] or nid), description=text,
                          source=proposal.get("source_url") or (f"library:{source_id}" if source_id else "(ingested; library unavailable)"),
                          reliability=n.get("confidence", 0.6))
            ev.provenance = ({"kind": "recorded", "evidence_id": source_id,
                              "url": proposal.get("source_url"), "quote": quote}
                             if recorded else {"kind": "asserted"})
            store.evidence[ev.id] = ev
            id_map[nid] = ev.id
            counts["evidence"] += 1
        else:
            skipped += 1

    # Second pass: edges, but only between two accepted (now-mapped) nodes.
    from .graph_io import _apply_edge_side_effects
    for e in proposal.get("edges", []):
        frm = id_map.get(e.get("from") or e.get("from_id"))
        to = id_map.get(e.get("to"))
        rel = e.get("rel")
        if not (frm and to and rel):
            continue
        edge = Edge(from_id=frm, rel=rel, to=to, notes=e.get("notes", ""))
        store.edges[edge.id] = edge
        counts["edges"] += 1
        src = store.get(frm)
        dst = store.get(to)
        if src and dst:
            _apply_edge_side_effects(store, src, dst, rel)

    proposal["status"] = "committed"
    proposal["committed_node_ids"] = sorted(accepted)
    _proposal_file(store, proposal_id).write_text(json.dumps(proposal, indent=2, default=str))
    store.save()

    return {"committed": counts, "skipped": skipped, "source_id": source_id,
            "id_map": id_map}
