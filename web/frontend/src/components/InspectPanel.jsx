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
  conceded: "#fb923c",
  answered: "#4ade80",
  withdrawn: "#555",
};

function btn(extra = {}) {
  return {
    background: "transparent",
    border: "1px solid #333",
    color: "#888",
    borderRadius: "3px",
    padding: "5px 8px",
    fontSize: "9px",
    cursor: "pointer",
    fontFamily: "'JetBrains Mono', monospace",
    letterSpacing: "1px",
    textTransform: "uppercase",
    ...extra,
  };
}

function inputStyle() {
  return {
    background: "#0A0A0A",
    border: "1px solid #222",
    borderRadius: "3px",
    color: "#e0e0e0",
    padding: "6px",
    fontSize: "10px",
    fontFamily: "'JetBrains Mono', monospace",
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
  };
}

// ── Defeater section (per-argument; supports concede) ──────────────

function DefeaterSection({ workspace, args, onUpdated }) {
  const [newDefeaterArg, setNewDefeaterArg] = useState(null);
  const [newDesc, setNewDesc] = useState("");
  const [newType, setNewType] = useState("undercutting");

  const allDefeaters = args.flatMap((a) =>
    (a.defeaters || []).map((d) => ({ ...d, argumentId: a.id, argumentLabel: a.label }))
  );

  const handleStatusChange = async (argId, idx, newStatus) => {
    await api.updateDefeater(workspace, argId, idx, { status: newStatus });
    onUpdated();
  };

  const handleAnswer = async (d) => {
    const response = prompt("How is this defeater answered (rebutted)?");
    if (response === null) return;
    await api.respondToDefeater(workspace, {
      argument_id: d.argumentId,
      response,
      defeater_index: d.index,
    });
    onUpdated();
  };

  const handleConcede = async (d) => {
    const note = prompt(
      "Concede this defeater (accept it as valid). What part of your thesis are you conceding?"
    );
    if (note === null) return;
    await api.concedeDefeater(workspace, {
      argument_id: d.argumentId,
      note,
      defeater_index: d.index,
    });
    onUpdated();
  };

  const handleAddDefeater = async () => {
    if (!newDefeaterArg || !newDesc.trim()) return;
    await api.addDefeater(workspace, newDefeaterArg, {
      type: newType,
      description: newDesc.trim(),
    });
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
              <div style={{
                fontSize: "10px",
                color: d.status === "conceded" ? "#fb923c" : "#4ade80",
                lineHeight: "1.4", marginBottom: "6px",
                paddingLeft: "8px", borderLeft: "2px solid #333",
              }}>
                {d.status === "conceded" ? "Conceded: " : "Response: "}{d.response}
              </div>
            )}
            <div style={{ fontSize: "9px", color: "#444", marginBottom: "4px" }}>
              on: {d.argumentLabel || d.argumentId.slice(0, 12) + "…"}
            </div>
            <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
              {d.status === "active" && (
                <>
                  <button
                    onClick={() => handleAnswer(d)}
                    style={btn({ background: "#4ade8022", borderColor: "#4ade80", color: "#4ade80" })}
                  >
                    Answer
                  </button>
                  <button
                    onClick={() => handleConcede(d)}
                    style={btn({ background: "#fb923c22", borderColor: "#fb923c", color: "#fb923c" })}
                  >
                    Concede
                  </button>
                  <button
                    onClick={() => handleStatusChange(d.argumentId, d.index, "withdrawn")}
                    style={btn()}
                  >
                    Withdraw
                  </button>
                </>
              )}
              {d.status !== "active" && (
                <button
                  onClick={() => handleStatusChange(d.argumentId, d.index, "active")}
                  style={btn({ background: "#f8717122", borderColor: "#f87171", color: "#f87171" })}
                >
                  Reactivate
                </button>
              )}
            </div>
          </div>
        );
      })}

      {args.length > 0 && (
        <div style={{ marginTop: "6px" }}>
          {newDefeaterArg === null ? (
            <button
              onClick={() => setNewDefeaterArg(args[0].id)}
              style={btn({ width: "100%", padding: "6px" })}
            >
              + Add Defeater
            </button>
          ) : (
            <div style={{ background: "#141414", borderRadius: "4px", padding: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
              {args.length > 1 && (
                <select
                  value={newDefeaterArg}
                  onChange={(e) => setNewDefeaterArg(e.target.value)}
                  style={inputStyle()}
                >
                  {args.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label || a.id.slice(0, 12) + "…"}
                    </option>
                  ))}
                </select>
              )}
              <select value={newType} onChange={(e) => setNewType(e.target.value)} style={inputStyle()}>
                <option value="undercutting">undercutting</option>
                <option value="rebutting">rebutting</option>
                <option value="undermining">undermining</option>
              </select>
              <input
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="What challenges this argument?"
                onKeyDown={(e) => e.key === "Enter" && handleAddDefeater()}
                style={inputStyle()}
              />
              <div style={{ display: "flex", gap: "4px" }}>
                <button
                  onClick={handleAddDefeater}
                  disabled={!newDesc.trim()}
                  style={{
                    flex: 1,
                    background: newDesc.trim() ? "#FF6B35" : "#222",
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
                  style={btn()}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Manual intervention shortcuts (claim only) ─────────────────────

function ManualIntervention({ workspace, node, onUpdated }) {
  const [openForm, setOpenForm] = useState(null); // null | "evidence" | "challenge" | "confidence"
  const [evTitle, setEvTitle] = useState("");
  const [evDesc, setEvDesc] = useState("");
  const [evSource, setEvSource] = useState("");
  const [evReliability, setEvReliability] = useState(0.7);
  const [chDesc, setChDesc] = useState("");
  const [chType, setChType] = useState("undercutting");
  const [confValue, setConfValue] = useState(node.confidence);
  const [confNote, setConfNote] = useState("");

  useEffect(() => {
    setConfValue(node.confidence);
  }, [node.confidence]);

  const reset = () => {
    setOpenForm(null);
    setEvTitle(""); setEvDesc(""); setEvSource(""); setEvReliability(0.7);
    setChDesc(""); setChType("undercutting");
    setConfNote("");
  };

  const submitEvidence = async () => {
    if (!evTitle.trim() || !evDesc.trim()) return;
    await api.addEvidenceToClaim(workspace, {
      claim_id: node.id,
      title: evTitle.trim(),
      description: evDesc.trim(),
      source: evSource,
      reliability: evReliability,
    });
    reset();
    onUpdated();
  };

  const submitChallenge = async () => {
    if (!chDesc.trim()) return;
    try {
      await api.challengeClaim(workspace, {
        claim_id: node.id,
        description: chDesc.trim(),
        defeater_type: chType,
      });
      reset();
      onUpdated();
    } catch (err) {
      alert(err.message);
    }
  };

  const submitConfidence = async () => {
    await api.setConfidence(workspace, {
      claim_id: node.id,
      confidence: confValue,
      note: confNote,
    });
    reset();
    onUpdated();
  };

  return (
    <div>
      <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px", display: "block" }}>
        Manual Intervention
      </label>

      {!openForm && (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <button onClick={() => setOpenForm("evidence")} style={btn({ width: "100%", padding: "6px" })}>
            + Add evidence
          </button>
          <button onClick={() => setOpenForm("challenge")} style={btn({ width: "100%", padding: "6px" })}>
            + Challenge this claim
          </button>
          <button onClick={() => setOpenForm("confidence")} style={btn({ width: "100%", padding: "6px" })}>
            ⚙ Set confidence
          </button>
        </div>
      )}

      {openForm === "evidence" && (
        <div style={{ background: "#141414", borderRadius: "4px", padding: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
          <input value={evTitle} onChange={(e) => setEvTitle(e.target.value)} placeholder="Title" style={inputStyle()} />
          <input value={evDesc} onChange={(e) => setEvDesc(e.target.value)} placeholder="Description" style={inputStyle()} />
          <input value={evSource} onChange={(e) => setEvSource(e.target.value)} placeholder="Source / citation" style={inputStyle()} />
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
              <span style={{ fontSize: "9px", color: "#555" }}>RELIABILITY</span>
              <span style={{ fontSize: "10px", color: "#FF6B35" }}>{(evReliability * 100).toFixed(0)}%</span>
            </div>
            <input
              type="range" min="5" max="99" value={evReliability * 100}
              onChange={(e) => setEvReliability(parseInt(e.target.value) / 100)}
              style={{ width: "100%", accentColor: "#FF6B35" }}
            />
          </div>
          <div style={{ display: "flex", gap: "4px" }}>
            <button onClick={submitEvidence} disabled={!evTitle.trim() || !evDesc.trim()} style={btn({
              flex: 1, background: "#FF6B3522", borderColor: "#FF6B35", color: "#FF6B35",
            })}>Add</button>
            <button onClick={reset} style={btn()}>Cancel</button>
          </div>
        </div>
      )}

      {openForm === "challenge" && (
        <div style={{ background: "#141414", borderRadius: "4px", padding: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
          <select value={chType} onChange={(e) => setChType(e.target.value)} style={inputStyle()}>
            <option value="undercutting">undercutting</option>
            <option value="rebutting">rebutting</option>
            <option value="undermining">undermining</option>
          </select>
          <input value={chDesc} onChange={(e) => setChDesc(e.target.value)} placeholder="What challenges this claim?" style={inputStyle()} />
          <div style={{ display: "flex", gap: "4px" }}>
            <button onClick={submitChallenge} disabled={!chDesc.trim()} style={btn({
              flex: 1, background: "#f8717122", borderColor: "#f87171", color: "#f87171",
            })}>Challenge</button>
            <button onClick={reset} style={btn()}>Cancel</button>
          </div>
        </div>
      )}

      {openForm === "confidence" && (
        <div style={{ background: "#141414", borderRadius: "4px", padding: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
              <span style={{ fontSize: "9px", color: "#555" }}>CONFIDENCE</span>
              <span style={{ fontSize: "10px", color: "#FF6B35" }}>{(confValue * 100).toFixed(0)}%</span>
            </div>
            <input
              type="range" min="5" max="99" value={confValue * 100}
              onChange={(e) => setConfValue(parseInt(e.target.value) / 100)}
              style={{ width: "100%", accentColor: "#FF6B35" }}
            />
          </div>
          <input value={confNote} onChange={(e) => setConfNote(e.target.value)} placeholder="Reason for adjustment (optional)" style={inputStyle()} />
          <div style={{ display: "flex", gap: "4px" }}>
            <button onClick={submitConfidence} style={btn({
              flex: 1, background: "#FF6B3522", borderColor: "#FF6B35", color: "#FF6B35",
            })}>Save</button>
            <button onClick={reset} style={btn()}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main InspectPanel ──────────────────────────────────────────────

export default function InspectPanel({ workspace, node, edges, allNodes, onUpdated, onSelectNode }) {
  const [relatedArgs, setRelatedArgs] = useState([]);

  useEffect(() => {
    if (!workspace || !node) { setRelatedArgs([]); return; }
    api.getArgumentsForNode(workspace, node.id).then(setRelatedArgs).catch(() => setRelatedArgs([]));
  }, [workspace, node?.id]);

  if (!node) {
    return (
      <div style={{ color: "#444", fontSize: "11px", textAlign: "center", marginTop: "40px" }}>
        Click a node on the graph to inspect it
      </div>
    );
  }

  const color = NODE_COLORS[node.type] || "#60a5fa";
  const atmsColor = ATMS_COLORS[node.atms] || "#555";

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
    if (node.type === "claim") await api.deleteClaim(workspace, node.id);
    else if (node.type === "evidence") await api.deleteEvidence(workspace, node.id);
    onUpdated();
  };

  const supportingArgs = relatedArgs.filter((a) => a.conclusion === node.id);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span style={{ color, fontSize: "14px" }}>{node.type === "evidence" ? "■" : "●"}</span>
        <span style={{ fontSize: "10px", color: "#555", textTransform: "uppercase", letterSpacing: "1px" }}>{node.type}</span>
        <span style={{ fontSize: "10px", color: atmsColor, marginLeft: "auto", textTransform: "uppercase" }}>{node.atms}</span>
      </div>

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
          readOnly
          disabled
          style={{ width: "100%", marginTop: "4px", accentColor: "#FF6B35" }}
        />
        {node.type === "claim" && (
          <div style={{ fontSize: "9px", color: "#444", marginTop: "2px" }}>
            Use "Set confidence" below to change.
          </div>
        )}
      </div>

      {node.modality && (
        <div>
          <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Modality</label>
          <div style={{ fontSize: "11px", color: "#888", marginTop: "4px" }}>{node.modality}</div>
        </div>
      )}

      {node.notes && (
        <div>
          <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Notes</label>
          <div style={{
            background: "#141414", border: "1px solid #222", borderRadius: "3px",
            color: "#999", padding: "8px 10px", fontSize: "11px",
            fontFamily: "'JetBrains Mono', monospace", marginTop: "4px",
            lineHeight: "1.5", wordBreak: "break-word", whiteSpace: "pre-wrap",
          }}>
            {node.notes}
          </div>
        </div>
      )}

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

      {node.type === "claim" && (
        <DefeaterSection
          workspace={workspace}
          args={supportingArgs}
          onUpdated={() => {
            api.getArgumentsForNode(workspace, node.id).then(setRelatedArgs).catch(() => {});
            onUpdated();
          }}
        />
      )}

      {node.type === "claim" && workspace && (
        <ManualIntervention
          workspace={workspace}
          node={node}
          onUpdated={onUpdated}
        />
      )}

      <div>
        <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>ID</label>
        <div style={{ fontSize: "9px", color: "#444", fontFamily: "'JetBrains Mono', monospace", marginTop: "2px", wordBreak: "break-all" }}>
          {node.id}
        </div>
      </div>

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
