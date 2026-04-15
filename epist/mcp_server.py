"""
MCP server for the Epistemic Workbench.
Exposes thesis generation, analysis, and enhancement as tools for Claude Desktop.

Logging: all output goes to stderr (stdout is the JSON-RPC channel).
Log file: ~/EPISTEMIC_TOOLS/workspaces/.mcp-server.log (if writable).
"""
import json
import logging
import os
import sys
import time
import traceback
from functools import wraps
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Ensure epist package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from epist.store import Store
from epist.model import DefeaterStatus
from epist.agent import (
    generate_full_graph_async,
    enhance_thesis_async,
    synthesize_thesis_async,
    compute_summary,
    count_subgraph,
    list_theses,
    get_thesis_versions,
    write_thesis_md,
)

# ── Logging ──────────────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("epist.mcp")
logger.setLevel(logging.DEBUG)

# Always log to stderr (safe for stdio MCP servers)
_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE))
_stderr_handler.setLevel(logging.INFO)
logger.addHandler(_stderr_handler)

# Also log to a file if the workspaces dir is writable
_log_dir = Path(os.environ.get(
    "EPIST_WORKSPACES",
    Path.home() / "EPISTEMIC_TOOLS" / "workspaces",
))
try:
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = _log_dir / ".mcp-server.log"
    _file_handler = logging.FileHandler(str(_log_file))
    _file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE))
    _file_handler.setLevel(logging.DEBUG)
    logger.addHandler(_file_handler)
except Exception:
    pass  # can't write log file — stderr only

# Track in-flight operations for diagnostics
_active_calls = {}


def _log_tool(fn):
    """Decorator that logs tool calls with timing and error tracking."""
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        call_id = f"{fn.__name__}-{int(time.time() * 1000) % 100000}"
        # Build a short summary of the args for logging
        arg_summary = ""
        if args:
            arg_summary = str(args[0])[:60]
        if kwargs:
            kw_parts = [f"{k}={str(v)[:30]}" for k, v in list(kwargs.items())[:3]]
            arg_summary += " " + " ".join(kw_parts) if arg_summary else " ".join(kw_parts)

        _active_calls[call_id] = {
            "tool": fn.__name__,
            "started": time.time(),
            "args": arg_summary,
        }

        logger.info(f"CALL {call_id} {fn.__name__}({arg_summary})")
        start = time.time()
        try:
            result = await fn(*args, **kwargs)
            elapsed = time.time() - start
            result_len = len(str(result)) if result else 0
            logger.info(f"  OK {call_id} {fn.__name__} {elapsed:.1f}s ({result_len} chars)")
            return result
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"  ERR {call_id} {fn.__name__} {elapsed:.1f}s: {e}")
            logger.debug(traceback.format_exc())
            raise
        finally:
            _active_calls.pop(call_id, None)

    return wrapper

logger.info(f"MCP server starting, PID={os.getpid()}")


# ── Background job queue ─────────────────────────────────────────────
# Long-running LLM calls (generate, enhance, synthesize) exceed Claude
# Desktop's hardcoded 60s MCP timeout. Instead of blocking, we run them
# in a background thread and return a job ID immediately. The caller
# polls job_status to get the result.

import asyncio
import threading
import uuid

_jobs = {}  # job_id -> {status, tool, workspace, started, finished, result, error}


def _run_job_in_thread(job_id, coro_fn, *args):
    """Run an async function in a new event loop on a background thread."""
    def _thread_target():
        logger.info(f"JOB {job_id} starting in background thread")
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(coro_fn(*args))
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["result"] = result
            _jobs[job_id]["finished"] = time.time()
            elapsed = _jobs[job_id]["finished"] - _jobs[job_id]["started"]
            logger.info(f"JOB {job_id} completed in {elapsed:.1f}s")
        except Exception as e:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)
            _jobs[job_id]["finished"] = time.time()
            logger.error(f"JOB {job_id} failed: {e}")
            logger.debug(traceback.format_exc())
        finally:
            loop.close()

    _jobs[job_id] = {
        "status": "running",
        "tool": coro_fn.__name__,
        "started": time.time(),
        "finished": None,
        "result": None,
        "error": None,
    }
    t = threading.Thread(target=_thread_target, daemon=True)
    t.start()


# ── Config ───────────────────────────────────────────────────────────

WORKSPACES_DIR = Path(os.environ.get(
    "EPIST_WORKSPACES",
    Path.home() / "EPISTEMIC_TOOLS" / "workspaces",
))

logger.info(f"Workspaces dir: {WORKSPACES_DIR}")

mcp = FastMCP("epistemic-workbench")


# ── Helpers ──────────────────────────────────────────────────────────

def _resolve_workspace(workspace: str) -> Path:
    """Resolve a workspace name to a path."""
    p = Path(workspace)
    return p if p.is_absolute() else WORKSPACES_DIR / workspace


def _get_store(workspace: str) -> Store:
    return Store(_resolve_workspace(workspace))


# ── Tools ────────────────────────────────────────────────────────────

