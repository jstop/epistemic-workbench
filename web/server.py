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
import anthropic

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

# Load API key from ~/.api_keys/env if not already set
_api_keys_file = Path.home() / ".api_keys" / "env"
if not os.environ.get("ANTHROPIC_API_KEY") and _api_keys_file.exists():
    for line in _api_keys_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            val = line.split("=", 1)[1].strip().strip("'\"")
            os.environ["ANTHROPIC_API_KEY"] = val
            break


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
    """Return root theses: claims that are argument conclusions but not premises of other arguments."""
    # Find all claims used as premises
    premise_ids = set()
    conclusion_ids = set()
    support_count = {}
    for a in store.arguments.values():
        conclusion_ids.add(a.conclusion)
        support_count[a.conclusion] = support_count.get(a.conclusion, 0) + 1
        for pid in a.premises:
            premise_ids.add(pid)

    # Root theses = conclusions that are never used as premises
    root_ids = conclusion_ids - premise_ids
    # Fallback: if no pure roots, use all conclusions
    if not root_ids:
        root_ids = conclusion_ids

    ranked = sorted(root_ids, key=lambda cid: support_count.get(cid, 0), reverse=True)
    results = []
    for cid in ranked:
        c = store.claims.get(cid)
        if c:
            results.append({
                "id": cid,
                "label": f"{c.subject} {c.predicate} {c.object}",
                "notes": c.notes,
                "support_count": support_count.get(cid, 0),
            })
    return results


