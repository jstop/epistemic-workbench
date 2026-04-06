"""
Agent SDK implementation of thesis generation and enhancement.
Uses ClaudeSDKClient with custom MCP tools for graph building,
and raw API with structured outputs for enhancement suggestions.
"""
import json
import os
from pathlib import Path
from typing import Optional

import anyio
from pydantic import BaseModel

from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    ResultMessage,
)

from epist.model import (
    Claim, Evidence, Argument, Confidence, Defeater,
    Modality, EvidenceType, InferencePattern,
    DefeaterType, DefeaterStatus,
)

# Re-export pure-computation functions from llm.py
from epist.llm import (
    compute_summary,
    count_subgraph,
    list_theses,
    get_thesis_versions,
    write_thesis_md,
    accept_enhanced_thesis,
)


# ── API key ──────────────────────────────────────────────────────────

def _ensure_api_key():
    """Load API key from ~/.api_keys/env if not already set."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        api_keys_file = Path.home() / ".api_keys" / "env"
        if api_keys_file.exists():
            for line in api_keys_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    os.environ["ANTHROPIC_API_KEY"] = val
                    break
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set. Set it in env or ~/.api_keys/env")


# ── MCP tools for graph building ─────────────────────────────────────

def _make_generate_tools(store):
    """Create MCP tools bound to a store instance."""

    @tool(
        "create_claim",
        "Create a claim node in the argument graph. Returns the claim ID.",
        {
            "subject": str,
            "predicate": str,
            "object": str,
            "confidence": float,
            "modality": str,
            "notes": str,
            "is_root": bool,
        },
    )
    async def create_claim(args):
        c = store.add_claim(Claim(
            subject=args["subject"],
            predicate=args["predicate"],
            object=args["object"],
            confidence=Confidence(args.get("confidence", 0.7)),
            modality=Modality(args.get("modality", "empirical")),
            notes=args.get("notes", ""),
            is_root=args.get("is_root", False),
        ))
        label = f"{c.subject} {c.predicate} {c.object}"
        return {"content": [{"type": "text", "text": f"claim_id={c.id}\nlabel={label}"}]}

    @tool(
        "create_evidence",
        "Add a piece of evidence to the argument graph. Returns the evidence ID.",
        {
            "title": str,
            "description": str,
            "evidence_type": str,
            "source": str,
            "reliability": float,
        },
    )
    async def create_evidence(args):
        e = store.add_evidence(Evidence(
            title=args["title"],
            description=args["description"],
            evidence_type=EvidenceType(args.get("evidence_type", "observation")),
            source=args.get("source", ""),
            reliability=args.get("reliability", 0.7),
        ))
        return {"content": [{"type": "text", "text": f"evidence_id={e.id}\ntitle={e.title}"}]}

    @tool(
        "create_argument",
        "Create an argument linking premise IDs to a conclusion ID. "
        "premise_ids is a JSON array of claim/evidence ID strings.",
        {
            "conclusion_id": str,
            "premise_ids": str,
            "pattern": str,
            "label": str,
            "confidence": float,
        },
    )
    async def create_argument(args):
        # Parse premise_ids from JSON string or comma-separated
        raw = args["premise_ids"]
        if raw.startswith("["):
            premise_ids = json.loads(raw)
        else:
            premise_ids = [p.strip() for p in raw.split(",") if p.strip()]

        conc_id = args["conclusion_id"]
        if conc_id not in store.claims and conc_id not in store.evidence:
            return {"content": [{"type": "text", "text": f"ERROR: conclusion_id {conc_id} not found"}]}
        for pid in premise_ids:
            if not store.get(pid):
                return {"content": [{"type": "text", "text": f"ERROR: premise_id {pid} not found"}]}

        a = store.add_argument(Argument(
            conclusion=conc_id,
            premises=premise_ids,
            pattern=InferencePattern(args.get("pattern", "abduction")),
            label=args.get("label", ""),
            confidence=Confidence(args.get("confidence", 0.7)),
        ))
        return {"content": [{"type": "text", "text": f"argument_id={a.id}\nlabel={a.label}"}]}

    @tool(
        "add_defeater",
        "Add an objection/defeater to an existing argument.",
        {
            "argument_id": str,
            "defeater_type": str,
            "description": str,
        },
    )
    async def add_defeater(args):
        arg_id = args["argument_id"]
        if arg_id not in store.arguments:
            return {"content": [{"type": "text", "text": f"ERROR: argument_id {arg_id} not found"}]}
        store.arguments[arg_id].defeaters.append(Defeater(
            type=DefeaterType(args.get("defeater_type", "undercutting")),
            description=args["description"],
            status=DefeaterStatus.ACTIVE,
        ))
        store.save()
        return {"content": [{"type": "text", "text": f"Defeater added to argument {arg_id}"}]}

    @tool(
        "link_assumptions",
        "Link assumption claim IDs to the root thesis. "
        "assumption_ids is a JSON array of claim ID strings.",
        {
            "thesis_id": str,
            "assumption_ids": str,
        },
    )
    async def link_assumptions(args):
        thesis_id = args["thesis_id"]
        thesis = store.claims.get(thesis_id)
        if not thesis:
            return {"content": [{"type": "text", "text": f"ERROR: thesis_id {thesis_id} not found"}]}
        raw = args["assumption_ids"]
        if raw.startswith("["):
            ids = json.loads(raw)
        else:
            ids = [p.strip() for p in raw.split(",") if p.strip()]
        thesis.assumes = ids
        store.save()
        return {"content": [{"type": "text", "text": f"Linked {len(ids)} assumptions to thesis"}]}

    return [create_claim, create_evidence, create_argument,
            add_defeater, link_assumptions]


# ── Generate (Agent SDK with tools) ──────────────────────────────────

GENERATE_SYSTEM = """\
You are an epistemic analyst. Decompose the given thesis into a \
structured argument graph by calling the provided tools.

