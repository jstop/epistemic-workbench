import { useState } from "react";
import * as api from "../api.js";

const MODALITIES = ["empirical", "analytic", "normative", "modal", "predictive"];
const EVIDENCE_TYPES = ["observation", "experiment", "testimony", "document", "statistical", "formal_proof"];
const PATTERNS = [
  "modus_ponens", "modus_tollens", "abduction", "induction",
  "analogy", "testimony", "causal", "statistical",
];

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
  const [mode, setMode] = useState("claim");

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
    await api.createArgument(workspace, { conclusion: argConclusion, premises: argPremises, pattern: argPattern, label: argLabel, confidence: argConfidence });
    setArgLabel(""); setArgPremises([]); setArgConfidence(0.7);
    onAdded();
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
        {["claim", "evidence", "argument"].map((m) => (
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
                  <span style={{ color: n.type === "evidence" ? "#4ade80" : "#60a5fa", marginRight: "6px" }}>
                    {n.type === "evidence" ? "■" : "●"}
                  </span>
                  {n.label.length > 35 ? n.label.slice(0, 33) + "…" : n.label}
                </div>
              ))}
            </div>
          </div>
          <div><Label>Pattern</Label><Select value={argPattern} onChange={(e) => setArgPattern(e.target.value)} options={PATTERNS} /></div>
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