@app.get("/api/summary")
def get_summary(thesis_id: Optional[str] = None):
    if not store.claims:
        return {"markdown": "No claims yet.", "thesis": None}

    atms = compute_atms(store)

    # Use provided thesis_id or find root thesis
    if thesis_id and thesis_id in store.claims:
        thesis = store.claims[thesis_id]
    else:
        # Root thesis = conclusion that is never a premise, with most support
        premise_ids = set()
        support_count = {}
        for a in store.arguments.values():
            support_count[a.conclusion] = support_count.get(a.conclusion, 0) + 1
            for pid in a.premises:
                premise_ids.add(pid)
        root_ids = set(support_count.keys()) - premise_ids
        if root_ids:
            thesis_id = max(root_ids, key=lambda cid: support_count.get(cid, 0))
        elif support_count:
            thesis_id = max(support_count, key=support_count.get)
        else:
            thesis_id = next(iter(store.claims))
        thesis = store.claims.get(thesis_id)
        if not thesis:
            thesis_id = next(iter(store.claims))
            thesis = store.claims[thesis_id]

    # Walk the argument subgraph reachable from this thesis
    subgraph_nodes = set()  # all node IDs in this thesis's tree
    subgraph_args = set()   # all argument IDs in this thesis's tree

    def walk(node_id):
        if node_id in subgraph_nodes:
            return
        subgraph_nodes.add(node_id)
        for aid, a in store.arguments.items():
            if a.conclusion == node_id:
                subgraph_args.add(aid)
                for pid in a.premises:
                    walk(pid)
        # Also walk assumptions
        c = store.claims.get(node_id)
        if c:
            for assumed_id in c.assumes:
                walk(assumed_id)

    walk(thesis_id)

    # Gather supporting arguments for thesis (direct supporters only)
    supporting = []
    for aid in subgraph_args:
        a = store.arguments[aid]
        if a.conclusion == thesis_id:
            premises = []
            for pid in a.premises:
                p = store.get(pid)
                if p:
                    premises.append({
                        "type": type(p).__name__.lower(),
                        "label": f"{p.subject} {p.predicate} {p.object}" if hasattr(p, "subject") else getattr(p, "title", pid[:12]),
                        "confidence": p.confidence.level if hasattr(p, "confidence") else getattr(p, "reliability", None),
                        "notes": getattr(p, "notes", "") or getattr(p, "description", ""),
                    })
            supporting.append({
                "label": a.label or "(unlabeled)",
                "pattern": a.pattern.value,
                "confidence": a.confidence.level,
                "premises": premises,
                "defeaters": [
                    {"type": d.type.value, "description": d.description,
                     "status": d.status.value, "response": d.response}
                    for d in a.defeaters
                ],
            })

    # Defeaters scoped to this thesis's subgraph only
    all_defeaters = []
    for aid in subgraph_args:
        a = store.arguments[aid]
        for d in a.defeaters:
            all_defeaters.append({
                "type": d.type.value,
                "description": d.description,
                "status": d.status.value,
                "response": d.response,
                "argument_label": a.label or "(unlabeled)",
            })

    # Assumptions
    assumptions = surface_assumptions(store, thesis_id)

    # Issues — scoped to subgraph
    coherence = check_coherence(store)
    blind_spots = find_blind_spots(store)
    # Filter to only issues mentioning nodes in our subgraph
    coherence = [c for c in coherence if any(nid[:12] in c.get("message", "") for nid in subgraph_nodes) or c.get("severity") == "high"]
    blind_spots = [b for b in blind_spots if any(nid[:12] in b.get("message", "") for nid in subgraph_nodes) or b.get("risk") == "high"]

    # Confidence assessment scoped to subgraph
    subgraph_arg_objs = [store.arguments[aid] for aid in subgraph_args]
    arg_confidences = [a.confidence.level for a in subgraph_arg_objs]
    claims_in_subgraph = [nid for nid in subgraph_nodes if nid in store.claims]
    claims_with_support = len(set(a.conclusion for a in subgraph_arg_objs))
    active_defeaters = sum(1 for d in all_defeaters if d["status"] == "active")

    assessment = {
        "thesis_confidence": thesis.confidence.level,
        "average_argument_strength": sum(arg_confidences) / len(arg_confidences) if arg_confidences else 0,
        "claims_supported": f"{claims_with_support}/{len(claims_in_subgraph)}",
        "active_defeaters": active_defeaters,
        "atms_status": atms.get(thesis_id, "unknown"),
    }

    # Build markdown
    thesis_label = f"{thesis.subject} {thesis.predicate} {thesis.object}"
    md = []
    md.append(f"# {thesis.notes or thesis_label}")
    md.append("")
    md.append(f"**Thesis:** {thesis_label}")
    md.append(f"**Confidence:** {thesis.confidence.level:.0%} | **ATMS:** {atms.get(thesis_id, 'unknown')}")
    md.append("")

    if supporting:
        md.append("## Supporting Arguments")
        md.append("")
        for arg in supporting:
            md.append(f"### {arg['label']}")
            md.append(f"*Pattern: {arg['pattern']} | Confidence: {arg['confidence']:.0%}*")
            md.append("")
            for p in arg["premises"]:
                conf_str = f" ({p['confidence']:.0%})" if p["confidence"] is not None else ""
                md.append(f"- **{p['type'].title()}:** {p['label']}{conf_str}")
                if p["notes"]:
                    md.append(f"  - {p['notes']}")
            if arg["defeaters"]:
                md.append("")
                for d in arg["defeaters"]:
                    status_marker = "ACTIVE" if d["status"] == "active" else d["status"]
                    md.append(f"- **Objection [{status_marker}]:** {d['description']}")
                    if d["response"]:
                        md.append(f"  - *Response:* {d['response']}")
            md.append("")

    active = [d for d in all_defeaters if d["status"] == "active"]
    answered = [d for d in all_defeaters if d["status"] == "answered"]

    if all_defeaters:
        md.append("## Known Objections")
        md.append("")
        if active:
            md.append("### Unresolved")
            for d in active:
                md.append(f"- [{d['type']}] {d['description']} *(on: {d['argument_label']})*")
            md.append("")
        if answered:
            md.append("### Answered")
            for d in answered:
                md.append(f"- ~~{d['description']}~~ — {d['response'] or '(no response recorded)'}")
            md.append("")

    if assumptions:
        md.append("## Assumptions")
        md.append("")
        for a in assumptions:
            status = "supported" if a["supported"] else "**UNSUPPORTED**"
            md.append(f"- {a['label']} [{a['type']}] — {status}")
        md.append("")

    if coherence or blind_spots:
        md.append("## Unresolved Issues")
        md.append("")
        for iss in coherence:
            md.append(f"- **{iss['severity'].upper()}** ({iss['check']}): {iss['message']}")
        for sp in blind_spots:
            md.append(f"- **{sp['risk'].upper()} RISK:** {sp['message']}")
        md.append("")

    if active:
        md.append("## What Would Change My Mind")
        md.append("")
        for d in active:
            md.append(f"- If {d['description'].lower()}")
        md.append("")

    md.append("## Confidence Assessment")
    md.append("")
    md.append(f"- **Thesis confidence:** {assessment['thesis_confidence']:.0%}")
    md.append(f"- **Average argument strength:** {assessment['average_argument_strength']:.0%}")
    md.append(f"- **Claims with support:** {assessment['claims_supported']}")
    md.append(f"- **Active defeaters:** {assessment['active_defeaters']}")
    md.append(f"- **Overall status:** {assessment['atms_status']}")

    return {
        "thesis": {
            "label": thesis_label,
            "notes": thesis.notes,
            "confidence": thesis.confidence.level,
            "atms_status": atms.get(thesis_id, "unknown"),
        },
        "supporting_arguments": supporting,
        "objections": all_defeaters,
        "assumptions": assumptions,
        "unresolved_issues": {"coherence": coherence, "blind_spots": blind_spots},
        "confidence_assessment": assessment,
        "markdown": "\n".join(md),
    }


