import { useState } from "react";
import * as api from "../api.js";

const MODALITIES = ["empirical", "analytic", "normative", "modal", "predictive"];
const EVIDENCE_TYPES = ["observation", "experiment", "testimony", "document", "statistical", "formal_proof"];
const PATTERNS = [
  "modus_ponens", "modus_tollens", "abduction", "induction",
  "analogy", "testimony", "causal", "statistical",
];
const NODE_ROLES = ["claim", "thesis", "objection", "concession"];
const SUPPORT_MODES = ["conjunctive", "disjunctive", "independent"];
const RELATIONS = ["supports", "refutes", "rebuts", "concedes", "grounds", "narrows", "supersedes"];
const ROLE_SYMBOLS = { claim: "●", thesis: "◉", objection: "◆", concession: "◇", evidence: "■" };
const ROLE_COLORS = { claim: "#60a5fa", thesis: "#FF6B35", objection: "#f87171", concession: "#fb923c", evidence: "#4ade80" };

function NodeSelect({ value, onChange, nodes, placeholder }) {
  return (
    <select
      value={value} onChange={onChange}
      style={{
        width: "100%", background: "#141414", border: "1px solid #222",
        borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
        fontSize: "11px", fontFamily: "'JetBrains Mono', monospace",
        outline: "none", marginTop: "4px", boxSizing: "border-box",
      }}
    >
      <option value="">{placeholder}</option>
      {nodes.map((n) => (
        <option key={n.id} value={n.id}>
          {ROLE_SYMBOLS[n.node_type || n.type] || "●"} {n.label.length > 44 ? n.label.slice(0, 42) + "…" : n.label}
        </option>
      ))}
    </select>
  );
}

function Label({ children }) {
  return <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>{children}</label>;
}

function Input({ value, onChange, placeholder, ...props }) {
  return (
    <input
      value={value} onChange={onChange} placeholder={placeholder}
      style={{
        width: "100%", background: "#141414", border: "1px solid #222",
        borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
        fontSize: "12px", fontFamily: "'JetBrains Mono', monospace",
        outline: "none", marginTop: "4px", boxSizing: "border-box",
      }}
      {...props}
    />
  );
}

