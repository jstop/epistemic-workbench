"""
FastAPI server wrapping the epistemic engine.
"""
import json as json_mod
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure epist package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from epist.model import (
    Claim, Evidence, Argument, Confidence, Scope, Identity,
    Modality, EvidenceType, InferencePattern, Defeater,
    DefeaterType, DefeaterStatus,
)
from epist.store import Store, _serialize
from epist.engine import (
    compute_atms, ATMSStatus, check_coherence, find_blind_spots,
    surface_assumptions, stress_test, bayesian_update, compute_calibration,
)
from epist.llm import (
    generate_full_graph as _generate_full_graph_impl,
    compute_summary as _compute_summary_impl,
    enhance_thesis as _enhance_thesis_impl,
    accept_enhanced_thesis as _accept_enhanced_impl,
    get_thesis_versions as _get_thesis_versions_impl,
    list_theses as _list_theses_impl,
    count_subgraph as _count_subgraph,
    GENERATE_PROMPT, ENHANCE_PROMPT,
)

app = FastAPI(title="Epistemic Workbench API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Store singleton ──────────────────────────────────────────────────

WORKSPACE = Path(os.environ.get("EPIST_HOME", Path(__file__).parent.parent / "demo-workspace"))
store: Store = Store(WORKSPACE)

# API key loading is handled by epist.llm.get_client()


def reload_store():
    global store
    store = Store(WORKSPACE)


# ── Pydantic request models ─────────────────────────────────────────

class ClaimCreate(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = 0.7
    modality: str = "empirical"
    notes: str = ""
    is_root: bool = False

class ClaimUpdate(BaseModel):
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    confidence: Optional[float] = None
    modality: Optional[str] = None
    notes: Optional[str] = None
    assumes: Optional[list[str]] = None

class EvidenceCreate(BaseModel):
    title: str
    description: str
    evidence_type: str = "observation"
    source: str = ""
    reliability: float = 0.7
    notes: str = ""

class ArgumentCreate(BaseModel):
    conclusion: str
    premises: list[str]
    pattern: str = "modus_ponens"
    label: str = ""
    confidence: float = 0.7

class DefeaterCreate(BaseModel):
    type: str = "undercutting"  # rebutting, undercutting, undermining
    description: str

class DefeaterUpdate(BaseModel):
    status: str  # active, answered, withdrawn
    response: Optional[str] = None

class GenerateRequest(BaseModel):
    thesis: str

class AcceptEnhancedRequest(BaseModel):
    thesis_id: str
    enhanced_thesis: str
    rationale: str = ""
    changes: list = []

class BayesianRequest(BaseModel):
    prior: float
    likelihood_true: float
    likelihood_false: float


# ── Workspace ────────────────────────────────────────────────────────

@app.get("/api/workspace")
def workspace_info():
    return {
        "home": str(store.home),
        "stats": {
            "claims": len(store.claims),
            "evidence": len(store.evidence),
            "arguments": len(store.arguments),
            "evaluations": len(store.evaluations),
            "predictions": len(store.predictions),
        },
    }


# ── Claims CRUD ──────────────────────────────────────────────────────

@app.get("/api/claims")
def list_claims():
    return [_serialize(c) for c in store.claims.values()]


@app.post("/api/claims")
def create_claim(body: ClaimCreate):
    c = Claim(
        subject=body.subject, predicate=body.predicate, object=body.object,
        confidence=Confidence(body.confidence),
        modality=Modality(body.modality),
        notes=body.notes,
        is_root=body.is_root,
    )
    store.add_claim(c)
    return _serialize(c)


@app.get("/api/claims/{eo_id}")
def get_claim(eo_id: str):
    c = store.claims.get(eo_id)
    if not c:
        raise HTTPException(404, "Claim not found")
    return _serialize(c)


@app.put("/api/claims/{eo_id}")
def update_claim(eo_id: str, body: ClaimUpdate):
    c = store.claims.get(eo_id)
    if not c:
        raise HTTPException(404, "Claim not found")
    if body.subject is not None:
        c.subject = body.subject
    if body.predicate is not None:
        c.predicate = body.predicate
    if body.object is not None:
        c.object = body.object
    if body.confidence is not None:
        c.confidence = Confidence(body.confidence)
    if body.modality is not None:
        c.modality = Modality(body.modality)
    if body.notes is not None:
        c.notes = body.notes
    if body.assumes is not None:
        c.assumes = body.assumes
    store.save()
    return _serialize(c)


@app.delete("/api/claims/{eo_id}")
def delete_claim(eo_id: str):
    if eo_id not in store.claims:
        raise HTTPException(404, "Claim not found")
    del store.claims[eo_id]
    # Remove arguments that reference this claim
    to_remove = [
        aid for aid, a in store.arguments.items()
        if a.conclusion == eo_id or eo_id in a.premises
    ]
    for aid in to_remove:
        del store.arguments[aid]
    store.save()
    return {"ok": True}


# ── Evidence CRUD ────────────────────────────────────────────────────

@app.get("/api/evidence")
def list_evidence():
    return [_serialize(e) for e in store.evidence.values()]


@app.post("/api/evidence")
def create_evidence(body: EvidenceCreate):
    e = Evidence(
        title=body.title, description=body.description,
        evidence_type=EvidenceType(body.evidence_type),
        source=body.source, reliability=body.reliability,
        notes=body.notes,
    )
    store.add_evidence(e)
    return _serialize(e)


@app.delete("/api/evidence/{eo_id}")
def delete_evidence(eo_id: str):
    if eo_id not in store.evidence:
        raise HTTPException(404, "Evidence not found")
    del store.evidence[eo_id]
    to_remove = [
        aid for aid, a in store.arguments.items()
        if eo_id in a.premises
    ]
    for aid in to_remove:
        del store.arguments[aid]
    store.save()
    return {"ok": True}


# ── Arguments CRUD ───────────────────────────────────────────────────

@app.get("/api/arguments")
def list_arguments():
    return [_serialize(a) for a in store.arguments.values()]


@app.post("/api/arguments")
def create_argument(body: ArgumentCreate):
    # Validate references
    conc = store.get(body.conclusion)
    if not conc:
        raise HTTPException(400, f"Conclusion not found: {body.conclusion}")
    for pid in body.premises:
        if not store.get(pid):
            raise HTTPException(400, f"Premise not found: {pid}")
    a = Argument(
        conclusion=conc.id, premises=body.premises,
        pattern=InferencePattern(body.pattern),
        label=body.label, confidence=Confidence(body.confidence),
    )
    store.add_argument(a)
    return _serialize(a)


@app.delete("/api/arguments/{eo_id}")
def delete_argument(eo_id: str):
    if eo_id not in store.arguments:
        raise HTTPException(404, "Argument not found")
    del store.arguments[eo_id]
    store.save()
    return {"ok": True}


@app.get("/api/arguments/for-node/{eo_id}")
def arguments_for_node(eo_id: str):
    """Return all arguments where this node is the conclusion or a premise."""
    results = []
    for aid, a in store.arguments.items():
        if a.conclusion == eo_id or eo_id in a.premises:
            results.append({
                **_serialize(a),
                "defeaters": [
                    {"index": i, "type": d.type.value, "description": d.description,
                     "status": d.status.value, "response": d.response}
                    for i, d in enumerate(a.defeaters)
                ],
            })
    return results


# ── Defeater management ─────────────────────────────────────────────

@app.get("/api/arguments/{eo_id}/defeaters")
def list_defeaters(eo_id: str):
    arg = store.arguments.get(eo_id)
    if not arg:
        raise HTTPException(404, "Argument not found")
    return [
        {"index": i, "type": d.type.value, "description": d.description,
         "status": d.status.value, "response": d.response}
        for i, d in enumerate(arg.defeaters)
    ]


@app.post("/api/arguments/{eo_id}/defeaters")
def add_defeater(eo_id: str, body: DefeaterCreate):
    arg = store.arguments.get(eo_id)
    if not arg:
        raise HTTPException(404, "Argument not found")
    d = Defeater(
        type=DefeaterType(body.type),
        description=body.description,
        status=DefeaterStatus.ACTIVE,
    )
    arg.defeaters.append(d)
    store.save()
    return {"ok": True, "index": len(arg.defeaters) - 1}


@app.put("/api/arguments/{eo_id}/defeaters/{idx}")
def update_defeater(eo_id: str, idx: int, body: DefeaterUpdate):
    arg = store.arguments.get(eo_id)
    if not arg:
        raise HTTPException(404, "Argument not found")
    if idx < 0 or idx >= len(arg.defeaters):
        raise HTTPException(404, "Defeater not found")
    arg.defeaters[idx].status = DefeaterStatus(body.status)
    if body.response is not None:
        arg.defeaters[idx].response = body.response
    store.save()
    return {"ok": True}


# ── Graph endpoint ───────────────────────────────────────────────────

@app.get("/api/graph")
def get_graph():
    atms = compute_atms(store)
    nodes = []
    edges = []

    for cid, c in store.claims.items():
        nodes.append({
            "id": cid,
            "type": "claim",
            "label": f"{c.subject} {c.predicate} {c.object}",
            "confidence": c.confidence.level,
            "modality": c.modality.value,
            "atms": atms.get(cid, "unknown"),
            "notes": c.notes,
        })

    for eid, e in store.evidence.items():
        nodes.append({
            "id": eid,
            "type": "evidence",
            "label": e.title,
            "confidence": e.reliability,
            "atms": atms.get(eid, "unknown"),
            "notes": e.description,
        })

    node_ids = {n["id"] for n in nodes}

    for aid, a in store.arguments.items():
        for pid in a.premises:
            if pid in node_ids and a.conclusion in node_ids:
                edges.append({
                    "source": pid,
                    "target": a.conclusion,
                    "type": "supports",
                    "argument_id": aid,
                    "label": a.label,
                    "pattern": a.pattern.value,
                    "confidence": a.confidence.level,
                })
        # Active defeaters: mark on the conclusion node (edges require both endpoints to be nodes)
        for d in a.defeaters:
            if d.status == DefeaterStatus.ACTIVE:
                for n in nodes:
                    if n["id"] == a.conclusion:
                        n.setdefault("defeaters", []).append(d.description[:80])

    for cid, c in store.claims.items():
        for assumed_id in c.assumes:
            if assumed_id in node_ids:
                edges.append({
                    "source": cid,
                    "target": assumed_id,
                    "type": "assumes",
                })

    return {"nodes": nodes, "edges": edges}


# ── Analysis endpoints ───────────────────────────────────────────────

@app.get("/api/analysis/atms")
def get_atms():
    return compute_atms(store)


@app.get("/api/analysis/coherence")
def get_coherence():
    return check_coherence(store)


@app.get("/api/analysis/blind-spots")
def get_blind_spots():
    return find_blind_spots(store)


@app.get("/api/analysis/assumptions/{eo_id}")
def get_assumptions(eo_id: str):
    obj = store.get(eo_id)
    if not obj:
        raise HTTPException(404, "Object not found")
    return surface_assumptions(store, obj.id)


@app.get("/api/analysis/stress-test/{eo_id}")
def get_stress_test(eo_id: str):
    obj = store.get(eo_id)
    if not obj:
        raise HTTPException(404, "Object not found")
    result = stress_test(store, obj.id)
    if not result:
        raise HTTPException(404, "Could not generate stress test")
    return result


@app.post("/api/analysis/bayesian-update")
def bayesian(body: BayesianRequest):
    posterior = bayesian_update(body.prior, body.likelihood_true, body.likelihood_false)
    return {
        "prior": body.prior,
        "posterior": posterior,
        "delta": posterior - body.prior,
    }


# ── Summary / Export ─────────────────────────────────────────────────

@app.get("/api/summary/theses")
def list_theses():
    """Return root theses grouped by lineage, showing only the latest version per lineage."""
    return _list_theses_impl(store)


def _compute_summary(thesis_id: Optional[str] = None):
    """Compute summary data for a thesis. Delegates to epist.llm."""
    return _compute_summary_impl(store, thesis_id)


@app.get("/api/summary")
def get_summary(thesis_id: Optional[str] = None):
    return _compute_summary(thesis_id)


# ── Enhance thesis ───────────────────────────────────────────────────

class EnhanceRequest(BaseModel):
    thesis_id: str


@app.post("/api/enhance-thesis")
async def enhance_thesis(body: EnhanceRequest):
    """Use Claude to suggest an enhanced version of the thesis based on its analysis."""
    try:
        return _enhance_thesis_impl(store, body.thesis_id)
    except RuntimeError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"LLM call failed: {e}")


# ── Auto-generate argument graph ─────────────────────────────────────

@app.post("/api/generate")
async def generate_graph(body: GenerateRequest):
    """Use Claude to auto-generate an argument graph from a thesis."""
    try:
        thesis_id = _generate_full_graph_impl(store, body.thesis)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"LLM call failed: {e}")

    return {
        "ok": True,
        "created": _count_subgraph(store, thesis_id),
        "thesis_id": thesis_id,
    }


@app.post("/api/accept-enhanced-thesis")
async def accept_enhanced_thesis(body: AcceptEnhancedRequest):
    """Accept an enhanced thesis: generate a new argument graph and link it to the previous version."""
    try:
        result = _accept_enhanced_impl(
            store, body.thesis_id, body.enhanced_thesis,
            body.rationale, body.changes,
        )
    except RuntimeError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"LLM call failed: {e}")
    return {"ok": True, **result}


@app.get("/api/thesis-versions/{thesis_id}")
def get_thesis_versions(thesis_id: str):
    """Walk backward via previous_version to find lineage root, then build ordered chain."""
    try:
        return _get_thesis_versions_impl(store, thesis_id)
    except RuntimeError as e:
        raise HTTPException(404, str(e))