@mcp.tool()
@_log_tool
async def list_workspaces() -> str:
    """List all epistemic workspaces.

    Returns a summary of each workspace with thesis info and object counts.
    """
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
            is_git = (d / ".git").is_dir()
            results.append(
                f"- **{d.name}** {'(git)' if is_git else ''}\n"
                f"  Thesis: {thesis_text[:120] or '(empty)'}\n"
                f"  Objects: {len(s.claims)} claims, {len(s.evidence)} evidence, "
                f"{len(s.arguments)} arguments"
            )
        except Exception:
            results.append(f"- **{d.name}** (error loading)")
    if not results:
        return "No workspaces found. Use generate_thesis to create one."
    return "\n".join(results)


async def _do_generate(thesis: str, workspace: str) -> str:
    """The actual generate work — runs in a background thread."""
    ws_path = _resolve_workspace(workspace)
    s = Store(ws_path)
    s.clear()
    if not s.is_git_repo():
        s.git_init()

    thesis_id = await generate_full_graph_async(s, thesis)

    result = compute_summary(s, thesis_id)
    (s.home / "summary.md").write_text(result["markdown"])

    counts = count_subgraph(s, thesis_id)
    short_thesis = thesis[:72] + ("..." if len(thesis) > 72 else "")
    s.git_commit(
        f"[generate] {short_thesis}\n\n"
        f"Thesis: {thesis}\n"
        f"Objects: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments, {counts['assumptions']} assumptions, "
        f"{counts['defeaters']} defeaters"
    )

    return (
        f"Generated argument graph in workspace '{workspace}'\n\n"
        f"Created: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments, {counts['assumptions']} assumptions, "
        f"{counts['defeaters']} defeaters\n\n"
        f"Thesis ID: {thesis_id}"
    )


@mcp.tool()
@_log_tool
async def generate_thesis(thesis: str, workspace: str) -> str:
    """Generate a full argument graph from a thesis statement.

    This runs in the background because it takes 30-90 seconds.
    Returns a job ID immediately. Use job_status to check when it's done
    and retrieve the result.

    Args:
        thesis: The thesis statement to decompose
        workspace: Workspace name (created under workspaces directory)
    """
    # Quick validation before spawning the background job
    ws_path = _resolve_workspace(workspace)
    ws_path.mkdir(parents=True, exist_ok=True)

    job_id = f"gen-{uuid.uuid4().hex[:8]}"
    _jobs[job_id] = {"workspace": workspace, "thesis": thesis[:80]}
    _run_job_in_thread(job_id, _do_generate, thesis, workspace)

    return (
        f"**Generation started** in background.\n\n"
        f"- Job ID: `{job_id}`\n"
        f"- Workspace: `{workspace}`\n"
        f"- Thesis: {thesis[:100]}{'...' if len(thesis) > 100 else ''}\n\n"
        f"This takes 30-90 seconds. Call **job_status** with job_id `{job_id}` "
        f"to check progress and get the result.\n\n"
        f"Or call **get_summary** on workspace `{workspace}` once the job completes."
    )


@mcp.tool()
@_log_tool
async def get_summary(workspace: str) -> str:
    """Get the full analysis summary for a workspace's thesis.

    Returns markdown with supporting arguments, objections, assumptions,
    confidence assessment, and what would change the conclusion.

    Args:
        workspace: Workspace name or path
    """
    s = _get_store(workspace)
    if not s.claims:
        return "No claims in this workspace. Use generate_thesis first."

    result = compute_summary(s)
    if not result.get("thesis"):
        return "No thesis found."

    # Save summary.md
    (s.home / "summary.md").write_text(result["markdown"])
    if s.is_git_repo():
        assessment = result.get("confidence_assessment", {})
        thesis_label = result["thesis"]["notes"] or result["thesis"]["label"]
        short_label = thesis_label[:72] + ("..." if len(thesis_label) > 72 else "")
        s.git_commit(
            f"[analysis] {short_label}\n\n"
            f"Confidence: {assessment.get('thesis_confidence', 0):.0%}\n"
            f"Active defeaters: {assessment.get('active_defeaters', 0)}\n"
            f"ATMS: {assessment.get('atms_status', 'unknown')}"
        )

    return result["markdown"]


async def _do_enhance_and_accept(workspace: str) -> str:
    """The actual enhance+accept work — runs in a background thread."""
    s = _get_store(workspace)
    if not s.claims:
        return "No claims in this workspace. Use generate_thesis first."

    summary_data = compute_summary(s)
    if not summary_data.get("thesis"):
        return "No thesis found."

    thesis_info = summary_data["thesis"]
    resolved_id = thesis_info["id"]

    result = await enhance_thesis_async(s, resolved_id)

    enhanced_text = result["enhanced_thesis"]
    rationale = result.get("rationale", "")
    changes = result.get("changes", [])

    s.clear()
    new_thesis_id = await generate_full_graph_async(s, enhanced_text)

    new_summary = compute_summary(s, new_thesis_id)
    (s.home / "summary.md").write_text(new_summary["markdown"])

    counts = count_subgraph(s, new_thesis_id)

    change_lines = ""
    for ch in changes:
        tag = ch.get("type", "change") if isinstance(ch, dict) else "change"
        desc = ch.get("description", str(ch)) if isinstance(ch, dict) else str(ch)
        change_lines += f"\n- [{tag}] {desc}"

    short_rationale = rationale[:72] + ("..." if len(rationale) > 72 else "")
    s.git_commit(
        f"[enhance] {short_rationale}\n\n"
        f"Thesis: {enhanced_text}\n\n"
        f"Rationale: {rationale}\n"
        f"Changes:{change_lines}\n\n"
        f"Objects: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments"
    )

    change_summary = "\n".join(
        f"- [{ch.get('type', 'change')}] {ch.get('description', '')}"
        for ch in changes if isinstance(ch, dict)
    )

    return (
        f"## Enhanced Thesis\n\n{enhanced_text}\n\n"
        f"## Rationale\n\n{rationale}\n\n"
        f"## Changes\n\n{change_summary}\n\n"
        f"## New Graph\n\n"
        f"Created: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments\n\n"
        f"---\n\nUse get_summary to see the full analysis of the enhanced thesis."
    )


