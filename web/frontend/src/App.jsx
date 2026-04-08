import { useState, useEffect, useCallback } from "react";
import Graph from "./components/Graph.jsx";
import AddPanel from "./components/AddPanel.jsx";
import InspectPanel from "./components/InspectPanel.jsx";
import AnalysisPanel from "./components/AnalysisPanel.jsx";
import SummaryPanel from "./components/SummaryPanel.jsx";
import WorkspaceSidebar from "./components/WorkspaceSidebar.jsx";
import NewWorkspaceModal from "./components/NewWorkspaceModal.jsx";
import CompareModal from "./components/CompareModal.jsx";
import * as api from "./api.js";

const STORAGE_KEY = "epist.workspace";

export default function App() {
  // Workspace state
  const [workspaces, setWorkspaces] = useState([]);
  const [currentWorkspace, setCurrentWorkspace] = useState(
    () => localStorage.getItem(STORAGE_KEY) || null
  );
  const [workspaceInfo, setWorkspaceInfo] = useState(null);
  const [branches, setBranches] = useState([]);
  const [currentBranch, setCurrentBranch] = useState("");

  // Graph state
  const [fullGraph, setFullGraph] = useState({ nodes: [], edges: [] });
  const [selectedId, setSelectedId] = useState(null);
  const [highlightIds, setHighlightIds] = useState([]);
  const [panel, setPanel] = useState("inspect");
  const [analysisKey, setAnalysisKey] = useState(0);

  // Thesis selection (for workspaces with multiple thesis lineages)
  const [theses, setTheses] = useState([]);
  const [activeThesisId, setActiveThesisId] = useState(null);

  // Modals
  const [showNewWorkspace, setShowNewWorkspace] = useState(false);
  const [compareTarget, setCompareTarget] = useState(null); // string branch name
  const [mergeTarget, setMergeTarget] = useState(null);     // string branch name
  const [busyMessage, setBusyMessage] = useState(null);

  // ── Workspace lifecycle ───────────────────────────────────────────

  const refreshWorkspaceList = useCallback(async () => {
    try {
      const list = await api.listWorkspaces();
      setWorkspaces(list);
      // If no current workspace selected and list isn't empty, pick the first
      if (!currentWorkspace && list.length > 0) {
        setCurrentWorkspace(list[0].name);
      }
    } catch (err) {
      console.error("Failed to list workspaces:", err);
    }
  }, [currentWorkspace]);

  const refreshBranches = useCallback(async (name) => {
    try {
      const bs = await api.listBranches(name);
      setBranches(bs);
      const current = bs.find((b) => b.is_current);
      if (current) setCurrentBranch(current.name);
    } catch (err) {
      console.error("Failed to list branches:", err);
      setBranches([]);
    }
  }, []);

  const refreshGraph = useCallback(async (name) => {
    if (!name) return;
    try {
      const [g, info, t] = await Promise.all([
        api.getGraph(name),
        api.getWorkspaceInfo(name),
        api.getTheses(name),
      ]);
      setFullGraph(g);
      setWorkspaceInfo(info);
      setTheses(t);
      setAnalysisKey((k) => k + 1);
      // Default to single thesis if there's exactly one
      if (t.length === 1) setActiveThesisId(t[0].id);
      else if (t.length === 0) setActiveThesisId(null);
    } catch (err) {
      console.error("Failed to fetch graph:", err);
      setFullGraph({ nodes: [], edges: [] });
      setWorkspaceInfo(null);
    }
  }, []);

  useEffect(() => {
    refreshWorkspaceList();
  }, [refreshWorkspaceList]);

  useEffect(() => {
    if (currentWorkspace) {
      localStorage.setItem(STORAGE_KEY, currentWorkspace);
      refreshGraph(currentWorkspace);
      refreshBranches(currentWorkspace);
    }
  }, [currentWorkspace, refreshGraph, refreshBranches]);

  // ── Selection / panel handlers ────────────────────────────────────

  const handleSelectWorkspace = useCallback((name) => {
    setCurrentWorkspace(name);
    setSelectedId(null);
    setActiveThesisId(null);
    setPanel("inspect");
  }, []);

  const handleSelectNode = (id) => {
    setSelectedId(id);
    setPanel("inspect");
  };

  const handleUpdated = useCallback(() => {
    if (currentWorkspace) {
      refreshGraph(currentWorkspace);
      refreshBranches(currentWorkspace);
    }
  }, [currentWorkspace, refreshGraph, refreshBranches]);

  // ── Fork/branch actions ───────────────────────────────────────────

  const handleSwitchBranch = useCallback(async (forkName) => {
    if (!currentWorkspace) return;
    try {
      await api.switchBranch(currentWorkspace, forkName);
      handleUpdated();
    } catch (err) {
      alert(`Switch failed: ${err.message}`);
    }
  }, [currentWorkspace, handleUpdated]);

  const handleFork = useCallback(async (forkName) => {
    if (!currentWorkspace) return;
    try {
      await api.fork(currentWorkspace, forkName);
      handleUpdated();
    } catch (err) {
      alert(`Fork failed: ${err.message}`);
    }
  }, [currentWorkspace, handleUpdated]);

  const handleCompare = useCallback((other) => {
    setCompareTarget(other);
  }, []);

  const handleMerge = useCallback((other) => {
    setMergeTarget(other);
  }, []);

  // ── Filter graph by active thesis ─────────────────────────────────

  const graph = (() => {
    if (!activeThesisId) return fullGraph;

    const conclusionToPremises = {};
    fullGraph.edges.forEach((e) => {
      if (e.type === "supports" || e.type === "assumes") {
        const src = e.source?.id || e.source;
        const tgt = e.target?.id || e.target;
        if (!conclusionToPremises[tgt]) conclusionToPremises[tgt] = [];
        conclusionToPremises[tgt].push(src);
      }
    });

    const reachable = new Set();
    const walk = (id) => {
      if (reachable.has(id)) return;
      reachable.add(id);
      (conclusionToPremises[id] || []).forEach(walk);
    };
    walk(activeThesisId);

    const nodes = fullGraph.nodes.filter((n) => reachable.has(n.id));
    const edges = fullGraph.edges.filter((e) => {
      const src = e.source?.id || e.source;
      const tgt = e.target?.id || e.target;
      return reachable.has(src) && reachable.has(tgt);
    });
    return { nodes, edges };
  })();

  const selectedNode = graph.nodes.find((n) => n.id === selectedId);

  // Header thesis label
  const thesis = activeThesisId
    ? graph.nodes.find((n) => n.id === activeThesisId)
    : graph.nodes.find((n) => n.is_root);

  const stats = workspaceInfo?.stats;

  // ── Defeater chip click → select conclusion node ──────────────────

  const handleSelectDefeater = (defeater) => {
    // Find the conclusion node for this defeater's argument
    const arg = fullGraph.edges.find(
      (e) => e.argument_id === defeater.argument_id
    );
    if (arg) {
      const tgt = arg.target?.id || arg.target;
      setSelectedId(tgt);
      setPanel("inspect");
    }
  };

  return (
    <div style={{
      height: "100vh", display: "flex", flexDirection: "column",
      background: "#0A0A0A", fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      color: "#e0e0e0", overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px", borderBottom: "1px solid #1a1a1a", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0, flex: 1 }}>
          <span style={{ fontSize: "10px", letterSpacing: "3px", color: "#FF6B35", textTransform: "uppercase", flexShrink: 0 }}>
            Workbench
          </span>
          {currentWorkspace && (
            <>
              <span style={{ fontSize: "10px", color: "#555" }}>·</span>
              <span style={{ fontSize: "10px", color: "#888", fontWeight: 600 }}>
                {currentWorkspace}
              </span>
              {currentBranch && currentBranch !== "master" && currentBranch !== "main" && (
                <span style={{
                  fontSize: "9px", color: "#a78bfa",
                  background: "#a78bfa18", border: "1px solid #a78bfa44",
                  borderRadius: "3px", padding: "1px 6px",
                }}>
                  {currentBranch}
                </span>
              )}
            </>
          )}
          {thesis && (
            <span
              onClick={() => handleSelectNode(thesis.id)}
              style={{
                fontSize: "11px", color: "#aaa", cursor: "pointer",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                marginLeft: "8px",
              }}
              title={thesis.notes || thesis.label}
            >
              {(thesis.notes || thesis.label).slice(0, 80)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          {stats && (
            <span style={{ fontSize: "10px", color: "#555" }}>
              {stats.claims}c · {stats.evidence}e · {stats.arguments}a
            </span>
          )}
          {theses.length > 1 && (
            <select
              value={activeThesisId || ""}
              onChange={(e) => setActiveThesisId(e.target.value || null)}
              style={{
                background: "#141414", border: "1px solid #333", borderRadius: "3px",
                color: "#e0e0e0", padding: "4px 6px", fontSize: "9px",
                fontFamily: "'JetBrains Mono', monospace", outline: "none",
                cursor: "pointer", maxWidth: "180px",
              }}
            >
              <option value="">ALL GRAPHS</option>
              {theses.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label.slice(0, 40)}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={() => currentWorkspace && handleUpdated()}
            disabled={!currentWorkspace}
            style={{
              background: "transparent", border: "1px solid #333", borderRadius: "3px",
              color: "#666", padding: "4px 10px", fontSize: "10px", cursor: "pointer",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            RELOAD
          </button>
        </div>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Workspace sidebar */}
        <WorkspaceSidebar
          workspaces={workspaces}
          currentWorkspace={currentWorkspace}
          branches={branches}
          currentBranch={currentBranch}
          onSelectWorkspace={handleSelectWorkspace}
          onSwitchBranch={handleSwitchBranch}
          onFork={handleFork}
          onCompare={handleCompare}
          onMerge={handleMerge}
          onNew={() => setShowNewWorkspace(true)}
          onRefresh={refreshWorkspaceList}
        />

        {/* Graph canvas */}
        <div style={{ flex: 1, position: "relative", minWidth: 0 }}>
          {currentWorkspace && fullGraph.nodes.length > 0 ? (
            <Graph
              nodes={graph.nodes}
              edges={graph.edges}
              selectedId={selectedId}
              highlightIds={highlightIds}
              onSelectNode={handleSelectNode}
              onSelectDefeater={handleSelectDefeater}
            />
          ) : (
            <div style={{
              height: "100%", display: "flex", alignItems: "center", justifyContent: "center",
              flexDirection: "column", gap: "12px",
            }}>
              {!currentWorkspace ? (
                <>
                  <div style={{ color: "#444", fontSize: "11px" }}>No workspace selected</div>
                  <button
                    onClick={() => setShowNewWorkspace(true)}
                    style={{
                      background: "#FF6B3522", border: "1px solid #FF6B35",
                      color: "#FF6B35", padding: "8px 16px", fontSize: "10px",
                      cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
                      letterSpacing: "1px", borderRadius: "3px",
                    }}
                  >
                    + NEW WORKSPACE
                  </button>
                </>
              ) : (
                <div style={{ color: "#444", fontSize: "11px" }}>Empty workspace</div>
              )}
            </div>
          )}

          {fullGraph.nodes.length > 0 && (
            <div style={{
              position: "absolute", bottom: "12px", left: "12px",
              background: "#141414", border: "1px solid #222", borderRadius: "4px",
              padding: "8px 12px", display: "flex", gap: "16px", alignItems: "center",
            }}>
              <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                <span style={{ color: "#60a5fa", fontSize: "12px" }}>●</span>
                <span style={{ fontSize: "9px", color: "#555" }}>Claim</span>
              </div>
              <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                <span style={{ color: "#4ade80", fontSize: "12px" }}>■</span>
                <span style={{ fontSize: "9px", color: "#555" }}>Evidence</span>
              </div>
              <div style={{ fontSize: "9px", color: "#333" }}>|</div>
              <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                <span style={{ fontSize: "9px", color: "#4ade80" }}>accepted</span>
                <span style={{ fontSize: "9px", color: "#fbbf24" }}>provisional</span>
                <span style={{ fontSize: "9px", color: "#f87171" }}>defeated</span>
              </div>
              <div style={{ fontSize: "9px", color: "#333" }}>|</div>
              <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
                <span style={{ fontSize: "9px", color: "#888" }}>defeater:</span>
                <span style={{ fontSize: "9px", color: "#f87171" }}>active</span>
                <span style={{ fontSize: "9px", color: "#fb923c" }}>conceded</span>
                <span style={{ fontSize: "9px", color: "#4ade80" }}>answered</span>
              </div>
            </div>
          )}
        </div>

        {/* Right panel */}
        <div style={{
          width: "380px", borderLeft: "1px solid #1a1a1a", display: "flex",
          flexDirection: "column", flexShrink: 0, overflow: "hidden",
        }}>
          <div style={{ display: "flex", borderBottom: "1px solid #1a1a1a", flexShrink: 0 }}>
            {[
              { key: "inspect", label: "Inspect" },
              { key: "add", label: "Add" },
              { key: "analysis", label: "Analysis" },
              { key: "summary", label: "Summary" },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setPanel(tab.key)}
                style={{
                  flex: 1, background: panel === tab.key ? "#141414" : "transparent",
                  border: "none", borderBottom: panel === tab.key ? "2px solid #FF6B35" : "2px solid transparent",
                  color: panel === tab.key ? "#FF6B35" : "#555", padding: "10px 0",
                  fontSize: "10px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: "1px", textTransform: "uppercase",
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div style={{ flex: 1, overflow: "auto", padding: "14px" }}>
            {panel === "inspect" && (
              <InspectPanel
                workspace={currentWorkspace}
                node={selectedNode}
                edges={graph.edges}
                allNodes={graph.nodes}
                onUpdated={handleUpdated}
                onSelectNode={handleSelectNode}
              />
            )}
            {panel === "add" && (
              <AddPanel
                workspace={currentWorkspace}
                graphNodes={graph.nodes}
                onAdded={handleUpdated}
              />
            )}
            {panel === "analysis" && (
              <AnalysisPanel
                key={analysisKey}
                workspace={currentWorkspace}
                selectedId={selectedId}
                onSelectNode={handleSelectNode}
                onHighlight={setHighlightIds}
              />
            )}
            <div style={{ display: panel === "summary" ? "block" : "none" }}>
              <SummaryPanel
                workspace={currentWorkspace}
                activeThesisId={activeThesisId}
                onThesisChange={(id) => { setActiveThesisId(id); handleUpdated(); }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Modals */}
      {showNewWorkspace && (
        <NewWorkspaceModal
          onClose={() => setShowNewWorkspace(false)}
          onCreated={(name) => {
            setShowNewWorkspace(false);
            refreshWorkspaceList();
            setCurrentWorkspace(name);
          }}
          setBusy={setBusyMessage}
        />
      )}
      {compareTarget && currentWorkspace && (
        <CompareModal
          workspace={currentWorkspace}
          other={compareTarget}
          mode="compare"
          onClose={() => setCompareTarget(null)}
        />
      )}
      {mergeTarget && currentWorkspace && (
        <CompareModal
          workspace={currentWorkspace}
          other={mergeTarget}
          mode="merge"
          onClose={() => setMergeTarget(null)}
          onMerged={() => {
            setMergeTarget(null);
            handleUpdated();
          }}
          setBusy={setBusyMessage}
        />
      )}
      {busyMessage && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
          background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center",
          justifyContent: "center", zIndex: 1000,
        }}>
          <div style={{
            background: "#141414", border: "1px solid #333", borderRadius: "4px",
            padding: "20px 32px", color: "#FF6B35", fontSize: "12px",
            fontFamily: "'JetBrains Mono', monospace", letterSpacing: "1px",
          }}>
            ⟳ {busyMessage}
          </div>
        </div>
      )}
    </div>
  );
}
