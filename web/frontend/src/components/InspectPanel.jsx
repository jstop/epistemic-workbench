import { useState } from "react";
import * as api from "../api.js";

const NODE_COLORS = {
  claim: "#60a5fa",
  evidence: "#4ade80",
};

const ATMS_COLORS = {
  accepted: "#4ade80",
  provisional: "#fbbf24",
  defeated: "#f87171",
  unknown: "#555",
};

export default function InspectPanel({ node, edges, allNodes, onUpdated, onSelectNode }) {
  const [editing, setEditing] = useState(false);

  if (!node) {
    return (
      <div style={{ color: "#444", fontSize: "11px", textAlign: "center", marginTop: "40px" }}>
        Click a node on the graph to inspect it
      </div>
    );
  }

  const color = NODE_COLORS[node.type] || "#60a5fa";
  const atmsColor = ATMS_COLORS[node.atms] || "#555";

  // Find connections
  const connections = edges
    .map((e, i) => ({ edge: e, idx: i }))
    .filter(({ edge }) => {
      const src = edge.source?.id || edge.source;
      const tgt = edge.target?.id || edge.target;
      return src === node.id || tgt === node.id;
    })
    .map(({ edge, idx }) => {
      const src = edge.source?.id || edge.source;
      const isSource = src === node.id;
      const otherId = isSource ? (edge.target?.id || edge.target) : src;
      const other = allNodes.find((n) => n.id === otherId);
      return { edge, idx, isSource, other };
    });

  const handleDelete = async () => {
    if (!confirm(`Delete this ${node.type}?`)) return;
    if (node.type === "claim") await api.deleteClaim(node.id);
    else if (node.type === "evidence") await api.deleteEvidence(node.id);
    onUpdated();
  };

  const handleConfidenceChange = async (val) => {
    if (node.type === "claim") {
      await api.updateClaim(node.id, { confidence: val / 100 });
      onUpdated();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* Type + ATMS badge */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span style={{ color, fontSize: "14px" }}>{node.type === "evidence" ? "■" : "●"}</span>
        <span style={{ fontSize: "10px", color: "#555", textTransform: "uppercase", letterSpacing: "1px" }}>{node.type}</span>
        <span style={{ fontSize: "10px", color: atmsColor, marginLeft: "auto", textTransform: "uppercase" }}>{node.atms}</span>
      </div>

      {/* Label */}
      <div>
        <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>
          {node.type === "claim" ? "Statement" : "Title"}
        </label>
        <div style={{
          width: "100%", background: "#141414", border: "1px solid #222",
          borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
          fontSize: "12px", fontFamily: "'JetBrains Mono', monospace",
          marginTop: "4px", boxSizing: "border-box", lineHeight: "1.4",
          wordBreak: "break-word",
        }}>
          {node.label}
        </div>
      </div>

      {/* Confidence */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>
            {node.type === "evidence" ? "Reliability" : "Confidence"}
          </label>
          <span style={{ fontSize: "12px", color: "#FF6B35" }}>{(node.confidence * 100).toFixed(0)}%</span>
        </div>
        <input
          type="range" min="5" max="99"
          value={node.confidence * 100}
          onChange={(e) => handleConfidenceChange(parseInt(e.target.value))}
          disabled={node.type !== "claim"}
          style={{ width: "100%", marginTop: "4px", accentColor: "#FF6B35" }}
        />
      </div>

      {/* Modality */}
      {node.modality && (
        <div>
          <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Modality</label>
          <div style={{ fontSize: "11px", color: "#888", marginTop: "4px" }}>{node.modality}</div>
        </div>
      )}

      {/* Notes */}
      {node.notes && (
        <div>
          <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Notes</label>
          <div style={{
            background: "#141414", border: "1px solid #222", borderRadius: "3px",
            color: "#999", padding: "8px 10px", fontSize: "11px",
            fontFamily: "'JetBrains Mono', monospace", marginTop: "4px",
            lineHeight: "1.5", wordBreak: "break-word",
          }}>
            {node.notes}
          </div>
        </div>
      )}

      {/* Connections */}
      <div>
        <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px", display: "block" }}>
          Connections ({connections.length})
        </label>
        {connections.length === 0 ? (
          <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic" }}>No connections</div>
        ) : (
          connections.map(({ edge, isSource, other }, i) => {
            const edgeColor = edge.type === "attacks" ? "#f87171" : edge.type === "assumes" ? "#fbbf24" : "#4ade80";
            return (
              <div
                key={i}
                onClick={() => other && onSelectNode(other.id)}
                style={{
                  display: "flex", alignItems: "center", gap: "6px",
                  padding: "5px 6px", background: "#141414", borderRadius: "3px",
                  marginBottom: "4px", fontSize: "10px", cursor: "pointer",
                }}
              >
                <span style={{ color: edgeColor }}>{isSource ? "→" : "←"}</span>
                <span style={{ color: edgeColor, fontSize: "9px" }}>{edge.type}</span>
                <span style={{ color: "#888", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {other?.label || "?"}
                </span>
              </div>
            );
          })
        )}
      </div>

      {/* ID */}
      <div>
        <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>ID</label>
        <div style={{ fontSize: "9px", color: "#444", fontFamily: "'JetBrains Mono', monospace", marginTop: "2px", wordBreak: "break-all" }}>
          {node.id}
        </div>
      </div>

      {/* Delete */}
      <button
        onClick={handleDelete}
        style={{
          background: "transparent", border: "1px solid #333",
          color: "#f87171", borderRadius: "3px", padding: "8px",
          fontSize: "10px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        DELETE {node.type.toUpperCase()}
      </button>
    </div>
  );
}
