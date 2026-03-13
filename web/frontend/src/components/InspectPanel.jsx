import { useState, useEffect } from "react";
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

const DEFEATER_STATUS_COLORS = {
  active: "#f87171",
  answered: "#4ade80",
  withdrawn: "#555",
};

function DefeaterSection({ arguments: args, onUpdated }) {
  const [newDefeaterArg, setNewDefeaterArg] = useState(null);
  const [newDesc, setNewDesc] = useState("");
  const [newType, setNewType] = useState("undercutting");

  const allDefeaters = args.flatMap((a) =>
    (a.defeaters || []).map((d) => ({ ...d, argumentId: a.id, argumentLabel: a.label }))
  );

  const handleStatusChange = async (argId, idx, newStatus) => {
    await api.updateDefeater(argId, idx, { status: newStatus });
    onUpdated();
  };

  const handleAddDefeater = async () => {
    if (!newDefeaterArg || !newDesc.trim()) return;
    await api.addDefeater(newDefeaterArg, { type: newType, description: newDesc.trim() });
    setNewDesc("");
    setNewDefeaterArg(null);
    onUpdated();
  };

  return (
    <div>
      <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px", display: "block" }}>
        Defeaters ({allDefeaters.length})
      </label>

      {allDefeaters.length === 0 && (
        <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic", marginBottom: "8px" }}>
          No defeaters on supporting arguments
        </div>
      )}

      {allDefeaters.map((d, i) => {
        const statusColor = DEFEATER_STATUS_COLORS[d.status] || "#555";
        return (
          <div key={i} style={{
            padding: "8px", background: "#141414", borderRadius: "4px",
            borderLeft: `3px solid ${statusColor}`, marginBottom: "6px",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
              <span style={{ fontSize: "9px", color: statusColor, textTransform: "uppercase", letterSpacing: "1px" }}>
                {d.type} · {d.status}
              </span>
            </div>
            <div style={{ fontSize: "10px", color: "#ccc", lineHeight: "1.4", marginBottom: "6px" }}>
              {d.description}
            </div>
            {d.response && (
              <div style={{ fontSize: "10px", color: "#4ade80", lineHeight: "1.4", marginBottom: "6px", paddingLeft: "8px", borderLeft: "2px solid #333" }}>
                Response: {d.response}
              </div>
            )}
            <div style={{ fontSize: "9px", color: "#444", marginBottom: "4px" }}>
              on: {d.argumentLabel || d.argumentId.slice(0, 12) + "…"}
            </div>
            <div style={{ display: "flex", gap: "4px" }}>
              {d.status === "active" && (
                <>
                  <button
                    onClick={() => {
                      const response = prompt("How is this defeater answered?");
                      if (response !== null) {
                        api.updateDefeater(d.argumentId, d.index, { status: "answered", response }).then(onUpdated);
                      }
                    }}
                    style={{
                      background: "#4ade8022", border: "1px solid #4ade80", color: "#4ade80",
                      borderRadius: "3px", padding: "3px 8px", fontSize: "9px", cursor: "pointer",
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    ANSWER
                  </button>
                  <button
                    onClick={() => handleStatusChange(d.argumentId, d.index, "withdrawn")}
                    style={{
                      background: "transparent", border: "1px solid #333", color: "#666",
                      borderRadius: "3px", padding: "3px 8px", fontSize: "9px", cursor: "pointer",
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    WITHDRAW
                  </button>
                </>
              )}
              {d.status !== "active" && (
                <button
                  onClick={() => handleStatusChange(d.argumentId, d.index, "active")}
                  style={{
                    background: "#f8717122", border: "1px solid #f87171", color: "#f87171",
                    borderRadius: "3px", padding: "3px 8px", fontSize: "9px", cursor: "pointer",
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  REACTIVATE
                </button>
              )}
            </div>
          </div>
        );
      })}

      {/* Add defeater */}
      {args.length > 0 && (
        <div style={{ marginTop: "6px" }}>
          {newDefeaterArg === null ? (
            <button
              onClick={() => setNewDefeaterArg(args[0].id)}
              style={{
                background: "transparent", border: "1px solid #333", color: "#888",
                borderRadius: "3px", padding: "6px", fontSize: "9px", cursor: "pointer",
                fontFamily: "'JetBrains Mono', monospace", width: "100%",
                textTransform: "uppercase", letterSpacing: "1px",
              }}
            >
              + Add Defeater
            </button>
          ) : (
            <div style={{ background: "#141414", borderRadius: "4px", padding: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
              {args.length > 1 && (
                <select
                  value={newDefeaterArg} onChange={(e) => setNewDefeaterArg(e.target.value)}
                  style={{
                    background: "#0A0A0A", border: "1px solid #222", borderRadius: "3px",
                    color: "#e0e0e0", padding: "6px", fontSize: "10px",
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  {args.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label || a.id.slice(0, 12) + "…"}
                    </option>
                  ))}
                </select>
              )}
              <select
                value={newType} onChange={(e) => setNewType(e.target.value)}
                style={{
                  background: "#0A0A0A", border: "1px solid #222", borderRadius: "3px",
                  color: "#e0e0e0", padding: "6px", fontSize: "10px",
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                <option value="undercutting">undercutting</option>
                <option value="rebutting">rebutting</option>
                <option value="undermining">undermining</option>
              </select>
              <input
                value={newDesc} onChange={(e) => setNewDesc(e.target.value)}
                placeholder="What challenges this argument?"
                onKeyDown={(e) => e.key === "Enter" && handleAddDefeater()}
                style={{
                  background: "#0A0A0A", border: "1px solid #222", borderRadius: "3px",
                  color: "#e0e0e0", padding: "6px", fontSize: "10px",
                  fontFamily: "'JetBrains Mono', monospace", outline: "none",
                }}
              />
              <div style={{ display: "flex", gap: "4px" }}>
                <button
                  onClick={handleAddDefeater}
                  disabled={!newDesc.trim()}
                  style={{
                    flex: 1, background: newDesc.trim() ? "#FF6B35" : "#222",
                    color: newDesc.trim() ? "#0A0A0A" : "#555",
                    border: "none", borderRadius: "3px", padding: "6px",
                    fontSize: "9px", cursor: newDesc.trim() ? "pointer" : "default",
                    fontFamily: "'JetBrains Mono', monospace", fontWeight: 600,
                  }}
                >
                  ADD
                </button>
                <button
                  onClick={() => { setNewDefeaterArg(null); setNewDesc(""); }}
                  style={{
                    background: "transparent", border: "1px solid #333", color: "#666",
                    borderRadius: "3px", padding: "6px", fontSize: "9px", cursor: "pointer",
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  CANCEL
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function InspectPanel({ node, edges, allNodes, onUpdated, onSelectNode }) {
  const [relatedArgs, setRelatedArgs] = useState([]);

  useEffect(() => {
    if (!node) { setRelatedArgs([]); return; }
    api.getArgumentsForNode(node.id).then(setRelatedArgs).catch(() => setRelatedArgs([]));
  }, [node?.id]);

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

  // Arguments that conclude this node (for defeater management)
  const supportingArgs = relatedArgs.filter((a) => a.conclusion === node.id);

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

      {/* Defeaters */}
      {node.type === "claim" && (
        <DefeaterSection
          arguments={supportingArgs}
          onUpdated={() => {
            api.getArgumentsForNode(node.id).then(setRelatedArgs).catch(() => {});
            onUpdated();
          }}
        />
      )}

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
