#!/usr/bin/env python3
"""
Demo: Build an epistemic graph around the thesis that
coordination failures are fundamentally epistemological failures.

Run: python demo.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ["EPIST_HOME"] = str(Path(__file__).parent / "demo-workspace")

from rich.console import Console
from rich.panel import Panel

from epist.model import *
from epist.store import Store
from epist.engine import (
    compute_atms, check_coherence, find_blind_spots,
    surface_assumptions, stress_test, ATMSStatus,
)

console = Console()
store = Store(Path("demo-workspace"))
store.init_workspace()

console.print(Panel("[bold]Epistemic Workbench Demo[/bold]\nBuilding: Coordination failures are epistemological failures"))

# ── Core thesis ───────────────────────────────────────────────────────

thesis = store.add_claim(Claim(
    subject="coordination-failures",
    predicate="are-caused-by",
    object="epistemic-fragmentation",
    confidence=Confidence(0.85),
    modality=Modality.EMPIRICAL,
    notes="Core thesis: most coordination failures aren't preference disagreements but breakdowns in shared epistemic infrastructure",
))

# ── Supporting claims ─────────────────────────────────────────────────

identity_claim = store.add_claim(Claim(
    subject="identity-infrastructure",
    predicate="is-prerequisite-for",
    object="trust-networks",
    confidence=Confidence(0.90),
    modality=Modality.ANALYTIC,
    notes="You can't build trust without knowing who you're trusting",
))

epistemic_coord = store.add_claim(Claim(
    subject="epistemic-coordination",
    predicate="requires",
    object="shared-verifiable-facts",
    confidence=Confidence(0.95),
    modality=Modality.ANALYTIC,
    notes="Coordination requires common ground; common ground requires shared facts",
))

captured_identity = store.add_claim(Claim(
    subject="captured-identity-systems",
    predicate="prevent",
    object="voluntary-coordination",
    confidence=Confidence(0.80),
    modality=Modality.EMPIRICAL,
    notes="When identity is controlled by platforms, coordination is limited to what platforms allow",
))

osmio_claim = store.add_claim(Claim(
    subject="PKI-based-identity",
    predicate="enables",
    object="accountable-anonymity",
    confidence=Confidence(0.75),
    modality=Modality.EMPIRICAL,
    notes="Osmio's architecture: verify identity cryptographically without exposing it",
))

commons_claim = store.add_claim(Claim(
    subject="communities",
    predicate="should-be-able-to",
    object="fork-epistemic-foundations",
    confidence=Confidence(0.80),
    modality=Modality.NORMATIVE,
    notes="Like forking code — if a community disagrees about foundational assumptions, they should be able to fork and maintain their own branch",
))

dkg_claim = store.add_claim(Claim(
    subject="decentralized-knowledge-graphs",
    predicate="can-serve-as",
    object="epistemic-infrastructure",
    confidence=Confidence(0.65),
    modality=Modality.EMPIRICAL,
    notes="OriginTrail DKG as a possible substrate for knowledge asset verification",
))

# ── Evidence ──────────────────────────────────────────────────────────

replication = store.add_evidence(Evidence(
    title="Replication crisis data",
    description="Only 36% of psychology studies replicate (Open Science Collaboration, 2015)",
    evidence_type=EvidenceType.STATISTICAL,
    source="Open Science Collaboration, Science 349(6251), 2015",
    reliability=0.90,
))

ostrom = store.add_evidence(Evidence(
    title="Ostrom commons governance",
    description="Elinor Ostrom demonstrated that polycentric governance outperforms both pure market and pure state for commons management",
    evidence_type=EvidenceType.DOCUMENT,
    source="Governing the Commons, 1990",
    reliability=0.85,
))

axelrod = store.add_evidence(Evidence(
    title="Axelrod cooperation dynamics",
    description="Robert Axelrod's tournament showed cooperation emerges from repeated interaction with known partners (identity → cooperation)",
    evidence_type=EvidenceType.EXPERIMENT,
    source="The Evolution of Cooperation, 1984",
    reliability=0.85,
))

osmio_docs = store.add_evidence(Evidence(
    title="Osmio PKI operational history",
    description="Osmio chartered at ITU Geneva 2005, operating PKI-based digital identity infrastructure as digital municipality",
    evidence_type=EvidenceType.DOCUMENT,
    source="Osmio organizational documents",
    reliability=0.80,
))

platform_data = store.add_evidence(Evidence(
    title="Platform identity capture",
    description="Facebook, Google, Twitter control identity for 4B+ users; deplatforming = identity death in those ecosystems",
    evidence_type=EvidenceType.OBSERVATION,
    reliability=0.75,
))

# ── Arguments ─────────────────────────────────────────────────────────

arg1 = store.add_argument(Argument(
    conclusion=thesis.id,
    premises=[replication.id, epistemic_coord.id],
    pattern=InferencePattern.ABDUCTION,
    label="Replication crisis as epistemic infrastructure failure",
    confidence=Confidence(0.75),
))

arg2 = store.add_argument(Argument(
    conclusion=thesis.id,
    premises=[ostrom.id, identity_claim.id],
    pattern=InferencePattern.ABDUCTION,
    label="Polycentric governance requires identity infrastructure",
    confidence=Confidence(0.70),
))

arg3 = store.add_argument(Argument(
    conclusion=identity_claim.id,
    premises=[axelrod.id],
    pattern=InferencePattern.INDUCTION,
    label="Axelrod: identity enables cooperation",
    confidence=Confidence(0.80),
))

arg4 = store.add_argument(Argument(
    conclusion=captured_identity.id,
    premises=[platform_data.id],
    pattern=InferencePattern.INDUCTION,
    label="Platform monopoly evidence",
    confidence=Confidence(0.75),
))

arg5 = store.add_argument(Argument(
    conclusion=osmio_claim.id,
    premises=[osmio_docs.id],
    pattern=InferencePattern.TESTIMONY,
    label="Osmio operational evidence",
    confidence=Confidence(0.70),
))

# Add a defeater to the DKG claim
dkg_arg = store.add_argument(Argument(
    conclusion=dkg_claim.id,
    premises=[osmio_claim.id],
    pattern=InferencePattern.ANALOGY,
    label="PKI + DKG as epistemic substrate",
    confidence=Confidence(0.55),
    defeaters=[Defeater(
        type=DefeaterType.UNDERCUTTING,
        description="DKG centralization concerns: OriginTrail's paranet structure may reproduce the centralization it claims to solve",
        status=DefeaterStatus.ACTIVE,
    )],
))

# Normative argument without normative premise (will trigger Hume's guillotine)
arg_fork = store.add_argument(Argument(
    conclusion=commons_claim.id,
    premises=[ostrom.id, epistemic_coord.id],
    pattern=InferencePattern.ABDUCTION,
    label="Communities should fork foundations (from Ostrom + epistemic coordination)",
    confidence=Confidence(0.70),
))


# ── Run all analysis ──────────────────────────────────────────────────

console.print("\n" + "═" * 60)
console.print("[bold]1. ATMS STATUS[/bold]")
console.print("═" * 60 + "\n")

atms = compute_atms(store)
for oid, st in atms.items():
    obj = store.get(oid)
    if not obj:
        continue
    label = ""
    if hasattr(obj, 'subject'):
        label = f"{obj.subject} {obj.predicate} {obj.object}"
    elif hasattr(obj, 'title'):
        label = obj.title
    elif hasattr(obj, 'label'):
        label = obj.label or "(unlabeled)"
    c = "green" if st == ATMSStatus.ACCEPTED else "yellow" if st == ATMSStatus.PROVISIONAL else "red"
    console.print(f"  [{c}]{st:12s}[/{c}] {type(obj).__name__:10s} {label[:60]}")


console.print("\n" + "═" * 60)
console.print("[bold]2. COHERENCE CHECK[/bold]")
console.print("═" * 60 + "\n")

issues = check_coherence(store)
if issues:
    for iss in issues:
        sev_colors = {"error": "red", "warning": "yellow", "info": "blue"}
        c = sev_colors.get(iss["severity"], "white")
        console.print(f"  [{c}]{iss['severity'].upper():8s}[/{c}] {iss['check']}")
        console.print(f"           {iss['message']}\n")
else:
    console.print("  [green]✓ No coherence issues[/green]\n")


console.print("═" * 60)
console.print("[bold]3. BLIND SPOT SCAN[/bold]")
console.print("═" * 60 + "\n")

spots = find_blind_spots(store)
if spots:
    for sp in spots:
        c = "red" if sp["risk"] == "high" else "yellow"
        console.print(f"  [{c}]▲ {sp['risk'].upper():6s}[/{c}] {sp['message']}\n")
else:
    console.print("  [green]✓ No blind spots[/green]\n")


console.print("═" * 60)
console.print("[bold]4. ASSUMPTION SURFACING (core thesis)[/bold]")
console.print("═" * 60 + "\n")

assumptions = surface_assumptions(store, thesis.id)
if assumptions:
    for a in assumptions:
        indent = "  " * (a["depth"] + 1)
        icon = "📌" if a["type"] == "explicit" else "👁"
        supported = "[green]supported[/green]" if a["supported"] else "[red]UNSUPPORTED[/red]"
        console.print(f"  {indent}{icon} [{a['type']}] {a['label']}")
        console.print(f"  {indent}   {supported}")
else:
    console.print("  [dim]No assumptions traced[/dim]\n")


console.print("\n" + "═" * 60)
console.print("[bold]5. STRESS TEST (core thesis)[/bold]")
console.print("═" * 60 + "\n")

result = stress_test(store, thesis.id)
if result:
    console.print("[bold red]  Attack Surfaces:[/bold red]")
    for a in result["attack_surfaces"]:
        console.print(f"    ⚔  {a}")
    console.print("\n[bold yellow]  Crux Questions:[/bold yellow]")
    for q in result["crux_questions"]:
        console.print(f"    ?  {q}")
    console.print("\n[bold blue]  Steelman Opposition:[/bold blue]")
    for p in result["steelman_prompts"]:
        console.print(f"    💪 {p}")


console.print("\n" + "═" * 60)
console.print("[bold]SUMMARY[/bold]")
console.print("═" * 60 + "\n")

console.print(f"  Claims:     {len(store.claims)}")
console.print(f"  Evidence:   {len(store.evidence)}")
console.print(f"  Arguments:  {len(store.arguments)}")
console.print(f"  Issues:     {len(issues)}")
console.print(f"  Blind spots: {len(spots)}")
console.print(f"  ATMS defeated: {sum(1 for s in atms.values() if s == ATMSStatus.DEFEATED)}")
console.print()