# ── Auto-generate argument graph ─────────────────────────────────────

GENERATE_PROMPT = """\
You are an epistemic analyst. Given a thesis statement, decompose it into a structured argument graph.

Return a JSON object with exactly this structure:
{
  "thesis": {
    "subject": "short-hyphenated-subject",
    "predicate": "short-hyphenated-verb",
    "object": "short-hyphenated-object",
    "confidence": 0.7,
    "modality": "empirical",
    "notes": "The full thesis statement in natural language"
  },
  "claims": [
    {
      "subject": "...",
      "predicate": "...",
      "object": "...",
      "confidence": 0.5-0.95,
      "modality": "empirical|analytic|normative",
      "notes": "Natural language explanation of this claim"
    }
  ],
  "evidence": [
    {
      "title": "Short title",
      "description": "Detailed description of the evidence",
      "evidence_type": "observation|experiment|testimony|document|statistical",
      "source": "Citation or source if known",
      "reliability": 0.5-0.95
    }
  ],
  "arguments": [
    {
      "conclusion_ref": "thesis|claim_0|claim_1|...",
      "premise_refs": ["claim_0", "evidence_0", ...],
      "pattern": "abduction|induction|modus_ponens|analogy|causal|testimony",
      "label": "Short description of this argument",
      "confidence": 0.5-0.9
    }
  ],
  "assumptions": [
    {
      "subject": "...",
      "predicate": "...",
      "object": "...",
      "notes": "Why this is assumed and what it would mean if wrong"
    }
  ],
  "defeaters": [
    {
      "argument_ref": "argument_0|argument_1|...",
      "type": "rebutting|undercutting|undermining",
      "description": "What challenges this argument"
    }
  ]
}

Rules:
- Generate 3-5 supporting claims that decompose the thesis
- Generate 2-4 pieces of evidence (real or plausible) supporting the claims
- Generate arguments linking evidence and claims to the thesis
- Surface 2-3 unstated assumptions the thesis depends on
- Generate 1-2 defeaters (genuine challenges, not strawmen)
- Use realistic confidence levels (not all high)
- The "modality" field should be "empirical" for factual claims, "analytic" for logical/definitional claims, "normative" for value claims
- Reference format: "thesis" for the thesis, "claim_0" for first claim, "evidence_0" for first evidence, "argument_0" for first argument
- Be intellectually honest - include real weaknesses

Return ONLY the JSON object, no other text.
"""


