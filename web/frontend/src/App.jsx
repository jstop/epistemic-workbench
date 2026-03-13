import { useState, useEffect, useCallback } from "react";
import Graph from "./components/Graph.jsx";
import AddPanel from "./components/AddPanel.jsx";
import InspectPanel from "./components/InspectPanel.jsx";
import AnalysisPanel from "./components/AnalysisPanel.jsx";
import * as api from "./api.js";

export default function App() {
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [workspace, setWorkspace] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [highlightIds, setHighlightIds] = useState([]);
  const [panel, setPanel] = useState("add");
  const [analysisKey, setAnalysisKey] = useState(0);

  const fetchAll = useCallback(async () => {
    try {
      const [g, w] = await Promise.all([api.getGraph(), api.getWorkspace()]);
      setGraph(g);
      setWorkspace(w);
      setAnalysisKey((k) => k + 1);
    } catch (err) {
      console.error("Failed to fetch:", err);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const selectedNode = graph.nodes.find((n) => n.id === selectedId);

  const handleSelectNode = (id) => {
    setSelectedId(id);
    const node = graph.nodes.find((n) => n.id === id);
    if (node && node.type === "claim") {
      setPanel("inspect");
    }
  };

  const handleAdded = () => {
    fetchAll();
  };

  const stats = workspace?.stats;
  const totalIssues = 0; // computed in AnalysisPanel

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
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ fontSize: "10px", letterSpacing: "3px", color: "#FF6B35", textTransform: "uppercase" }}>
            Epistemic Workbench
          </span>
          {workspace && (
            <span style={{ fontSize: "10px", color: "#444" }}>
              {workspace.home}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {stats && (
            <span style={{ fontSize: "10px", color: "#555" }}>
              {stats.claims} claims · {stats.evidence} evidence · {stats.arguments} arguments
            </span>
          )}
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
          {/* Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid #1a1a1a", flexShrink: 0 }}>
            {[
              { key: "add", label: "Add" },
              { key: "inspect", label: "Inspect" },
              { key: "analysis", label: "Analysis" },
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
          </div>
        </div>
      </div>
    </div>
  );
}
