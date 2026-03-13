import { useState, useEffect, useCallback } from "react";
import Graph from "./components/Graph.jsx";
import AddPanel from "./components/AddPanel.jsx";
import InspectPanel from "./components/InspectPanel.jsx";
import AnalysisPanel from "./components/AnalysisPanel.jsx";
import SummaryPanel from "./components/SummaryPanel.jsx";
import GuidedFlow from "./components/GuidedFlow.jsx";
import * as api from "./api.js";

export default function App() {
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [workspace, setWorkspace] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [highlightIds, setHighlightIds] = useState([]);
  const [panel, setPanel] = useState("add");
  const [analysisKey, setAnalysisKey] = useState(0);
  const [showGuided, setShowGuided] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [g, w] = await Promise.all([api.getGraph(), api.getWorkspace()]);
      setGraph(g);
      setWorkspace(w);
      setAnalysisKey((k) => k + 1);
      // Show guided flow if workspace is empty on first load
      if (initialLoad) {
        setInitialLoad(false);
        if (g.nodes.length === 0) setShowGuided(true);
      }
    } catch (err) {
      console.error("Failed to fetch:", err);
    }
  }, [initialLoad]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const selectedNode = graph.nodes.find((n) => n.id === selectedId);

  const handleSelectNode = (id) => {
    setSelectedId(id);
    setPanel("inspect");
  };

  const handleAdded = () => {
    fetchAll();
  };

  const stats = workspace?.stats;

  // Find the root thesis: the claim that is the target of the most support edges
  const thesis = (() => {
    if (graph.nodes.length === 0) return null;
    const supportCount = {};
    graph.edges.forEach((e) => {
      const tgt = e.target?.id || e.target;
      if (e.type === "supports") supportCount[tgt] = (supportCount[tgt] || 0) + 1;
    });
    const topId = Object.entries(supportCount).sort((a, b) => b[1] - a[1])[0]?.[0];
    return graph.nodes.find((n) => n.id === topId);
  })();

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
              {thesis.notes || thesis.label}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          {stats && (
            <span style={{ fontSize: "10px", color: "#555" }}>
              {stats.claims}c · {stats.evidence}e · {stats.arguments}a
            </span>
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
                {panel === "summary" && (
                  <SummaryPanel />
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
