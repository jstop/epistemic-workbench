import { useState, useEffect, useCallback } from "react";
import Graph from "./components/Graph.jsx";
import AddPanel from "./components/AddPanel.jsx";
import InspectPanel from "./components/InspectPanel.jsx";
import AnalysisPanel from "./components/AnalysisPanel.jsx";
import SummaryPanel from "./components/SummaryPanel.jsx";
import GuidedFlow from "./components/GuidedFlow.jsx";
import * as api from "./api.js";

export default function App() {
  const [fullGraph, setFullGraph] = useState({ nodes: [], edges: [] });
  const [workspace, setWorkspace] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [highlightIds, setHighlightIds] = useState([]);
  const [panel, setPanel] = useState("add");
  const [analysisKey, setAnalysisKey] = useState(0);
  const [showGuided, setShowGuided] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  const [theses, setTheses] = useState([]);
  const [activeThesisId, setActiveThesisId] = useState(null); // null = show all
  const [versions, setVersions] = useState(null);
  const [showHistory, setShowHistory] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [g, w, t] = await Promise.all([api.getGraph(), api.getWorkspace(), api.getTheses()]);
      setFullGraph(g);
      setWorkspace(w);
      setTheses(t);
      setAnalysisKey((k) => k + 1);
      if (initialLoad) {
        setInitialLoad(false);
        if (g.nodes.length === 0) setShowGuided(true);
        // Auto-select if there's exactly one thesis
        else if (t.length === 1) setActiveThesisId(t[0].id);
      }
    } catch (err) {
      console.error("Failed to fetch:", err);
    }
  }, [initialLoad]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Fetch versions when active thesis changes
  useEffect(() => {
    if (!activeThesisId) { setVersions(null); return; }
    api.getThesisVersions(activeThesisId)
      .then(setVersions)
      .catch(() => setVersions(null));
  }, [activeThesisId]);

  const handleThesisChange = useCallback((id) => {
    setActiveThesisId(id);
    setShowHistory(false);
    fetchAll();
  }, [fetchAll]);

  const handleVersionNav = (direction) => {
    if (!versions || !versions.versions.length) return;
    const newIndex = versions.current_index + direction;
    if (newIndex < 0 || newIndex >= versions.versions.length) return;
    const targetId = versions.versions[newIndex].thesis_id;
    handleThesisChange(targetId);
  };

  // Filter graph to active thesis subgraph
  const graph = (() => {
    if (!activeThesisId) return fullGraph;

    // Walk subgraph from thesis
    const nodeMap = {};
    fullGraph.nodes.forEach((n) => { nodeMap[n.id] = n; });

    // Build adjacency: conclusion -> premises from edges
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

  const handleSelectNode = (id) => {
    setSelectedId(id);
    setPanel("inspect");
  };

  const handleAdded = () => {
    fetchAll();
  };

  const stats = workspace?.stats;

  // Active thesis node for header display
  const thesis = activeThesisId
    ? graph.nodes.find((n) => n.id === activeThesisId)
    : (() => {
        if (graph.nodes.length === 0) return null;
        const supportCount = {};
        graph.edges.forEach((e) => {
          const tgt = e.target?.id || e.target;
          if (e.type === "supports") supportCount[tgt] = (supportCount[tgt] || 0) + 1;
        });
        const topId = Object.entries(supportCount).sort((a, b) => b[1] - a[1])[0]?.[0];
        return graph.nodes.find((n) => n.id === topId);
      })();

  const hasVersions = versions && versions.versions.length > 1;
  const currentVersion = versions ? versions.current_index + 1 : 1;
  const totalVersions = versions ? versions.versions.length : 1;

  const changeTypeColors = {
    scope: "#60a5fa", precision: "#a78bfa", qualifier: "#fbbf24",
    strength: "#4ade80", acknowledgment: "#f97316",
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
          {thesis && (
            <span
              onClick={() => handleSelectNode(thesis.id)}
              style={{
                fontSize: "12px", color: "#e0e0e0", cursor: "pointer",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}
              title={thesis.notes || thesis.label}
            >
              {thesis.label}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          {stats && (
            <span style={{ fontSize: "10px", color: "#555" }}>
              {stats.claims}c · {stats.evidence}e · {stats.arguments}a
            </span>
          )}
          {/* Version navigator */}
          {hasVersions && (
            <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              <button
                onClick={() => handleVersionNav(-1)}
                disabled={currentVersion <= 1}
                style={{
                  background: "transparent", border: "none",
                  color: currentVersion > 1 ? "#a78bfa" : "#333",
                  fontSize: "12px", cursor: currentVersion > 1 ? "pointer" : "default",
                  fontFamily: "'JetBrains Mono', monospace", padding: "2px 4px",
                }}
              >&lt;</button>
              <span style={{ fontSize: "9px", color: "#a78bfa", letterSpacing: "1px" }}>
                v{currentVersion}/{totalVersions}
              </span>
              <button
                onClick={() => handleVersionNav(1)}
                disabled={currentVersion >= totalVersions}
                style={{
                  background: "transparent", border: "none",
                  color: currentVersion < totalVersions ? "#a78bfa" : "#333",
                  fontSize: "12px", cursor: currentVersion < totalVersions ? "pointer" : "default",
                  fontFamily: "'JetBrains Mono', monospace", padding: "2px 4px",
                }}
              >&gt;</button>
              <button
                onClick={() => setShowHistory(!showHistory)}
                style={{
                  background: showHistory ? "#a78bfa22" : "transparent",
                  border: "1px solid #a78bfa44", borderRadius: "3px",
                  color: showHistory ? "#a78bfa" : "#666",
                  fontSize: "8px", cursor: "pointer",
                  fontFamily: "'JetBrains Mono', monospace",
                  padding: "2px 6px", letterSpacing: "1px",
                }}
              >HISTORY</button>
            </div>
          )}
          {theses.length > 1 && (
            <select
              value={activeThesisId || ""}
              onChange={(e) => handleThesisChange(e.target.value || null)}
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
            onClick={() => setShowGuided(true)}
            style={{
              background: "#FF6B3522", border: "1px solid #FF6B35", borderRadius: "3px",
              color: "#FF6B35", padding: "4px 10px", fontSize: "9px", cursor: "pointer",
              fontFamily: "'JetBrains Mono', monospace", letterSpacing: "1px",
            }}
          >
            + NEW
          </button>
          <button
            onClick={fetchAll}
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

      {/* History dropdown below header */}
      {showHistory && versions && (
        <div style={{
          borderBottom: "1px solid #1a1a1a", padding: "8px 16px",
          background: "#0d0d0d", maxHeight: "180px", overflowY: "auto",
        }}>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {versions.versions.map((v) => (
              <div
                key={v.thesis_id}
                onClick={() => handleThesisChange(v.thesis_id)}
                style={{
                  padding: "6px 10px", borderRadius: "3px", cursor: "pointer",
                  background: v.thesis_id === activeThesisId ? "#a78bfa18" : "#141414",
                  border: v.thesis_id === activeThesisId ? "1px solid #a78bfa44" : "1px solid #222",
                  minWidth: "140px", maxWidth: "260px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "10px", color: v.thesis_id === activeThesisId ? "#a78bfa" : "#888", fontWeight: 600 }}>
                    v{v.version}
                  </span>
                  <span style={{ fontSize: "8px", color: "#444" }}>
                    {new Date(v.created_at * 1000).toLocaleDateString()}
                  </span>
                </div>
                <div style={{ fontSize: "9px", color: "#666", marginTop: "3px", lineHeight: "1.3" }}>
                  {(v.notes || v.label).slice(0, 60)}...
                </div>
                {v.rationale && (
                  <div style={{ fontSize: "8px", color: "#555", marginTop: "3px", fontStyle: "italic" }}>
                    {v.rationale.slice(0, 80)}
                  </div>
                )}
                {v.changes && v.changes.length > 0 && (
                  <div style={{ display: "flex", gap: "3px", marginTop: "3px", flexWrap: "wrap" }}>
                    {v.changes.map((c, j) => (
                      <span key={j} style={{
                        fontSize: "7px", color: changeTypeColors[c.type] || "#888",
                        border: `1px solid ${changeTypeColors[c.type] || "#444"}44`,
                        borderRadius: "2px", padding: "0px 3px", textTransform: "uppercase",
                      }}>
                        {c.type}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Graph canvas */}
        <div style={{ flex: 1, position: "relative" }}>
          <Graph
            nodes={graph.nodes}
            edges={graph.edges}
            selectedId={selectedId}
            highlightIds={highlightIds}
            onSelectNode={handleSelectNode}
          />
          {/* Legend */}
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
          </div>
        </div>

        {/* Side panel */}
        <div style={{
          width: "340px", borderLeft: "1px solid #1a1a1a", display: "flex",
          flexDirection: "column", flexShrink: 0, overflow: "hidden",
        }}>
          {showGuided ? (
            /* Guided flow replaces the entire side panel */
            <div style={{ flex: 1, overflow: "auto", padding: "14px" }}>
              <GuidedFlow
                onAdded={handleAdded}
                onComplete={() => { setShowGuided(false); setPanel("analysis"); }}
              />
            </div>
          ) : (
            <>
              {/* Tabs */}
              <div style={{ display: "flex", borderBottom: "1px solid #1a1a1a", flexShrink: 0 }}>
                {[
                  { key: "add", label: "Add" },
                  { key: "inspect", label: "Inspect" },
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

              {/* Panel content */}
              <div style={{ flex: 1, overflow: "auto", padding: "14px" }}>
                {panel === "add" && (
                  <AddPanel graphNodes={graph.nodes} onAdded={handleAdded} />
                )}
                {panel === "inspect" && (
                  <InspectPanel
                    node={selectedNode}
                    edges={graph.edges}
                    allNodes={graph.nodes}
                    onUpdated={fetchAll}
                    onSelectNode={handleSelectNode}
                  />
                )}
                {panel === "analysis" && (
                  <AnalysisPanel
                    key={analysisKey}
                    selectedId={selectedId}
                    onSelectNode={(id) => { setSelectedId(id); setPanel("inspect"); }}
                    onHighlight={setHighlightIds}
                  />
                )}
                <div style={{ display: panel === "summary" ? "block" : "none" }}>
                  <SummaryPanel onThesisChange={handleThesisChange} activeThesisId={activeThesisId} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
