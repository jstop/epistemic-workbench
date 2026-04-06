"""
MCP server for the Epistemic Workbench.
Exposes thesis generation, analysis, and enhancement as tools for Claude Desktop.
"""
import json
import os
import sys
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

# ── Config ───────────────────────────────────────────────────────────

WORKSPACES_DIR = Path(os.environ.get(
    "EPIST_WORKSPACES",
    Path.home() / "EPISTEMIC_TOOLS" / "workspaces",
))

mcp = FastMCP("epistemic-workbench")


# ── Helpers ──────────────────────────────────────────────────────────

def _resolve_workspace(workspace: str) -> Path:
    """Resolve a workspace name to a path."""
    p = Path(workspace)
    if p.is_absolute():
        return p
    return WORKSPACES_DIR / workspace


def _get_store(workspace: str) -> Store:
    return Store(_resolve_workspace(workspace))


# ── Tools ────────────────────────────────────────────────────────────

@mcp.tool()
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


@mcp.tool()
async def generate_thesis(thesis: str, workspace: str) -> str:
    """Generate a full argument graph from a thesis statement.

    Creates a new git-versioned workspace with claims, evidence, arguments,
    assumptions, and defeaters decomposed from the thesis.

    Args:
        thesis: The thesis statement to decompose
        workspace: Workspace name (created under workspaces directory)
    """
    ws_path = _resolve_workspace(workspace)
    s = Store(ws_path)
    s.clear()
    if not s.is_git_repo():
        s.git_init()

    thesis_id = await generate_full_graph_async(s, thesis)

    # Write summary
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


@mcp.tool()
async def enhance_and_accept(workspace: str) -> str:
    """Suggest an enhanced thesis and regenerate the argument graph.

    Analyzes the current thesis, suggests improvements based on objections
    and weaknesses, then generates a new argument graph for the enhanced thesis.
    The old version is preserved in git history.

    Args:
        workspace: Workspace name or path
    """
    s = _get_store(workspace)
    if not s.claims:
        return "No claims in this workspace. Use generate_thesis first."

    summary_data = compute_summary(s)
    if not summary_data.get("thesis"):
        return "No thesis found."

    thesis_info = summary_data["thesis"]
    resolved_id = thesis_info["id"]

    # Get enhancement suggestion
    result = await enhance_thesis_async(s, resolved_id)

    enhanced_text = result["enhanced_thesis"]
    rationale = result.get("rationale", "")
    changes = result.get("changes", [])

    # Clear and regenerate
    s.clear()
    new_thesis_id = await generate_full_graph_async(s, enhanced_text)

    # Write summary
    new_summary = compute_summary(s, new_thesis_id)
    (s.home / "summary.md").write_text(new_summary["markdown"])

    counts = count_subgraph(s, new_thesis_id)

    # Git commit
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

    # Build response
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
async def respond_to_defeater(workspace: str, argument_id: str, response: str, defeater_index: int = -1) -> str:
    """Respond to a defeater on an argument, marking it as answered.

    The response is recorded and the defeater status changes from active to
    answered, which may change the ATMS status of the thesis.

    Args:
        workspace: Workspace name or path
        argument_id: ID (or prefix) of the argument with the defeater
        response: Your response explaining why this defeater is addressed
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
        f"Defeater marked as answered.\n\n"
        f"**Defeater:** {d.description}\n"
        f"**Response:** {response}\n\n"
        f"Thesis ATMS status: **{thesis_status}**"
    )


@mcp.tool()
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


# ── Entry point ──────────────────────────────────────────────────────

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
