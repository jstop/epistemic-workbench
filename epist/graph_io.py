"""
F1 — Direct authoring + import/export for argument graphs.

Pivot: analyzer → editor. This module adds the primitives the workbench was
missing — create claims/arguments/typed-edges by hand, and import/export a
whole graph as JSON — without disturbing the generate path or the ATMS engine.

Two interchange shapes are supported by `import_graph`:

  • internal  ("format": "epist-graph/v1") — the exact, lossless serialization
    that `export_graph` emits. `import_graph(export_graph(W))` round-trips with
    no loss because every field is serialized and every id is preserved.

  • flat ("nodes" + "edges", brief §4) — the authored-corpus shape with flat
    `text` / `status` / `source` / `confidence` / `killed_by` nodes and
    `{from, rel, to}` edges. Mapped onto the internal model on import.

The generic edge layer (model.Edge / store.edges) is authoritative and lossless.
For relations the ATMS engine already understands, `link()` also maintains the
backing Argument/Defeater constructs so authored graphs are analyzed by the same
pass as generated ones.
"""
from .model import (
    Claim, Evidence, Argument, Edge, Confidence, Defeater,
    Modality, EvidenceType, InferencePattern, DefeaterType, DefeaterStatus,
    NodeType, EdgeRelation, NODE_STATUSES, SUPPORT_MODES,
)
from .store import (
    _serialize, _deserialize_claim, _deserialize_evidence,
    _deserialize_argument, _deserialize_evaluation, _deserialize_prediction,
    _deserialize_edge,
)

FORMAT_VERSION = "epist-graph/v1"

_CLAIM_NODE_TYPES = {"claim", "thesis", "objection", "concession"}


# ── Authoring primitives ─────────────────────────────────────────────

def add_claim(store, text, node_type="claim", status=None, confidence=0.7,
              subject="", predicate="", object="", modality="empirical",
              notes="", is_root=None):
    """Create a claim (or thesis/objection/concession) by hand. Returns the Claim.

    `text` is the natural-language statement (stored in notes). subject/predicate
    /object are optional structured forms; if omitted, the text is used as the
    subject so the node still renders.
    """
    if node_type not in _CLAIM_NODE_TYPES:
        raise ValueError(f"node_type must be one of {sorted(_CLAIM_NODE_TYPES)}, got {node_type!r}")
    if status is not None and status not in NODE_STATUSES:
        raise ValueError(f"status must be one of {sorted(NODE_STATUSES)} or None, got {status!r}")
    if is_root is None:
        is_root = node_type == "thesis"
    c = Claim(
        subject=subject or text,
        predicate=predicate,
        object=object,
        confidence=Confidence(confidence),
        modality=Modality(modality),
        node_type=node_type,
        status=status,
        notes=notes or text,
        is_root=is_root,
    )
    store.add_claim(c)
    return c


def add_argument(store, conclusion_id, premise_ids, pattern="modus_ponens",
                 label="", confidence=0.7, support_mode="conjunctive"):
    """Create an argument linking premise ids to a conclusion id. Returns the Argument.

    Defaults to support_mode='conjunctive' for multi-premise arguments (the
    honest default — F3 wires the propagation that makes this matter); a single
    premise behaves identically under any mode.
    """
    if support_mode not in SUPPORT_MODES:
        raise ValueError(f"support_mode must be one of {sorted(SUPPORT_MODES)}, got {support_mode!r}")
    conc = store.get(conclusion_id)
    if not conc:
        raise ValueError(f"conclusion not found: {conclusion_id}")
    resolved_premises = []
    for pid in premise_ids:
        p = store.get(pid)
        if not p:
            raise ValueError(f"premise not found: {pid}")
        resolved_premises.append(p.id)
    if not resolved_premises:
        raise ValueError("an argument needs at least one premise")
    a = Argument(
        conclusion=conc.id,
        premises=resolved_premises,
        pattern=InferencePattern(pattern),
        label=label,
        confidence=Confidence(confidence),
        support_mode=support_mode,
    )
    store.add_argument(a)
    return a


