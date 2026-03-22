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
from epist.llm import (
    generate_full_graph,
    compute_summary,
    enhance_thesis,
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

    thesis_id = generate_full_graph(s, thesis)

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
    result = enhance_thesis(s, resolved_id)

    enhanced_text = result["enhanced_thesis"]
    rationale = result.get("rationale", "")
    changes = result.get("changes", [])

    # Clear and regenerate
    s.clear()
    new_thesis_id = generate_full_graph(s, enhanced_text)

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
    result = enhance_thesis(s, thesis_info["id"])

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


# ── Entry point ──────────────────────────────────────────────────────

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
