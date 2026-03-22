"""
Simple JSON-file store for epistemic objects.
All objects stored in a single workspace directory.
Each workspace can optionally be a git repo for version tracking.
"""
import json
import os
import subprocess
from pathlib import Path
from dataclasses import asdict
from .model import (
    Claim, Evidence, Argument, Evaluation, Prediction,
    Confidence, Scope, Identity, Defeater,
    Modality, EvidenceType, InferencePattern, DefeaterType,
    DefeaterStatus, EvaluationJudgment,
)


def _serialize(obj):
    """Convert dataclass to serializable dict."""
    d = asdict(obj) if hasattr(obj, '__dataclass_fields__') else obj
    result = {}
    for k, v in d.items():
        if isinstance(v, (Modality, EvidenceType, InferencePattern,
                          DefeaterType, DefeaterStatus, EvaluationJudgment)):
            result[k] = v.value
        elif isinstance(v, dict):
            result[k] = v
        elif isinstance(v, list):
            result[k] = [_serialize(i) if isinstance(i, dict) else
                         (i.value if hasattr(i, 'value') else i) for i in v]
        else:
            result[k] = v
    return result


def _deserialize_claim(d):
    return Claim(
        subject=d["subject"], predicate=d["predicate"], object=d["object"],
        confidence=Confidence(**d["confidence"]) if isinstance(d["confidence"], dict) else Confidence(d["confidence"]),
        modality=Modality(d.get("modality", "empirical")),
        scope=Scope(**d.get("scope", {})) if isinstance(d.get("scope"), dict) else Scope(),
        identity=Identity(**d.get("identity", {})) if isinstance(d.get("identity"), dict) else Identity(),
        assumes=d.get("assumes", []),
        is_root=d.get("is_root", False),
        previous_version=d.get("previous_version", None),
        version_meta=d.get("version_meta", None),
        notes=d.get("notes", ""),
        created_at=d.get("created_at", 0),
        id=d["id"],
    )


def _deserialize_evidence(d):
    return Evidence(
        title=d["title"], description=d["description"],
        evidence_type=EvidenceType(d.get("evidence_type", "observation")),
        source=d.get("source", ""),
        reliability=d.get("reliability", 0.7),
        identity=Identity(**d.get("identity", {})) if isinstance(d.get("identity"), dict) else Identity(),
        notes=d.get("notes", ""),
        created_at=d.get("created_at", 0),
        id=d["id"],
    )


def _deserialize_argument(d):
    defeaters = []
    for df in d.get("defeaters", []):
        if isinstance(df, dict):
            defeaters.append(Defeater(
                type=DefeaterType(df["type"]),
                description=df["description"],
                status=DefeaterStatus(df.get("status", "active")),
                response=df.get("response"),
            ))
    return Argument(
        conclusion=d["conclusion"], premises=d["premises"],
        pattern=InferencePattern(d.get("pattern", "modus_ponens")),
        label=d.get("label", ""),
        confidence=Confidence(**d["confidence"]) if isinstance(d["confidence"], dict) else Confidence(d["confidence"]),
        defeaters=defeaters,
        identity=Identity(**d.get("identity", {})) if isinstance(d.get("identity"), dict) else Identity(),
        notes=d.get("notes", ""),
        created_at=d.get("created_at", 0),
        id=d["id"],
    )


def _deserialize_evaluation(d):
    return Evaluation(
        target=d["target"],
        judgment=EvaluationJudgment(d["judgment"]),
        reasoning=d.get("reasoning", ""),
        identity=Identity(**d.get("identity", {})) if isinstance(d.get("identity"), dict) else Identity(),
        created_at=d.get("created_at", 0),
        id=d["id"],
    )


def _deserialize_prediction(d):
    return Prediction(
        subject=d["subject"], predicate=d["predicate"], object=d["object"],
        confidence=Confidence(**d["confidence"]) if isinstance(d["confidence"], dict) else Confidence(d["confidence"]),
        resolution_date=d.get("resolution_date", ""),
        resolved=d.get("resolved", False),
        outcome=d.get("outcome"),
        identity=Identity(**d.get("identity", {})) if isinstance(d.get("identity"), dict) else Identity(),
        notes=d.get("notes", ""),
        created_at=d.get("created_at", 0),
        id=d["id"],
    )