@mcp.tool()
@_log_tool
async def enhance_and_accept(workspace: str) -> str:
    """Suggest an enhanced thesis and regenerate the argument graph.

    This runs in the background because it takes 60-120 seconds (enhance + generate).
    Returns a job ID immediately. Use job_status to check when it's done.

    Args:
        workspace: Workspace name or path
    """
    # Quick validation
    s = _get_store(workspace)
    if not s.claims:
        return "No claims in this workspace. Use generate_thesis first."

    job_id = f"enh-{uuid.uuid4().hex[:8]}"
    _jobs[job_id] = {"workspace": workspace}
    _run_job_in_thread(job_id, _do_enhance_and_accept, workspace)

    return (
        f"**Enhancement started** in background.\n\n"
        f"- Job ID: `{job_id}`\n"
        f"- Workspace: `{workspace}`\n\n"
        f"This takes 60-120 seconds (analyze + enhance + regenerate). "
        f"Call **job_status** with job_id `{job_id}` to check progress.\n\n"
        f"Or call **get_summary** on workspace `{workspace}` once the job completes."
    )


@mcp.tool()
@_log_tool
async def suggest_enhancement(workspace: str) -> str:
    """Suggest an enhanced thesis WITHOUT accepting it.

    Analyzes the current thesis and proposes improvements. Does not modify
    the workspace. Use enhance_and_accept to apply changes.

    Args:
        workspace: Workspace name or path
    """
    s = _get_store(workspace)
    if not s.claims:
        return "No claims in this workspace."

    summary_data = compute_summary(s)
    if not summary_data.get("thesis"):
        return "No thesis found."

    thesis_info = summary_data["thesis"]
    result = await enhance_thesis_async(s, thesis_info["id"])

    change_summary = "\n".join(
        f"- [{ch.get('type', 'change')}] {ch.get('description', '')}"
        for ch in result.get("changes", []) if isinstance(ch, dict)
    )

    return (
        f"## Current Thesis\n\n{thesis_info['notes'] or thesis_info['label']}\n"
        f"Confidence: {thesis_info['confidence']:.0%}\n\n"
        f"## Suggested Enhancement\n\n{result['enhanced_thesis']}\n\n"
        f"## Rationale\n\n{result['rationale']}\n\n"
        f"## Changes\n\n{change_summary}\n\n"
        f"---\n\nUse enhance_and_accept to apply this enhancement."
    )


@mcp.tool()
@_log_tool
async def get_versions(workspace: str) -> str:
    """Show version history for a workspace from git log.

    Args:
        workspace: Workspace name or path
    """
    s = _get_store(workspace)
    if not s.is_git_repo():
        return "Not a git-backed workspace."

    commits = s.git_log()
    version_commits = [c for c in commits if c["subject"].startswith(("[generate]", "[enhance]"))]
    version_commits.reverse()

    if not version_commits:
        return "No thesis versions found."

    lines = [f"**Version history ({len(version_commits)} versions)**\n"]
    for i, c in enumerate(version_commits):
        v = i + 1
        tag = "generate" if "[generate]" in c["subject"] else "enhance"
        subject = c["subject"].replace("[generate] ", "").replace("[enhance] ", "")
        current = " **(current)**" if i == len(version_commits) - 1 else ""

        lines.append(f"### v{v} — {c['date'][:10]}{current}")
        lines.append(f"[{tag}] {subject}")

        if c["body"]:
            for line in c["body"].split("\n"):
                if line.startswith("Thesis: "):
                    thesis_text = line[8:]
                    if len(thesis_text) > 200:
                        thesis_text = thesis_text[:197] + "..."
                    lines.append(f"\n> {thesis_text}")
                    break
                elif line.startswith("Rationale: "):
                    lines.append(f"\n*{line[11:]}*")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
@_log_tool
async def get_workspace_stats(workspace: str) -> str:
    """Get object counts and thesis info for a workspace.

    Args:
        workspace: Workspace name or path
    """
    s = _get_store(workspace)
    thesis_text = ""
    for c in s.claims.values():
        if c.is_root:
            thesis_text = c.notes or f"{c.subject} {c.predicate} {c.object}"
            break

    is_git = s.is_git_repo()
    return (
        f"**Workspace:** {s.home}\n"
        f"**Git:** {'yes' if is_git else 'no'}\n"
        f"**Thesis:** {thesis_text or '(none)'}\n\n"
        f"- Claims: {len(s.claims)}\n"
        f"- Evidence: {len(s.evidence)}\n"
        f"- Arguments: {len(s.arguments)}\n"
        f"- Evaluations: {len(s.evaluations)}\n"
        f"- Predictions: {len(s.predictions)}\n"
        f"- Total: {len(s.all_objects())}"
    )


