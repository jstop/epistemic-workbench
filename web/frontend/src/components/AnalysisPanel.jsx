import { useState, useEffect } from "react";
import * as api from "../api.js";

const SEV = {
  error: { color: "#f87171", icon: "▲" },
  warning: { color: "#fbbf24", icon: "◆" },
  info: { color: "#60a5fa", icon: "●" },
};

const RISK = {
  high: { color: "#f87171" },
  medium: { color: "#fbbf24" },
  low: { color: "#60a5fa" },
};

function Section({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginBottom: "16px" }}>
      <div
        onClick={() => setOpen(!open)}
        style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: "6px", marginBottom: "8px" }}
      >
        <span style={{ fontSize: "10px", color: "#555" }}>{open ? "▼" : "▶"}</span>
        <span style={{ fontSize: "10px", color: "#FF6B35", letterSpacing: "1px", textTransform: "uppercase" }}>{title}</span>
      </div>
      {open && children}
    </div>
  );
}

export default function AnalysisPanel({ workspace, selectedId, onSelectNode, onHighlight }) {
  const [coherence, setCoherence] = useState([]);
  const [blindSpots, setBlindSpots] = useState([]);
  const [stressTest, setStressTest] = useState(null);
  const [assumptions, setAssumptions] = useState([]);

  useEffect(() => {
    if (!workspace) return;
    api.getCoherence(workspace).then(setCoherence).catch(() => {});
    api.getBlindSpots(workspace).then(setBlindSpots).catch(() => {});
  }, [workspace]);

  useEffect(() => {
    if (!workspace || !selectedId) {
      setStressTest(null);
      setAssumptions([]);
      return;
    }
    api.getStressTest(workspace, selectedId).then(setStressTest).catch(() => setStressTest(null));
    api.getAssumptions(workspace, selectedId).then(setAssumptions).catch(() => setAssumptions([]));
  }, [workspace, selectedId]);

  const refresh = () => {
    if (!workspace) return;
    api.getCoherence(workspace).then(setCoherence).catch(() => {});
    api.getBlindSpots(workspace).then(setBlindSpots).catch(() => {});
  };

  if (!workspace) {
    return <div style={{ color: "#555", fontSize: "10px" }}>Select a workspace first.</div>;
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <span style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>
          {coherence.length + blindSpots.length} issue{coherence.length + blindSpots.length !== 1 ? "s" : ""}
        </span>
        <button onClick={refresh} style={{
          background: "transparent", border: "1px solid #333", borderRadius: "3px",
          color: "#666", padding: "2px 8px", fontSize: "9px", cursor: "pointer",
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          REFRESH
        </button>
      </div>

      <Section title={`Coherence (${coherence.length})`}>
        {coherence.length === 0 ? (
          <div style={{ fontSize: "10px", color: "#4ade80" }}>No coherence issues</div>
        ) : (
          coherence.map((iss, i) => {
            const sev = SEV[iss.severity] || SEV.info;
            return (
              <div
                key={i}
                onClick={() => { if (iss.objects?.[0]) onSelectNode(iss.objects[0]); }}
                onMouseEnter={() => onHighlight(iss.objects || [])}
                onMouseLeave={() => onHighlight([])}
                style={{
                  padding: "8px", background: "#141414", borderRadius: "4px",
                  borderLeft: `3px solid ${sev.color}`, marginBottom: "6px", cursor: "pointer",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "3px" }}>
                  <span style={{ color: sev.color, fontSize: "8px" }}>{sev.icon}</span>
                  <span style={{ fontSize: "9px", color: sev.color, textTransform: "uppercase", letterSpacing: "1px" }}>
                    {iss.check}
                  </span>
                </div>
                <div style={{ fontSize: "10px", color: "#ccc", lineHeight: "1.4" }}>{iss.message}</div>
              </div>
            );
          })
        )}
      </Section>

      <Section title={`Blind Spots (${blindSpots.length})`}>
        {blindSpots.length === 0 ? (
          <div style={{ fontSize: "10px", color: "#4ade80" }}>No blind spots detected</div>
        ) : (
          blindSpots.map((sp, i) => {
            const risk = RISK[sp.risk] || RISK.low;
            return (
              <div
                key={i}
                onClick={() => { if (sp.claim_id) onSelectNode(sp.claim_id); }}
                onMouseEnter={() => onHighlight(sp.claim_id ? [sp.claim_id] : [])}
                onMouseLeave={() => onHighlight([])}
                style={{
                  padding: "8px", background: "#141414", borderRadius: "4px",
                  borderLeft: `3px solid ${risk.color}`, marginBottom: "6px", cursor: "pointer",
                }}
              >
                <div style={{ fontSize: "9px", color: risk.color, textTransform: "uppercase", letterSpacing: "1px", marginBottom: "3px" }}>
                  {sp.risk} risk
                </div>
                <div style={{ fontSize: "10px", color: "#ccc", lineHeight: "1.4" }}>{sp.message}</div>
              </div>
            );
          })
        )}
      </Section>

      {selectedId && stressTest && (
        <Section title="Stress Test" defaultOpen={true}>
          {stressTest.attack_surfaces?.length > 0 && (
            <div style={{ marginBottom: "10px" }}>
              <div style={{ fontSize: "9px", color: "#f87171", marginBottom: "4px", textTransform: "uppercase", letterSpacing: "1px" }}>
                Attack Surfaces
              </div>
              {stressTest.attack_surfaces.map((a, i) => (
                <div key={i} style={{ fontSize: "10px", color: "#ccc", padding: "3px 0 3px 10px", borderLeft: "2px solid #333" }}>
                  {a}
                </div>
              ))}
            </div>
          )}
          {stressTest.crux_questions?.length > 0 && (
            <div style={{ marginBottom: "10px" }}>
              <div style={{ fontSize: "9px", color: "#fbbf24", marginBottom: "4px", textTransform: "uppercase", letterSpacing: "1px" }}>
                Crux Questions
              </div>
              {stressTest.crux_questions.map((q, i) => (
                <div key={i} style={{ fontSize: "10px", color: "#ccc", padding: "3px 0 3px 10px", borderLeft: "2px solid #333" }}>
                  {q}
                </div>
              ))}
            </div>
          )}
          {stressTest.steelman_prompts?.length > 0 && (
            <div>
              <div style={{ fontSize: "9px", color: "#60a5fa", marginBottom: "4px", textTransform: "uppercase", letterSpacing: "1px" }}>
                Steelman Opposition
              </div>
              {stressTest.steelman_prompts.map((p, i) => (
                <div key={i} style={{ fontSize: "10px", color: "#ccc", padding: "3px 0 3px 10px", borderLeft: "2px solid #333" }}>
                  {p}
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {selectedId && assumptions.length > 0 && (
        <Section title={`Assumptions (${assumptions.length})`} defaultOpen={true}>
          {assumptions.map((a, i) => (
            <div
              key={i}
              onClick={() => onSelectNode(a.id)}
              style={{
                padding: "6px 8px", background: "#141414", borderRadius: "3px",
                marginBottom: "4px", cursor: "pointer", marginLeft: `${a.depth * 12}px`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ fontSize: "10px" }}>{a.type === "explicit" ? "📌" : "👁"}</span>
                <span style={{ fontSize: "10px", color: "#ccc" }}>{a.label}</span>
              </div>
              <span style={{ fontSize: "9px", color: a.supported ? "#4ade80" : "#f87171", marginLeft: "22px" }}>
                {a.supported ? "supported" : "UNSUPPORTED"}
              </span>
            </div>
          ))}
        </Section>
      )}
    </div>
  );
}
