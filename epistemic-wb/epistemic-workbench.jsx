import { useState, useCallback, useRef, useEffect } from "react";
import * as d3 from "d3";

// ── Data Helpers ─────────────────────────────────────────────────────
const uid = () => Math.random().toString(36).slice(2, 10);
const edgeSourceId = (e) => e.source.id || e.source;
const edgeTargetId = (e) => e.target.id || e.target;

const EDGE_TYPES = {
  supports: { label: "supports", color: "#4ade80", dash: "none" },
  attacks: { label: "attacks", color: "#f87171", dash: "8,4" },
  assumes: { label: "assumes", color: "#fbbf24", dash: "4,4" },
};

const NODE_TYPES = {
  thesis: { label: "Thesis", color: "#FF6B35", symbol: "◆" },
  claim: { label: "Claim", color: "#60a5fa", symbol: "●" },
  evidence: { label: "Evidence", color: "#4ade80", symbol: "■" },
  assumption: { label: "Assumption", color: "#fbbf24", symbol: "△" },
};

// ── Graph Component ──────────────────────────────────────────────────
function Graph({ nodes, edges, selectedId, onSelectNode, onCreateEdge }) {
  const svgRef = useRef(null);
  const simRef = useRef(null);
  const dragSourceRef = useRef(null);
  const [dragLine, setDragLine] = useState(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(edges).id(d => d.id).distance(140).strength(0.4))
      .force("charge", d3.forceManyBody().strength(-400))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(50))
      .alphaDecay(0.02);

    simRef.current = sim;

    return () => sim.stop();
  }, [nodes.length, edges.length]);

  // Force re-render on tick + clamp nodes to viewport
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!simRef.current || !svgRef.current) return;
    simRef.current.nodes(nodes);
    simRef.current.force("link").links(edges);
    simRef.current.alpha(0.3).restart();
    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;
    simRef.current.on("tick", () => {
      nodes.forEach(n => {
        n.x = Math.max(40, Math.min(width - 40, n.x));
        n.y = Math.max(40, Math.min(height - 40, n.y));
      });
      setTick(t => t + 1);
    });
  }, [nodes, edges]);

  const handleDragStart = (e, node) => {
    if (e.shiftKey) {
      dragSourceRef.current = node;
      return;
    }
    const sim = simRef.current;
    if (!sim) return;
    sim.alphaTarget(0.1).restart();
    node.fx = node.x;
    node.fy = node.y;

    const onMove = (ev) => {
      const rect = svgRef.current.getBoundingClientRect();
      node.fx = ev.clientX - rect.left;
      node.fy = ev.clientY - rect.top;
    };
    const onUp = () => {
      sim.alphaTarget(0);
      node.fx = null;
      node.fy = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const handleMouseMove = (e) => {
    if (!dragSourceRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    setDragLine({
      x1: dragSourceRef.current.x,
      y1: dragSourceRef.current.y,
      x2: e.clientX - rect.left,
      y2: e.clientY - rect.top,
    });
  };

  const handleMouseUp = (e, targetNode) => {
    if (dragSourceRef.current && targetNode && dragSourceRef.current.id !== targetNode.id) {
      onCreateEdge(dragSourceRef.current.id, targetNode.id);
    }
    dragSourceRef.current = null;
    setDragLine(null);
  };

  return (
    <svg
      ref={svgRef}
      style={{ width: "100%", height: "100%", background: "transparent" }}
      onMouseMove={handleMouseMove}
      onMouseUp={() => { dragSourceRef.current = null; setDragLine(null); }}
    >
      <defs>
        <marker id="arrow-supports" viewBox="0 0 10 6" refX="28" refY="3" markerWidth="8" markerHeight="6" orient="auto">
          <path d="M0,0 L10,3 L0,6 Z" fill="#4ade80" />
        </marker>
        <marker id="arrow-attacks" viewBox="0 0 10 6" refX="28" refY="3" markerWidth="8" markerHeight="6" orient="auto">
          <path d="M0,0 L10,3 L0,6 Z" fill="#f87171" />
        </marker>
        <marker id="arrow-assumes" viewBox="0 0 10 6" refX="28" refY="3" markerWidth="8" markerHeight="6" orient="auto">
          <path d="M0,0 L10,3 L0,6 Z" fill="#fbbf24" />
        </marker>
      </defs>

      {/* Edges */}
      {edges.map((e, i) => {
        const src = nodes.find(n => n.id === edgeSourceId(e));
        const tgt = nodes.find(n => n.id === edgeTargetId(e));
        if (!src || !tgt) return null;
        const cfg = EDGE_TYPES[e.type] || EDGE_TYPES.supports;
        return (
          <g key={i}>
            <line
              x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
              stroke={cfg.color} strokeWidth={1.5} strokeDasharray={cfg.dash}
              markerEnd={`url(#arrow-${e.type})`} opacity={0.7}
            />
            <text
              x={(src.x + tgt.x) / 2} y={(src.y + tgt.y) / 2 - 6}
              fill={cfg.color} fontSize="9" fontFamily="'JetBrains Mono', monospace"
              textAnchor="middle" opacity={0.6}
            >
              {cfg.label}
            </text>
          </g>
        );
      })}

      {/* Drag line preview */}
      {dragLine && (
        <line
          x1={dragLine.x1} y1={dragLine.y1} x2={dragLine.x2} y2={dragLine.y2}
          stroke="#FF6B35" strokeWidth={1.5} strokeDasharray="6,3" opacity={0.6}
        />
      )}

      {/* Nodes */}
      {nodes.map(node => {
        const cfg = NODE_TYPES[node.type] || NODE_TYPES.claim;
        const isSelected = node.id === selectedId;
        const radius = node.type === "thesis" ? 24 : 18;
        return (
          <g
            key={node.id}
            style={{ cursor: "grab" }}
            onMouseDown={(e) => handleDragStart(e, node)}
            onMouseUp={(e) => handleMouseUp(e, node)}
            onClick={(e) => { e.stopPropagation(); onSelectNode(node.id); }}
          >
            <circle
              cx={node.x} cy={node.y} r={radius}
              fill={isSelected ? cfg.color : "#1a1a1a"}
              stroke={cfg.color}
              strokeWidth={isSelected ? 2.5 : 1.5}
              opacity={0.95}
            />
            {/* Confidence ring */}
            <circle
              cx={node.x} cy={node.y} r={radius + 4}
              fill="none" stroke={cfg.color} strokeWidth={1}
              strokeDasharray={`${(node.confidence / 100) * (2 * Math.PI * (radius + 4))} ${2 * Math.PI * (radius + 4)}`}
              transform={`rotate(-90 ${node.x} ${node.y})`}
              opacity={0.4}
            />
            <text
              x={node.x} y={node.y + 1}
              fill={isSelected ? "#0A0A0A" : cfg.color}
              fontSize="12" fontFamily="'JetBrains Mono', monospace"
              textAnchor="middle" dominantBaseline="middle"
              style={{ pointerEvents: "none" }}
            >
              {cfg.symbol}
            </text>
            <text
              x={node.x} y={node.y + radius + 14}
              fill="#a0a0a0" fontSize="10" fontFamily="'JetBrains Mono', monospace"
              textAnchor="middle" style={{ pointerEvents: "none" }}
            >
              {node.label.length > 20 ? node.label.slice(0, 18) + "…" : node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Analysis Engine ──────────────────────────────────────────────────
function analyzeGraph(nodes, edges) {
  const issues = [];

  // Unsupported claims (claims with no incoming "supports" edges)
  const supported = new Set(edges.filter(e => e.type === "supports").map(e => edgeTargetId(e)));
  nodes.forEach(n => {
    if ((n.type === "claim" || n.type === "thesis") && !supported.has(n.id)) {
      issues.push({ severity: "high", node: n.id, label: n.label, msg: `"${n.label}" has no supporting evidence or arguments` });
    }
  });

  // High confidence with no evidence
  nodes.forEach(n => {
    if (n.confidence >= 80) {
      const hasSupport = edges.some(e => edgeTargetId(e) === n.id && e.type === "supports");
      if (!hasSupport && n.type !== "evidence") {
        issues.push({ severity: "medium", node: n.id, label: n.label, msg: `"${n.label}" at ${n.confidence}% confidence but lacks structural support` });
      }
    }
  });

  // Unexamined assumptions
  const assumptions = nodes.filter(n => n.type === "assumption");
  assumptions.forEach(a => {
    const hasAttack = edges.some(e => edgeTargetId(e) === a.id && e.type === "attacks");
    if (!hasAttack) {
      issues.push({ severity: "low", node: a.id, label: a.label, msg: `Assumption "${a.label}" has not been stress-tested` });
    }
  });

  // Orphan nodes
  nodes.forEach(n => {
    const connected = edges.some(e => edgeSourceId(e) === n.id || edgeTargetId(e) === n.id);
    if (!connected && nodes.length > 1) {
      issues.push({ severity: "medium", node: n.id, label: n.label, msg: `"${n.label}" is disconnected from the argument` });
    }
  });

  // Attacked claims with no defense
  nodes.forEach(n => {
    const attacks = edges.filter(e => edgeTargetId(e) === n.id && e.type === "attacks");
    const supports = edges.filter(e => edgeTargetId(e) === n.id && e.type === "supports");
    if (attacks.length > 0 && supports.length === 0) {
      issues.push({ severity: "high", node: n.id, label: n.label, msg: `"${n.label}" is attacked but has no supporting evidence` });
    }
  });

  return issues.sort((a, b) => {
    const sev = { high: 0, medium: 1, low: 2 };
    return sev[a.severity] - sev[b.severity];
  });
}

// ── Main App ─────────────────────────────────────────────────────────
export default function EpistemicWorkbench() {
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [panel, setPanel] = useState("add"); // add | inspect | analysis
  const [edgeType, setEdgeType] = useState("supports");
  const [question, setQuestion] = useState("");
  const [questionSet, setQuestionSet] = useState(false);

  // Add form state
  const [newLabel, setNewLabel] = useState("");
  const [newType, setNewType] = useState("claim");
  const [newConfidence, setNewConfidence] = useState(65);
  const [newNotes, setNewNotes] = useState("");

  const selectedNode = nodes.find(n => n.id === selectedId);
  const issues = analyzeGraph(nodes, edges);

  const setQuestion_ = () => {
    if (!question.trim()) return;
    const thesisNode = {
      id: uid(),
      type: "thesis",
      label: question.trim(),
      confidence: 50,
      notes: "",
      x: 400,
      y: 250,
    };
    setNodes([thesisNode]);
    setSelectedId(thesisNode.id);
    setQuestionSet(true);
  };

  const addNode = () => {
    if (!newLabel.trim()) return;
    const n = {
      id: uid(),
      type: newType,
      label: newLabel.trim(),
      confidence: newConfidence,
      notes: newNotes,
      x: 300 + Math.random() * 200,
      y: 200 + Math.random() * 200,
    };
    setNodes(prev => [...prev, n]);
    setNewLabel("");
    setNewNotes("");
    setNewConfidence(65);
    setSelectedId(n.id);
  };

  const deleteNode = (id) => {
    setNodes(prev => prev.filter(n => n.id !== id));
    setEdges(prev => prev.filter(e => edgeSourceId(e) !== id && edgeTargetId(e) !== id));
    if (selectedId === id) setSelectedId(null);
  };

  const updateNode = (id, updates) => {
    setNodes(prev => prev.map(n => n.id === id ? { ...n, ...updates } : n));
  };

  const createEdge = (sourceId, targetId) => {
    const exists = edges.some(e =>
      edgeSourceId(e) === sourceId && edgeTargetId(e) === targetId
    );
    if (exists) return;
    setEdges(prev => [...prev, { source: sourceId, target: targetId, type: edgeType }]);
  };

  const deleteEdge = (idx) => {
    setEdges(prev => prev.filter((_, i) => i !== idx));
  };

  const reset = () => {
    setNodes([]);
    setEdges([]);
    setSelectedId(null);
    setQuestion("");
    setQuestionSet(false);
  };

  // ── Render ─────────────────────────────────────────────────────────
  const sevColor = { high: "#f87171", medium: "#fbbf24", low: "#60a5fa" };
  const sevIcon = { high: "▲", medium: "◆", low: "●" };

  if (!questionSet) {
    return (
      <div style={{
        height: "100vh", display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", background: "#0A0A0A", fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        color: "#e0e0e0", padding: "2rem",
      }}>
        <div style={{ marginBottom: "2rem", textAlign: "center" }}>
          <div style={{ fontSize: "11px", letterSpacing: "4px", color: "#FF6B35", marginBottom: "8px", textTransform: "uppercase" }}>
            Epistemic Workbench
          </div>
          <div style={{ fontSize: "22px", fontWeight: 300, color: "#e0e0e0", marginBottom: "6px" }}>
            What are you reasoning about?
          </div>
          <div style={{ fontSize: "12px", color: "#666", maxWidth: "400px" }}>
            State a question, thesis, or problem. The workbench will help you decompose it into claims, surface assumptions, and find blind spots.
          </div>
        </div>
        <div style={{ display: "flex", gap: "8px", width: "100%", maxWidth: "560px" }}>
          <input
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => e.key === "Enter" && setQuestion_()}
            placeholder="e.g. Coordination failures are fundamentally epistemological"
            style={{
              flex: 1, background: "#141414", border: "1px solid #333", borderRadius: "4px",
              color: "#e0e0e0", padding: "12px 14px", fontSize: "13px",
              fontFamily: "'JetBrains Mono', monospace", outline: "none",
            }}
            autoFocus
          />
          <button
            onClick={setQuestion_}
            style={{
              background: "#FF6B35", color: "#0A0A0A", border: "none", borderRadius: "4px",
              padding: "12px 20px", fontSize: "12px", fontFamily: "'JetBrains Mono', monospace",
              cursor: "pointer", fontWeight: 600, letterSpacing: "1px",
            }}
          >
            BEGIN
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      height: "100vh", display: "flex", flexDirection: "column",
      background: "#0A0A0A", fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      color: "#e0e0e0", overflow: "hidden",
    }}>
      {/* ── Header ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px", borderBottom: "1px solid #1a1a1a", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ fontSize: "10px", letterSpacing: "3px", color: "#FF6B35", textTransform: "uppercase" }}>
            Workbench
          </span>
          <span style={{ fontSize: "12px", color: "#888", maxWidth: "400px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {question}
          </span>
        </div>
        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          <span style={{ fontSize: "10px", color: "#555" }}>
            {nodes.length} nodes · {edges.length} edges
            {issues.filter(i => i.severity === "high").length > 0 &&
              <span style={{ color: "#f87171", marginLeft: "8px" }}>
                {issues.filter(i => i.severity === "high").length} blind spots
              </span>
            }
          </span>
          <button onClick={reset} style={{
            background: "transparent", border: "1px solid #333", borderRadius: "3px",
            color: "#666", padding: "4px 10px", fontSize: "10px", cursor: "pointer",
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            RESET
          </button>
        </div>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* ── Graph Canvas ── */}
        <div style={{ flex: 1, position: "relative" }}>
          <Graph
            nodes={nodes}
            edges={edges}
            selectedId={selectedId}
            onSelectNode={setSelectedId}
            onCreateEdge={createEdge}
          />
          {/* Edge type selector (floating) */}
          <div style={{
            position: "absolute", bottom: "12px", left: "12px",
            background: "#141414", border: "1px solid #222", borderRadius: "4px",
            padding: "6px 10px", display: "flex", gap: "8px", alignItems: "center",
          }}>
            <span style={{ fontSize: "9px", color: "#555", textTransform: "uppercase", letterSpacing: "1px" }}>
              Shift+drag to connect:
            </span>
            {Object.entries(EDGE_TYPES).map(([key, cfg]) => (
              <button
                key={key}
                onClick={() => setEdgeType(key)}
                style={{
                  background: edgeType === key ? cfg.color + "22" : "transparent",
                  border: `1px solid ${edgeType === key ? cfg.color : "#333"}`,
                  color: cfg.color, padding: "2px 8px", borderRadius: "3px",
                  fontSize: "10px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                {cfg.label}
              </button>
            ))}
          </div>
        </div>

        {/* ── Side Panel ── */}
        <div style={{
          width: "320px", borderLeft: "1px solid #1a1a1a", display: "flex",
          flexDirection: "column", flexShrink: 0, overflow: "hidden",
        }}>
          {/* Tab bar */}
          <div style={{
            display: "flex", borderBottom: "1px solid #1a1a1a", flexShrink: 0,
          }}>
            {[
              { key: "add", label: "Add" },
              { key: "inspect", label: "Inspect" },
              { key: "analysis", label: `Analysis ${issues.length > 0 ? `(${issues.length})` : ""}` },
            ].map(tab => (
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
            {/* ── ADD PANEL ── */}
            {panel === "add" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                <div>
                  <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Type</label>
                  <div style={{ display: "flex", gap: "4px", marginTop: "4px" }}>
                    {Object.entries(NODE_TYPES).filter(([k]) => k !== "thesis").map(([key, cfg]) => (
                      <button
                        key={key}
                        onClick={() => setNewType(key)}
                        style={{
                          flex: 1, background: newType === key ? cfg.color + "22" : "#141414",
                          border: `1px solid ${newType === key ? cfg.color : "#222"}`,
                          color: newType === key ? cfg.color : "#666",
                          padding: "6px 0", borderRadius: "3px", fontSize: "10px",
                          cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
                        }}
                      >
                        {cfg.symbol} {cfg.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Statement</label>
                  <input
                    value={newLabel}
                    onChange={e => setNewLabel(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && addNode()}
                    placeholder={
                      newType === "claim" ? "A specific belief or proposition" :
                      newType === "evidence" ? "Concrete evidence or data" :
                      "An unstated assumption"
                    }
                    style={{
                      width: "100%", background: "#141414", border: "1px solid #222",
                      borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
                      fontSize: "12px", fontFamily: "'JetBrains Mono', monospace",
                      outline: "none", marginTop: "4px", boxSizing: "border-box",
                    }}
                  />
                </div>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>
                      Confidence
                    </label>
                    <span style={{ fontSize: "12px", color: newConfidence >= 80 ? "#f87171" : newConfidence >= 50 ? "#fbbf24" : "#60a5fa" }}>
                      {newConfidence}%
                    </span>
                  </div>
                  <input
                    type="range" min="5" max="99" value={newConfidence}
                    onChange={e => setNewConfidence(parseInt(e.target.value))}
                    style={{ width: "100%", marginTop: "4px", accentColor: "#FF6B35" }}
                  />
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "8px", color: "#444" }}>
                    <span>speculative</span><span>moderate</span><span>very confident</span>
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Notes (optional)</label>
                  <textarea
                    value={newNotes}
                    onChange={e => setNewNotes(e.target.value)}
                    placeholder="Why do you believe this? What would change your mind?"
                    rows={3}
                    style={{
                      width: "100%", background: "#141414", border: "1px solid #222",
                      borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
                      fontSize: "11px", fontFamily: "'JetBrains Mono', monospace",
                      outline: "none", resize: "vertical", marginTop: "4px", boxSizing: "border-box",
                    }}
                  />
                </div>

                <button
                  onClick={addNode}
                  disabled={!newLabel.trim()}
                  style={{
                    background: newLabel.trim() ? "#FF6B35" : "#222",
                    color: newLabel.trim() ? "#0A0A0A" : "#555",
                    border: "none", borderRadius: "3px", padding: "10px",
                    fontSize: "11px", cursor: newLabel.trim() ? "pointer" : "default",
                    fontFamily: "'JetBrains Mono', monospace", fontWeight: 600,
                    letterSpacing: "1px",
                  }}
                >
                  ADD TO GRAPH
                </button>
              </div>
            )}

            {/* ── INSPECT PANEL ── */}
            {panel === "inspect" && (
              <div>
                {selectedNode ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ color: NODE_TYPES[selectedNode.type]?.color, fontSize: "14px" }}>
                        {NODE_TYPES[selectedNode.type]?.symbol}
                      </span>
                      <span style={{ fontSize: "10px", color: "#555", textTransform: "uppercase", letterSpacing: "1px" }}>
                        {NODE_TYPES[selectedNode.type]?.label}
                      </span>
                    </div>

                    <div>
                      <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Statement</label>
                      <input
                        value={selectedNode.label}
                        onChange={e => updateNode(selectedNode.id, { label: e.target.value })}
                        style={{
                          width: "100%", background: "#141414", border: "1px solid #222",
                          borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
                          fontSize: "12px", fontFamily: "'JetBrains Mono', monospace",
                          outline: "none", marginTop: "4px", boxSizing: "border-box",
                        }}
                      />
                    </div>

                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Confidence</label>
                        <span style={{ fontSize: "12px", color: "#FF6B35" }}>{selectedNode.confidence}%</span>
                      </div>
                      <input
                        type="range" min="5" max="99" value={selectedNode.confidence}
                        onChange={e => updateNode(selectedNode.id, { confidence: parseInt(e.target.value) })}
                        style={{ width: "100%", marginTop: "4px", accentColor: "#FF6B35" }}
                      />
                    </div>

                    <div>
                      <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Notes</label>
                      <textarea
                        value={selectedNode.notes || ""}
                        onChange={e => updateNode(selectedNode.id, { notes: e.target.value })}
                        placeholder="Why do you believe this? What would change your mind?"
                        rows={4}
                        style={{
                          width: "100%", background: "#141414", border: "1px solid #222",
                          borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
                          fontSize: "11px", fontFamily: "'JetBrains Mono', monospace",
                          outline: "none", resize: "vertical", marginTop: "4px", boxSizing: "border-box",
                        }}
                      />
                    </div>

                    {/* Connections */}
                    <div>
                      <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px", display: "block" }}>
                        Connections
                      </label>
                      {edges
                        .map((e, i) => ({ edge: e, idx: i }))
                        .filter(({ edge }) => edgeSourceId(edge) === selectedNode.id || edgeTargetId(edge) === selectedNode.id)
                        .map(({ edge, idx }) => {
                          const isSource = edgeSourceId(edge) === selectedNode.id;
                          const otherId = isSource ? edgeTargetId(edge) : edgeSourceId(edge);
                          const other = nodes.find(n => n.id === otherId);
                          const cfg = EDGE_TYPES[edge.type];
                          return (
                            <div key={idx} style={{
                              display: "flex", alignItems: "center", gap: "6px",
                              padding: "4px 6px", background: "#141414", borderRadius: "3px",
                              marginBottom: "4px", fontSize: "10px",
                            }}>
                              <span style={{ color: cfg.color }}>{isSource ? "→" : "←"}</span>
                              <span style={{ color: cfg.color, fontSize: "9px" }}>{cfg.label}</span>
                              <span style={{ color: "#888", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {other?.label || "?"}
                              </span>
                              <button
                                onClick={() => deleteEdge(idx)}
                                style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: "10px", padding: "0 2px" }}
                              >
                                ×
                              </button>
                            </div>
                          );
                        })
                      }
                      {edges.filter(e => edgeSourceId(e) === selectedNode.id || edgeTargetId(e) === selectedNode.id).length === 0 && (
                        <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic" }}>
                          No connections yet. Shift+drag to another node.
                        </div>
                      )}
                    </div>

                    {selectedNode.type !== "thesis" && (
                      <button
                        onClick={() => deleteNode(selectedNode.id)}
                        style={{
                          background: "transparent", border: "1px solid #333",
                          color: "#f87171", borderRadius: "3px", padding: "8px",
                          fontSize: "10px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
                          marginTop: "8px",
                        }}
                      >
                        DELETE NODE
                      </button>
                    )}
                  </div>
                ) : (
                  <div style={{ color: "#444", fontSize: "11px", textAlign: "center", marginTop: "40px" }}>
                    Click a node on the graph to inspect it
                  </div>
                )}
              </div>
            )}

            {/* ── ANALYSIS PANEL ── */}
            {panel === "analysis" && (
              <div>
                {issues.length === 0 ? (
                  <div style={{ textAlign: "center", marginTop: "40px" }}>
                    <div style={{ fontSize: "18px", marginBottom: "8px" }}>✓</div>
                    <div style={{ fontSize: "11px", color: "#4ade80" }}>No blind spots detected</div>
                    <div style={{ fontSize: "10px", color: "#444", marginTop: "4px" }}>
                      Add more claims and connections to deepen the analysis
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "4px" }}>
                      {issues.length} issue{issues.length !== 1 ? "s" : ""} found
                    </div>
                    {issues.map((issue, i) => (
                      <div
                        key={i}
                        onClick={() => { setSelectedId(issue.node); setPanel("inspect"); }}
                        style={{
                          padding: "10px", background: "#141414", borderRadius: "4px",
                          borderLeft: `3px solid ${sevColor[issue.severity]}`,
                          cursor: "pointer", transition: "background 0.15s",
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = "#1a1a1a"}
                        onMouseLeave={e => e.currentTarget.style.background = "#141414"}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
                          <span style={{ color: sevColor[issue.severity], fontSize: "8px" }}>{sevIcon[issue.severity]}</span>
                          <span style={{ fontSize: "9px", color: sevColor[issue.severity], textTransform: "uppercase", letterSpacing: "1px" }}>
                            {issue.severity}
                          </span>
                        </div>
                        <div style={{ fontSize: "11px", color: "#ccc", lineHeight: "1.4" }}>
                          {issue.msg}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