# ── Manual intervention tools ─────────────────────────────────────────

@mcp.tool()
@_log_tool
async def respond_to_defeater(workspace: str, argument_id: str, response: str, defeater_index: int = -1) -> str:
    """Rebut a defeater on an argument with a counter-response.

    Use this when you have a counter-argument that addresses the objection
    so the defeater no longer applies. The defeater is marked 'answered'
    and the engine treats the argument as no longer defeated by it.

    For accepting a defeater as valid (rather than rebutting it), use
    concede_defeater instead.

    Args:
        workspace: Workspace name or path
        argument_id: ID (or prefix) of the argument with the defeater
        response: Your counter-argument explaining why the defeater fails
        defeater_index: Which defeater to respond to (-1 = first active)
    """
    s = _get_store(workspace)
    obj = s.get(argument_id)
    if not obj or not hasattr(obj, 'defeaters'):
        return f"Error: argument not found: {argument_id}"

    if defeater_index >= 0:
        if defeater_index >= len(obj.defeaters):
            return f"Error: defeater index {defeater_index} out of range (0-{len(obj.defeaters)-1})"
        d = obj.defeaters[defeater_index]
    else:
        d = next((d for d in obj.defeaters if d.status == DefeaterStatus.ACTIVE), None)
        if not d:
            return "No active defeaters on this argument."

    d.status = DefeaterStatus.ANSWERED
    d.response = response
    s.save()

    if s.is_git_repo():
        s.git_commit(f"[manual] Respond to defeater: {d.description[:50]}")

    from epist.engine import compute_atms
    atms = compute_atms(s)

    thesis = next((c for c in s.claims.values() if c.is_root), None)
    thesis_status = atms.get(thesis.id, "unknown") if thesis else "unknown"

    return (
        f"Defeater marked as answered (rebutted).\n\n"
        f"**Defeater:** {d.description}\n"
        f"**Response:** {response}\n\n"
        f"Thesis ATMS status: **{thesis_status}**"
    )


@mcp.tool()
@_log_tool
async def concede_defeater(workspace: str, argument_id: str, note: str, defeater_index: int = -1) -> str:
    """Concede a defeater — accept it as a valid criticism that still defeats the argument.

    Unlike respond_to_defeater (which rebuts), this acknowledges the defeater
    is correct. The argument remains DEFEATED in the ATMS, but the defeater
    is explicitly marked as accepted rather than unaddressed. This is the
    epistemically honest move when the objection is genuinely valid — the
    thesis should usually be narrowed or qualified afterwards.

    Use this when:
    - The objection is correct and your thesis should be weaker
    - You want the graph to show "I considered this and accepted it"
      rather than "this is unanswered"
    - You plan to revise the thesis to incorporate the limitation

    Args:
        workspace: Workspace name or path
        argument_id: ID (or prefix) of the argument with the defeater
        note: Your acknowledgment — what you're conceding and why
        defeater_index: Which defeater to concede (-1 = first active)
    """
    s = _get_store(workspace)
    obj = s.get(argument_id)
    if not obj or not hasattr(obj, 'defeaters'):
        return f"Error: argument not found: {argument_id}"

    if defeater_index >= 0:
        if defeater_index >= len(obj.defeaters):
            return f"Error: defeater index {defeater_index} out of range (0-{len(obj.defeaters)-1})"
        d = obj.defeaters[defeater_index]
    else:
        d = next((d for d in obj.defeaters if d.status == DefeaterStatus.ACTIVE), None)
        if not d:
            return "No active defeaters on this argument."

    d.status = DefeaterStatus.CONCEDED
    d.response = note
    s.save()

    if s.is_git_repo():
        s.git_commit(f"[manual] Concede defeater: {d.description[:50]}")

    from epist.engine import compute_atms
    atms = compute_atms(s)
    thesis = next((c for c in s.claims.values() if c.is_root), None)
    thesis_status = atms.get(thesis.id, "unknown") if thesis else "unknown"

    return (
        f"Defeater conceded (accepted as valid).\n\n"
        f"**Defeater:** {d.description}\n"
        f"**Conceded:** {note}\n\n"
        f"The argument remains defeated. Consider narrowing the thesis or "
        f"using set_confidence to lower it accordingly.\n\n"
        f"Thesis ATMS status: **{thesis_status}**"
    )


