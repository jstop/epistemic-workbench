"""Who is writing.

Mirrors the living library's rule: the actor is a property of the CHANNEL a
process is, never a field in a request. The MCP server declares itself an
agent at import; the web server declares the browser session as the owner's
channel; a script or an agent's shell tool has no terminal and is named as
such; only a person at an interactive terminal writes as the owner.

This does not resist forgery — an in-process caller can declare anything. It
resists the failure that actually happens: a machine filling the owner's slot
because the default let it.
"""
from __future__ import annotations

import os
import sys

OWNER = "owner"
CHANNEL_ACTOR: str | None = None


def declare_channel(actor: str) -> None:
    """Called once by the process that IS a channel (server entrypoints)."""
    global CHANNEL_ACTOR
    CHANNEL_ACTOR = actor


def agent_actor(name: str | None) -> str:
    n = (name or "").strip().removeprefix("agent:").strip()
    if not n or n == OWNER:
        n = "unknown"
    return f"agent:{n}"


def resolve_actor() -> str:
    if CHANNEL_ACTOR:
        return CHANNEL_ACTOR
    explicit = os.environ.get("EPIST_ACTOR", "").strip()
    if explicit:
        return explicit if explicit != OWNER else OWNER
    try:
        interactive = sys.stdin.isatty()
    except (AttributeError, ValueError):
        interactive = False
    return OWNER if interactive else "agent:cli"


def git_author(actor: str | None = None) -> str:
    a = actor or resolve_actor()
    local = a.replace(":", ".")
    return f"{a} <{local}@epist.local>"
