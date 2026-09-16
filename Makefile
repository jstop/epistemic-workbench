# Epistemic Workbench — local web UI
#
#   make web        build the frontend (if node_modules present) and serve on :8111
#   make serve      serve only (uses the last built frontend)
#   make build      build the frontend
#   make test       run the test suite
#   make backup     back up every workspace off-machine (workspaces-backup/backup.sh)
#
# The MCP server Claude Desktop uses (epist/mcp_server.py) and this web UI
# share the same workspaces directory and the same engine; edits from either
# are git commits in the workspace repo, so they interleave cleanly.

PY      ?= $(HOME)/python/global/bin/python
PORT    ?= 8111
EPIST_WORKSPACES ?= $(HOME)/workspace/epistemic/workspaces
export EPIST_WORKSPACES

.PHONY: web serve build test open backup

build:
	cd web/frontend && npm run build

serve:
	$(PY) -m uvicorn web.server:app --port $(PORT)

web: build serve

open:
	open http://127.0.0.1:$(PORT)

test:
	$(PY) -m pytest tests -q

backup:
	$(HOME)/workspace/epistemic/workspaces-backup/backup.sh