@mcp.tool()
@_log_tool
async def add_evidence_to_claim(workspace: str, claim_id: str, title: str,
                                 description: str, source: str = "",
                                 evidence_type: str = "observation",
                                 reliability: float = 0.7,
                                 pattern: str = "induction") -> str:
    """Attach new evidence to a specific claim via a supporting argument.

    Creates an evidence node and an argument linking it to the claim.
    This is how you add external sources, citations, or observations
    to strengthen (or challenge) a specific part of the argument graph.

    Args:
        workspace: Workspace name or path
        claim_id: ID (or prefix) of the claim to attach evidence to
        title: Short title for the evidence
        description: Detailed description of the evidence
        source: Citation or source URL
        evidence_type: observation, experiment, testimony, document, or statistical
        reliability: How reliable is this evidence (0.0-1.0)
        pattern: Inference pattern (induction, abduction, testimony, causal, etc.)
    """
    from epist.model import Evidence, Argument, Confidence, EvidenceType, InferencePattern

    s = _get_store(workspace)
    target = s.get(claim_id)
    if not target:
        return f"Error: claim not found: {claim_id}"

    e = Evidence(
        title=title, description=description,
        evidence_type=EvidenceType(evidence_type),
        source=source, reliability=reliability,
    )
    s.add_evidence(e)

    a = Argument(
        conclusion=target.id,
        premises=[e.id],
        pattern=InferencePattern(pattern),
        label=f"Evidence: {title}",
        confidence=Confidence(reliability),
    )
    s.add_argument(a)

    if s.is_git_repo():
        s.git_commit(f"[manual] Add evidence: {title}")

    from epist.engine import compute_atms
    atms = compute_atms(s)
    target_label = f"{target.subject} {target.predicate} {target.object}" if hasattr(target, 'subject') else claim_id[:12]
    target_status = atms.get(target.id, "unknown")

    return (
        f"Evidence added and linked to claim.\n\n"
        f"**Evidence:** {title}\n"
        f"**Source:** {source or '(none)'}\n"
        f"**Reliability:** {reliability:.0%}\n"
        f"**Linked to:** {target_label}\n"
        f"**Claim status:** {target_status}"
    )


@mcp.tool()
@_log_tool
async def challenge_claim(workspace: str, claim_id: str, description: str,
                           defeater_type: str = "undercutting") -> str:
    """Add a defeater/challenge to arguments supporting a claim.

    Adds an active defeater to the strongest supporting argument for this claim.
    This may change the ATMS status of the claim and the thesis.

    Args:
        workspace: Workspace name or path
        claim_id: ID (or prefix) of the claim to challenge
        description: What challenges this claim
        defeater_type: rebutting, undercutting, or undermining
    """
    from epist.model import Defeater, DefeaterType, DefeaterStatus

    s = _get_store(workspace)
    target = s.get(claim_id)
    if not target:
        return f"Error: claim not found: {claim_id}"

    supporting_args = [a for a in s.arguments.values() if a.conclusion == target.id]
    if not supporting_args:
        return "No supporting arguments found for this claim. Cannot attach a defeater."

    arg = max(supporting_args, key=lambda a: a.confidence.level)
    arg.defeaters.append(Defeater(
        type=DefeaterType(defeater_type),
        description=description,
        status=DefeaterStatus.ACTIVE,
    ))
    s.save()

    if s.is_git_repo():
        s.git_commit(f"[manual] Challenge: {description[:50]}")

    from epist.engine import compute_atms
    atms = compute_atms(s)
    target_label = f"{target.subject} {target.predicate} {target.object}" if hasattr(target, 'subject') else claim_id[:12]
    target_status = atms.get(target.id, "unknown")

    return (
        f"Challenge added.\n\n"
        f"**Type:** {defeater_type}\n"
        f"**Challenge:** {description}\n"
        f"**On argument:** {arg.label or '(unlabeled)'}\n"
        f"**Claim status:** {target_status}"
    )


@mcp.tool()
@_log_tool
async def set_confidence(workspace: str, claim_id: str, confidence: float,
                          note: str = "") -> str:
    """Manually set confidence on a claim.

    Args:
        workspace: Workspace name or path
        claim_id: ID (or prefix) of the claim
        confidence: New confidence value (0.0-1.0)
        note: Reason for the adjustment
    """
    from epist.model import Confidence

    s = _get_store(workspace)
    target = s.get(claim_id)
    if not target or not hasattr(target, 'confidence'):
        return f"Error: claim not found: {claim_id}"

    old_val = target.confidence.level
    target.confidence = Confidence(confidence)
    if note:
        existing = target.notes or ""
        target.notes = f"{existing}\n[{confidence:.0%}] {note}".strip() if existing else f"[{confidence:.0%}] {note}"
    s.save()

    label = f"{target.subject} {target.predicate} {target.object}" if hasattr(target, 'subject') else claim_id[:12]
    if s.is_git_repo():
        s.git_commit(f"[manual] Set confidence {old_val:.0%} -> {confidence:.0%}: {label[:40]}")

    return (
        f"Confidence updated.\n\n"
        f"**Claim:** {label}\n"
        f"**Was:** {old_val:.0%}\n"
        f"**Now:** {confidence:.0%}\n"
        + (f"**Note:** {note}" if note else "")
    )


