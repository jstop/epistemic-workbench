import { useState, useEffect } from "react";
import * as api from "../api.js";

const NODE_COLORS = {
  claim: "#60a5fa",
  thesis: "#FF6B35",
  objection: "#f87171",
  concession: "#fb923c",
  evidence: "#4ade80",
};

const ROLE_SYMBOLS = { claim: "●", thesis: "◉", objection: "◆", concession: "◇", evidence: "■" };
const EDGE_COLORS = {
  supports: "#4ade80", grounds: "#4ade80", attacks: "#f87171", refutes: "#f87171",
  rebuts: "#f87171", concedes: "#fb923c", narrows: "#a78bfa", supersedes: "#a78bfa",
  assumes: "#fbbf24",
};
const SUPPORT_MODES = ["conjunctive", "disjunctive", "independent"];
const RELATIONS = ["supports", "refutes", "rebuts", "concedes", "grounds", "narrows", "supersedes"];

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

// ── Provenance (evidence only) ─────────────────────────────────────

function ProvenanceSection({ workspace, node, onUpdated }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [quote, setQuote] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [msg, setMsg] = useState(null);
  const recorded = node.provenance === "recorded";
  const detail = node.provenance_detail || {};

  const submit = async () => {
    setMsg(null);
    try {
      const r = await api.attachSource(workspace, {
        node_id: node.id,
        source_id: sourceId ? parseInt(sourceId, 10) : null,
        url, quote,
      });
      if (r.ok) { setOpen(false); setUrl(""); setQuote(""); setSourceId(""); onUpdated(); }
      else setMsg(`Still asserted — ${r.reason}`);
    } catch (err) { setMsg(err.message); }
  };

  return (
    <div>
      <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px", display: "block" }}>
        Provenance
      </label>
      <div style={{
        padding: "8px", background: "#141414", borderRadius: "4px",
        borderLeft: `3px solid ${recorded ? "#4ade80" : "#fbbf24"}`, fontSize: "10px",
      }}>
        <div style={{ color: recorded ? "#4ade80" : "#fbbf24", textTransform: "uppercase", letterSpacing: "1px", fontSize: "9px", marginBottom: "4px" }}>
          {recorded ? "recorded" : "asserted — unverified"}
        </div>
        {recorded ? (
          <div style={{ color: "#999", lineHeight: 1.5, wordBreak: "break-all" }}>
            {detail.source_id != null && <div>recall source #{detail.source_id}</div>}
            {detail.url && <div>{detail.url}</div>}
            {detail.quote && <div style={{ color: "#777", fontStyle: "italic" }}>“{detail.quote}”</div>}
          </div>
        ) : (
          <div style={{ color: "#777", lineHeight: 1.5 }}>
            A source string is not provenance. {node.source ? `Claimed source: ${node.source}` : "No source given."}
          </div>
        )}
      </div>
      {!recorded && !open && (
        <button onClick={() => setOpen(true)} style={btn({ width: "100%", padding: "6px", marginTop: "6px" })}>
          + Attach real source
        </button>
      )}
      {open && (
        <div style={{ background: "#141414", borderRadius: "4px", padding: "8px", marginTop: "6px", display: "flex", flexDirection: "column", gap: "6px" }}>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Source URL" style={inputStyle()} />
          <input value={quote} onChange={(e) => setQuote(e.target.value)} placeholder="Supporting quote (optional)" style={inputStyle()} />
          <input value={sourceId} onChange={(e) => setSourceId(e.target.value)} placeholder="…or an existing recall source id" style={inputStyle()} />
          {msg && <div style={{ fontSize: "9px", color: "#f87171" }}>{msg}</div>}
          <div style={{ display: "flex", gap: "4px" }}>
            <button onClick={submit} disabled={!url && !sourceId} style={btn({ flex: 1, background: "#4ade8022", borderColor: "#4ade80", color: "#4ade80" })}>Record</button>
            <button onClick={() => { setOpen(false); setMsg(null); }} style={btn()}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Supporting arguments: support mode (F3) ────────────────────────

function SupportModeSection({ workspace, args, onUpdated }) {
  if (args.length === 0) return null;
  const change = async (argId, mode) => {
    try {
      await api.setSupportMode(workspace, { argument_id: argId, mode });
      onUpdated();
    } catch (err) { alert(err.message); }
  };
  return (
    <div>
      <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px", display: "block" }}>
        Supporting arguments ({args.length})
      </label>
      {args.map((a) => (
        <div key={a.id} style={{ padding: "6px 8px", background: "#141414", borderRadius: "4px", marginBottom: "4px", fontSize: "10px" }}>
          <div style={{ color: "#ccc", marginBottom: "4px" }}>{a.label || "(unlabeled)"} <span style={{ color: "#555" }}>· {a.pattern} · {Math.round((a.confidence?.level ?? a.confidence ?? 0) * 100)}%</span></div>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ color: "#555", fontSize: "9px" }}>{a.premises?.length || 0} premises, combined</span>
            <select value={a.support_mode || "independent"} onChange={(e) => change(a.id, e.target.value)} style={{ ...inputStyle(), width: "auto", padding: "3px 6px" }}>
              {SUPPORT_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        </div>
      ))}
      <div style={{ fontSize: "9px", color: "#444", marginTop: "2px" }}>
        conjunctive = all premises required (product) · disjunctive = alternatives (max) · independent = each lends support (noisy-OR)
      </div>
    </div>
  );
}

// ── Lifecycle: supersede / typed links (F1 + F4) ───────────────────

function LifecycleSection({ workspace, node, allNodes, onUpdated, onSelectNode }) {
  const [openForm, setOpenForm] = useState(null); // null | "supersede" | "link"
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [relation, setRelation] = useState("rebuts");
  const [direction, setDirection] = useState("out"); // out: node → target ; in: target → node

  const others = allNodes.filter((n) => n.id !== node.id);
  const killer = node.killed_by ? allNodes.find((n) => n.id === node.killed_by) : null;

  const doSupersede = async () => {
    if (!target) return;
    try {
      await api.supersede(workspace, { old_claim_id: node.id, new_claim_id: target, reason });
      setOpenForm(null); setTarget(""); setReason("");
      onUpdated();
    } catch (err) { alert(err.message); }
  };

  const doLink = async () => {
    if (!target) return;
    const body = direction === "out"
      ? { from_id: node.id, to_id: target, relation }
      : { from_id: target, to_id: node.id, relation };
    try {
      await api.link(workspace, body);
      setOpenForm(null); setTarget("");
      onUpdated();
    } catch (err) { alert(err.message); }
  };

  const select = (
    <select value={target} onChange={(e) => setTarget(e.target.value)} style={inputStyle()}>
      <option value="">Select node…</option>
      {others.map((n) => (
        <option key={n.id} value={n.id}>{ROLE_SYMBOLS[n.node_type || n.type] || "●"} {n.label.length > 44 ? n.label.slice(0, 42) + "…" : n.label}</option>
      ))}
    </select>
  );

  return (
    <div>
      <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px", display: "block" }}>
        Lifecycle
      </label>
      {node.status && (
        <div style={{ padding: "6px 8px", background: "#141414", borderRadius: "4px", marginBottom: "6px", fontSize: "10px", borderLeft: "3px solid #a78bfa" }}>
          <span style={{ color: "#a78bfa", textTransform: "uppercase", letterSpacing: "1px", fontSize: "9px" }}>{node.status}</span>
          {killer && (
            <div onClick={() => onSelectNode(killer.id)} style={{ color: "#888", cursor: "pointer", marginTop: "3px" }}>
              {node.status === "superseded" ? "superseded by" : "killed by"}: <span style={{ color: "#ccc" }}>{killer.label.slice(0, 60)}</span>
            </div>
          )}
        </div>
      )}
      {!openForm && (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {node.type === "claim" && !node.status && (
            <button onClick={() => setOpenForm("supersede")} style={btn({ width: "100%", padding: "6px" })}>
              ↻ Supersede with another claim
            </button>
          )}
          <button onClick={() => setOpenForm("link")} style={btn({ width: "100%", padding: "6px" })}>
            ⇄ Add typed link
          </button>
        </div>
      )}
      {openForm === "supersede" && (
        <div style={{ background: "#141414", borderRadius: "4px", padding: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
          <div style={{ fontSize: "9px", color: "#777" }}>This claim stays in the graph as history, marked superseded.</div>
          {select}
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why? (kept as rationale)" style={inputStyle()} />
          <div style={{ display: "flex", gap: "4px" }}>
            <button onClick={doSupersede} disabled={!target} style={btn({ flex: 1, background: "#a78bfa22", borderColor: "#a78bfa", color: "#a78bfa" })}>Supersede</button>
            <button onClick={() => setOpenForm(null)} style={btn()}>Cancel</button>
          </div>
        </div>
      )}
      {openForm === "link" && (
        <div style={{ background: "#141414", borderRadius: "4px", padding: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
          <div style={{ display: "flex", gap: "4px" }}>
            <select value={direction} onChange={(e) => setDirection(e.target.value)} style={inputStyle()}>
              <option value="out">this node →</option>
              <option value="in">→ this node</option>
            </select>
            <select value={relation} onChange={(e) => setRelation(e.target.value)} style={inputStyle()}>
              {RELATIONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          {select}
          <div style={{ display: "flex", gap: "4px" }}>
            <button onClick={doLink} disabled={!target} style={btn({ flex: 1, background: "#FF6B3522", borderColor: "#FF6B35", color: "#FF6B35" })}>Link</button>
            <button onClick={() => setOpenForm(null)} style={btn()}>Cancel</button>
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

  const role = node.node_type || (node.is_root ? "thesis" : node.type);
  const color = NODE_COLORS[role] || NODE_COLORS[node.type] || "#60a5fa";
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
        <span style={{ color, fontSize: "14px" }}>{ROLE_SYMBOLS[role] || "●"}</span>
        <span style={{ fontSize: "10px", color, textTransform: "uppercase", letterSpacing: "1px" }}>{role}</span>
        {node.type === "evidence" && (
          <span style={{ fontSize: "9px", color: node.provenance === "recorded" ? "#4ade80" : "#fbbf24", textTransform: "uppercase", letterSpacing: "1px" }}>
            {node.provenance === "recorded" ? "recorded" : "asserted"}
          </span>
        )}
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
        {node.derived != null && (
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: "4px" }}>
            <span style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>Derived (propagated)</span>
            <span style={{ fontSize: "11px", color: Math.abs(node.derived - node.confidence) >= 0.05 ? "#fbbf24" : "#888" }}>
              {(node.derived * 100).toFixed(0)}%
            </span>
          </div>
        )}
        {node.type === "claim" && (
          <div style={{ fontSize: "9px", color: "#444", marginTop: "2px" }}>
            Stored value is what was asserted; derived is what the supporting arguments and objections actually warrant. Use "Set confidence" below to change the stored value.
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
            const edgeColor = EDGE_COLORS[edge.type] || "#4ade80";
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
                <span style={{ color: edgeColor, fontSize: "9px" }}>{edge.type}{edge.support_mode && edge.support_mode !== "independent" ? ` (${edge.support_mode})` : ""}</span>
                <span style={{ color: "#888", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {other?.label || "?"}
                </span>
              </div>
            );
          })
        )}
      </div>

      {node.type === "evidence" && workspace && (
        <ProvenanceSection workspace={workspace} node={node} onUpdated={onUpdated} />
      )}

      {node.type === "claim" && workspace && (
        <SupportModeSection
          workspace={workspace}
          args={supportingArgs}
          onUpdated={() => {
            api.getArgumentsForNode(workspace, node.id).then(setRelatedArgs).catch(() => {});
            onUpdated();
          }}
        />
      )}

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

      {workspace && (
        <LifecycleSection
          workspace={workspace}
          node={node}
          allNodes={allNodes}
          onUpdated={onUpdated}
          onSelectNode={onSelectNode}
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
        DELETE {node.type.toUpperCase()} (prefer supersede — deletion loses the dialectic)
      </button>
    </div>
  );
}
