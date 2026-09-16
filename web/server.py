"""
FastAPI server wrapping the epistemic engine.
Multi-workspace, agent-SDK-backed (subscription billing), with full
fork/merge and manual intervention support. Mirrors the MCP server.
"""
import json as json_mod
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
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
    propagate_confidence,
)
from epist import graph_io, provenance, ingest
from epist.provenance import provenance_kind
# Sync utilities (no LLM calls)
from epist.llm import (
    compute_summary,
    count_subgraph,
    list_theses as _list_theses_impl,
    get_thesis_versions as _get_thesis_versions_impl,
    write_thesis_md,
)
# Async LLM (uses Agent SDK + Claude Code subscription, not API key)
from epist.agent import (
    generate_full_graph_async,
    enhance_thesis_async,
    synthesize_thesis_async,
)
from epist.compare import (
    compute_graph_diff,
    compute_analysis_delta,
    format_diff_markdown,
)


app = FastAPI(title="Epistemic Workbench API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Workspace resolution ─────────────────────────────────────────────

WORKSPACES_DIR = Path(os.environ.get(
    "EPIST_WORKSPACES",
    Path.home() / "workspace" / "epistemic" / "workspaces",
))


def _resolve_workspace(name: str) -> Path:
    p = Path(name)
    return p if p.is_absolute() else WORKSPACES_DIR / name


def get_store(name: str) -> Store:
    """FastAPI dependency: resolve workspace name to a fresh Store.
    Raises 404 if the workspace directory does not exist."""
    path = _resolve_workspace(name)
    if not path.exists():
        raise HTTPException(404, f"Workspace '{name}' not found")
    return Store(path)


def get_or_create_store(name: str) -> Store:
    """Like get_store, but creates the workspace directory if missing.
    Used by endpoints that need to initialize a workspace (e.g. generate)."""
    path = _resolve_workspace(name)
    path.mkdir(parents=True, exist_ok=True)
    return Store(path)


def _git_commit_manual(s: Store, message: str):
    if s.is_git_repo():
        s.git_commit(f"[manual] {message}")


import re as _re
_BRANCH_NAME_RE = _re.compile(r"^[a-z0-9][a-z0-9._/-]*$")


def _validate_branch_name(name: str) -> bool:
    if not name or len(name) > 64:
        return False
    if ".." in name or name.startswith("/") or name.endswith("/"):
        return False
    return bool(_BRANCH_NAME_RE.match(name))


def _autosave_if_dirty(s: Store, label: str = "auto-save"):
    if s.is_git_repo() and s.git_has_changes():
        s.git_commit(f"[manual] {label}")


# ── Pydantic request models ─────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str

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
    status: str  # active, answered, conceded, withdrawn
    response: Optional[str] = None

class GenerateRequest(BaseModel):
    thesis: str

class EnhanceRequest(BaseModel):
    thesis_id: str

class AcceptEnhancedRequest(BaseModel):
    thesis_id: str
    enhanced_thesis: str
    rationale: str = ""
    changes: list = []

class BayesianRequest(BaseModel):
    prior: float
    likelihood_true: float
    likelihood_false: float

class RespondRequest(BaseModel):
    argument_id: str
    response: str
    defeater_index: int = -1

class ConcedeRequest(BaseModel):
    argument_id: str
    note: str
    defeater_index: int = -1

class AddEvidenceRequest(BaseModel):
    claim_id: str
    title: str
    description: str
    source: str = ""
    evidence_type: str = "observation"
    reliability: float = 0.7
    pattern: str = "induction"

class ChallengeRequest(BaseModel):
    claim_id: str
    description: str
    defeater_type: str = "undercutting"

class SetConfidenceRequest(BaseModel):
    claim_id: str
    confidence: float
    note: str = ""

class ForkRequest(BaseModel):
    fork_name: str

class SwitchRequest(BaseModel):
    fork_name: str

class MergeRequest(BaseModel):
    source_branch: str
    mode: str = "synthesize"  # pick | synthesize

# ── F1–F5 request models ──

class QuickClaimRequest(BaseModel):
    text: str
    node_type: str = "claim"        # claim | thesis | objection | concession
    confidence: float = 0.7
    status: Optional[str] = None    # live/defeated/superseded/conceded/rebutted/open
    modality: str = "empirical"

class AuthoredArgumentRequest(BaseModel):
    conclusion_id: str
    premise_ids: list[str]
    pattern: str = "modus_ponens"
    label: str = ""
    confidence: float = 0.7
    support_mode: str = "conjunctive"

class LinkRequest(BaseModel):
    from_id: str
    to_id: str
    relation: str

class SupportModeRequest(BaseModel):
    argument_id: str
    mode: str

class SupersedeRequest(BaseModel):
    old_claim_id: str
    new_claim_id: str
    reason: str = ""

class ImportRequest(BaseModel):
    graph: dict
    mode: str = "merge"

class AttachSourceRequest(BaseModel):
    node_id: str
    source_id: Optional[int] = None
    url: str = ""
    quote: str = ""
    source_type: str = "document"

class IngestRequest(BaseModel):
    source_text: str = ""
    url: str = ""
    title: str = ""

class CommitProposalRequest(BaseModel):
    accepted_node_ids: list[str]


# ── Workspaces (top-level listing/create) ────────────────────────────

@app.get("/api/workspaces")
def list_workspaces():
    """List all workspaces with thesis text and object counts."""
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for d in sorted(WORKSPACES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        try:
            s = Store(d)
            thesis_text = ""
            for c in s.claims.values():
                if c.is_root:
                    thesis_text = c.notes or f"{c.subject} {c.predicate} {c.object}"
                    break
            results.append({
                "name": d.name,
                "thesis_text": thesis_text,
                "is_git": s.is_git_repo(),
                "branch": s.git_current_branch() if s.is_git_repo() else "",
                "claims": len(s.claims),
                "evidence": len(s.evidence),
                "arguments": len(s.arguments),
            })
        except Exception as e:
            results.append({
                "name": d.name,
                "thesis_text": "(error loading)",
                "error": str(e),
                "is_git": False,
                "branch": "",
                "claims": 0,
                "evidence": 0,
                "arguments": 0,
            })
    return results


@app.post("/api/workspaces")
def create_workspace(body: WorkspaceCreate):
    """Create an empty git-backed workspace. Use generate to populate it."""
    if not _validate_branch_name(body.name):
        raise HTTPException(400, f"Invalid workspace name: {body.name}")
    path = _resolve_workspace(body.name)
    if path.exists():
        raise HTTPException(409, f"Workspace '{body.name}' already exists")
    path.mkdir(parents=True, exist_ok=True)
    s = Store(path)
    s.init_workspace()
    s.git_init()
    return {"ok": True, "name": body.name, "home": str(path)}


@app.get("/api/workspaces/{name}")
def workspace_info(name: str, s: Store = Depends(get_store)):
    """Get workspace metadata: branch, stats, current thesis."""
    thesis_text = ""
    thesis_id = ""
    for cid, c in s.claims.items():
        if c.is_root:
            thesis_text = c.notes or f"{c.subject} {c.predicate} {c.object}"
            thesis_id = cid
            break
    return {
        "name": name,
        "home": str(s.home),
        "is_git": s.is_git_repo(),
        "branch": s.git_current_branch() if s.is_git_repo() else "",
        "thesis_text": thesis_text,
        "thesis_id": thesis_id,
        "stats": {
            "claims": len(s.claims),
            "evidence": len(s.evidence),
            "arguments": len(s.arguments),
            "evaluations": len(s.evaluations),
            "predictions": len(s.predictions),
        },
    }


# ── Claims CRUD ──────────────────────────────────────────────────────

@app.get("/api/workspaces/{name}/claims")
def list_claims(name: str, s: Store = Depends(get_store)):
    return [_serialize(c) for c in s.claims.values()]


@app.post("/api/workspaces/{name}/claims")
def create_claim(name: str, body: ClaimCreate, s: Store = Depends(get_store)):
    c = Claim(
        subject=body.subject, predicate=body.predicate, object=body.object,
        confidence=Confidence(body.confidence),
        modality=Modality(body.modality),
        notes=body.notes,
        is_root=body.is_root,
    )
    s.add_claim(c)
    _git_commit_manual(s, f"Create claim: {c.subject} {c.predicate} {c.object}"[:80])
    return _serialize(c)


@app.get("/api/workspaces/{name}/claims/{eo_id}")
def get_claim(name: str, eo_id: str, s: Store = Depends(get_store)):
    c = s.claims.get(eo_id)
    if not c:
        raise HTTPException(404, "Claim not found")
    return _serialize(c)


@app.put("/api/workspaces/{name}/claims/{eo_id}")
def update_claim(name: str, eo_id: str, body: ClaimUpdate, s: Store = Depends(get_store)):
    c = s.claims.get(eo_id)
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
    s.save()
    _git_commit_manual(s, f"Update claim: {c.subject} {c.predicate} {c.object}"[:80])
    return _serialize(c)


@app.delete("/api/workspaces/{name}/claims/{eo_id}")
def delete_claim(name: str, eo_id: str, s: Store = Depends(get_store)):
    if eo_id not in s.claims:
        raise HTTPException(404, "Claim not found")
    label = f"{s.claims[eo_id].subject} {s.claims[eo_id].predicate} {s.claims[eo_id].object}"
    del s.claims[eo_id]
    to_remove = [
        aid for aid, a in s.arguments.items()
        if a.conclusion == eo_id or eo_id in a.premises
    ]
    for aid in to_remove:
        del s.arguments[aid]
    s.save()
    _git_commit_manual(s, f"Delete claim: {label}"[:80])
    return {"ok": True, "cascaded_arguments": len(to_remove)}


# ── Evidence CRUD ────────────────────────────────────────────────────

@app.get("/api/workspaces/{name}/evidence")
def list_evidence(name: str, s: Store = Depends(get_store)):
    return [_serialize(e) for e in s.evidence.values()]


@app.post("/api/workspaces/{name}/evidence")
def create_evidence(name: str, body: EvidenceCreate, s: Store = Depends(get_store)):
    e = Evidence(
        title=body.title, description=body.description,
        evidence_type=EvidenceType(body.evidence_type),
        source=body.source, reliability=body.reliability,
        notes=body.notes,
    )
    s.add_evidence(e)
    _git_commit_manual(s, f"Create evidence: {e.title}"[:80])
    return _serialize(e)


@app.delete("/api/workspaces/{name}/evidence/{eo_id}")
def delete_evidence(name: str, eo_id: str, s: Store = Depends(get_store)):
    if eo_id not in s.evidence:
        raise HTTPException(404, "Evidence not found")
    title = s.evidence[eo_id].title
    del s.evidence[eo_id]
    to_remove = [
        aid for aid, a in s.arguments.items()
        if eo_id in a.premises
    ]
    for aid in to_remove:
        del s.arguments[aid]
    s.save()
    _git_commit_manual(s, f"Delete evidence: {title}"[:80])
    return {"ok": True, "cascaded_arguments": len(to_remove)}


# ── Arguments CRUD ───────────────────────────────────────────────────

@app.get("/api/workspaces/{name}/arguments")
def list_arguments(name: str, s: Store = Depends(get_store)):
    return [_serialize(a) for a in s.arguments.values()]


@app.post("/api/workspaces/{name}/arguments")
def create_argument(name: str, body: ArgumentCreate, s: Store = Depends(get_store)):
    conc = s.get(body.conclusion)
    if not conc:
        raise HTTPException(400, f"Conclusion not found: {body.conclusion}")
    for pid in body.premises:
        if not s.get(pid):
            raise HTTPException(400, f"Premise not found: {pid}")
    a = Argument(
        conclusion=conc.id, premises=body.premises,
        pattern=InferencePattern(body.pattern),
        label=body.label, confidence=Confidence(body.confidence),
    )
    s.add_argument(a)
    _git_commit_manual(s, f"Create argument: {a.label or a.id[:12]}"[:80])
    return _serialize(a)


@app.delete("/api/workspaces/{name}/arguments/{eo_id}")
def delete_argument(name: str, eo_id: str, s: Store = Depends(get_store)):
    if eo_id not in s.arguments:
        raise HTTPException(404, "Argument not found")
    label = s.arguments[eo_id].label or eo_id[:12]
    del s.arguments[eo_id]
    s.save()
    _git_commit_manual(s, f"Delete argument: {label}"[:80])
    return {"ok": True}


@app.get("/api/workspaces/{name}/arguments/for-node/{eo_id}")
def arguments_for_node(name: str, eo_id: str, s: Store = Depends(get_store)):
    """Return all arguments where this node is the conclusion or a premise."""
    results = []
    for aid, a in s.arguments.items():
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

@app.get("/api/workspaces/{name}/arguments/{eo_id}/defeaters")
def list_defeaters(name: str, eo_id: str, s: Store = Depends(get_store)):
    arg = s.arguments.get(eo_id)
    if not arg:
        raise HTTPException(404, "Argument not found")
    return [
        {"index": i, "type": d.type.value, "description": d.description,
         "status": d.status.value, "response": d.response}
        for i, d in enumerate(arg.defeaters)
    ]


@app.post("/api/workspaces/{name}/arguments/{eo_id}/defeaters")
def add_defeater(name: str, eo_id: str, body: DefeaterCreate, s: Store = Depends(get_store)):
    arg = s.arguments.get(eo_id)
    if not arg:
        raise HTTPException(404, "Argument not found")
    d = Defeater(
        type=DefeaterType(body.type),
        description=body.description,
        status=DefeaterStatus.ACTIVE,
    )
    arg.defeaters.append(d)
    s.save()
    _git_commit_manual(s, f"Add defeater: {d.description[:60]}")
    return {"ok": True, "index": len(arg.defeaters) - 1}


@app.put("/api/workspaces/{name}/arguments/{eo_id}/defeaters/{idx}")
def update_defeater(name: str, eo_id: str, idx: int, body: DefeaterUpdate, s: Store = Depends(get_store)):
    arg = s.arguments.get(eo_id)
    if not arg:
        raise HTTPException(404, "Argument not found")
    if idx < 0 or idx >= len(arg.defeaters):
        raise HTTPException(404, "Defeater not found")
    arg.defeaters[idx].status = DefeaterStatus(body.status)
    if body.response is not None:
        arg.defeaters[idx].response = body.response
    s.save()
    _git_commit_manual(s, f"Update defeater {idx} on {eo_id[:12]}: {body.status}")
    return {"ok": True}


# ── Graph endpoint ───────────────────────────────────────────────────

@app.get("/api/workspaces/{name}/graph")
def get_graph(name: str, s: Store = Depends(get_store)):
    atms = compute_atms(s)
    try:
        derived = propagate_confidence(s, atms)
    except Exception:
        derived = {}
    nodes = []
    edges = []

    for cid, c in s.claims.items():
        label = f"{c.subject} {c.predicate} {c.object}".strip()
        nodes.append({
            "id": cid,
            "type": "claim",
            "node_type": getattr(c, "node_type", "claim") or "claim",
            "label": label or (c.notes or "")[:60],
            "confidence": c.confidence.level,
            "derived": derived.get(cid),
            "modality": c.modality.value,
            "atms": atms.get(cid, "unknown"),
            "status": getattr(c, "status", None),
            "killed_by": getattr(c, "killed_by", None),
            "notes": c.notes,
            "is_root": c.is_root,
        })

    for eid, e in s.evidence.items():
        nodes.append({
            "id": eid,
            "type": "evidence",
            "node_type": "evidence",
            "label": e.title,
            "confidence": e.reliability,
            "derived": derived.get(eid),
            "atms": atms.get(eid, "unknown"),
            "notes": e.description,
            "source": e.source,
            "provenance": provenance_kind(e),
            "provenance_detail": getattr(e, "provenance", None),
        })

    node_index = {n["id"]: n for n in nodes}

    for aid, a in s.arguments.items():
        for pid in a.premises:
            if pid in node_index and a.conclusion in node_index:
                edges.append({
                    "source": pid,
                    "target": a.conclusion,
                    "type": "supports",
                    "argument_id": aid,
                    "label": a.label,
                    "pattern": a.pattern.value,
                    "confidence": a.confidence.level,
                    "support_mode": getattr(a, "support_mode", "independent"),
                })
        # Attach full per-defeater records to the conclusion node
        for i, d in enumerate(a.defeaters):
            n = node_index.get(a.conclusion)
            if n is not None:
                n.setdefault("defeaters", []).append({
                    "argument_id": aid,
                    "argument_label": a.label,
                    "index": i,
                    "type": d.type.value,
                    "status": d.status.value,
                    "description": d.description,
                    "response": d.response,
                })

    for cid, c in s.claims.items():
        for assumed_id in c.assumes:
            if assumed_id in node_index:
                edges.append({
                    "source": cid,
                    "target": assumed_id,
                    "type": "assumes",
                })

    # F1 — generic typed edges (refutes / rebuts / concedes / grounds / narrows /
    # supersedes). 'supports' edges are already mirrored as arguments above, so
    # they are skipped here to avoid drawing the same relation twice.
    for eid, e in getattr(s, "edges", {}).items():
        rel = e.rel.value if hasattr(e.rel, "value") else str(e.rel)
        if rel == "supports":
            continue
        if e.from_id in node_index and e.to in node_index:
            edges.append({
                "source": e.from_id,
                "target": e.to,
                "type": rel,
                "edge_id": eid,
                "notes": getattr(e, "notes", ""),
            })

    return {"nodes": nodes, "edges": edges}


# ── Analysis endpoints ───────────────────────────────────────────────

@app.get("/api/workspaces/{name}/analysis/atms")
def get_atms(name: str, s: Store = Depends(get_store)):
    return compute_atms(s)


@app.get("/api/workspaces/{name}/analysis/coherence")
def get_coherence(name: str, s: Store = Depends(get_store)):
    return check_coherence(s)


@app.get("/api/workspaces/{name}/analysis/blind-spots")
def get_blind_spots(name: str, s: Store = Depends(get_store)):
    return find_blind_spots(s)


@app.get("/api/workspaces/{name}/analysis/assumptions/{eo_id}")
def get_assumptions(name: str, eo_id: str, s: Store = Depends(get_store)):
    obj = s.get(eo_id)
    if not obj:
        raise HTTPException(404, "Object not found")
    return surface_assumptions(s, obj.id)


@app.get("/api/workspaces/{name}/analysis/stress-test/{eo_id}")
def get_stress_test(name: str, eo_id: str, s: Store = Depends(get_store)):
    obj = s.get(eo_id)
    if not obj:
        raise HTTPException(404, "Object not found")
    result = stress_test(s, obj.id)
    if not result:
        raise HTTPException(404, "Could not generate stress test")
    return result


@app.post("/api/workspaces/{name}/analysis/bayesian-update")
def bayesian(name: str, body: BayesianRequest, s: Store = Depends(get_store)):
    posterior = bayesian_update(body.prior, body.likelihood_true, body.likelihood_false)
    return {
        "prior": body.prior,
        "posterior": posterior,
        "delta": posterior - body.prior,
    }


# ── Summary / theses ─────────────────────────────────────────────────

@app.get("/api/workspaces/{name}/summary/theses")
def list_theses(name: str, s: Store = Depends(get_store)):
    return _list_theses_impl(s)


@app.get("/api/workspaces/{name}/summary")
def get_summary(name: str, thesis_id: Optional[str] = None, s: Store = Depends(get_store)):
    return compute_summary(s, thesis_id)


@app.get("/api/workspaces/{name}/thesis-versions/{thesis_id}")
def get_thesis_versions(name: str, thesis_id: str, s: Store = Depends(get_store)):
    try:
        return _get_thesis_versions_impl(s, thesis_id)
    except RuntimeError as e:
        raise HTTPException(404, str(e))


# ── LLM endpoints (async, subscription-billed via agent.py) ──────────

@app.post("/api/workspaces/{name}/generate")
async def generate_graph(name: str, body: GenerateRequest):
    """Generate a full argument graph from a thesis. Auto-creates workspace + git repo."""
    s = get_or_create_store(name)
    s.clear()
    if not s.is_git_repo():
        s.git_init()

    try:
        thesis_id = await generate_full_graph_async(s, body.thesis)
    except Exception as e:
        raise HTTPException(500, f"LLM call failed: {e}")

    # Write summary.md
    try:
        result = compute_summary(s, thesis_id)
        (s.home / "summary.md").write_text(result["markdown"])
    except Exception:
        pass

    counts = count_subgraph(s, thesis_id)
    short_thesis = body.thesis[:72] + ("..." if len(body.thesis) > 72 else "")
    s.git_commit(
        f"[generate] {short_thesis}\n\n"
        f"Thesis: {body.thesis}\n"
        f"Objects: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments, {counts['assumptions']} assumptions, "
        f"{counts['defeaters']} defeaters"
    )

    return {
        "ok": True,
        "thesis_id": thesis_id,
        "created": counts,
    }


@app.post("/api/workspaces/{name}/enhance-thesis")
async def enhance_thesis_endpoint(name: str, body: EnhanceRequest):
    """Suggest an enhanced version of the thesis (does not modify workspace)."""
    s = get_store(name)
    try:
        return await enhance_thesis_async(s, body.thesis_id)
    except RuntimeError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"LLM call failed: {e}")


@app.post("/api/workspaces/{name}/accept-enhanced-thesis")
async def accept_enhanced_thesis_endpoint(name: str, body: AcceptEnhancedRequest):
    """Accept an enhanced thesis: clear workspace, regenerate from new thesis text,
    commit with [enhance] tag. The old version is preserved in git history."""
    s = get_store(name)
    if body.thesis_id not in s.claims:
        raise HTTPException(404, "Original thesis not found")

    # F4 — non-destructive revision: the prior thesis and its subgraph stay in
    # the graph marked superseded; only the root flag moves.
    s.claims[body.thesis_id].is_root = False
    s.save()
    try:
        new_thesis_id = await generate_full_graph_async(s, body.enhanced_thesis)
    except Exception as e:
        s.claims[body.thesis_id].is_root = True
        s.save()
        raise HTTPException(500, f"LLM call failed: {e}")
    graph_io.supersede(s, body.thesis_id, new_thesis_id, reason=body.rationale)

    try:
        new_summary = compute_summary(s, new_thesis_id)
        (s.home / "summary.md").write_text(new_summary["markdown"])
    except Exception:
        pass

    counts = count_subgraph(s, new_thesis_id)
    change_lines = ""
    for ch in body.changes:
        tag = ch.get("type", "change") if isinstance(ch, dict) else "change"
        desc = ch.get("description", str(ch)) if isinstance(ch, dict) else str(ch)
        change_lines += f"\n- [{tag}] {desc}"

    short_rationale = body.rationale[:72] + ("..." if len(body.rationale) > 72 else "")
    s.git_commit(
        f"[enhance] {short_rationale}\n\n"
        f"Thesis: {body.enhanced_thesis}\n\n"
        f"Rationale: {body.rationale}\n"
        f"Changes:{change_lines}\n\n"
        f"Objects: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments"
    )

    return {"ok": True, "new_thesis_id": new_thesis_id, "created": counts}


# ── Manual intervention ──────────────────────────────────────────────

@app.post("/api/workspaces/{name}/respond-to-defeater")
def respond_to_defeater(name: str, body: RespondRequest, s: Store = Depends(get_store)):
    """Rebut a defeater (mark as answered, no longer defeats the argument)."""
    obj = s.get(body.argument_id)
    if not obj or not hasattr(obj, "defeaters"):
        raise HTTPException(404, f"Argument not found: {body.argument_id}")

    if body.defeater_index >= 0:
        if body.defeater_index >= len(obj.defeaters):
            raise HTTPException(400, f"Defeater index out of range")
        d = obj.defeaters[body.defeater_index]
    else:
        d = next((d for d in obj.defeaters if d.status == DefeaterStatus.ACTIVE), None)
        if not d:
            raise HTTPException(400, "No active defeaters on this argument")

    d.status = DefeaterStatus.ANSWERED
    d.response = body.response
    s.save()
    _git_commit_manual(s, f"Respond to defeater: {d.description[:50]}")

    atms = compute_atms(s)
    thesis = next((c for c in s.claims.values() if c.is_root), None)
    return {
        "ok": True,
        "defeater_status": d.status.value,
        "thesis_status": atms.get(thesis.id) if thesis else "unknown",
    }


@app.post("/api/workspaces/{name}/concede-defeater")
def concede_defeater(name: str, body: ConcedeRequest, s: Store = Depends(get_store)):
    """Concede a defeater (accept as valid; argument remains defeated but acknowledged)."""
    obj = s.get(body.argument_id)
    if not obj or not hasattr(obj, "defeaters"):
        raise HTTPException(404, f"Argument not found: {body.argument_id}")

    if body.defeater_index >= 0:
        if body.defeater_index >= len(obj.defeaters):
            raise HTTPException(400, f"Defeater index out of range")
        d = obj.defeaters[body.defeater_index]
    else:
        d = next((d for d in obj.defeaters if d.status == DefeaterStatus.ACTIVE), None)
        if not d:
            raise HTTPException(400, "No active defeaters on this argument")

    d.status = DefeaterStatus.CONCEDED
    d.response = body.note
    s.save()
    _git_commit_manual(s, f"Concede defeater: {d.description[:50]}")

    atms = compute_atms(s)
    thesis = next((c for c in s.claims.values() if c.is_root), None)
    return {
        "ok": True,
        "defeater_status": d.status.value,
        "thesis_status": atms.get(thesis.id) if thesis else "unknown",
    }


@app.post("/api/workspaces/{name}/add-evidence-to-claim")
def add_evidence_to_claim(name: str, body: AddEvidenceRequest, s: Store = Depends(get_store)):
    """Create an evidence node and link it to a claim via a supporting argument."""
    target = s.get(body.claim_id)
    if not target:
        raise HTTPException(404, f"Claim not found: {body.claim_id}")

    e = Evidence(
        title=body.title,
        description=body.description,
        evidence_type=EvidenceType(body.evidence_type),
        source=body.source,
        reliability=body.reliability,
    )
    s.add_evidence(e)

    a = Argument(
        conclusion=target.id,
        premises=[e.id],
        pattern=InferencePattern(body.pattern),
        label=f"Evidence: {body.title}",
        confidence=Confidence(body.reliability),
    )
    s.add_argument(a)
    _git_commit_manual(s, f"Add evidence: {body.title}"[:80])

    atms = compute_atms(s)
    return {
        "ok": True,
        "evidence_id": e.id,
        "argument_id": a.id,
        "claim_status": atms.get(target.id, "unknown"),
    }


@app.post("/api/workspaces/{name}/challenge-claim")
def challenge_claim(name: str, body: ChallengeRequest, s: Store = Depends(get_store)):
    """Add a defeater to the strongest supporting argument for a claim."""
    target = s.get(body.claim_id)
    if not target:
        raise HTTPException(404, f"Claim not found: {body.claim_id}")

    supporting_args = [a for a in s.arguments.values() if a.conclusion == target.id]
    if not supporting_args:
        raise HTTPException(400, "No supporting arguments to challenge")

    arg = max(supporting_args, key=lambda a: a.confidence.level)
    arg.defeaters.append(Defeater(
        type=DefeaterType(body.defeater_type),
        description=body.description,
        status=DefeaterStatus.ACTIVE,
    ))
    s.save()
    _git_commit_manual(s, f"Challenge: {body.description[:50]}")

    atms = compute_atms(s)
    return {
        "ok": True,
        "argument_id": arg.id,
        "claim_status": atms.get(target.id, "unknown"),
    }


@app.post("/api/workspaces/{name}/set-confidence")
def set_confidence(name: str, body: SetConfidenceRequest, s: Store = Depends(get_store)):
    """Manually adjust confidence on a claim, optionally with a note."""
    target = s.get(body.claim_id)
    if not target or not hasattr(target, "confidence"):
        raise HTTPException(404, f"Claim not found: {body.claim_id}")

    old_val = target.confidence.level
    target.confidence = Confidence(body.confidence)
    if body.note:
        existing = target.notes or ""
        target.notes = (
            f"{existing}\n[{body.confidence:.0%}] {body.note}".strip()
            if existing else f"[{body.confidence:.0%}] {body.note}"
        )
    s.save()

    label = f"{target.subject} {target.predicate} {target.object}" if hasattr(target, "subject") else body.claim_id[:12]
    _git_commit_manual(s, f"Set confidence {old_val:.0%} -> {body.confidence:.0%}: {label[:40]}")
    return {"ok": True, "old_confidence": old_val, "new_confidence": body.confidence}


# ── Forks (branches, fork, switch, compare, merge) ───────────────────

@app.get("/api/workspaces/{name}/branches")
def list_branches(name: str, s: Store = Depends(get_store)):
    """List all branches in this workspace with thesis text and divergence info."""
    if not s.is_git_repo():
        return []

    branches = s.git_list_branches()
    if not branches:
        return []

    trunk = next((b["name"] for b in branches if b["name"] in ("master", "main")), None)
    results = []
    for b in branches:
        thesis_text = s._git_show_file(b["name"], "thesis.md").strip() or ""
        commits_ahead = 0
        if trunk and b["name"] != trunk:
            commits_ahead = s.git_commits_since(b["name"], trunk)
        results.append({
            "name": b["name"],
            "commit": b["commit"],
            "is_current": b["is_current"],
            "thesis_text": thesis_text,
            "commits_ahead": commits_ahead,
        })
    return results


@app.post("/api/workspaces/{name}/fork")
def fork_workspace(name: str, body: ForkRequest, s: Store = Depends(get_store)):
    if not s.is_git_repo():
        raise HTTPException(400, "Not a git-backed workspace")
    if not _validate_branch_name(body.fork_name):
        raise HTTPException(400, f"Invalid fork name: {body.fork_name}")
    if s.git_branch_exists(body.fork_name):
        raise HTTPException(409, f"Fork '{body.fork_name}' already exists")

    current = s.git_current_branch()
    _autosave_if_dirty(s, f"auto-save before fork to {body.fork_name}")
    s.git_create_branch(body.fork_name)
    s.git_commit(f"[fork] Created from {current}")
    return {"ok": True, "branch": body.fork_name, "from": current}


@app.post("/api/workspaces/{name}/switch")
def switch_branch(name: str, body: SwitchRequest, s: Store = Depends(get_store)):
    if not s.is_git_repo():
        raise HTTPException(400, "Not a git-backed workspace")
    if not s.git_branch_exists(body.fork_name):
        raise HTTPException(404, f"Fork '{body.fork_name}' does not exist")

    current = s.git_current_branch()
    if current == body.fork_name:
        return {"ok": True, "branch": current, "unchanged": True}

    _autosave_if_dirty(s, f"auto-save before switch to {body.fork_name}")
    try:
        s.git_switch_branch(body.fork_name)
    except RuntimeError as e:
        raise HTTPException(500, f"Switch failed: {e}")

    thesis = next((c for c in s.claims.values() if c.is_root), None)
    return {
        "ok": True,
        "branch": body.fork_name,
        "from": current,
        "thesis_text": thesis.notes if thesis else "",
        "stats": {
            "claims": len(s.claims),
            "evidence": len(s.evidence),
            "arguments": len(s.arguments),
        },
    }


@app.get("/api/workspaces/{name}/compare/{other}")
def compare_branches(name: str, other: str, s: Store = Depends(get_store)):
    """Structural diff between current branch and `other`. Returns markdown + raw delta."""
    if not s.is_git_repo():
        raise HTTPException(400, "Not a git-backed workspace")
    if not s.git_branch_exists(other):
        raise HTTPException(404, f"Fork '{other}' does not exist")

    current = s.git_current_branch()
    if current == other:
        raise HTTPException(400, f"Cannot compare '{other}' with itself")

    other_store = s.load_branch_store(other)
    diff = compute_graph_diff(s, other_store)
    delta = compute_analysis_delta(s, other_store)
    md = format_diff_markdown(diff, delta, current, other)
    return {
        "current": current,
        "other": other,
        "markdown": md,
        "delta": delta,
    }


@app.post("/api/workspaces/{name}/merge")
async def merge_branches(name: str, body: MergeRequest):
    """Merge another fork into the current one (pick or synthesize)."""
    s = get_store(name)
    if not s.is_git_repo():
        raise HTTPException(400, "Not a git-backed workspace")
    if not s.git_branch_exists(body.source_branch):
        raise HTTPException(404, f"Fork '{body.source_branch}' does not exist")

    current = s.git_current_branch()
    if current == body.source_branch:
        raise HTTPException(400, f"Cannot merge '{body.source_branch}' with itself")

    if body.mode == "pick":
        _autosave_if_dirty(s, f"auto-save before merge from {body.source_branch}")
        try:
            s.git_switch_branch(body.source_branch)
        except RuntimeError as e:
            raise HTTPException(500, f"Switch failed: {e}")
        return {
            "ok": True,
            "mode": "pick",
            "branch": body.source_branch,
            "markdown": f"# Merge complete\n\nAdopted fork **{body.source_branch}** wholesale.",
        }

    if body.mode != "synthesize":
        raise HTTPException(400, f"Unknown mode: {body.mode}")

    other_store = s.load_branch_store(body.source_branch)
    try:
        result = await synthesize_thesis_async(current, s, body.source_branch, other_store)
    except Exception as e:
        raise HTTPException(500, f"Synthesis failed: {e}")

    merge_branch = f"merge/{body.source_branch}-into-{current}"
    if not _validate_branch_name(merge_branch):
        merge_branch = f"merge-{current}-{body.source_branch}"
    if s.git_branch_exists(merge_branch):
        import time as _time
        merge_branch = f"{merge_branch}-{int(_time.time())}"

    _autosave_if_dirty(s, "auto-save before merge synthesis")
    s.git_create_branch(merge_branch)
    s.clear()

    try:
        new_thesis_id = await generate_full_graph_async(s, result["synthesized_thesis"])
    except Exception as e:
        raise HTTPException(500, f"Graph generation failed: {e}")

    try:
        new_summary = compute_summary(s, new_thesis_id)
        (s.home / "summary.md").write_text(new_summary["markdown"])
    except Exception:
        pass

    counts = count_subgraph(s, new_thesis_id)
    incorp_lines = ""
    for x in result.get("incorporated_from_a", []):
        incorp_lines += f"\n- [from {current}] {x}"
    for x in result.get("incorporated_from_b", []):
        incorp_lines += f"\n- [from {body.source_branch}] {x}"
    for x in result.get("resolved_tensions", []):
        incorp_lines += f"\n- [resolved] {x}"

    short_rationale = result["rationale"][:72] + ("..." if len(result["rationale"]) > 72 else "")
    s.git_commit(
        f"[merge] {short_rationale}\n\n"
        f"Synthesized from: {current} + {body.source_branch}\n"
        f"Thesis: {result['synthesized_thesis']}\n\n"
        f"Rationale: {result['rationale']}\n"
        f"Incorporations:{incorp_lines}\n\n"
        f"Objects: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments"
    )

    from_a = "\n".join(f"- {x}" for x in result.get("incorporated_from_a", []))
    from_b = "\n".join(f"- {x}" for x in result.get("incorporated_from_b", []))
    tensions = "\n".join(f"- {x}" for x in result.get("resolved_tensions", []))

    md = (
        f"# Merge complete\n\n"
        f"**New branch:** `{merge_branch}`\n\n"
        f"## Synthesized thesis\n\n{result['synthesized_thesis']}\n\n"
        f"## Rationale\n\n{result['rationale']}\n\n"
        f"## Incorporated from {current}\n\n{from_a or '_(none)_'}\n\n"
        f"## Incorporated from {body.source_branch}\n\n{from_b or '_(none)_'}\n\n"
        f"## Resolved tensions\n\n{tensions or '_(none)_'}\n\n"
        f"## New graph\n\n"
        f"Created: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments"
    )

    return {
        "ok": True,
        "mode": "synthesize",
        "branch": merge_branch,
        "thesis_id": new_thesis_id,
        "markdown": md,
        "synthesis": result,
    }


# ── Git history ──────────────────────────────────────────────────────

@app.get("/api/workspaces/{name}/git-log")
def git_log(name: str, max_count: int = 50, s: Store = Depends(get_store)):
    """Return commit history for the current branch."""
    return s.git_log(max_count=max_count)


# ── F1: direct authoring + import/export ─────────────────────────────

@app.post("/api/workspaces/{name}/add-claim")
def add_claim_route(name: str, body: QuickClaimRequest, s: Store = Depends(get_store)):
    if not s.is_git_repo():
        s.git_init()
    try:
        c = graph_io.add_claim(s, body.text, node_type=body.node_type,
                               confidence=body.confidence,
                               status=(body.status or None), modality=body.modality)
    except ValueError as e:
        raise HTTPException(400, str(e))
    s.git_commit(f"[manual] Add {body.node_type}: {body.text[:50]}")
    return {"ok": True, "id": c.id, "node_type": body.node_type}


@app.post("/api/workspaces/{name}/add-argument")
def add_argument_route(name: str, body: AuthoredArgumentRequest, s: Store = Depends(get_store)):
    if not s.is_git_repo():
        s.git_init()
    try:
        a = graph_io.add_argument(s, body.conclusion_id, body.premise_ids,
                                  pattern=body.pattern, label=body.label,
                                  confidence=body.confidence,
                                  support_mode=body.support_mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    s.git_commit(f"[manual] Add argument: {body.label or a.id[:12]}")
    return {"ok": True, "id": a.id}


@app.post("/api/workspaces/{name}/link")
def link_route(name: str, body: LinkRequest, s: Store = Depends(get_store)):
    if not s.is_git_repo():
        s.git_init()
    try:
        e = graph_io.link(s, body.from_id, body.to_id, body.relation)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    s.git_commit(f"[manual] Link {body.relation}: {e.from_id[:8]}→{e.to[:8]}")
    return {"ok": True, "id": e.id, "from_id": e.from_id, "to": e.to, "relation": body.relation}


@app.post("/api/workspaces/{name}/set-support-mode")
def set_support_mode_route(name: str, body: SupportModeRequest, s: Store = Depends(get_store)):
    try:
        a = graph_io.set_support_mode(s, body.argument_id, body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _git_commit_manual(s, f"Set support_mode={body.mode} on {body.argument_id[:12]}")
    derived = propagate_confidence(s)
    return {"ok": True, "argument_id": a.id, "mode": body.mode,
            "conclusion_derived": derived.get(a.conclusion)}


@app.post("/api/workspaces/{name}/supersede")
def supersede_route(name: str, body: SupersedeRequest, s: Store = Depends(get_store)):
    try:
        r = graph_io.supersede(s, body.old_claim_id, body.new_claim_id, reason=body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _git_commit_manual(s, f"Supersede {r['old'][:8]} with {r['new'][:8]}")
    return {"ok": True, **r}


@app.get("/api/workspaces/{name}/export")
def export_route(name: str, s: Store = Depends(get_store)):
    return graph_io.export_graph(s)


@app.post("/api/workspaces/{name}/import")
def import_route(name: str, body: ImportRequest):
    s = get_or_create_store(name)
    if not s.is_git_repo():
        s.git_init()
    try:
        summary = graph_io.import_graph(s, body.graph, mode=body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    s.git_commit(f"[manual] Import graph ({summary.get('mode')}, mode={body.mode})")
    return {"ok": True, **summary}


@app.get("/api/workspaces/{name}/analysis/propagation")
def propagation_route(name: str, s: Store = Depends(get_store)):
    """F3 — derived (propagated) confidence for every object. Never persisted."""
    return propagate_confidence(s)


# ── F2: provenance ───────────────────────────────────────────────────

@app.get("/api/workspaces/{name}/unsourced")
def unsourced_route(name: str, s: Store = Depends(get_store)):
    return {"rows": provenance.list_unsourced(s), "counts": provenance.provenance_counts(s)}


@app.post("/api/workspaces/{name}/attach-source")
def attach_source_route(name: str, body: AttachSourceRequest, s: Store = Depends(get_store)):
    result = provenance.attach_source(
        s, body.node_id,
        source_id=(body.source_id or None),
        url=(body.url or None),
        quote=(body.quote or None),
        source_type=body.source_type,
    )
    if result.get("ok"):
        _git_commit_manual(s, f"Attach source to evidence {body.node_id[:12]}")
        return {"ok": True, **result}
    # Recorded provenance is never faked: report why it stayed asserted.
    return {"ok": False, "reason": result.get("reason", "unknown error")}


# ── F5: corpus ingestion (propose-then-curate) ───────────────────────

import threading, time, uuid

_jobs: dict = {}  # job_id -> {status, workspace, started, finished, result, error}


def _run_job(job_id: str, fn, *args):
    def _target():
        try:
            _jobs[job_id]["result"] = fn(*args)
            _jobs[job_id]["status"] = "completed"
        except Exception as e:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)
        finally:
            _jobs[job_id]["finished"] = time.time()
    threading.Thread(target=_target, daemon=True).start()


def _do_ingest(name: str, source_text: str, url: str, title: str) -> dict:
    s = get_or_create_store(name)
    if not s.is_git_repo():
        s.git_init()
    source_ref = {"url": url} if url else None
    result = ingest.ingest_document(
        s, source_text=source_text or None, source_ref=source_ref,
        extractor=ingest.llm_extractor, title=(title or None),
    )
    s.git_commit(f"[ingest] proposal {result['proposal_id']} from source")
    return result


@app.post("/api/workspaces/{name}/ingest")
def ingest_route(name: str, body: IngestRequest):
    if not (body.source_text or body.url):
        raise HTTPException(400, "provide source_text (and optionally url/title)")
    job_id = f"ing-{uuid.uuid4().hex[:8]}"
    _jobs[job_id] = {"status": "running", "workspace": name,
                     "started": time.time(), "finished": None,
                     "result": None, "error": None}
    _run_job(job_id, _do_ingest, name, body.source_text, body.url, body.title)
    return {"ok": True, "job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status_route(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    return {"job_id": job_id, **job}


@app.get("/api/workspaces/{name}/proposals")
def list_proposals_route(name: str, s: Store = Depends(get_store)):
    return ingest.list_proposals(s)


@app.get("/api/workspaces/{name}/proposals/{proposal_id}")
def review_proposal_route(name: str, proposal_id: str, s: Store = Depends(get_store)):
    try:
        return ingest.review_proposal(s, proposal_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/workspaces/{name}/proposals/{proposal_id}/commit")
def commit_proposal_route(name: str, proposal_id: str, body: CommitProposalRequest,
                          s: Store = Depends(get_store)):
    try:
        result = ingest.commit_proposal(s, proposal_id, body.accepted_node_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if s.is_git_repo():
        s.git_commit(f"[ingest] commit {len(body.accepted_node_ids)} nodes from {proposal_id}")
    return {"ok": True, **result}


# ── Static frontend ──────────────────────────────────────────────────

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/")
    def root_index():
        return FileResponse(str(_FRONTEND_DIST / "index.html"))

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Anything not under /api or /assets serves the SPA
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            raise HTTPException(404)
        index = _FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(404)