Work step by step:
1. Create the root thesis claim using create_claim with is_root=true. \
   Use the full thesis text as 'notes'. Use short-hyphenated strings for \
   subject/predicate/object (e.g. "climate-change", "causes", "sea-level-rise").
2. Create 3-5 supporting sub-claims that decompose the thesis into testable parts.
3. Create 2-4 pieces of evidence (real or plausible) supporting the claims.
4. Create arguments linking premises (claim/evidence IDs) to conclusions, \
   building a tree that converges on the thesis. For premise_ids, pass a \
   JSON array like ["id1","id2"]. Every sub-claim must connect back to the \
   thesis through argument chains.
5. Create 2-3 assumption claims (confidence ~0.5), then call link_assumptions \
   to attach them to the thesis.
6. Add 1-2 defeaters (genuine challenges, not strawmen) to the most important arguments.

Guidelines:
- Use realistic confidence levels (0.5-0.95, not all high)
- Modality: "empirical" for factual, "analytic" for logical, "normative" for value claims
- Evidence types: observation, experiment, testimony, document, statistical
- Inference patterns: abduction, induction, modus_ponens, analogy, causal, testimony
- Defeater types: rebutting, undercutting, undermining
- Be intellectually honest — include real weaknesses
"""


async def _generate_full_graph_async(store, thesis_text: str, on_tool_call=None) -> str:
    """Async implementation using Agent SDK with custom tools."""
    _ensure_api_key()
    write_thesis_md(store, thesis_text)

    tools = _make_generate_tools(store)
    server = create_sdk_mcp_server("epist-tools", tools=tools)

    options = ClaudeAgentOptions(
        mcp_servers={"epist": server},
        system_prompt=GENERATE_SYSTEM,
        model="claude-opus-4-6",
        thinking={"type": "adaptive"},
        max_turns=40,
        permission_mode="bypassPermissions",
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(f"Decompose this thesis into an argument graph:\n\n{thesis_text}")
        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                break

    # Find root thesis
    for cid, c in store.claims.items():
        if c.is_root:
            return cid
    raise RuntimeError("Agent did not create a root thesis claim")


def generate_full_graph(store, thesis_text: str, on_tool_call=None) -> str:
    """Sync wrapper — calls the async Agent SDK implementation."""
    return anyio.run(_generate_full_graph_async, store, thesis_text, on_tool_call)


# Async version for callers already in an event loop (MCP server)
generate_full_graph_async = _generate_full_graph_async


# ── Enhance (raw API with structured output) ─────────────────────────

class Change(BaseModel):
    type: str
    description: str


class Enhancement(BaseModel):
    enhanced_thesis: str
    rationale: str
    changes: list[Change]


ENHANCE_SYSTEM = """\
You are an epistemic analyst. Given a thesis and the full analysis of its \
argument graph, suggest a refined version that is more precise, nuanced, \
and defensible.

