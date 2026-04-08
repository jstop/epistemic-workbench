"""
Shared LLM functions for thesis generation, enhancement, and analysis.
Used by both the CLI and the web server.
"""
import json
import os
from pathlib import Path

import anthropic

from epist.model import (
    Claim, Evidence, Argument, Confidence, Defeater,
    Modality, EvidenceType, InferencePattern,
    DefeaterType, DefeaterStatus,
)
from epist.engine import (
    compute_atms, ATMSStatus, check_coherence, find_blind_spots,
    surface_assumptions,
)


# ── Prompts ──────────────────────────────────────────────────────────

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
- CRITICAL: The thesis is the single root. Every claim must connect back to the thesis through argument chains. Do NOT create orphan sub-claims with no path to the thesis.
- Create at least one argument with conclusion_ref "thesis" that uses claims as premises, forming a converging tree
- Surface 2-3 unstated assumptions the thesis depends on
- Generate 1-2 defeaters (genuine challenges, not strawmen)
- Use realistic confidence levels (not all high)
- The "modality" field should be "empirical" for factual claims, "analytic" for logical/definitional claims, "normative" for value claims
- Reference format: "thesis" for the thesis, "claim_0" for first claim, "evidence_0" for first evidence, "argument_0" for first argument
- Be intellectually honest - include real weaknesses

Return ONLY the JSON object, no other text.
"""

ENHANCE_PROMPT = """\
You are an epistemic analyst. Given a thesis and the full analysis of its argument graph, suggest a refined version that is more precise, nuanced, and defensible.

Your enhancement should:
1. Preserve the core claim's intent and direction
2. Add qualifiers or scope limitations where the analysis reveals vulnerabilities
3. Acknowledge or incorporate key objections
4. Strengthen language where evidence strongly supports it
5. NOT completely change the thesis — refine it

Return a JSON object with exactly this structure:
{
  "enhanced_thesis": "The refined thesis statement in natural language",
  "rationale": "A 2-3 sentence explanation of why this version is stronger",
  "changes": [
    {
      "type": "scope|precision|qualifier|strength|acknowledgment",
      "description": "What was changed and why"
    }
  ]
}

Return ONLY the JSON object, no other text.
"""


# ── Client ───────────────────────────────────────────────────────────

def get_client():
    """Get Anthropic client, loading key from ~/.api_keys/env if needed."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        api_keys_file = Path.home() / ".api_keys" / "env"
        if api_keys_file.exists():
            for line in api_keys_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    os.environ["ANTHROPIC_API_KEY"] = val
                    break
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set. Set it in env or ~/.api_keys/env")
    return anthropic.Anthropic(api_key=api_key, max_retries=5)


def _parse_llm_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from LLM response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]
    return json.loads(raw)


# ── Generate ─────────────────────────────────────────────────────────

def write_thesis_md(store, thesis_text: str):
    """Write thesis.md to the workspace."""
    (store.home / "thesis.md").write_text(thesis_text + "\n")


