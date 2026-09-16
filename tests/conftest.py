import sys
from pathlib import Path

# Make the `epist` package importable when running pytest from anywhere.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest as _pytest


@_pytest.fixture
def temp_library(tmp_path, monkeypatch):
    """Point the living-library bridge at a throwaway canonical store so tests
    that write evidence/beliefs never touch the real one. Yields the library's
    engine module (or skips if the library is not present on this machine)."""
    from epist import library_client
    lib = tmp_path / "lib"
    lib.mkdir()
    monkeypatch.setenv("EPISTEMIC_DB_PATH", str(lib / "canonical.db"))
    monkeypatch.setenv("EPISTEMIC_CONTENT_DIR", str(lib / "evidence_store"))
    monkeypatch.setenv("EPISTEMIC_BELIEFS_DIR", str(lib / "beliefs"))
    monkeypatch.setenv("EPISTEMIC_EVENTS_JSONL", str(lib / "events.jsonl"))
    monkeypatch.setenv("EPISTEMIC_INDEX_PATH", str(lib / "MEMORY.md"))
    library_client.reset()
    if not library_client.available():
        _pytest.skip(library_client.unavailable_reason())
    eng = library_client._in_library_thread(library_client._load)
    library_client._in_library_thread(eng._LOGS.clear)

    class _ThreadProxy:
        """Every call on the wrapped object runs on the library's thread — the
        canonical log's sqlite connection has thread affinity, and the bridge
        funnels all production access through that one thread."""
        def __init__(self, target): self._t = target
        def __getattr__(self, name):
            def call(*a, **k):
                return library_client._in_library_thread(lambda: getattr(self._t, name)(*a, **k))
            return call

    class _EngineProxy:
        module = eng
        def get_log(self):
            return _ThreadProxy(library_client._in_library_thread(eng.get_log))
        def __getattr__(self, name):
            attr = getattr(eng, name)
            if callable(attr):
                return lambda *a, **k: library_client._in_library_thread(attr, *a, **k)
            return attr

    yield _EngineProxy()
    library_client._in_library_thread(eng._LOGS.clear)
    library_client.reset()


@_pytest.fixture(autouse=True)
def _hermetic_library(request, tmp_path, monkeypatch):
    """No test touches the real living library. Tests that need one ask for
    `temp_library`; everything else sees the bridge as unavailable."""
    if "temp_library" in request.fixturenames:
        yield
        return
    from epist import library_client
    monkeypatch.setenv("EPIST_MEMORY_PATH", str(tmp_path / "no-library-here"))
    library_client.reset()
    yield
    library_client.reset()


@_pytest.fixture
def no_library(tmp_path, monkeypatch):
    """Make the bridge report unavailable, so provenance must stay asserted."""
    from epist import library_client
    monkeypatch.setenv("EPIST_MEMORY_PATH", str(tmp_path / "nowhere"))
    library_client.reset()
    yield
    library_client.reset()