@mcp.tool()
@_log_tool
async def show_graph(workspace: str) -> str:
    """Show the argument graph structure for the current thesis.

    Returns a tree view of claims, evidence, arguments, and defeaters
    with ATMS status indicators.

    Args:
        workspace: Workspace name or path
    """
    from epist.engine import compute_atms

    s = _get_store(workspace)
    thesis = next((c for c in s.claims.values() if c.is_root), None)
    if not thesis:
        return "No thesis found."

    atms = compute_atms(s)

    def status_icon(st):
        return {"accepted": "+", "provisional": "~", "defeated": "x", "unknown": "?"}.get(st, "?")

    lines = []
    thesis_label = thesis.notes or f"{thesis.subject} {thesis.predicate} {thesis.object}"
    if len(thesis_label) > 100:
        thesis_label = thesis_label[:97] + "..."
    st = atms.get(thesis.id, "unknown")
    lines.append(f"[{status_icon(st)}] **THESIS:** {thesis_label} ({thesis.confidence.level:.0%})")
    lines.append(f"    ID: `{thesis.id[:16]}`")

    def render_node(node_id, indent=1, visited=None):
        if visited is None:
            visited = set()
        if node_id in visited:
            return
        visited.add(node_id)
        prefix = "    " * indent

        for arg in s.arguments.values():
            if arg.conclusion == node_id:
                arg_st = atms.get(arg.id, "unknown")
                defeaters_active = [d for d in arg.defeaters if d.status == DefeaterStatus.ACTIVE]
                defeaters_answered = [d for d in arg.defeaters if d.status == DefeaterStatus.ANSWERED]

                lines.append(f"{prefix}[{status_icon(arg_st)}] **Argument:** {arg.label or '(unlabeled)'} ({arg.pattern.value}, {arg.confidence.level:.0%})")
                lines.append(f"{prefix}    ID: `{arg.id[:16]}`")

                for d in defeaters_active:
                    lines.append(f"{prefix}    [x] DEFEATER ({d.type.value}): {d.description[:80]}")
                for d in defeaters_answered:
                    lines.append(f"{prefix}    [+] ~~{d.description[:60]}~~ — {d.response or '(answered)'}")

                for pid in arg.premises:
                    p = s.get(pid)
                    if not p:
                        continue
                    p_st = atms.get(pid, "unknown")
                    if hasattr(p, 'subject'):
                        plabel = f"{p.subject} {p.predicate} {p.object}"
                        pconf = f"{p.confidence.level:.0%}"
                        lines.append(f"{prefix}    [{status_icon(p_st)}] Claim: {plabel} ({pconf})")
                        lines.append(f"{prefix}        ID: `{pid[:16]}`")
                        render_node(pid, indent + 2, visited)
                    else:
                        lines.append(f"{prefix}    [{status_icon(p_st)}] Evidence: {p.title} ({p.reliability:.0%}) src={p.source or '(none)'}")
                        lines.append(f"{prefix}        ID: `{pid[:16]}`")

    render_node(thesis.id)

    if thesis.assumes:
        lines.append("")
        lines.append("**Assumptions:**")
        for aid in thesis.assumes:
            a = s.get(aid)
            if a:
                a_st = atms.get(aid, "unknown")
                lines.append(f"    [{status_icon(a_st)}] {a.subject} {a.predicate} {a.object} ({a.confidence.level:.0%})")
                lines.append(f"        ID: `{aid[:16]}`")

    return "\n".join(lines)


# ── Fork-and-merge tools ─────────────────────────────────────────────

import re as _re
_BRANCH_NAME_RE = _re.compile(r"^[a-z0-9][a-z0-9._/-]*$")


def _validate_branch_name(name: str) -> bool:
    if not name or len(name) > 64:
        return False
    if ".." in name or name.startswith("/") or name.endswith("/"):
        return False
    return bool(_BRANCH_NAME_RE.match(name))


def _autosave_if_dirty(s, label: str = "auto-save"):
    if s.is_git_repo() and s.git_has_changes():
        s.git_commit(f"[manual] {label}")


@mcp.tool()
@_log_tool
async def fork_workspace(workspace: str, fork_name: str) -> str:
    """Create a new fork (git branch) of an argument graph workspace.

    Forks let you explore alternative framings without losing the original.
    The new branch starts at the current state and can be developed
    independently. Use compare_forks to see how forks differ, and
    merge_forks to combine insights.

    Args:
        workspace: Workspace name or path
        fork_name: Name for the new fork (lowercase, alphanumeric, hyphens)
    """
    s = _get_store(workspace)
    if not s.is_git_repo():
        return "Error: not a git-backed workspace"
    if not _validate_branch_name(fork_name):
        return f"Error: invalid fork name '{fork_name}'. Use lowercase letters, digits, hyphens, dots, slashes."
    if s.git_branch_exists(fork_name):
        return f"Error: fork '{fork_name}' already exists"

    current = s.git_current_branch()
    _autosave_if_dirty(s, f"auto-save before fork to {fork_name}")
    s.git_create_branch(fork_name)
    s.git_commit(f"[fork] Created from {current}")

    return (
        f"Forked **{current}** → **{fork_name}**\n\n"
        f"Now on branch '{fork_name}'. Use switch_fork to return to '{current}'."
    )


