"""Publish a workspace to Braid as one thesis.

Braid (https://braid.joshautomates.com) is a public network of signed claims. A
``braid-thesis/1`` bundle is this workspace's argument reduced to what a stranger
can weigh: claims with the author's confidence, arguments with the objections
the author already raised against them, and evidence with an honest note about
whether its provenance is recorded. The bundle is uploaded UNSIGNED and inert;
nothing is public under anyone's name until the owner reviews it on Braid and
seals its digest with one signature. This module holds no keys and signs nothing.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request

from . import graph_io

FORMAT = "braid-thesis/1"
DEFAULT_HOST = os.environ.get("BRAID_HOST", "https://braid.joshautomates.com")
# Nodes the author has already let go of are history, not part of the thesis as it stands.
DEAD_STATUSES = {"superseded", "retired", "withdrawn", "killed", "rejected"}


class BraidError(RuntimeError):
    """The Braid host could not be reached, or refused the bundle."""


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _words(slug) -> str:
    return re.sub(r"\s+", " ", str(slug or "").replace("-", " ").replace("_", " ")).strip()


def _val(v):
    return getattr(v, "value", v)


def claim_text(c: dict) -> str:
    """Hand-added claims keep their sentence in notes; generated ones carry a hyphenated triple."""
    notes = (c.get("notes") or "").strip()
    triple = " ".join(w for w in (_words(c.get("subject")), _words(c.get("predicate")), _words(c.get("object"))) if w)
    text = notes if notes and not c.get("predicate") else (triple or notes)
    return _clip(text[:1].upper() + text[1:], 600)


def build_bundle(store, name: str) -> dict:
    """Reduce a workspace to a braid-thesis/1 bundle. Read-only."""
    g = graph_io.export_graph(store)
    claims = [c for c in g["claims"] if (c.get("status") or "") not in DEAD_STATUSES]
    if not claims:
        raise BraidError("this workspace has no live claims to publish")
    live = {c["id"] for c in claims} | {e["id"] for e in g["evidence"]}
    roots = [c for c in claims if c.get("is_root")] or claims[:1]
    root = max(roots, key=lambda c: c.get("created_at") or 0)

    thesis_md = store.home / "thesis.md"
    first_para = ""
    if thesis_md.exists():
        body = re.sub(r"^#.*\n", "", thesis_md.read_text().strip()).strip()
        first_para = body.split("\n\n")[0].replace("\n", " ") if body else ""
    commit = ""
    if store.is_git_repo():
        commit = subprocess.run(["git", "-C", str(store.home), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip()

    return {
        "format": FORMAT,
        "title": _clip(_words(name).title() or "Untitled thesis", 120),
        "text": _clip(first_para or claim_text(root), 600),
        "source": {"tool": "epistemic-workbench", "workspace": _clip(name, 80), "commit": commit,
                   "graph_format": g.get("format")},
        "root": root["id"],
        "claims": [{
            "id": c["id"], "text": claim_text(c), "modality": _val(c.get("modality")),
            "kind": c.get("node_type") or "claim",
            "confidence": float((c.get("confidence") or {}).get("level", 0.5)),
            "assumes": [a for a in c.get("assumes") or [] if a in live],
        } for c in claims],
        "arguments": [{
            "id": a["id"], "conclusion": a["conclusion"],
            "premises": [p for p in a["premises"] if p in live],
            "pattern": _val(a.get("pattern")), "label": a.get("label") or "",
            "confidence": float((a.get("confidence") or {}).get("level", 0.5)),
            "objections": [{
                "type": _val(d.get("type")), "text": d.get("description") or "",
                "status": _val(d.get("status")), "response": d.get("response") or "",
            } for d in (a.get("defeaters") or [])][:12],
        } for a in g["arguments"] if a["conclusion"] in live],
        "evidence": [{
            "id": e["id"], "title": _clip(e.get("title") or "untitled", 200), "text": e.get("description") or "",
            "type": _val(e.get("evidence_type")), "source": e.get("source") or "",
            "reliability": e.get("reliability"),
            # Only a recorded source counts as provenance; a bare `source` string never does (F2).
            "provenance": ((e.get("provenance") or {}).get("kind") or "asserted"),
        } for e in g["evidence"]],
    }


def counts(bundle: dict) -> dict:
    return {
        "claims": len(bundle["claims"]), "arguments": len(bundle["arguments"]),
        "evidence": len(bundle["evidence"]),
        "objections": sum(len(a["objections"]) for a in bundle["arguments"]),
    }


def upload(bundle: dict, host: str = "") -> dict:
    """Upload the bundle, unsigned. Returns {"sha256", "submit"}; the submit URL is Braid's review-and-sign page."""
    host = (host or DEFAULT_HOST).rstrip("/")
    text = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    req = urllib.request.Request(
        host + "/api/bundle", data=json.dumps({"text": text}).encode(),
        headers={"content-type": "application/json", "user-agent": "epistemic-workbench"})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.load(res)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except ValueError:
            pass
        raise BraidError(f"Braid refused the bundle: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise BraidError(f"could not reach Braid at {host}: {e}") from e
