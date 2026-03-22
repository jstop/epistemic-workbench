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
    ACTIVE = "active"
    ANSWERED = "answered"
    WITHDRAWN = "withdrawn"


class EvaluationJudgment(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    SUSPEND = "suspend"
    NEEDS_WORK = "needs_work"


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
