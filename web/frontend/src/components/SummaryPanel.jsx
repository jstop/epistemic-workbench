import { useState, useEffect } from "react";
import * as api from "../api.js";

export default function SummaryPanel() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const fetch = () => {
    setLoading(true);
    api.getSummary()
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  };

  useEffect(fetch, []);

  const handleCopy = async () => {
    if (!summary?.markdown) return;
    await navigator.clipboard.writeText(summary.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!summary?.markdown) return;
    const blob = new Blob([summary.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "epistemic-summary.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return <div style={{ color: "#444", fontSize: "11px", textAlign: "center", marginTop: "40px" }}>Loading…</div>;
  }

  if (!summary || !summary.thesis) {
    return <div style={{ color: "#444", fontSize: "11px", textAlign: "center", marginTop: "40px" }}>No claims to summarize yet.</div>;
  }

  const thesis = summary.thesis;
  const atmsColor = thesis.atms_status === "accepted" ? "#4ade80" : thesis.atms_status === "defeated" ? "#f87171" : "#fbbf24";
  const assessment = summary.confidence_assessment;
  const activeDefeaters = summary.objections.filter((d) => d.status === "active");
  const answeredDefeaters = summary.objections.filter((d) => d.status === "answered");
  const coherenceIssues = summary.unresolved_issues?.coherence || [];
  const blindSpots = summary.unresolved_issues?.blind_spots || [];
  const assumptions = summary.assumptions || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      {/* Actions */}
      <div style={{ display: "flex", gap: "6px" }}>
        <button onClick={handleCopy} style={{
          flex: 1, background: "#141414", border: "1px solid #222", borderRadius: "3px",
          color: copied ? "#4ade80" : "#888", padding: "6px", fontSize: "9px",
          cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
          letterSpacing: "1px", textTransform: "uppercase",
        }}>
          {copied ? "COPIED" : "COPY MD"}
        </button>
        <button onClick={handleDownload} style={{
          flex: 1, background: "#141414", border: "1px solid #222", borderRadius: "3px",
          color: "#888", padding: "6px", fontSize: "9px",
          cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
          letterSpacing: "1px", textTransform: "uppercase",
        }}>
          DOWNLOAD
        </button>
        <button onClick={fetch} style={{
          background: "#141414", border: "1px solid #222", borderRadius: "3px",
          color: "#666", padding: "6px 10px", fontSize: "9px",
          cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
        }}>
          ↻
        </button>
      </div>

      {/* Thesis */}
      <div style={{ background: "#141414", borderRadius: "4px", padding: "12px", borderLeft: "3px solid #FF6B35" }}>
        <div style={{ fontSize: "9px", color: "#FF6B35", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px" }}>
          Thesis
        </div>
        <div style={{ fontSize: "12px", color: "#e0e0e0", lineHeight: "1.5", marginBottom: "6px" }}>
          {thesis.notes || thesis.label}
        </div>
        <div style={{ display: "flex", gap: "12px", fontSize: "10px" }}>
          <span style={{ color: "#888" }}>Confidence: <span style={{ color: "#FF6B35" }}>{(thesis.confidence * 100).toFixed(0)}%</span></span>
          <span style={{ color: atmsColor }}>{thesis.atms_status}</span>
        </div>
      </div>

      {/* Supporting Arguments */}
      {summary.supporting_arguments.length > 0 && (
        <div>
          <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px" }}>
            Supporting Arguments
          </div>
          {summary.supporting_arguments.map((arg, i) => (
            <div key={i} style={{ background: "#141414", borderRadius: "4px", padding: "10px", marginBottom: "6px" }}>
              <div style={{ fontSize: "11px", color: "#e0e0e0", marginBottom: "4px" }}>{arg.label}</div>
              <div style={{ fontSize: "9px", color: "#555", marginBottom: "6px" }}>
                {arg.pattern} · {(arg.confidence * 100).toFixed(0)}%
              </div>
              {arg.premises.map((p, j) => (
                <div key={j} style={{ fontSize: "10px", color: "#888", paddingLeft: "8px", borderLeft: "2px solid #222", marginBottom: "3px" }}>
                  <span style={{ color: p.type === "evidence" ? "#4ade80" : "#60a5fa" }}>
                    {p.type === "evidence" ? "■" : "●"}
                  </span>{" "}
                  {p.label}
                  {p.confidence != null && <span style={{ color: "#555" }}> ({(p.confidence * 100).toFixed(0)}%)</span>}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Objections */}
      {(activeDefeaters.length > 0 || answeredDefeaters.length > 0) && (
        <div>
          <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px" }}>
            Known Objections
          </div>
          {activeDefeaters.map((d, i) => (
            <div key={`a-${i}`} style={{
              background: "#141414", borderRadius: "4px", padding: "8px",
              borderLeft: "3px solid #f87171", marginBottom: "4px",
            }}>
              <div style={{ fontSize: "9px", color: "#f87171", marginBottom: "3px" }}>UNRESOLVED · {d.type}</div>
              <div style={{ fontSize: "10px", color: "#ccc", lineHeight: "1.4" }}>{d.description}</div>
            </div>
          ))}
          {answeredDefeaters.map((d, i) => (
            <div key={`r-${i}`} style={{
              background: "#141414", borderRadius: "4px", padding: "8px",
              borderLeft: "3px solid #4ade80", marginBottom: "4px",
            }}>
              <div style={{ fontSize: "9px", color: "#4ade80", marginBottom: "3px" }}>ANSWERED · {d.type}</div>
              <div style={{ fontSize: "10px", color: "#666", lineHeight: "1.4", textDecoration: "line-through" }}>{d.description}</div>
              {d.response && (
                <div style={{ fontSize: "10px", color: "#888", marginTop: "3px", paddingLeft: "8px", borderLeft: "2px solid #333" }}>
                  {d.response}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Assumptions */}
      {assumptions.length > 0 && (
        <div>
          <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px" }}>
            Assumptions
          </div>
          {assumptions.map((a, i) => (
            <div key={i} style={{ display: "flex", gap: "6px", alignItems: "baseline", marginBottom: "3px" }}>
              <span style={{ fontSize: "10px" }}>{a.type === "explicit" ? "📌" : "👁"}</span>
              <span style={{ fontSize: "10px", color: "#888", flex: 1 }}>{a.label}</span>
              <span style={{ fontSize: "9px", color: a.supported ? "#4ade80" : "#f87171" }}>
                {a.supported ? "✓" : "!"}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Unresolved Issues */}
      {(coherenceIssues.length > 0 || blindSpots.length > 0) && (
        <div>
          <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px" }}>
            Unresolved Issues
          </div>
          {coherenceIssues.map((iss, i) => (
            <div key={`c-${i}`} style={{ fontSize: "10px", color: "#fbbf24", marginBottom: "3px" }}>
              {iss.message}
            </div>
          ))}
          {blindSpots.map((sp, i) => (
            <div key={`b-${i}`} style={{ fontSize: "10px", color: sp.risk === "high" ? "#f87171" : "#fbbf24", marginBottom: "3px" }}>
              {sp.message}
            </div>
          ))}
        </div>
      )}

      {/* What would change my mind */}
      {activeDefeaters.length > 0 && (
        <div>
          <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px" }}>
            What Would Change My Mind
          </div>
          {activeDefeaters.map((d, i) => (
            <div key={i} style={{ fontSize: "10px", color: "#888", marginBottom: "3px", paddingLeft: "8px", borderLeft: "2px solid #333" }}>
              If {d.description.charAt(0).toLowerCase() + d.description.slice(1)}
            </div>
          ))}
        </div>
      )}

      {/* Confidence Assessment */}
      <div style={{ background: "#141414", borderRadius: "4px", padding: "10px" }}>
        <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "8px" }}>
          Confidence Assessment
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "4px 12px", fontSize: "10px" }}>
          <span style={{ color: "#888" }}>Thesis confidence</span>
          <span style={{ color: "#FF6B35", textAlign: "right" }}>{(assessment.thesis_confidence * 100).toFixed(0)}%</span>
          <span style={{ color: "#888" }}>Avg argument strength</span>
          <span style={{ color: "#FF6B35", textAlign: "right" }}>{(assessment.average_argument_strength * 100).toFixed(0)}%</span>
          <span style={{ color: "#888" }}>Claims with support</span>
          <span style={{ color: "#888", textAlign: "right" }}>{assessment.claims_supported}</span>
          <span style={{ color: "#888" }}>Active defeaters</span>
          <span style={{ color: assessment.active_defeaters > 0 ? "#f87171" : "#4ade80", textAlign: "right" }}>{assessment.active_defeaters}</span>
          <span style={{ color: "#888" }}>Overall status</span>
          <span style={{ color: atmsColor, textAlign: "right", textTransform: "uppercase" }}>{assessment.atms_status}</span>
        </div>
      </div>
    </div>
  );
}
