"""
Epistemic Object data models.
Every object is content-addressed (SHA-256 of canonical JSON).
"""
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Modality(Enum):
    EMPIRICAL = "empirical"
    ANALYTIC = "analytic"
    NORMATIVE = "normative"
    MODAL = "modal"
    PREDICTIVE = "predictive"


class EvidenceType(Enum):
    OBSERVATION = "observation"
    EXPERIMENT = "experiment"
    TESTIMONY = "testimony"
    DOCUMENT = "document"
    STATISTICAL = "statistical"
    FORMAL_PROOF = "formal_proof"


class InferencePattern(Enum):
    MODUS_PONENS = "modus_ponens"
    MODUS_TOLLENS = "modus_tollens"
    ABDUCTION = "abduction"
    INDUCTION = "induction"
    ANALOGY = "analogy"
    TESTIMONY = "testimony"
    CAUSAL = "causal"
    STATISTICAL = "statistical"
    TRANSCENDENTAL = "transcendental"
    ELIMINATION = "elimination"
    BEST_EXPLANATION = "best_explanation"
    COMPOSITION = "composition"
    DIVISION = "division"
    PRECEDENT = "precedent"


class DefeaterType(Enum):
    REBUTTING = "rebutting"
    UNDERCUTTING = "undercutting"
    UNDERMINING = "undermining"


class DefeaterStatus(Enum):
    ACTIVE = "active"          # unaddressed objection (defeats argument)
    ANSWERED = "answered"      # rebutted with a counter-response (no longer defeats)
    CONCEDED = "conceded"      # accepted as a valid criticism (still defeats, but acknowledged)
    WITHDRAWN = "withdrawn"    # original objection no longer stands (does not defeat)


