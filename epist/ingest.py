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


EXTRACTOR_MODEL = "claude-opus-4-6"


def llm_extractor(text: str) -> dict:
    """Production extractor: ask the LLM to surface the argumentation present in
    `text`, each node grounded in a verbatim span. Returns {nodes, edges}."""
    from .llm import get_client, _parse_llm_json
    client = get_client()
    resp = client.messages.create(
        model=EXTRACTOR_MODEL,
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


llm_extractor.identity = f"epistemic-workbench/ingest@{EXTRACTOR_MODEL}"


def _extractor_identity(extractor) -> str:
    ident = getattr(extractor, "identity", None)
    if ident:
        return ident
    return library_client.interpreter_id(f"ingest-{getattr(extractor, '__name__', 'extractor')}")


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

    import datetime as _dt
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    proposed = extractor(text) or {}
    nodes = proposed.get("nodes", [])
    edges = proposed.get("edges", [])
    interpreter = _extractor_identity(extractor)

    proposal_id = f"prop-{uuid.uuid4().hex[:8]}"

    # Run identity (phase 3). Each proposed node is a derived, grounded
    # interpretation in the substrate — located verbatim in the source it came
    # from and naming the interpreter that produced it. Nothing here is a
    # belief or a live claim; that is what commit_proposal (a person) does.
    run_id = None
    if source_id is not None:
        run_id = library_client.new_run_id()
        for n in nodes:
            span = n.get("span")
            quote = span if isinstance(span, str) and span.strip() else None
            iid = None
            if quote:
                iid = library_client.record_interpretation(
                    kind=f"proposed-{n.get('type', 'claim')}",
                    statement=n.get("text", "") or n.get("id", ""),
                    grounding=[{"evidence_id": source_id, "quote": quote}],
                    interpreter=interpreter,
                    metadata={"run_id": run_id, "proposal_id": proposal_id,
                              "node_id": n.get("id"), "confidence": n.get("confidence"),
                              "claim_hash": library_client.claim_hash(n.get("text", ""))})
            n["interpretation_id"] = iid
        library_client.record_run(
            kind="extract", interpreter=interpreter, inputs=[source_id],
            outputs=[{"type": "proposal", "id": proposal_id},
                     *[{"type": "interpretation", "id": n["interpretation_id"], "node_id": n.get("id")}
                       for n in nodes if n.get("interpretation_id")]],
            params={"workspace": Path(store.home).name, "title": title,
                    "nodes": len(nodes), "edges": len(edges),
                    "ungrounded_nodes": sum(1 for n in nodes if not n.get("interpretation_id"))},
            run_id=run_id, started_at=started)

    proposal = {
        "proposal_id": proposal_id,
        "created_at": time.time(),
        "status": "pending",
        "source_id": source_id,
        "source_type": source_type,
        "source_url": url,
        "title": title,
        "interpreter": interpreter,
        "run_id": run_id,
        "nodes": nodes,
        "edges": edges,
    }
    p = _proposals_path(store)
    p.mkdir(parents=True, exist_ok=True)
    _proposal_file(store, proposal_id).write_text(json.dumps(proposal, indent=2, default=str))

    return {"proposal_id": proposal_id, "source_id": source_id, "run_id": run_id,
            "interpreter": interpreter,
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
                "span": span, "claim_hash": library_client.claim_hash(text or ""),
                "interpretation_id": n.get("interpretation_id"),
                "run_id": proposal.get("run_id")})
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

    # Curation is a person's run: which proposed interpretations were accepted
    # into the live graph, by content hash, under this channel's actor.
    from epist.actor import resolve_actor
    curate_run = None
    if source_id is not None:
        outputs = []
        for n in proposal.get("nodes", []):
            nid = n.get("id")
            if nid in accepted and nid in id_map:
                outputs.append({"type": "accepted", "node_id": nid, "id": id_map[nid],
                                "interpretation_id": n.get("interpretation_id"),
                                "claim_hash": library_client.claim_hash(n.get("text", ""))})
        curate_run = library_client.record_run(
            kind="curate", interpreter=library_client.interpreter_id("curate"),
            inputs=[source_id],
            outputs=outputs,
            params={"workspace": Path(store.home).name, "proposal_id": proposal_id,
                    "extract_run_id": proposal.get("run_id"), "accepted_by": resolve_actor(),
                    "accepted": len(outputs), "skipped": skipped})
    proposal["curate_run_id"] = curate_run
    _proposal_file(store, proposal_id).write_text(json.dumps(proposal, indent=2, default=str))
    store.save()

    return {"committed": counts, "skipped": skipped, "source_id": source_id,
            "id_map": id_map, "run_id": curate_run}