@mcp.tool()
@_log_tool
async def list_forks(workspace: str) -> str:
    """List all forks (branches) in a workspace with their thesis text.

    Args:
        workspace: Workspace name or path
    """
    s = _get_store(workspace)
    if not s.is_git_repo():
        return "Not a git-backed workspace."

    branches = s.git_list_branches()
    if not branches:
        return "No branches found."

    trunk = next((b["name"] for b in branches if b["name"] in ("master", "main")), None)

    lines = [f"**Forks in {s.home.name}**\n"]
    for b in branches:
        marker = "→ " if b["is_current"] else "  "
        thesis = s._git_show_file(b["name"], "thesis.md").strip() or "(no thesis.md)"
        if len(thesis) > 120:
            thesis = thesis[:117] + "..."
        if trunk and b["name"] != trunk:
            count = s.git_commits_since(b["name"], trunk)
            commit_str = f" (+{count} commits)"
        else:
            commit_str = ""
        lines.append(f"{marker}**{b['name']}**{commit_str}")
        lines.append(f"   {thesis}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
@_log_tool
async def switch_fork(workspace: str, fork_name: str) -> str:
    """Switch to a different fork (branch).

    Args:
        workspace: Workspace name or path
        fork_name: Name of the fork to switch to
    """
    s = _get_store(workspace)
    if not s.is_git_repo():
        return "Error: not a git-backed workspace"
    if not s.git_branch_exists(fork_name):
        return f"Error: fork '{fork_name}' does not exist"

    current = s.git_current_branch()
    if current == fork_name:
        return f"Already on '{fork_name}'."

    _autosave_if_dirty(s, f"auto-save before switch to {fork_name}")
    try:
        s.git_switch_branch(fork_name)
    except RuntimeError as e:
        return f"Error: switch failed: {e}"

    thesis = next((c for c in s.claims.values() if c.is_root), None)
    thesis_text = ""
    if thesis:
        thesis_text = thesis.notes or f"{thesis.subject} {thesis.predicate} {thesis.object}"

    return (
        f"Switched **{current}** → **{fork_name}**\n\n"
        f"**Thesis:** {thesis_text}\n\n"
        f"Objects: {len(s.claims)} claims, {len(s.evidence)} evidence, "
        f"{len(s.arguments)} arguments"
    )


@mcp.tool()
@_log_tool
async def compare_forks(workspace: str, other_branch: str) -> str:
    """Show a structural diff between the current fork and another fork.

    Compares argument graphs by semantic identity (subject/predicate/object
    triple), not text. Reports added/removed/modified claims, evidence,
    arguments, defeaters, and the analysis delta (confidence, ATMS status,
    coherence issues).

    Args:
        workspace: Workspace name or path
        other_branch: Name of the fork to compare against
    """
    from epist.compare import compute_graph_diff, compute_analysis_delta, format_diff_markdown

    s = _get_store(workspace)
    if not s.is_git_repo():
        return "Error: not a git-backed workspace"
    if not s.git_branch_exists(other_branch):
        return f"Error: fork '{other_branch}' does not exist"

    current = s.git_current_branch()
    if current == other_branch:
        return f"Cannot compare '{other_branch}' with itself."

    other = s.load_branch_store(other_branch)
    diff = compute_graph_diff(s, other)
    delta = compute_analysis_delta(s, other)
    return format_diff_markdown(diff, delta, current, other_branch)


@mcp.tool()
@_log_tool
async def merge_forks(workspace: str, source_branch: str, mode: str = "synthesize") -> str:
    """Merge another fork into the current one.

    Modes:
    - 'pick': adopt the source fork wholesale (just switches to that branch)
    - 'synthesize': use the LLM to synthesize a new thesis incorporating
      insights from both forks, then generate a new graph on a merge/ branch

    Args:
        workspace: Workspace name or path
        source_branch: Name of the fork to merge in
        mode: 'pick' or 'synthesize' (default: synthesize)
    """
    s = _get_store(workspace)
    if not s.is_git_repo():
        return "Error: not a git-backed workspace"
    if not s.git_branch_exists(source_branch):
        return f"Error: fork '{source_branch}' does not exist"

    current = s.git_current_branch()
    if current == source_branch:
        return f"Cannot merge '{source_branch}' with itself."

    if mode == "pick":
        _autosave_if_dirty(s, f"auto-save before merge from {source_branch}")
        try:
            s.git_switch_branch(source_branch)
        except RuntimeError as e:
            return f"Error: switch failed: {e}"
        return f"Adopted fork **{source_branch}** wholesale. Now on that branch."

    if mode != "synthesize":
        return f"Error: unknown mode '{mode}'. Use 'pick' or 'synthesize'."

    # Synthesize mode
    other = s.load_branch_store(source_branch)
    try:
        result = await synthesize_thesis_async(current, s, source_branch, other)
    except Exception as e:
        return f"Error: synthesis failed: {e}"

    # Create merge branch
    merge_branch = f"merge/{source_branch}-into-{current}"
    if not _validate_branch_name(merge_branch):
        merge_branch = f"merge-{current}-{source_branch}"
    if s.git_branch_exists(merge_branch):
        import time as _time
        merge_branch = f"{merge_branch}-{int(_time.time())}"

    _autosave_if_dirty(s, "auto-save before merge synthesis")
    s.git_create_branch(merge_branch)
    s.clear()

    try:
        new_thesis_id = await generate_full_graph_async(s, result["synthesized_thesis"])
    except Exception as e:
        return f"Error: graph generation failed: {e}"

    new_summary = compute_summary(s, new_thesis_id)
    (s.home / "summary.md").write_text(new_summary["markdown"])

    counts = count_subgraph(s, new_thesis_id)

    incorp_lines = ""
    for x in result.get("incorporated_from_a", []):
        incorp_lines += f"\n- [from {current}] {x}"
    for x in result.get("incorporated_from_b", []):
        incorp_lines += f"\n- [from {source_branch}] {x}"
    for x in result.get("resolved_tensions", []):
        incorp_lines += f"\n- [resolved] {x}"

    short_rationale = result["rationale"][:72] + ("..." if len(result["rationale"]) > 72 else "")
    s.git_commit(
        f"[merge] {short_rationale}\n\n"
        f"Synthesized from: {current} + {source_branch}\n"
        f"Thesis: {result['synthesized_thesis']}\n\n"
        f"Rationale: {result['rationale']}\n"
        f"Incorporations:{incorp_lines}\n\n"
        f"Objects: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments"
    )

    from_a = "\n".join(f"- {x}" for x in result.get("incorporated_from_a", []))
    from_b = "\n".join(f"- {x}" for x in result.get("incorporated_from_b", []))
    tensions = "\n".join(f"- {x}" for x in result.get("resolved_tensions", []))

    return (
        f"## Merge complete\n\n"
        f"**New branch:** `{merge_branch}`\n\n"
        f"## Synthesized thesis\n\n{result['synthesized_thesis']}\n\n"
        f"## Rationale\n\n{result['rationale']}\n\n"
        f"## Incorporated from {current}\n\n{from_a or '_(none)_'}\n\n"
        f"## Incorporated from {source_branch}\n\n{from_b or '_(none)_'}\n\n"
        f"## Resolved tensions\n\n{tensions or '_(none)_'}\n\n"
        f"## New graph\n\n"
        f"Created: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments"
    )


# ── Job status + diagnostics ──────────────────────────────────────────

_server_start_time = time.time()


@mcp.tool()
@_log_tool
async def job_status(job_id: str = "") -> str:
    """Check the status of a background job (generate, enhance, merge).

    If job_id is empty, shows all recent jobs. If a job is completed,
    returns the full result. If failed, returns the error.

    Args:
        job_id: The job ID returned by generate_thesis, enhance_and_accept, etc.
    """
    if job_id and job_id in _jobs:
        job = _jobs[job_id]
        elapsed = (job.get("finished") or time.time()) - job["started"]

        if job["status"] == "running":
            return (
                f"**Job `{job_id}` is still running** ({elapsed:.0f}s elapsed)\n\n"
                f"Tool: {job['tool']}\n\n"
                f"Call job_status again in 15-30 seconds to check."
            )
        elif job["status"] == "completed":
            return (
                f"**Job `{job_id}` completed** in {elapsed:.0f}s\n\n"
                f"---\n\n{job['result']}"
            )
        elif job["status"] == "failed":
            return (
                f"**Job `{job_id}` failed** after {elapsed:.0f}s\n\n"
                f"Error: {job['error']}"
            )

    # Show all jobs
    if not _jobs:
        return "No jobs have been submitted yet."

    lines = [f"**All jobs ({len(_jobs)}):**\n"]
    for jid, job in sorted(_jobs.items(), key=lambda x: x[1].get("started", 0), reverse=True):
        elapsed = (job.get("finished") or time.time()) - job.get("started", 0)
        status_icon = {"running": "⟳", "completed": "✓", "failed": "✗"}.get(job["status"], "?")
        lines.append(
            f"- {status_icon} `{jid}` **{job['tool']}** — {job['status']} ({elapsed:.0f}s)"
        )
        if job.get("workspace"):
            lines.append(f"  workspace: {job['workspace']}")
    if not job_id:
        lines.append(f"\nCall job_status with a specific job_id to get the full result.")
    elif job_id not in _jobs:
        lines.append(f"\nJob `{job_id}` not found.")
    return "\n".join(lines)


@mcp.tool()
@_log_tool
async def server_status() -> str:
    """Show MCP server diagnostics: uptime, active calls, background jobs, log file.

    Use this to diagnose timeouts or unresponsive behavior.
    """
    uptime = time.time() - _server_start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)

    lines = [
        f"**Epistemic Workbench MCP Server**\n",
        f"- PID: `{os.getpid()}`",
        f"- Uptime: {hours}h {minutes}m {seconds}s",
        f"- Workspaces dir: `{WORKSPACES_DIR}`",
        f"- Log file: `{_log_dir / '.mcp-server.log'}`",
        f"- Active calls: {len(_active_calls)}",
    ]

    if _active_calls:
        lines.append("\n**In-flight tool calls:**\n")
        for call_id, info in _active_calls.items():
            elapsed = time.time() - info["started"]
            lines.append(
                f"- `{call_id}` **{info['tool']}** — {elapsed:.0f}s elapsed"
                f"\n  args: {info['args']}"
            )
    else:
        lines.append("\n_No tool calls in flight._")

    running_jobs = {jid: j for jid, j in _jobs.items() if j["status"] == "running"}
    if running_jobs:
        lines.append(f"\n**Background jobs ({len(running_jobs)} running):**\n")
        for jid, job in running_jobs.items():
            elapsed = time.time() - job["started"]
            lines.append(f"- `{jid}` **{job['tool']}** — {elapsed:.0f}s elapsed")
    else:
        lines.append(f"\n_No background jobs running._ ({len(_jobs)} total jobs tracked)")

    # Show last 10 lines of log file
    try:
        log_path = _log_dir / ".mcp-server.log"
        if log_path.exists():
            log_lines = log_path.read_text().strip().split("\n")
            recent = log_lines[-15:] if len(log_lines) > 15 else log_lines
            lines.append(f"\n**Recent log ({len(log_lines)} total lines):**\n")
            lines.append("```")
            lines.extend(recent)
            lines.append("```")
    except Exception:
        pass

    return "\n".join(lines)


# ── Entry point ──────────────────────────────────────────────────────

def main():
    logger.info("MCP server running (stdio transport)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