Your enhancement should:
1. Preserve the core claim's intent and direction
2. Add qualifiers or scope limitations where the analysis reveals vulnerabilities
3. Acknowledge or incorporate key objections
4. Strengthen language where evidence strongly supports it
5. NOT completely change the thesis — refine it
"""


async def _enhance_thesis_async(store, thesis_id: str) -> dict:
    """Suggest an enhanced version via Agent SDK query.
    Returns {enhanced_thesis, rationale, changes}.
    """
    from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

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

    context_parts = [f"Original thesis: {thesis['notes'] or thesis['label']}"]

    if supporting:
        lines = []
        for a in supporting:
            lines.append(f"- {a['label']} (confidence: {a['confidence']:.0%}, pattern: {a['pattern']})")
            for p in a["premises"]:
                lines.append(f"  - [{p['type']}] {p['label']}")
        context_parts.append(f"Supporting arguments ({len(supporting)}):\n" + "\n".join(lines))

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

    user_message = "\n\n".join(context_parts)
    prompt = (
        user_message + "\n\nReturn a JSON object with keys: "
        "enhanced_thesis (string), rationale (string), "
        "changes (array of {type, description}). Return ONLY the JSON."
    )

    result_text = ""
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=ENHANCE_SYSTEM,
            model="claude-opus-4-6",
            allowed_tools=[],
            max_turns=1,
        ),
    ):
        if isinstance(message, ResultMessage):
            result_text = message.result

    raw = result_text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]
    result = Enhancement.model_validate_json(raw)
    return {
        "enhanced_thesis": result.enhanced_thesis,
        "rationale": result.rationale,
        "changes": [c.model_dump() for c in result.changes],
    }


def enhance_thesis(store, thesis_id: str) -> dict:
    """Sync wrapper for enhance."""
    return anyio.run(_enhance_thesis_async, store, thesis_id)


# Async version for MCP server
enhance_thesis_async = _enhance_thesis_async


# ── Synthesis (LLM-mediated merge of two forks) ──────────────────────

class Synthesis(BaseModel):
    synthesized_thesis: str
    rationale: str
    incorporated_from_a: list[str]
    incorporated_from_b: list[str]
    resolved_tensions: list[str]


SYNTHESIZE_SYSTEM = """\
You are an epistemic analyst. Two forks of an argument graph have been \
developed independently. Each represents a different framing of the same \
underlying question.

Your task: synthesize a new thesis that incorporates the strongest insights \
from both forks while resolving their disagreements. The synthesis should be \
stronger than either fork alone — it should not simply concatenate them.

Guidelines:
1. Preserve the empirical claims that both forks support
2. Reconcile contradictory framings by finding a more precise statement
3. Carry forward defeaters that neither fork has answered
4. Carry forward responses to defeaters from whichever fork answered them
5. Be intellectually honest about remaining tensions
"""


async def _synthesize_thesis_async(label_a: str, store_a, label_b: str, store_b) -> dict:
    """Synthesize a new thesis from two forks via Agent SDK query.
    Returns {synthesized_thesis, rationale, incorporated_from_a,
    incorporated_from_b, resolved_tensions}.
    """
    from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage
    from epist.compare import compute_graph_diff, compute_analysis_delta, format_diff_markdown

    summary_a = compute_summary(store_a)
    summary_b = compute_summary(store_b)
    if not summary_a.get("thesis") or not summary_b.get("thesis"):
        raise RuntimeError("Both forks must have a thesis")

    diff = compute_graph_diff(store_a, store_b)
    delta = compute_analysis_delta(store_a, store_b)
    diff_md = format_diff_markdown(diff, delta, label_a, label_b)

    prompt = (
        f"## Fork A: {label_a}\n\n"
        f"Thesis: {summary_a['thesis']['notes'] or summary_a['thesis']['label']}\n\n"
        f"Analysis summary:\n{summary_a['markdown']}\n\n"
        f"## Fork B: {label_b}\n\n"
        f"Thesis: {summary_b['thesis']['notes'] or summary_b['thesis']['label']}\n\n"
        f"Analysis summary:\n{summary_b['markdown']}\n\n"
        f"## Structural diff\n\n{diff_md}\n\n"
        f"---\n\nReturn a JSON object with keys: "
        "synthesized_thesis (string), rationale (string), "
        "incorporated_from_a (array of strings), "
        "incorporated_from_b (array of strings), "
        "resolved_tensions (array of strings). Return ONLY the JSON."
    )

    result_text = ""
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=SYNTHESIZE_SYSTEM,
            model="claude-opus-4-6",
            allowed_tools=[],
            max_turns=1,
        ),
    ):
        if isinstance(message, ResultMessage):
            result_text = message.result

    raw = result_text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]
    result = Synthesis.model_validate_json(raw)
    return {
        "synthesized_thesis": result.synthesized_thesis,
        "rationale": result.rationale,
        "incorporated_from_a": result.incorporated_from_a,
        "incorporated_from_b": result.incorporated_from_b,
        "resolved_tensions": result.resolved_tensions,
    }


def synthesize_thesis(label_a: str, store_a, label_b: str, store_b) -> dict:
    """Sync wrapper for synthesis."""
    return anyio.run(_synthesize_thesis_async, label_a, store_a, label_b, store_b)


synthesize_thesis_async = _synthesize_thesis_async