def generate_full_graph(store, thesis_text: str) -> str:
    """Call Claude to decompose thesis, create all objects. Returns thesis_id."""
    write_thesis_md(store, thesis_text)
    client = get_client()

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=16000,
        messages=[{
            "role": "user",
            "content": f"{GENERATE_PROMPT}\n\nThesis: {thesis_text}",
        }],
    )
    data = _parse_llm_json(response.content[0].text)

    created_ids = {}

    # 1. Create thesis
    t = data["thesis"]
    thesis = store.add_claim(Claim(
        subject=t["subject"], predicate=t["predicate"], object=t["object"],
        confidence=Confidence(t.get("confidence", 0.7)),
        modality=Modality(t.get("modality", "empirical")),
        notes=thesis_text,
        is_root=True,
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

    return thesis.id


def count_subgraph(store, thesis_id: str) -> dict:
    """Count objects in a thesis's subgraph."""
    thesis = store.claims[thesis_id]
    subgraph_nodes = set()
    subgraph_args = set()

    def walk(node_id):
        if node_id in subgraph_nodes:
            return
        subgraph_nodes.add(node_id)
        for aid, a in store.arguments.items():
            if a.conclusion == node_id:
                subgraph_args.add(aid)
                for pid in a.premises:
                    walk(pid)
        c = store.claims.get(node_id)
        if c:
            for assumed_id in c.assumes:
                walk(assumed_id)

    walk(thesis_id)
    return {
        "claims": sum(1 for nid in subgraph_nodes if nid in store.claims),
        "evidence": sum(1 for nid in subgraph_nodes if nid in store.evidence),
        "arguments": len(subgraph_args),
        "assumptions": len(thesis.assumes),
        "defeaters": sum(len(store.arguments[aid].defeaters) for aid in subgraph_args if aid in store.arguments),
    }


# ── Summary ──────────────────────────────────────────────────────────

def compute_summary(store, thesis_id=None) -> dict:
    """Compute summary data for a thesis. Returns dict with markdown, thesis info, etc."""
    if not store.claims:
        return {"markdown": "No claims yet.", "thesis": None}

    atms = compute_atms(store)

    # Use provided thesis_id or find root thesis
    if thesis_id and thesis_id in store.claims:
        thesis = store.claims[thesis_id]
    else:
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
    subgraph_nodes = set()
    subgraph_args = set()

    def walk(node_id):
        if node_id in subgraph_nodes:
            return
        subgraph_nodes.add(node_id)
        for aid, a in store.arguments.items():
            if a.conclusion == node_id:
                subgraph_args.add(aid)
                for pid in a.premises:
                    walk(pid)
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

    assumptions = surface_assumptions(store, thesis_id)

    coherence = check_coherence(store)
    blind_spots = find_blind_spots(store)
    coherence = [c for c in coherence if any(nid[:12] in c.get("message", "") for nid in subgraph_nodes) or c.get("severity") == "high"]
    blind_spots = [b for b in blind_spots if any(nid[:12] in b.get("message", "") for nid in subgraph_nodes) or b.get("risk") == "high"]

    subgraph_arg_objs = [store.arguments[aid] for aid in subgraph_args]
    arg_confidences = [a.confidence.level for a in subgraph_arg_objs]
    claims_in_subgraph = [nid for nid in subgraph_nodes if nid in store.claims]
    claims_with_support = len(set(a.conclusion for a in subgraph_arg_objs))
    active_defeaters = sum(1 for d in all_defeaters if d["status"] == "active")
    conceded_defeaters = sum(1 for d in all_defeaters if d["status"] == "conceded")

    assessment = {
        "thesis_confidence": thesis.confidence.level,
        "average_argument_strength": sum(arg_confidences) / len(arg_confidences) if arg_confidences else 0,
        "claims_supported": f"{claims_with_support}/{len(claims_in_subgraph)}",
        "active_defeaters": active_defeaters,
        "conceded_defeaters": conceded_defeaters,
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
                    status_marker = {
                        "active": "ACTIVE",
                        "conceded": "CONCEDED",
                        "answered": "answered",
                        "withdrawn": "withdrawn",
                    }.get(d["status"], d["status"])
                    md.append(f"- **Objection [{status_marker}]:** {d['description']}")
                    if d["response"]:
                        label = "Conceded" if d["status"] == "conceded" else "Response"
                        md.append(f"  - *{label}:* {d['response']}")
            md.append("")

    active = [d for d in all_defeaters if d["status"] == "active"]
    answered = [d for d in all_defeaters if d["status"] == "answered"]
    conceded = [d for d in all_defeaters if d["status"] == "conceded"]

    if all_defeaters:
        md.append("## Known Objections")
        md.append("")
        if active:
            md.append("### Unresolved")
            for d in active:
                md.append(f"- [{d['type']}] {d['description']} *(on: {d['argument_label']})*")
            md.append("")
        if conceded:
            md.append("### Conceded (acknowledged limitations)")
            for d in conceded:
                md.append(f"- [{d['type']}] {d['description']} *(on: {d['argument_label']})*")
                if d["response"]:
                    md.append(f"  - *Conceded:* {d['response']}")
            md.append("")
        if answered:
            md.append("### Answered (rebutted)")
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
    if assessment.get("conceded_defeaters"):
        md.append(f"- **Conceded defeaters:** {assessment['conceded_defeaters']}")
    md.append(f"- **Overall status:** {assessment['atms_status']}")

    return {
        "thesis": {
            "id": thesis_id,
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


# ── Enhance ──────────────────────────────────────────────────────────

def enhance_thesis(store, thesis_id: str) -> dict:
    """Suggest an enhanced version. Returns {enhanced_thesis, rationale, changes}."""
    summary = compute_summary(store, thesis_id)
    if not summary or not summary.get("thesis"):
        raise RuntimeError("Thesis not found")

    thesis = summary["thesis"]
    supporting = summary["supporting_arguments"]
    objections = summary["objections"]
    assumptions = summary["assumptions"]
    issues = summary["unresolved_issues"]
    assessment = summary["confidence_assessment"]

    active_objections = [o for o in objections if o["status"] == "active"]
    conceded_objections = [o for o in objections if o["status"] == "conceded"]

    context_parts = [f"Original thesis: {thesis['notes'] or thesis['label']}"]

    if supporting:
        lines = []
        for a in supporting:
            lines.append(f"- {a['label']} (confidence: {a['confidence']:.0%}, pattern: {a['pattern']})")
            for p in a["premises"]:
                lines.append(f"  - [{p['type']}] {p['label']}")
        context_parts.append(f"Supporting arguments ({len(supporting)}):\n" + "\n".join(lines))

    if conceded_objections:
        lines = [
            f"- [{o['type']}] {o['description']}"
            + (f"\n    Conceded: {o['response']}" if o.get("response") else "")
            for o in conceded_objections
        ]
        context_parts.append(
            f"Conceded objections ({len(conceded_objections)}) — these are valid criticisms "
            f"the author has accepted; the refined thesis should explicitly acknowledge them "
            f"and narrow scope or add caveats accordingly:\n" + "\n".join(lines)
        )

    if active_objections:
        lines = [f"- [{o['type']}] {o['description']}" for o in active_objections]
        context_parts.append(f"Active objections ({len(active_objections)}):\n" + "\n".join(lines))

    if assumptions:
        lines = [f"- {a['label']} ({'supported' if a['supported'] else 'UNSUPPORTED'})" for a in assumptions]
        context_parts.append(f"Assumptions ({len(assumptions)}):\n" + "\n".join(lines))

    blind_spots = issues.get("blind_spots", [])
    coherence = issues.get("coherence", [])
    if blind_spots or coherence:
        lines = [f"- {i['message']}" for i in coherence] + [f"- {b['message']}" for b in blind_spots]
        context_parts.append(f"Unresolved issues:\n" + "\n".join(lines))

    context_parts.append(
        f"Confidence assessment:\n"
        f"- Thesis confidence: {assessment['thesis_confidence']:.0%}\n"
        f"- Average argument strength: {assessment['average_argument_strength']:.0%}\n"
        f"- Active defeaters: {assessment['active_defeaters']}\n"
        f"- ATMS status: {assessment['atms_status']}"
    )

    user_message = ENHANCE_PROMPT + "\n\n" + "\n\n".join(context_parts)
    client = get_client()

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": user_message}],
    )
    return _parse_llm_json(response.content[0].text)


# ── Accept Enhanced ──────────────────────────────────────────────────

def accept_enhanced_thesis(store, thesis_id: str, enhanced_thesis: str,
                           rationale: str = "", changes: list = None) -> dict:
    """Generate new graph for enhanced thesis, link versions. Returns {new_thesis_id, version_number}."""
    old_thesis = store.claims.get(thesis_id)
    if not old_thesis:
        raise RuntimeError("Original thesis not found")

    new_thesis_id = generate_full_graph(store, enhanced_thesis)

    # Patch the new thesis with version linkage
    new_thesis = store.claims[new_thesis_id]
    new_thesis.previous_version = thesis_id
    new_thesis.version_meta = {
        "rationale": rationale,
        "changes": changes or [],
    }
    store.save()

    # Compute version number by walking backward
    version = 1
    cursor = thesis_id
    while cursor:
        version += 1
        prev = store.claims.get(cursor)
        cursor = prev.previous_version if prev else None

    return {"new_thesis_id": new_thesis_id, "version_number": version}


# ── Versions ─────────────────────────────────────────────────────────

def get_thesis_versions(store, thesis_id: str) -> dict:
    """Walk version chain. Returns {current_index, versions[]}."""
    claim = store.claims.get(thesis_id)
    if not claim:
        raise RuntimeError("Thesis not found")

    # Walk backward to find root
    root_id = thesis_id
    visited = {thesis_id}
    while True:
        c = store.claims.get(root_id)
        if not c or not c.previous_version:
            break
        if c.previous_version in visited:
            break
        visited.add(c.previous_version)
        root_id = c.previous_version

    # Build forward index
    forward = {}
    for cid, c in store.claims.items():
        if c.previous_version and c.previous_version in store.claims:
            forward[c.previous_version] = cid

    # Walk forward from root
    versions = []
    cursor = root_id
    current_index = 0
    while cursor:
        c = store.claims[cursor]
        version_num = len(versions) + 1
        entry = {
            "thesis_id": cursor,
            "version": version_num,
            "label": f"{c.subject} {c.predicate} {c.object}",
            "notes": c.notes,
            "rationale": c.version_meta.get("rationale") if c.version_meta else None,
            "changes": c.version_meta.get("changes", []) if c.version_meta else [],
            "created_at": c.created_at,
        }
        versions.append(entry)
        if cursor == thesis_id:
            current_index = version_num - 1
        cursor = forward.get(cursor)

    return {"current_index": current_index, "versions": versions}


# ── List Theses ──────────────────────────────────────────────────────

def list_theses(store) -> list:
    """Return root theses grouped by lineage, showing only the latest version per lineage."""
    tagged_roots = {cid: c for cid, c in store.claims.items() if getattr(c, "is_root", False)}

    support_count = {}
    for a in store.arguments.values():
        support_count[a.conclusion] = support_count.get(a.conclusion, 0) + 1

    if tagged_roots:
        root_ids = list(tagged_roots.keys())
    else:
        premise_ids = set()
        conclusion_ids = set()
        for a in store.arguments.values():
            conclusion_ids.add(a.conclusion)
            for pid in a.premises:
                premise_ids.add(pid)
        root_ids = list(conclusion_ids - premise_ids) or list(conclusion_ids)

    # Build forward index for version chains
    forward = {}
    for cid, c in store.claims.items():
        if c.previous_version and c.previous_version in store.claims:
            forward[c.previous_version] = cid

    # For each root thesis, walk forward to find the latest version and count versions
    lineage_latest = {}
    for cid in root_ids:
        c = store.claims.get(cid)
        if not c:
            continue
        # Walk backward to find lineage root
        lineage_root = cid
        visited = {cid}
        while True:
            lc = store.claims.get(lineage_root)
            if not lc or not lc.previous_version:
                break
            if lc.previous_version in visited:
                break
            visited.add(lc.previous_version)
            lineage_root = lc.previous_version

        if lineage_root in lineage_latest:
            continue

        # Walk forward from lineage root to find latest
        cursor = lineage_root
        count = 1
        while cursor in forward:
            cursor = forward[cursor]
            count += 1
        lineage_latest[lineage_root] = (cursor, count)

    # Build results showing only the latest version per lineage
    latest_ids = [info[0] for info in lineage_latest.values()]
    ranked = sorted(latest_ids, key=lambda cid: support_count.get(cid, 0), reverse=True)
    results = []
    for cid in ranked:
        c = store.claims.get(cid)
        if c:
            version_count = 1
            for info in lineage_latest.values():
                if info[0] == cid:
                    version_count = info[1]
                    break
            results.append({
                "id": cid,
                "label": f"{c.subject} {c.predicate} {c.object}",
                "notes": c.notes,
                "support_count": support_count.get(cid, 0),
                "version_count": version_count,
            })
    return results