class Store:
    def __init__(self, home: Path):
        self.home = Path(home)
        self.claims: dict[str, Claim] = {}
        self.evidence: dict[str, Evidence] = {}
        self.arguments: dict[str, Argument] = {}
        self.evaluations: dict[str, Evaluation] = {}
        self.predictions: dict[str, Prediction] = {}
        self.foundations: dict[str, dict] = {}
        self._load()

    def _path(self, name):
        return self.home / f"{name}.json"

    def _load(self):
        if not self.home.exists():
            return
        for name, collection, deser in [
            ("claims", self.claims, _deserialize_claim),
            ("evidence", self.evidence, _deserialize_evidence),
            ("arguments", self.arguments, _deserialize_argument),
            ("evaluations", self.evaluations, _deserialize_evaluation),
            ("predictions", self.predictions, _deserialize_prediction),
        ]:
            p = self._path(name)
            if p.exists():
                data = json.loads(p.read_text())
                for d in data:
                    obj = deser(d)
                    collection[obj.id] = obj
        fp = self._path("foundations")
        if fp.exists():
            self.foundations = json.loads(fp.read_text())

    def save(self):
        self.home.mkdir(parents=True, exist_ok=True)
        for name, collection in [
            ("claims", self.claims),
            ("evidence", self.evidence),
            ("arguments", self.arguments),
            ("evaluations", self.evaluations),
            ("predictions", self.predictions),
        ]:
            data = [_serialize(obj) for obj in collection.values()]
            self._path(name).write_text(json.dumps(data, indent=2, default=str))
        self._path("foundations").write_text(json.dumps(self.foundations, indent=2, default=str))

    def add_claim(self, c: Claim) -> Claim:
        self.claims[c.id] = c
        self.save()
        return c

    def add_evidence(self, e: Evidence) -> Evidence:
        self.evidence[e.id] = e
        self.save()
        return e

    def add_argument(self, a: Argument) -> Argument:
        self.arguments[a.id] = a
        self.save()
        return a

    def add_evaluation(self, e: Evaluation) -> Evaluation:
        self.evaluations[e.id] = e
        self.save()
        return e

    def add_prediction(self, p: Prediction) -> Prediction:
        self.predictions[p.id] = p
        self.save()
        return p

    def get(self, eo_id: str):
        """Get any epistemic object by ID (or prefix)."""
        for collection in [self.claims, self.evidence, self.arguments,
                           self.evaluations, self.predictions]:
            if eo_id in collection:
                return collection[eo_id]
            # prefix match
            matches = [v for k, v in collection.items() if k.startswith(eo_id)]
            if len(matches) == 1:
                return matches[0]
        return None

    def all_objects(self):
        """Return all epistemic objects."""
        all_objs = {}
        all_objs.update(self.claims)
        all_objs.update(self.evidence)
        all_objs.update(self.arguments)
        all_objs.update(self.evaluations)
        all_objs.update(self.predictions)
        return all_objs

    def clear(self):
        """Wipe all collections (but keep the workspace directory)."""
        self.claims.clear()
        self.evidence.clear()
        self.arguments.clear()
        self.evaluations.clear()
        self.predictions.clear()
        self.foundations.clear()
        self.save()

    def init_workspace(self):
        self.home.mkdir(parents=True, exist_ok=True)
        self.save()

    # ── Git operations ───────────────────────────────────────────────

    def _git(self, *args, check=True):
        """Run a git command in the workspace directory."""
        result = subprocess.run(
            ["git"] + list(args),
            cwd=self.home,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
        return result

    def is_git_repo(self) -> bool:
        return (self.home / ".git").is_dir()

    def git_init(self):
        """Initialize workspace as a git repo."""
        self.home.mkdir(parents=True, exist_ok=True)
        self._git("init")
        gitignore = self.home / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("__pycache__/\n*.pyc\n.DS_Store\n")
        self._git("add", "-A")
        self._git("commit", "-m", "[init] epistemic workspace", "--allow-empty", check=False)

    def git_commit(self, message: str):
        """Stage all changes and commit. No-op if nothing changed."""
        self._git("add", "-A")
        # Check if there's anything to commit
        result = self._git("diff", "--cached", "--quiet", check=False)
        if result.returncode == 0:
            return  # nothing staged
        self._git("commit", "-m", message)

    def git_log(self, max_count: int = 50) -> list[dict]:
        """Return commit history as list of {hash, subject, body, date}."""
        if not self.is_git_repo():
            return []
        sep = "---COMMIT---"
        fmt = f"%H%n%s%n%b%n%aI%n{sep}"
        result = self._git("log", f"--max-count={max_count}", f"--format={fmt}", check=False)
        if result.returncode != 0:
            return []
        commits = []
        for block in result.stdout.strip().split(sep):
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            if len(lines) < 4:
                continue
            commits.append({
                "hash": lines[0],
                "subject": lines[1],
                "body": "\n".join(lines[2:-1]).strip(),
                "date": lines[-1],
            })
        return commits