function Select({ value, onChange, options }) {
  return (
    <select
      value={value} onChange={onChange}
      style={{
        width: "100%", background: "#141414", border: "1px solid #222",
        borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
        fontSize: "11px", fontFamily: "'JetBrains Mono', monospace",
        outline: "none", marginTop: "4px", boxSizing: "border-box",
      }}
    >
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

function SubmitButton({ onClick, disabled, children }) {
  return (
    <button
      onClick={onClick} disabled={disabled}
      style={{
        background: disabled ? "#222" : "#FF6B35",
        color: disabled ? "#555" : "#0A0A0A",
        border: "none", borderRadius: "3px", padding: "10px",
        fontSize: "11px", cursor: disabled ? "default" : "pointer",
        fontFamily: "'JetBrains Mono', monospace", fontWeight: 600,
        letterSpacing: "1px", width: "100%",
      }}
    >
      {children}
    </button>
  );
}

export default function AddPanel({ workspace, graphNodes, onAdded }) {
  const [mode, setMode] = useState("text");

  // Quick text claim (F1)
  const [qText, setQText] = useState("");
  const [qRole, setQRole] = useState("claim");
  const [qConf, setQConf] = useState(0.7);
  const [qModality, setQModality] = useState("empirical");

  // Typed link (F1)
  const [linkFrom, setLinkFrom] = useState("");
  const [linkTo, setLinkTo] = useState("");
  const [linkRel, setLinkRel] = useState("supports");

  // Import / export (F1)
  const [importText, setImportText] = useState("");
  const [importMode, setImportMode] = useState("merge");
  const [ioMsg, setIoMsg] = useState(null);

  const [argSupportMode, setArgSupportMode] = useState("conjunctive");

  // Claim form
  const [subject, setSubject] = useState("");
  const [predicate, setPredicate] = useState("");
  const [object, setObject] = useState("");
  const [confidence, setConfidence] = useState(0.7);
  const [modality, setModality] = useState("empirical");
  const [notes, setNotes] = useState("");

  // Evidence form
  const [evTitle, setEvTitle] = useState("");
  const [evDesc, setEvDesc] = useState("");
  const [evType, setEvType] = useState("observation");
  const [evSource, setEvSource] = useState("");
  const [evReliability, setEvReliability] = useState(0.7);

  // Argument form
  const [argConclusion, setArgConclusion] = useState("");
  const [argPremises, setArgPremises] = useState([]);
  const [argPattern, setArgPattern] = useState("abduction");
  const [argLabel, setArgLabel] = useState("");
  const [argConfidence, setArgConfidence] = useState(0.7);

  const addClaim = async () => {
    if (!workspace || !subject.trim() || !predicate.trim() || !object.trim()) return;
    await api.createClaim(workspace, { subject, predicate, object, confidence, modality, notes });
    setSubject(""); setPredicate(""); setObject(""); setNotes(""); setConfidence(0.7);
    onAdded();
  };

  const addEvidence = async () => {
    if (!workspace || !evTitle.trim() || !evDesc.trim()) return;
    await api.createEvidence(workspace, { title: evTitle, description: evDesc, evidence_type: evType, source: evSource, reliability: evReliability });
    setEvTitle(""); setEvDesc(""); setEvSource(""); setEvReliability(0.7);
    onAdded();
  };

  const addArgument = async () => {
    if (!workspace || !argConclusion || argPremises.length === 0) return;
    try {
      await api.addAuthoredArgument(workspace, {
        conclusion_id: argConclusion, premise_ids: argPremises, pattern: argPattern,
        label: argLabel, confidence: argConfidence, support_mode: argSupportMode,
      });
    } catch (err) { alert(err.message); return; }
    setArgLabel(""); setArgPremises([]); setArgConfidence(0.7);
    onAdded();
  };

  const addQuick = async () => {
    if (!workspace || !qText.trim()) return;
    try {
      await api.addClaimText(workspace, { text: qText.trim(), node_type: qRole, confidence: qConf, modality: qModality });
    } catch (err) { alert(err.message); return; }
    setQText(""); setQConf(0.7);
    onAdded();
  };

  const addLink = async () => {
    if (!workspace || !linkFrom || !linkTo || linkFrom === linkTo) return;
    try {
      await api.link(workspace, { from_id: linkFrom, to_id: linkTo, relation: linkRel });
    } catch (err) { alert(err.message); return; }
    setLinkFrom(""); setLinkTo("");
    onAdded();
  };

  const doExport = async () => {
    setIoMsg(null);
    try {
      const g = await api.exportGraph(workspace);
      const text = JSON.stringify(g, null, 2);
      await navigator.clipboard.writeText(text);
      setIoMsg(`Copied ${g.claims.length} claims, ${g.evidence.length} evidence, ${g.arguments.length} arguments, ${g.edges.length} edges to clipboard.`);
    } catch (err) { setIoMsg(err.message); }
  };

  const doImport = async () => {
    setIoMsg(null);
    let g;
    try { g = JSON.parse(importText); } catch { setIoMsg("Not valid JSON."); return; }
    if (importMode === "replace" && !confirm("Replace the whole workspace with this graph? The prior state stays in git history.")) return;
    try {
      const r = await api.importGraph(workspace, g, importMode);
      setIoMsg(`Imported (${r.mode}): ${Object.entries(r).filter(([k]) => !["ok", "mode"].includes(k)).map(([k, v]) => `${k} ${v}`).join(", ")}`);
      setImportText("");
      onAdded();
    } catch (err) { setIoMsg(err.message); }
  };

  if (!workspace) {
    return <div style={{ color: "#555", fontSize: "10px" }}>Select a workspace first.</div>;
  }

  const togglePremise = (id) => {
    setArgPremises((prev) => prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]);
  };

  const confColor = confidence >= 0.8 ? "#f87171" : confidence >= 0.5 ? "#fbbf24" : "#60a5fa";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* Mode selector */}
      <div style={{ display: "flex", gap: "4px" }}>
        {["text", "claim", "evidence", "argument", "link", "import"].map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{
              flex: 1, background: mode === m ? "#FF6B3522" : "#141414",
              border: `1px solid ${mode === m ? "#FF6B35" : "#222"}`,
              color: mode === m ? "#FF6B35" : "#666",
              padding: "6px 0", borderRadius: "3px", fontSize: "10px",
              cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
              textTransform: "uppercase",
            }}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Quick text node (F1) */}
      {mode === "text" && (
        <>
          <div style={{ fontSize: "9px", color: "#555", lineHeight: 1.5 }}>
            Write the statement in plain language and pick its dialectical role. Objections and concessions are first-class nodes; link them with a typed edge afterwards.
          </div>
          <div><Label>Statement</Label>
            <textarea value={qText} onChange={(e) => setQText(e.target.value)} placeholder="e.g. Reputation systems cannot assign responsibility across contexts" rows={3}
              style={{ width: "100%", background: "#141414", border: "1px solid #222", borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px", fontSize: "12px", fontFamily: "'JetBrains Mono', monospace", outline: "none", marginTop: "4px", boxSizing: "border-box", resize: "vertical" }} />
          </div>
          <div><Label>Role</Label>
            <div style={{ display: "flex", gap: "4px", marginTop: "4px" }}>
              {NODE_ROLES.map((r) => (
                <button key={r} onClick={() => setQRole(r)} style={{
                  flex: 1, background: qRole === r ? `${ROLE_COLORS[r]}22` : "#141414",
                  border: `1px solid ${qRole === r ? ROLE_COLORS[r] : "#222"}`,
                  color: qRole === r ? ROLE_COLORS[r] : "#666", padding: "6px 0", borderRadius: "3px",
                  fontSize: "10px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
                }}>{ROLE_SYMBOLS[r]} {r}</button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Label>Confidence</Label>
              <span style={{ fontSize: "12px", color: "#FF6B35" }}>{(qConf * 100).toFixed(0)}%</span>
            </div>
            <input type="range" min="5" max="99" value={qConf * 100} onChange={(e) => setQConf(parseInt(e.target.value) / 100)} style={{ width: "100%", marginTop: "4px", accentColor: "#FF6B35" }} />
          </div>
          <div><Label>Modality</Label><Select value={qModality} onChange={(e) => setQModality(e.target.value)} options={MODALITIES} /></div>
          <SubmitButton onClick={addQuick} disabled={!qText.trim()}>ADD {qRole.toUpperCase()}</SubmitButton>
        </>
      )}

      {/* Typed link (F1) */}
      {mode === "link" && (
        <>
          <div style={{ fontSize: "9px", color: "#555", lineHeight: 1.5 }}>
            Edges are the lossless source of truth. supports / grounds create an argument; refutes / rebuts / concedes attach a defeater; supersedes marks the target as history.
          </div>
          <div><Label>From</Label><NodeSelect value={linkFrom} onChange={(e) => setLinkFrom(e.target.value)} nodes={graphNodes} placeholder="Select source…" /></div>
          <div><Label>Relation</Label><Select value={linkRel} onChange={(e) => setLinkRel(e.target.value)} options={RELATIONS} /></div>
          <div><Label>To</Label><NodeSelect value={linkTo} onChange={(e) => setLinkTo(e.target.value)} nodes={graphNodes} placeholder="Select target…" /></div>
          <SubmitButton onClick={addLink} disabled={!linkFrom || !linkTo || linkFrom === linkTo}>LINK</SubmitButton>
        </>
      )}

      {/* Import / export (F1) */}
      {mode === "import" && (
        <>
          <button onClick={doExport} style={{
            background: "#141414", border: "1px solid #333", color: "#888", borderRadius: "3px",
            padding: "8px", fontSize: "10px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace", letterSpacing: "1px",
          }}>EXPORT WORKSPACE → CLIPBOARD (epist-graph/v1)</button>
          <div><Label>Import JSON (epist-graph/v1 export or a {"{nodes, edges}"} document)</Label>
            <textarea value={importText} onChange={(e) => setImportText(e.target.value)} placeholder='{"nodes": [...], "edges": [...]}' rows={8}
              style={{ width: "100%", background: "#141414", border: "1px solid #222", borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px", fontSize: "10px", fontFamily: "'JetBrains Mono', monospace", outline: "none", marginTop: "4px", boxSizing: "border-box", resize: "vertical" }} />
          </div>
          <div><Label>Mode</Label><Select value={importMode} onChange={(e) => setImportMode(e.target.value)} options={["merge", "replace"]} /></div>
          {ioMsg && <div style={{ fontSize: "10px", color: "#4ade80", lineHeight: 1.5 }}>{ioMsg}</div>}
          <SubmitButton onClick={doImport} disabled={!importText.trim()}>IMPORT</SubmitButton>
        </>
      )}

      {/* Claim form */}
      {mode === "claim" && (
        <>
          <div><Label>Subject</Label><Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="e.g. coordination-failures" /></div>
          <div><Label>Predicate</Label><Input value={predicate} onChange={(e) => setPredicate(e.target.value)} placeholder="e.g. are-caused-by" /></div>
          <div><Label>Object</Label><Input value={object} onChange={(e) => setObject(e.target.value)} placeholder="e.g. epistemic-fragmentation" /></div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Label>Confidence</Label>
              <span style={{ fontSize: "12px", color: confColor }}>{(confidence * 100).toFixed(0)}%</span>
            </div>
            <input type="range" min="5" max="99" value={confidence * 100} onChange={(e) => setConfidence(parseInt(e.target.value) / 100)} style={{ width: "100%", marginTop: "4px", accentColor: "#FF6B35" }} />
          </div>
          <div><Label>Modality</Label><Select value={modality} onChange={(e) => setModality(e.target.value)} options={MODALITIES} /></div>
          <div><Label>Notes</Label><Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Why do you believe this?" /></div>
          <SubmitButton onClick={addClaim} disabled={!subject.trim() || !predicate.trim() || !object.trim()}>ADD CLAIM</SubmitButton>
        </>
      )}

      {/* Evidence form */}
      {mode === "evidence" && (
        <>
          <div><Label>Title</Label><Input value={evTitle} onChange={(e) => setEvTitle(e.target.value)} placeholder="e.g. Replication crisis data" /></div>
          <div><Label>Description</Label><Input value={evDesc} onChange={(e) => setEvDesc(e.target.value)} placeholder="What does this evidence show?" /></div>
          <div><Label>Type</Label><Select value={evType} onChange={(e) => setEvType(e.target.value)} options={EVIDENCE_TYPES} /></div>
          <div><Label>Source</Label><Input value={evSource} onChange={(e) => setEvSource(e.target.value)} placeholder="Citation or URL" /></div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Label>Reliability</Label>
              <span style={{ fontSize: "12px", color: "#FF6B35" }}>{(evReliability * 100).toFixed(0)}%</span>
            </div>
            <input type="range" min="5" max="99" value={evReliability * 100} onChange={(e) => setEvReliability(parseInt(e.target.value) / 100)} style={{ width: "100%", marginTop: "4px", accentColor: "#FF6B35" }} />
          </div>
          <SubmitButton onClick={addEvidence} disabled={!evTitle.trim() || !evDesc.trim()}>ADD EVIDENCE</SubmitButton>
        </>
      )}

      {/* Argument form */}
      {mode === "argument" && (
        <>
          <div>
            <Label>Conclusion (claim)</Label>
            <select
              value={argConclusion} onChange={(e) => setArgConclusion(e.target.value)}
              style={{
                width: "100%", background: "#141414", border: "1px solid #222",
                borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
                fontSize: "11px", fontFamily: "'JetBrains Mono', monospace",
                outline: "none", marginTop: "4px", boxSizing: "border-box",
              }}
            >
              <option value="">Select conclusion…</option>
              {graphNodes.filter((n) => n.type === "claim").map((n) => (
                <option key={n.id} value={n.id}>{n.label.length > 40 ? n.label.slice(0, 38) + "…" : n.label}</option>
              ))}
            </select>
          </div>
          <div>
            <Label>Premises (click to select)</Label>
            <div style={{ maxHeight: "150px", overflow: "auto", marginTop: "4px", border: "1px solid #222", borderRadius: "3px" }}>
              {graphNodes.map((n) => (
                <div
                  key={n.id}
                  onClick={() => togglePremise(n.id)}
                  style={{
                    padding: "5px 8px", cursor: "pointer", fontSize: "10px",
                    background: argPremises.includes(n.id) ? "#FF6B3522" : "transparent",
                    borderLeft: argPremises.includes(n.id) ? "3px solid #FF6B35" : "3px solid transparent",
                    color: argPremises.includes(n.id) ? "#FF6B35" : "#888",
                  }}
                >
                  <span style={{ color: ROLE_COLORS[n.node_type || n.type] || "#60a5fa", marginRight: "6px" }}>
                    {ROLE_SYMBOLS[n.node_type || n.type] || "●"}
                  </span>
                  {n.label.length > 35 ? n.label.slice(0, 33) + "…" : n.label}
                </div>
              ))}
            </div>
          </div>
          <div><Label>Pattern</Label><Select value={argPattern} onChange={(e) => setArgPattern(e.target.value)} options={PATTERNS} /></div>
          <div><Label>Support mode (how premises combine)</Label><Select value={argSupportMode} onChange={(e) => setArgSupportMode(e.target.value)} options={SUPPORT_MODES} /></div>
          <div><Label>Label</Label><Input value={argLabel} onChange={(e) => setArgLabel(e.target.value)} placeholder="Short description of this argument" /></div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <Label>Confidence</Label>
              <span style={{ fontSize: "12px", color: "#FF6B35" }}>{(argConfidence * 100).toFixed(0)}%</span>
            </div>
            <input type="range" min="5" max="99" value={argConfidence * 100} onChange={(e) => setArgConfidence(parseInt(e.target.value) / 100)} style={{ width: "100%", marginTop: "4px", accentColor: "#FF6B35" }} />
          </div>
          <SubmitButton onClick={addArgument} disabled={!argConclusion || argPremises.length === 0}>ADD ARGUMENT</SubmitButton>
        </>
      )}
    </div>
  );
}