def link(store, from_id, to_id, relation):
    """Create a typed edge between two objects, maintaining engine-visible
    constructs for the relations the ATMS already understands. Returns the Edge.

    relation ∈ supports, refutes, rebuts, concedes, grounds, narrows, supersedes.
    """
    rel = relation.value if isinstance(relation, EdgeRelation) else relation
    if rel not in {r.value for r in EdgeRelation}:
        raise ValueError(f"relation must be one of {[r.value for r in EdgeRelation]}, got {rel!r}")
    src = store.get(from_id)
    dst = store.get(to_id)
    if not src:
        raise ValueError(f"from_id not found: {from_id}")
    if not dst:
        raise ValueError(f"to_id not found: {to_id}")

    e = Edge(from_id=src.id, rel=rel, to=dst.id)
    store.add_edge(e)
    _apply_edge_side_effects(store, src, dst, rel)
    store.save()
    return e


def _apply_edge_side_effects(store, src, dst, rel):
    """Keep the ATMS-visible constructs in sync with a newly created edge.
    The Edge remains the lossless source of truth; these are derived so the
    engine analyzes authored graphs the same way it analyzes generated ones."""
    if rel in ("supports", "grounds"):
        # Reuse an existing argument with the same conclusion+premise if present.
        for a in store.arguments.values():
            if a.conclusion == dst.id and src.id in a.premises:
                return
        store.add_argument(Argument(
            conclusion=dst.id, premises=[src.id],
            pattern=InferencePattern.INDUCTION if rel == "grounds" else InferencePattern.MODUS_PONENS,
            label=f"{rel}: {_short(src)}",
            confidence=Confidence(_conf_of(src)),
            support_mode="independent",
        ))
    elif rel in ("refutes", "rebuts", "concedes"):
        status = DefeaterStatus.CONCEDED if rel == "concedes" else DefeaterStatus.ACTIVE
        dtype = DefeaterType.REBUTTING if rel in ("refutes", "rebuts") else DefeaterType.UNDERCUTTING
        supporting = [a for a in store.arguments.values() if a.conclusion == dst.id]
        if supporting:
            target = max(supporting, key=lambda a: a.confidence.level)
            target.defeaters.append(Defeater(
                type=dtype, description=f"{rel}: {_short(src)}", status=status,
            ))
        # If dst has no supporting argument, the edge alone records the objection.
    elif rel == "supersedes":
        # from supersedes to: mark the old node and record what killed it.
        if dst.id in store.claims:
            store.claims[dst.id].status = "superseded"
            store.claims[dst.id].killed_by = src.id
    # narrows: edge-only; no engine side effect yet.


def _short(obj):
    if hasattr(obj, "subject"):
        return (obj.notes or f"{obj.subject} {obj.predicate} {obj.object}").strip()[:60]
    return getattr(obj, "title", getattr(obj, "label", obj.id[:12]))


def _conf_of(obj):
    if hasattr(obj, "confidence"):
        return obj.confidence.level
    return getattr(obj, "reliability", 0.7)


# ── Export ───────────────────────────────────────────────────────────

def export_graph(store) -> dict:
    """Serialize the whole workspace to a lossless JSON-able dict."""
    return {
        "format": FORMAT_VERSION,
        "meta": {
            "node_types": [t.value for t in NodeType],
            "statuses": sorted(NODE_STATUSES),
            "edge_relations": [r.value for r in EdgeRelation],
        },
        "claims": [_serialize(c) for c in store.claims.values()],
        "evidence": [_serialize(e) for e in store.evidence.values()],
        "arguments": [_serialize(a) for a in store.arguments.values()],
        "evaluations": [_serialize(e) for e in store.evaluations.values()],
        "predictions": [_serialize(p) for p in store.predictions.values()],
        "edges": [_serialize(e) for e in store.edges.values()],
        "foundations": store.foundations,
    }


# ── Import ───────────────────────────────────────────────────────────