class EvaluationJudgment(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    SUSPEND = "suspend"
    NEEDS_WORK = "needs_work"


class NodeType(Enum):
    """Logical role of a Claim node. Lets imported/authored graphs carry the
    dialectical distinctions from the brief (thesis/objection/concession)
    without needing separate dataclasses — they are all Claims under the hood,
    so the existing ATMS/argument engine continues to analyze them."""
    CLAIM = "claim"
    THESIS = "thesis"
    OBJECTION = "objection"
    CONCESSION = "concession"


class EdgeRelation(Enum):
    """Typed relations for the generic edge layer (F1).

    `supports` and the defeater-family (`refutes`/`rebuts`) overlap with the
    Argument/Defeater constructs; the generic layer is what makes authored and
    imported graphs round-trip losslessly, and is the only home for relations
    the argument model cannot express (`grounds`, `narrows`, `supersedes`)."""
    SUPPORTS = "supports"
    REFUTES = "refutes"
    REBUTS = "rebuts"
    CONCEDES = "concedes"
    GROUNDS = "grounds"
    NARROWS = "narrows"
    SUPERSEDES = "supersedes"


# Stored node-status vocabulary for imported/authored graphs (brief §4). When a
# node carries no explicit status, the engine's ATMS computes one at read time.
NODE_STATUSES = {"live", "defeated", "superseded", "conceded", "rebutted", "open"}

# Argument premise-combination modes (F3 wires propagation onto these).
SUPPORT_MODES = {"conjunctive", "disjunctive", "independent"}


PATTERN_METADATA = {
    InferencePattern.MODUS_PONENS: {
        "min_premises": 2,
        "validity_conditions": ["Major premise must be conditional", "Minor premise must affirm antecedent"],
        "strength": "deductive",
    },
    InferencePattern.ABDUCTION: {
        "min_premises": 1,
        "validity_conditions": ["Must identify best available explanation", "Alternatives should be considered"],
        "strength": "ampliative",
    },
    InferencePattern.INDUCTION: {
        "min_premises": 1,
        "validity_conditions": ["Sample must be representative", "Sample size must be adequate"],
        "strength": "ampliative",
    },
    InferencePattern.CAUSAL: {
        "min_premises": 1,
        "validity_conditions": ["Temporal precedence", "No confounders identified", "Mechanism plausible"],
        "strength": "ampliative",
    },
    InferencePattern.ANALOGY: {
        "min_premises": 2,
        "validity_conditions": ["Relevant similarities identified", "Relevant differences addressed"],
        "strength": "ampliative",
    },
    InferencePattern.TESTIMONY: {
        "min_premises": 1,
        "validity_conditions": ["Source competence established", "Source sincerity plausible"],
        "strength": "testimonial",
    },
}

# Add defaults for patterns not explicitly listed
for p in InferencePattern:
    if p not in PATTERN_METADATA:
        PATTERN_METADATA[p] = {"min_premises": 1, "validity_conditions": [], "strength": "ampliative"}


def _hash(obj: dict) -> str:
    canonical = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class Confidence:
    level: float  # 0.0–1.0
    decomposition: Optional[dict] = None  # free-form breakdown


@dataclass
class Defeater:
    type: DefeaterType
    description: str
    status: DefeaterStatus = DefeaterStatus.ACTIVE
    response: Optional[str] = None


@dataclass
class Scope:
    domain: str = "general"
    temporal_bounds: Optional[str] = None
    geographic_bounds: Optional[str] = None
    population: Optional[str] = None


@dataclass
class Identity:
    author: str = "local"
    signed: bool = False


@dataclass
class Claim:
    subject: str
    predicate: str
    object: str
    confidence: Confidence
    modality: Modality = Modality.EMPIRICAL
    scope: Scope = field(default_factory=Scope)
    identity: Identity = field(default_factory=Identity)
    assumes: list = field(default_factory=list)  # list of claim IDs
    is_root: bool = False
    previous_version: Optional[str] = None   # claim ID of predecessor thesis
    version_meta: Optional[dict] = None      # {"rationale": str, "changes": list}
    node_type: str = "claim"                 # claim|thesis|objection|concession (F1)
    status: Optional[str] = None             # stored status override; None ⇒ ATMS computes (F1/F4)
    killed_by: Optional[str] = None          # id of the node that defeated/superseded this one (F1/F4)
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _hash({
                "type": "claim",
                "subject": self.subject,
                "predicate": self.predicate,
                "object": self.object,
                "created_at": self.created_at,
            })


@dataclass
class Evidence:
    title: str
    description: str
    evidence_type: EvidenceType = EvidenceType.OBSERVATION
    source: str = ""
    reliability: float = 0.7
    # F2 — provenance. None or {"kind":"asserted"} means UNVERIFIED (LLM-asserted
    # or hand-typed): a `source` string here is NOT proof of provenance. Only
    # {"kind":"recorded", "source_id": <recall id>, ...} is backed by a real
    # recorded source. The `source` string alone never makes evidence recorded.
    provenance: Optional[dict] = None
    identity: Identity = field(default_factory=Identity)
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _hash({
                "type": "evidence",
                "title": self.title,
                "created_at": self.created_at,
            })


@dataclass
class Argument:
    conclusion: str  # claim ID
    premises: list  # list of claim/evidence IDs
    pattern: InferencePattern = InferencePattern.MODUS_PONENS
    label: str = ""
    confidence: Confidence = field(default_factory=lambda: Confidence(0.7))
    defeaters: list = field(default_factory=list)
    support_mode: str = "independent"  # conjunctive|disjunctive|independent (F3 propagation)
    identity: Identity = field(default_factory=Identity)
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _hash({
                "type": "argument",
                "conclusion": self.conclusion,
                "premises": sorted(self.premises),
                "created_at": self.created_at,
            })


@dataclass
class Evaluation:
    target: str  # any EO ID
    judgment: EvaluationJudgment
    reasoning: str = ""
    identity: Identity = field(default_factory=Identity)
    created_at: float = field(default_factory=time.time)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _hash({
                "type": "evaluation",
                "target": self.target,
                "judgment": self.judgment.value,
                "created_at": self.created_at,
            })


@dataclass
class Prediction:
    subject: str
    predicate: str
    object: str
    confidence: Confidence
    resolution_date: str = ""
    resolved: bool = False
    outcome: Optional[bool] = None
    identity: Identity = field(default_factory=Identity)
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _hash({
                "type": "prediction",
                "subject": self.subject,
                "predicate": self.predicate,
                "object": self.object,
                "created_at": self.created_at,
            })


@dataclass
class Edge:
    """A typed relation between two epistemic objects (F1 generic edge layer).

    The existing model expresses `supports` via Argument and rebut/undercut via
    embedded Defeaters; the generic layer makes authored/imported graphs
    round-trip losslessly and is the only home for `grounds`/`narrows`/
    `supersedes`. The ATMS engine reads these via an adapter (see engine.py)."""
    from_id: str
    rel: str  # one of EdgeRelation values
    to: str
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _hash({
                "type": "edge",
                "from_id": self.from_id,
                "rel": self.rel,
                "to": self.to,
                "created_at": self.created_at,
            })
