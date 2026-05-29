"""
Thin adapter to the sibling `recall` provenance server (F2).

Design goals (from the brief's guardrails):
  • Integrate, don't rebuild — lean on recall's record_source / record_derivation
    / trace_derivation / list_orphan_derivations rather than inventing a parallel
    provenance store.
  • Don't over-couple — if recall is unreachable (package missing, db unwritable),
    every function degrades gracefully (returns None / [] / False) so the workbench
    keeps working and evidence simply stays `kind:"asserted"`.

We talk to recall by importing `recall.db` directly (same host) — no subprocess,
no MCP round-trip. The recall package location is found via EPIST_RECALL_PATH
(default: ~/workspace/recall); the db it writes is controlled by recall itself
(RECALL_DB env var, default ~/.recall/recall.db).
"""
import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("epist.recall")

_DEFAULT_RECALL_PATH = Path.home() / "workspace" / "recall"

# recall's allowed source types; we map a workbench source to one of these.
_DEFAULT_SOURCE_TYPE = "document"


def _ensure_on_path():
    """Make the recall package importable. Idempotent and NOT cached, so the
    sys.path entry is guaranteed present even when _db()'s import is a cache hit."""
    recall_path = str(Path(os.environ.get("EPIST_RECALL_PATH", _DEFAULT_RECALL_PATH)))
    if recall_path not in sys.path:
        sys.path.insert(0, recall_path)


@lru_cache(maxsize=1)
def _import_db():
    """Import recall.db once. Returns the module or None if it can't be imported."""
    _ensure_on_path()
    try:
        from recall import db  # type: ignore
        return db
    except Exception as e:
        logger.info(f"recall package not importable: {e}")
        return None


_schema_ready: set[str] = set()


def _db():
    """Return the recall.db module with its schema initialized against the
    CURRENT RECALL_DB, or None if unavailable. Schema init runs at most once per
    db path — recall's `with connect()` does not close its connections, so
    re-initializing on every call would leak file descriptors and eventually
    raise 'unable to open database file'."""
    _ensure_on_path()
    db = _import_db()
    if db is None:
        return None
    path = os.environ.get("RECALL_DB", str(Path.home() / ".recall" / "recall.db"))
    if path not in _schema_ready:
        try:
            db.init_schema()  # safe/idempotent; creates tables on a fresh db
            _schema_ready.add(path)
        except Exception as e:  # sqlite errors, perms — degrade
            logger.info(f"recall unavailable, provenance will degrade to asserted: {e}")
            return None
    return db


def reset_cache():
    """Drop cached state (used by tests that swap RECALL_DB)."""
    _import_db.cache_clear()
    _schema_ready.clear()


def is_available() -> bool:
    return _db() is not None


def record_source(content: str, source_type: str = _DEFAULT_SOURCE_TYPE,
                  external_id=None, url=None, summary=None) -> int | None:
    """Register a source in recall, returning its integer id (or None if recall
    is down). `url`, when given, is stored as the external_id so re-attaching the
    same URL is idempotent."""
    db = _db()
    if db is None:
        return None
    try:
        st = source_type if source_type in getattr(db, "VALID_SOURCE_TYPES", {source_type}) else "other"
        return db.record_source(
            source_type=st,
            content=content or (url or "(no content)"),
            external_id=external_id or url,
            content_summary=summary,
            metadata={"url": url} if url else None,
        )
    except Exception as e:
        logger.warning(f"recall.record_source failed: {e}")
        return None


def record_derivation(claim_text: str, source_record_id: int | None,
                      edge_type: str | None = None, context=None, notes=None) -> int | None:
    """Link a claim to a source (or record it as an orphan).

    Honors recall's invariant: `pattern_match` ⇔ source_record_id is None; every
    other edge_type REQUIRES a source. If no edge_type is given we infer it:
    a source ⇒ 'inference' (a grounded link), no source ⇒ 'pattern_match' (orphan).
    """
    db = _db()
    if db is None:
        return None
    if edge_type is None:
        edge_type = "pattern_match" if source_record_id is None else "inference"
    try:
        return db.record_derivation(
            claim_text=claim_text,
            edge_type=edge_type,
            source_record_id=source_record_id,
            context=context,
            notes=notes,
        )
    except Exception as e:
        logger.warning(f"recall.record_derivation failed: {e}")
        return None


def source_exists(source_record_id: int) -> bool:
    """True iff recall has a source with this id. Used to validate that an
    `attach_source(source_id=...)` points at a real recorded source."""
    db = _db()
    if db is None:
        return False
    # recall has no get_source(); probe directly. connect() is a contextmanager
    # that closes the connection on exit, so always use it as `with`.
    try:
        with db.connect() as conn:
            r = conn.execute(
                "SELECT 1 FROM source_record WHERE id = ?", (source_record_id,)
            ).fetchone()
            return r is not None
    except Exception as e:
        logger.warning(f"recall.source_exists failed: {e}")
        return False


def list_orphans(limit: int = 200) -> list[dict]:
    """recall's anti-confabulation view: claims asserted with no upstream source."""
    db = _db()
    if db is None:
        return []
    try:
        return db.list_orphan_derivations(limit=limit)
    except Exception as e:
        logger.warning(f"recall.list_orphan_derivations failed: {e}")
        return []