@app.post("/api/generate")
async def generate_graph(body: GenerateRequest):
    """Use Claude to auto-generate an argument graph from a thesis."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": f"{GENERATE_PROMPT}\n\nThesis: {body.thesis}",
            }],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fence if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
        data = json_mod.loads(raw)
    except json_mod.JSONDecodeError as e:
        raise HTTPException(500, f"Failed to parse LLM response: {e}")
    except Exception as e:
        raise HTTPException(500, f"LLM call failed: {e}")

    # Build objects from the generated structure
    created_ids = {}  # ref_name -> actual ID

    # 1. Create thesis
    t = data["thesis"]
    thesis = store.add_claim(Claim(
        subject=t["subject"], predicate=t["predicate"], object=t["object"],
        confidence=Confidence(t.get("confidence", 0.7)),
        modality=Modality(t.get("modality", "empirical")),
        notes=t.get("notes", body.thesis),
    ))
    created_ids["thesis"] = thesis.id

    # 2. Create claims
    for i, c in enumerate(data.get("claims", [])):
        claim = store.add_claim(Claim(
            subject=c["subject"], predicate=c["predicate"], object=c["object"],
            confidence=Confidence(c.get("confidence", 0.7)),
            modality=Modality(c.get("modality", "empirical")),
            notes=c.get("notes", ""),
        ))
        created_ids[f"claim_{i}"] = claim.id

    # 3. Create evidence
    for i, e in enumerate(data.get("evidence", [])):
        ev = store.add_evidence(Evidence(
            title=e["title"], description=e["description"],
            evidence_type=EvidenceType(e.get("evidence_type", "observation")),
            source=e.get("source", ""),
            reliability=e.get("reliability", 0.7),
        ))
        created_ids[f"evidence_{i}"] = ev.id

    # 4. Create arguments
    for i, a in enumerate(data.get("arguments", [])):
        conc_ref = a.get("conclusion_ref", "thesis")
        conc_id = created_ids.get(conc_ref)
        if not conc_id:
            continue
        premise_ids = [created_ids[ref] for ref in a.get("premise_refs", []) if ref in created_ids]
        if not premise_ids:
            continue
        arg = store.add_argument(Argument(
            conclusion=conc_id, premises=premise_ids,
            pattern=InferencePattern(a.get("pattern", "abduction")),
            label=a.get("label", ""),
            confidence=Confidence(a.get("confidence", 0.7)),
        ))
        created_ids[f"argument_{i}"] = arg.id

    # 5. Create assumptions as claims linked via assumes
    assumption_ids = []
    for a in data.get("assumptions", []):
        ac = store.add_claim(Claim(
            subject=a.get("subject", "assumption"),
            predicate=a.get("predicate", "is-assumed"),
            object=a.get("object", "true"),
            confidence=Confidence(0.5),
            modality=Modality("empirical"),
            notes=a.get("notes", ""),
        ))
        assumption_ids.append(ac.id)
    if assumption_ids:
        thesis.assumes = assumption_ids
        store.save()

    # 6. Add defeaters
    for d in data.get("defeaters", []):
        arg_ref = d.get("argument_ref", "argument_0")
        arg_id = created_ids.get(arg_ref)
        if arg_id and arg_id in store.arguments:
            store.arguments[arg_id].defeaters.append(Defeater(
                type=DefeaterType(d.get("type", "undercutting")),
                description=d["description"],
                status=DefeaterStatus.ACTIVE,
            ))
    store.save()

    return {
        "ok": True,
        "created": {
            "claims": sum(1 for k in created_ids if k.startswith("claim_")) + 1,
            "evidence": sum(1 for k in created_ids if k.startswith("evidence_")),
            "arguments": sum(1 for k in created_ids if k.startswith("argument_")),
            "assumptions": len(assumption_ids),
            "defeaters": len(data.get("defeaters", [])),
        },
        "thesis_id": thesis.id,
    }