def import_graph(store, graph_json: dict, mode: str = "merge") -> dict:
    """Load a graph (internal or flat §4 shape) into the store.

    mode='merge'   — add/overwrite objects by id, keep everything else.
    mode='replace' — clear the workspace first.
    Returns a summary dict of what was loaded.
    """
    if mode not in ("merge", "replace"):
        raise ValueError("mode must be 'merge' or 'replace'")
    if mode == "replace":
        store.clear()

    if _is_internal_shape(graph_json):
        summary = _import_internal(store, graph_json)
    elif "nodes" in graph_json:
        summary = _import_flat(store, graph_json)
    else:
        raise ValueError(
            "unrecognized graph format: expected an 'epist-graph/v1' export "
            "or a {nodes, edges} document"
        )
    store.save()
    return summary


def _is_internal_shape(g) -> bool:
    if g.get("format") == FORMAT_VERSION:
        return True
    # Heuristic: internal exports have typed collections, not a flat 'nodes' list.
    return "nodes" not in g and any(
        k in g for k in ("claims", "evidence", "arguments")
    )


def _import_internal(store, g) -> dict:
    counts = {}
    for name, collection, deser in [
        ("claims", store.claims, _deserialize_claim),
        ("evidence", store.evidence, _deserialize_evidence),
        ("arguments", store.arguments, _deserialize_argument),
        ("evaluations", store.evaluations, _deserialize_evaluation),
        ("predictions", store.predictions, _deserialize_prediction),
        ("edges", store.edges, _deserialize_edge),
    ]:
        n = 0
        for d in g.get(name, []):
            obj = deser(d)
            collection[obj.id] = obj
            n += 1
        counts[name] = n
    if isinstance(g.get("foundations"), dict):
        store.foundations.update(g["foundations"])
    return {"mode": "internal", **counts}


def _import_flat(store, g) -> dict:
    """Map the brief's §4 {nodes, edges} shape onto the internal model.
    Node ids are preserved so edges resolve and round-trips stay stable."""
    counts = {"claims": 0, "evidence": 0, "arguments": 0, "edges": 0, "skipped": 0}
    for node in g.get("nodes", []):
        ntype = node.get("type", "claim")
        nid = node.get("id")
        if not nid:
            counts["skipped"] += 1
            continue
        text = node.get("text", "")
        status = node.get("status")
        if status not in NODE_STATUSES:
            status = None  # unknown status string ⇒ let ATMS compute
        if ntype in _CLAIM_NODE_TYPES:
            store.claims[nid] = Claim(
                subject=text or nid, predicate="", object="",
                confidence=Confidence(node.get("confidence", 0.7)),
                node_type=ntype,
                status=status,
                killed_by=node.get("killed_by"),
                notes=text,
                is_root=(ntype == "thesis"),
                id=nid,
            )
            counts["claims"] += 1
        elif ntype == "evidence":
            store.evidence[nid] = Evidence(
                title=(text[:80] or nid), description=text,
                source=node.get("source", ""),
                reliability=node.get("confidence", 0.7),
                id=nid,
            )
            counts["evidence"] += 1
        elif ntype == "argument":
            store.arguments[nid] = Argument(
                conclusion=node.get("conclusion", ""),
                premises=node.get("premises", []),
                label=text,
                confidence=Confidence(node.get("confidence", 0.7)),
                id=nid,
            )
            counts["arguments"] += 1
        else:
            counts["skipped"] += 1

    valid_edges = []
    for edge in g.get("edges", []):
        frm = edge.get("from") or edge.get("from_id")
        rel = edge.get("rel")
        to = edge.get("to")
        if not (frm and rel and to):
            counts["skipped"] += 1
            continue
        e = Edge(from_id=frm, rel=rel, to=to, notes=edge.get("notes", ""))
        store.edges[e.id] = e
        counts["edges"] += 1
        valid_edges.append(e)

    # Build the engine-visible constructs so the imported graph is analyzed by
    # the same ATMS pass as generated ones. Supports/grounds first (they create
    # the arguments that refutes/concedes then attach defeaters to).
    _order = {"supports": 0, "grounds": 0, "refutes": 1, "rebuts": 1,
              "concedes": 1, "supersedes": 2, "narrows": 3}
    for e in sorted(valid_edges, key=lambda x: _order.get(x.rel, 9)):
        src = store.get(e.from_id)
        dst = store.get(e.to)
        if src and dst:
            _apply_edge_side_effects(store, src, dst, e.rel)
    counts["arguments"] = len(store.arguments)

    return {"mode": "flat", **counts}
