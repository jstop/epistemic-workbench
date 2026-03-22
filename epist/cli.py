"""
epist — Epistemic Workbench CLI
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.markdown import Markdown
from rich import box

sys.path.insert(0, str(Path(__file__).parent.parent))

from epist.model import (
    Claim, Evidence, Argument, Evaluation, Prediction,
    Confidence, Scope, Identity, Defeater,
    Modality, EvidenceType, InferencePattern, DefeaterType,
    DefeaterStatus, EvaluationJudgment, PATTERN_METADATA,
)
from epist.store import Store
from epist.engine import (
    compute_atms, ATMSStatus, check_coherence, bayesian_update,
    find_blind_spots, surface_assumptions, stress_test,
    compute_calibration,
)

console = Console()


def get_store(home=None):
    h = Path(home) if home else Path(os.environ.get("EPIST_HOME", Path.home() / ".epistemic"))
    return Store(h)


def short_id(eo_id: str) -> str:
    return eo_id[:12] + "…"


# ── Main Group ────────────────────────────────────────────────────────

@click.group()
@click.option("--home", envvar="EPIST_HOME", default=None, help="Workspace directory")
@click.pass_context
def cli(ctx, home):
    """epist — Epistemic Workbench"""
    ctx.ensure_object(dict)
    ctx.obj["home"] = home


# ── Init ──────────────────────────────────────────────────────────────

@cli.command()
@click.pass_context
def init(ctx):
    """Initialize a new epistemic workspace."""
    s = get_store(ctx.obj["home"])
    s.init_workspace()
    console.print(f"[green]✓[/green] Workspace initialized at {s.home}")


# ── Claim commands ────────────────────────────────────────────────────

@cli.group()
def claim():
    """Manage claims."""
    pass


@claim.command("new")
@click.option("--subject", "-s", required=True)
@click.option("--predicate", "-p", required=True)
@click.option("--object", "-o", required=True)
@click.option("--confidence", "-c", type=float, default=0.7)
@click.option("--modality", "-m", type=click.Choice([m.value for m in Modality]), default="empirical")
@click.option("--notes", default="")
@click.pass_context
def claim_new(ctx, subject, predicate, object, confidence, modality, notes):
    """Create a new claim."""
    s = get_store(ctx.obj["home"])
    c = Claim(
        subject=subject, predicate=predicate, object=object,
        confidence=Confidence(confidence),
        modality=Modality(modality),
        notes=notes,
    )
    s.add_claim(c)
    console.print(f"[green]✓[/green] Created claim [cyan]{short_id(c.id)}[/cyan]")
    console.print(f"  {subject} [dim]{predicate}[/dim] {object} [dim]({confidence:.0%})[/dim]")


@claim.command("list")
@click.pass_context
def claim_list(ctx):
    """List all claims."""
    s = get_store(ctx.obj["home"])
    status = compute_atms(s)
    if not s.claims:
        console.print("[dim]No claims yet.[/dim]")
        return
    table = Table(box=box.SIMPLE)
    table.add_column("ID", style="cyan", width=14)
    table.add_column("Subject")
    table.add_column("Predicate", style="dim")
    table.add_column("Object")
    table.add_column("Conf", justify="right")
    table.add_column("Modality", style="dim")
    table.add_column("ATMS")
    atms_colors = {ATMSStatus.ACCEPTED: "green", ATMSStatus.PROVISIONAL: "yellow",
                   ATMSStatus.DEFEATED: "red", ATMSStatus.UNKNOWN: "dim"}
    for cid, c in s.claims.items():
        st = status.get(cid, ATMSStatus.UNKNOWN)
        table.add_row(
            short_id(cid), c.subject, c.predicate, c.object,
            f"{c.confidence.level:.0%}", c.modality.value,
            f"[{atms_colors[st]}]{st}[/{atms_colors[st]}]",
        )
    console.print(table)


# ── Evidence commands ─────────────────────────────────────────────────

@cli.group()
def evidence():
    """Manage evidence."""
    pass


@evidence.command("new")
@click.option("--title", "-t", required=True)
@click.option("--description", "-d", required=True)
@click.option("--type", "etype", type=click.Choice([e.value for e in EvidenceType]), default="observation")
@click.option("--source", default="")
@click.option("--reliability", type=float, default=0.7)
@click.pass_context
def evidence_new(ctx, title, description, etype, source, reliability):
    """Add new evidence."""
    s = get_store(ctx.obj["home"])
    e = Evidence(title=title, description=description, evidence_type=EvidenceType(etype),
                 source=source, reliability=reliability)
    s.add_evidence(e)
    console.print(f"[green]✓[/green] Added evidence [cyan]{short_id(e.id)}[/cyan]: {title}")


@evidence.command("list")
@click.pass_context
def evidence_list(ctx):
    """List all evidence."""
    s = get_store(ctx.obj["home"])
    if not s.evidence:
        console.print("[dim]No evidence yet.[/dim]")
        return
    table = Table(box=box.SIMPLE)
    table.add_column("ID", style="cyan", width=14)
    table.add_column("Title")
    table.add_column("Type", style="dim")
    table.add_column("Reliability", justify="right")
    for eid, e in s.evidence.items():
        table.add_row(short_id(eid), e.title, e.evidence_type.value, f"{e.reliability:.0%}")
    console.print(table)


# ── Argument commands ─────────────────────────────────────────────────

@cli.group()
def argument():
    """Manage arguments."""
    pass


@argument.command("new")
@click.option("--conclusion", "-c", required=True, help="Claim ID for conclusion")
@click.option("--premise", "-p", multiple=True, required=True, help="Premise IDs (claim or evidence)")
@click.option("--pattern", type=click.Choice([p.value for p in InferencePattern]), default="modus_ponens")
@click.option("--label", "-l", default="")
@click.option("--confidence", type=float, default=0.7)
@click.pass_context
def argument_new(ctx, conclusion, premise, pattern, label, confidence):
    """Create an argument linking premises to conclusion."""
    s = get_store(ctx.obj["home"])
    # Resolve prefix IDs
    conc = s.get(conclusion)
    if not conc:
        console.print(f"[red]✗[/red] Conclusion not found: {conclusion}")
        return
    prem_ids = []
    for p in premise:
        obj = s.get(p)
        if not obj:
            console.print(f"[red]✗[/red] Premise not found: {p}")
            return
        prem_ids.append(obj.id)

    a = Argument(
        conclusion=conc.id, premises=prem_ids,
        pattern=InferencePattern(pattern), label=label,
        confidence=Confidence(confidence),
    )
    s.add_argument(a)
    console.print(f"[green]✓[/green] Created argument [cyan]{short_id(a.id)}[/cyan]: {label or '(unlabeled)'}")


@argument.command("list")
@click.pass_context
def argument_list(ctx):
    """List all arguments."""
    s = get_store(ctx.obj["home"])
    status = compute_atms(s)
    if not s.arguments:
        console.print("[dim]No arguments yet.[/dim]")
        return
    table = Table(box=box.SIMPLE)
    table.add_column("ID", style="cyan", width=14)
    table.add_column("Label")
    table.add_column("Pattern", style="dim")
    table.add_column("Premises", justify="right")
    table.add_column("ATMS")
    for aid, a in s.arguments.items():
        st = status.get(aid, ATMSStatus.UNKNOWN)
        c = "green" if st == ATMSStatus.ACCEPTED else "yellow" if st == ATMSStatus.PROVISIONAL else "red"
        table.add_row(short_id(aid), a.label or "(unlabeled)", a.pattern.value,
                       str(len(a.premises)), f"[{c}]{st}[/{c}]")
    console.print(table)


# ── Analysis commands ─────────────────────────────────────────────────

@cli.command("check")
@click.pass_context
def check(ctx):
    """Run coherence checker."""
    s = get_store(ctx.obj["home"])
    issues = check_coherence(s)
    if not issues:
        console.print("[green]✓ No coherence issues found.[/green]")
        return
    console.print(f"\n[bold]Found {len(issues)} issue(s):[/bold]\n")
    sev_colors = {"error": "red", "warning": "yellow", "info": "blue"}
    for iss in issues:
        c = sev_colors.get(iss["severity"], "white")
        console.print(f"  [{c}]{iss['severity'].upper()}[/{c}] [{c}]{iss['check']}[/{c}]")
        console.print(f"    {iss['message']}")
        console.print(f"    [dim]Objects: {', '.join(short_id(o) for o in iss['objects'])}[/dim]\n")


@cli.command("status")
@click.pass_context
def status(ctx):
    """Show ATMS status for all objects."""
    s = get_store(ctx.obj["home"])
    atms = compute_atms(s)
    if not atms:
        console.print("[dim]No objects to analyze.[/dim]")
        return
    table = Table(title="ATMS Status", box=box.SIMPLE)
    table.add_column("ID", style="cyan", width=14)
    table.add_column("Type", style="dim")
    table.add_column("Label")
    table.add_column("Status")
    atms_colors = {ATMSStatus.ACCEPTED: "green", ATMSStatus.PROVISIONAL: "yellow",
                   ATMSStatus.DEFEATED: "red", ATMSStatus.UNKNOWN: "dim"}
    for oid, st in atms.items():
        obj = s.get(oid)
        if not obj:
            continue
        otype = type(obj).__name__
        label = ""
        if hasattr(obj, 'subject'):
            label = f"{obj.subject} {obj.predicate} {obj.object}"
        elif hasattr(obj, 'title'):
            label = obj.title
        elif hasattr(obj, 'label'):
            label = obj.label
        c = atms_colors.get(st, "white")
        table.add_row(short_id(oid), otype, label[:50], f"[{c}]{st}[/{c}]")
    console.print(table)


@cli.command("blind-spots")
@click.pass_context
def blind_spots(ctx):
    """Scan for epistemic blind spots."""
    s = get_store(ctx.obj["home"])
    spots = find_blind_spots(s)
    if not spots:
        console.print("[green]✓ No blind spots detected.[/green]")
        return
    high = [sp for sp in spots if sp["risk"] == "high"]
    med = [sp for sp in spots if sp["risk"] == "medium"]
    console.print(f"\n[bold]Found {len(high)} high-risk and {len(med)} medium-risk blind spots:[/bold]\n")
    for sp in spots:
        c = "red" if sp["risk"] == "high" else "yellow"
        console.print(f"  [{c}]▲ {sp['risk'].upper()}[/{c}] {sp['message']}")
        console.print(f"    [dim]{short_id(sp['claim_id'])}[/dim]\n")


@cli.command("assumptions")
@click.argument("target_id")
@click.pass_context
def assumptions(ctx, target_id):
    """Surface all assumptions a claim depends on."""
    s = get_store(ctx.obj["home"])
    obj = s.get(target_id)
    if not obj:
        console.print(f"[red]✗[/red] Object not found: {target_id}")
        return
    results = surface_assumptions(s, obj.id)
    if not results:
        console.print("[dim]No assumptions found (or claim has no dependency chain).[/dim]")
        return

    console.print(f"\n[bold]Assumptions underlying {short_id(obj.id)}:[/bold]\n")
    for a in results:
        indent = "  " * (a["depth"] + 1)
        icon = "📌" if a["type"] == "explicit" else "👁"
        supported = "[green]supported[/green]" if a["supported"] else "[red]UNSUPPORTED[/red]"
        console.print(f"{indent}{icon} [{a['type']}] {a['label']}")
        console.print(f"{indent}   {supported} · [dim]{short_id(a['id'])}[/dim]")


@cli.command("stress-test")
@click.argument("target_id")
@click.pass_context
def stress_test_cmd(ctx, target_id):
    """Generate challenges for a claim."""
    s = get_store(ctx.obj["home"])
    obj = s.get(target_id)
    if not obj:
        console.print(f"[red]✗[/red] Object not found: {target_id}")
        return
    result = stress_test(s, obj.id)
    if not result:
        return

    console.print(Panel(f"[bold]Stress Test: {result['target']}[/bold]\n[dim]Modality: {result['modality']}[/dim]"))

    if result["attack_surfaces"]:
        console.print("\n[bold red]Attack Surfaces:[/bold red]")
        for a in result["attack_surfaces"]:
            console.print(f"  ⚔  {a}")

    if result["crux_questions"]:
        console.print("\n[bold yellow]Crux Questions:[/bold yellow]")
        for q in result["crux_questions"]:
            console.print(f"  ?  {q}")

    if result["steelman_prompts"]:
        console.print("\n[bold blue]Steelman the Opposition:[/bold blue]")
        for p in result["steelman_prompts"]:
            console.print(f"  💪 {p}")

    if result["alternative_explanations"]:
        console.print("\n[bold green]Alternative Explanations:[/bold green]")
        for e in result["alternative_explanations"]:
            console.print(f"  ↔  {e}")


@cli.command("stats")
@click.pass_context
def stats(ctx):
    """Show workspace statistics."""
    s = get_store(ctx.obj["home"])
    console.print(Panel(
        f"[bold]Workspace: {s.home}[/bold]\n\n"
        f"  Claims:       {len(s.claims)}\n"
        f"  Evidence:     {len(s.evidence)}\n"
        f"  Arguments:    {len(s.arguments)}\n"
        f"  Evaluations:  {len(s.evaluations)}\n"
        f"  Predictions:  {len(s.predictions)}\n"
        f"  Foundations:   {len(s.foundations)}\n"
        f"  ─────────────────\n"
        f"  Total objects: {len(s.all_objects())}",
        title="Epistemic Workbench Stats",
    ))


@cli.command("show")
@click.argument("eo_id")
@click.pass_context
def show(ctx, eo_id):
    """Show full details of an epistemic object."""
    s = get_store(ctx.obj["home"])
    obj = s.get(eo_id)
    if not obj:
        console.print(f"[red]✗[/red] Object not found: {eo_id}")
        return
    atms = compute_atms(s)
    st = atms.get(obj.id, ATMSStatus.UNKNOWN)

    lines = [f"[bold]{type(obj).__name__}[/bold] · [dim]{obj.id}[/dim]"]
    lines.append(f"ATMS: {st}")

    if hasattr(obj, 'subject'):
        lines.append(f"\n  {obj.subject} [dim]{obj.predicate}[/dim] {obj.object}")
    if hasattr(obj, 'title'):
        lines.append(f"\n  {obj.title}")
        lines.append(f"  {obj.description}")
    if hasattr(obj, 'label') and obj.label:
        lines.append(f"\n  Label: {obj.label}")
    if hasattr(obj, 'confidence'):
        lines.append(f"  Confidence: {obj.confidence.level:.0%}")
    if hasattr(obj, 'modality'):
        lines.append(f"  Modality: {obj.modality.value}")
    if hasattr(obj, 'notes') and obj.notes:
        lines.append(f"  Notes: {obj.notes}")
    if hasattr(obj, 'premises'):
        lines.append(f"  Premises: {len(obj.premises)}")
        for pid in obj.premises:
            p = s.get(pid)
            plabel = f"{p.subject} {p.predicate} {p.object}" if hasattr(p, 'subject') else getattr(p, 'title', pid[:12])
            lines.append(f"    → {short_id(pid)} {plabel}")
    if hasattr(obj, 'conclusion'):
        c = s.get(obj.conclusion)
        clabel = f"{c.subject} {c.predicate} {c.object}" if c and hasattr(c, 'subject') else obj.conclusion[:12]
        lines.append(f"  Conclusion: {short_id(obj.conclusion)} {clabel}")
    if hasattr(obj, 'defeaters') and obj.defeaters:
        lines.append(f"  Defeaters: {len(obj.defeaters)}")
        for d in obj.defeaters:
            lines.append(f"    [{d.status.value}] {d.type.value}: {d.description}")

    console.print(Panel("\n".join(lines)))


@cli.command("bayes")
@click.option("--prior", type=float, required=True)
@click.option("--likelihood-true", type=float, required=True)
@click.option("--likelihood-false", type=float, required=True)
@click.pass_context
def bayes(ctx, prior, likelihood_true, likelihood_false):
    """Run a Bayesian update."""
    posterior = bayesian_update(prior, likelihood_true, likelihood_false)
    console.print(f"\n  Prior:            {prior:.2%}")
    console.print(f"  P(E|H):          {likelihood_true:.2%}")
    console.print(f"  P(E|¬H):         {likelihood_false:.2%}")
    console.print(f"  [bold]Posterior:      {posterior:.2%}[/bold]")
    console.print(f"  Δ:                {posterior - prior:+.2%}\n")


@cli.command("export")
@click.option("--format", "fmt", type=click.Choice(["json"]), default="json")
@click.option("--output", "-o", default="export.json")
@click.pass_context
def export_cmd(ctx, fmt, output):
    """Export all objects."""
    s = get_store(ctx.obj["home"])
    from epist.store import _serialize
    data = {
        "claims": [_serialize(c) for c in s.claims.values()],
        "evidence": [_serialize(e) for e in s.evidence.values()],
        "arguments": [_serialize(a) for a in s.arguments.values()],
        "evaluations": [_serialize(e) for e in s.evaluations.values()],
        "predictions": [_serialize(p) for p in s.predictions.values()],
        "foundations": s.foundations,
    }
    Path(output).write_text(json.dumps(data, indent=2, default=str))
    console.print(f"[green]✓[/green] Exported {len(s.all_objects())} objects to {output}")


# ── LLM-powered commands ─────────────────────────────────────────────

@cli.command("generate")
@click.argument("thesis", required=False)
@click.option("--workspace", "-w", default=None, help="Create workspace at this path")
@click.pass_context
def generate(ctx, thesis, workspace):
    """Generate a full argument graph from a thesis statement.

    Creates a git-versioned workspace. Each generate/enhance cycle is a commit.
    """
    from epist.agent import generate_full_graph, count_subgraph, compute_summary

    if not thesis:
        if not sys.stdin.isatty():
            thesis = sys.stdin.read().strip()
        else:
            thesis = click.prompt("Enter thesis")
    if not thesis:
        console.print("[red]No thesis provided.[/red]")
        return

    # --workspace overrides --home / EPIST_HOME
    if workspace:
        ctx.obj["home"] = workspace

    s = get_store(ctx.obj["home"])

    # Clear any existing data (one thesis per workspace)
    s.clear()

    # Ensure git repo
    if not s.is_git_repo():
        s.git_init()

    with console.status("[bold cyan]Generating argument graph...[/bold cyan]"):
        try:
            thesis_id = generate_full_graph(s, thesis)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            return

    # Write summary.md
    try:
        result = compute_summary(s, thesis_id)
        (s.home / "summary.md").write_text(result["markdown"])
    except Exception:
        pass  # non-fatal

    counts = count_subgraph(s, thesis_id)

    # Git commit
    short_thesis = thesis[:72] + ("..." if len(thesis) > 72 else "")
    s.git_commit(
        f"[generate] {short_thesis}\n\n"
        f"Thesis: {thesis}\n"
        f"Objects: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments, {counts['assumptions']} assumptions, "
        f"{counts['defeaters']} defeaters"
    )

    console.print(f"\n[green]✓[/green] Generated argument graph")
    console.print(f"  {thesis[:80]}")
    console.print(
        f"\n  Created: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments, {counts['assumptions']} assumptions, "
        f"{counts['defeaters']} defeaters"
    )
    console.print(f"  [dim]Workspace: {s.home}[/dim]\n")


@cli.command("summary")
@click.argument("thesis_id", required=False)
@click.pass_context
def summary(ctx, thesis_id):
    """Show thesis summary and save as summary.md."""
    from epist.agent import compute_summary

    s = get_store(ctx.obj["home"])
    if not s.claims:
        console.print("[dim]No claims yet. Use 'generate' to create an argument graph.[/dim]")
        return

    try:
        result = compute_summary(s, thesis_id)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return

    if not result.get("thesis"):
        console.print("[dim]No thesis found.[/dim]")
        return

    # Write summary.md
    md_text = result["markdown"]
    (s.home / "summary.md").write_text(md_text)

    # Commit if in a git repo and content changed
    if s.is_git_repo():
        thesis_label = result["thesis"]["notes"] or result["thesis"]["label"]
        short_label = thesis_label[:72] + ("..." if len(thesis_label) > 72 else "")
        assessment = result.get("confidence_assessment", {})
        s.git_commit(
            f"[analysis] {short_label}\n\n"
            f"Confidence: {assessment.get('thesis_confidence', 0):.0%}\n"
            f"Active defeaters: {assessment.get('active_defeaters', 0)}\n"
            f"ATMS: {assessment.get('atms_status', 'unknown')}"
        )

    console.print()
    console.print(Markdown(md_text))


@cli.command("enhance")
@click.argument("thesis_id", required=False)
@click.option("--yes", "-y", is_flag=True, help="Auto-accept enhancement")
@click.pass_context
def enhance(ctx, thesis_id, yes):
    """Suggest an enhanced thesis, then regenerate the argument graph."""
    from epist.agent import (
        compute_summary, enhance_thesis, generate_full_graph, count_subgraph,
    )

    s = get_store(ctx.obj["home"])
    if not s.claims:
        console.print("[dim]No claims yet. Use 'generate' to create an argument graph.[/dim]")
        return

    # Resolve thesis
    summary_data = compute_summary(s, thesis_id)
    if not summary_data.get("thesis"):
        console.print("[dim]No thesis found.[/dim]")
        return

    thesis_info = summary_data["thesis"]
    resolved_id = thesis_info["id"]
    console.print(f"\n[bold]Current thesis:[/bold] {thesis_info['notes'] or thesis_info['label']}")
    console.print(f"[dim]Confidence: {thesis_info['confidence']:.0%}[/dim]\n")

    with console.status("[bold cyan]Analyzing and enhancing thesis...[/bold cyan]"):
        try:
            result = enhance_thesis(s, resolved_id)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            return

    console.print(Panel(
        f"[bold green]Enhanced thesis:[/bold green]\n{result['enhanced_thesis']}\n\n"
        f"[bold]Rationale:[/bold] {result['rationale']}",
        title="Suggested Enhancement",
    ))

    if result.get("changes"):
        console.print("\n[bold]Changes:[/bold]")
        for ch in result["changes"]:
            tag = ch.get("type", "change")
            console.print(f"  [{tag}] {ch['description']}")

    console.print()
    if not yes and not click.confirm("Accept and generate new graph?", default=False):
        console.print("[dim]Enhancement not applied.[/dim]")
        return

    # Clear and regenerate — git preserves the old state
    enhanced_text = result["enhanced_thesis"]
    rationale = result.get("rationale", "")
    changes = result.get("changes", [])

    s.clear()

    with console.status("[bold cyan]Generating new argument graph...[/bold cyan]"):
        try:
            new_thesis_id = generate_full_graph(s, enhanced_text)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            return

    # Write summary.md
    try:
        new_summary = compute_summary(s, new_thesis_id)
        (s.home / "summary.md").write_text(new_summary["markdown"])
    except Exception:
        pass

    counts = count_subgraph(s, new_thesis_id)

    # Build commit message
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

    console.print(f"\n[green]✓[/green] Enhanced thesis — new graph generated")
    console.print(f"  {enhanced_text[:80]}")
    console.print(
        f"\n  Created: {counts['claims']} claims, {counts['evidence']} evidence, "
        f"{counts['arguments']} arguments\n"
    )


@cli.command("versions")
@click.pass_context
def versions(ctx):
    """Show version history from git log."""
    s = get_store(ctx.obj["home"])

    if not s.is_git_repo():
        console.print("[dim]Not a git-backed workspace. Use 'generate --workspace' to create one.[/dim]")
        return

    commits = s.git_log()
    if not commits:
        console.print("[dim]No history yet.[/dim]")
        return

    # Filter to generate/enhance commits (skip analysis and init)
    version_commits = [c for c in commits if c["subject"].startswith(("[generate]", "[enhance]"))]
    version_commits.reverse()  # oldest first

    if not version_commits:
        console.print("[dim]No thesis versions found in history.[/dim]")
        return

    console.print(f"\n[bold]Version history ({len(version_commits)} versions):[/bold]\n")
    for i, c in enumerate(version_commits):
        version_num = i + 1
        tag = "generate" if "[generate]" in c["subject"] else "enhance"
        subject = c["subject"].replace("[generate] ", "").replace("[enhance] ", "")
        is_current = (i == len(version_commits) - 1)
        marker = " [bold yellow]<-- current[/bold yellow]" if is_current else ""

        console.print(f"  [bold]v{version_num}[/bold] [dim]{c['hash'][:8]}[/dim] [{c['date'][:10]}]{marker}")
        console.print(f"    [dim][{tag}][/dim] {subject}")
        if c["body"]:
            # Show thesis line from body
            for line in c["body"].split("\n"):
                if line.startswith("Thesis: "):
                    thesis_text = line[8:]
                    if len(thesis_text) > 100:
                        thesis_text = thesis_text[:97] + "..."
                    console.print(f"    {thesis_text}")
                    break
                elif line.startswith("Rationale: "):
                    console.print(f"    [italic]{line[11:]}[/italic]")
        console.print()


@cli.command("diff")
@click.argument("revision", default="HEAD~1")
@click.pass_context
def diff_cmd(ctx, revision):
    """Show what changed between versions (wraps git diff)."""
    s = get_store(ctx.obj["home"])
    if not s.is_git_repo():
        console.print("[dim]Not a git-backed workspace.[/dim]")
        return

    result = s._git("diff", "--stat", revision, check=False)
    if result.returncode != 0:
        console.print(f"[red]Error:[/red] {result.stderr.strip()}")
        return
    if not result.stdout.strip():
        console.print("[dim]No changes.[/dim]")
        return
    console.print(result.stdout)

    # Also show claim-level diff for summary.md if it exists
    detail = s._git("diff", revision, "--", "summary.md", check=False)
    if detail.stdout.strip():
        console.print(Panel(detail.stdout.strip()[:2000], title="summary.md changes"))


@cli.command("theses")
@click.pass_context
def theses(ctx):
    """List all thesis lineages (legacy multi-thesis workspaces)."""
    from epist.agent import list_theses

    s = get_store(ctx.obj["home"])
    if not s.claims:
        console.print("[dim]No claims yet. Use 'generate' to create an argument graph.[/dim]")
        return

    results = list_theses(s)
    if not results:
        console.print("[dim]No theses found.[/dim]")
        return

    table = Table(box=box.SIMPLE)
    table.add_column("ID", style="cyan", width=14)
    table.add_column("Thesis")
    table.add_column("Versions", justify="right")
    table.add_column("Support", justify="right")

    for r in results:
        label = r["notes"] or r["label"]
        if len(label) > 60:
            label = label[:57] + "..."
        table.add_row(
            short_id(r["id"]),
            label,
            str(r["version_count"]),
            str(r["support_count"]),
        )

    console.print(table)


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
