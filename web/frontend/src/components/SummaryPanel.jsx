import { useState, useEffect } from "react";
import * as api from "../api.js";

export default function SummaryPanel({ workspace, onThesisChange, activeThesisId }) {
  const [summary, setSummary] = useState(null);
  const [theses, setTheses] = useState([]);
  const [selectedThesis, setSelectedThesis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [enhanced, setEnhanced] = useState(null);
  const [enhancing, setEnhancing] = useState(false);
  const [enhanceError, setEnhanceError] = useState(null);
  const [accepting, setAccepting] = useState(false);

  const fetchTheses = () => {
    if (!workspace) return;
    api.getTheses(workspace).then(setTheses).catch(() => setTheses([]));
  };

  const fetch = (thesisId) => {
    if (!workspace) return;
    setLoading(true);
    api.getSummary(workspace, thesisId || selectedThesis)
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (workspace) {
      fetchTheses();
      fetch();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace]);

  // Re-fetch when parent's activeThesisId changes (e.g. version navigation in header)
  useEffect(() => {
    if (activeThesisId && activeThesisId !== selectedThesis) {
      setSelectedThesis(activeThesisId);
      setEnhanced(null);
      setEnhanceError(null);
      fetch(activeThesisId);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeThesisId]);

  const handleSelectThesis = (id) => {
    setSelectedThesis(id);
    setEnhanced(null);
    setEnhanceError(null);
    fetch(id);
    if (onThesisChange) onThesisChange(id);
  };

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

  const handleEnhance = async () => {
    const thesisId = summary?.thesis?.id;
    if (!workspace || !thesisId || enhancing) return;
    setEnhancing(true);
    setEnhanceError(null);
    try {
      const result = await api.enhanceThesis(workspace, thesisId);
      setEnhanced(result);
    } catch (err) {
      console.error("Enhance error:", err);
      setEnhanceError(err.message || "Enhancement failed");
    } finally {
      setEnhancing(false);
    }
  };

  const handleAcceptEnhanced = async () => {
    const thesisId = summary?.thesis?.id;
    if (!workspace || !thesisId || !enhanced?.enhanced_thesis || accepting) return;
    setAccepting(true);
    try {
      const result = await api.acceptEnhancedThesis(workspace, {
        thesis_id: thesisId,
        enhanced_thesis: enhanced.enhanced_thesis,
        rationale: enhanced.rationale || "",
        changes: enhanced.changes || [],
      });
      setEnhanced(null);
      setSelectedThesis(result.new_thesis_id);
      fetchTheses();
      fetch(result.new_thesis_id);
      if (onThesisChange) onThesisChange(result.new_thesis_id);
    } catch (err) {
      console.error("Accept error:", err);
      setEnhanceError(err.message || "Failed to accept enhanced thesis");
    } finally {
      setAccepting(false);
    }
  };

  if (!workspace) {
    return <div style={{ color: "#555", fontSize: "10px" }}>Select a workspace first.</div>;
  }

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

  const changeTypeColors = {
    scope: "#60a5fa", precision: "#a78bfa", qualifier: "#fbbf24",
    strength: "#4ade80", acknowledgment: "#f97316",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
      {/* Thesis selector */}
      {theses.length > 1 && (
        <div>
          <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "4px" }}>
            Select Thesis
          </div>
          <select
            value={selectedThesis || ""}
            onChange={(e) => handleSelectThesis(e.target.value || null)}
            style={{
              width: "100%", background: "#141414", border: "1px solid #222",
              borderRadius: "3px", color: "#e0e0e0", padding: "8px",
              fontSize: "11px", fontFamily: "'JetBrains Mono', monospace",
              outline: "none", cursor: "pointer",
            }}
          >
            <option value="">Auto (most supported)</option>
            {theses.map((t) => (
              <option key={t.id} value={t.id}>
                {(t.notes || t.label).slice(0, 50)}{t.version_count > 1 ? ` (v${t.version_count})` : ""}
              </option>
            ))}
          </select>
        </div>
      )}

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
        <button onClick={handleEnhance} disabled={enhancing} style={{
          flex: 1, background: enhancing ? "#1a1a2e" : "#141414",
          border: "1px solid #a78bfa44", borderRadius: "3px",
          color: enhancing ? "#a78bfa88" : "#a78bfa", padding: "6px", fontSize: "9px",
          cursor: enhancing ? "default" : "pointer", fontFamily: "'JetBrains Mono', monospace",
          letterSpacing: "1px", textTransform: "uppercase",
        }}>
          {enhancing ? "..." : "ENHANCE"}
        </button>
        <button onClick={() => { fetchTheses(); fetch(); }} style={{
          background: "#141414", border: "1px solid #222", borderRadius: "3px",
          color: "#666", padding: "6px 10px", fontSize: "9px",
          cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
        }}>
          ↻
        </button>
      </div>

      {enhancing && (
        <div style={{ fontSize: "9px", color: "#a78bfa88", textAlign: "center" }}>
          Analyzing thesis for improvements...
        </div>
      )}
      {accepting && (
        <div style={{ fontSize: "9px", color: "#a78bfa", textAlign: "center", letterSpacing: "1px" }}>
          GENERATING NEW VERSION...
        </div>
      )}
      {enhanceError && (
        <div style={{ fontSize: "9px", color: "#f87171", textAlign: "center" }}>
          {enhanceError}
        </div>
      )}

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

      {/* Enhanced Thesis Suggestion */}
      {enhanced && (
        <div style={{ background: "#141418", borderRadius: "4px", padding: "12px", borderLeft: "3px solid #a78bfa" }}>
          <div style={{ fontSize: "9px", color: "#a78bfa", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px" }}>
            Enhanced Thesis Suggestion
          </div>
          <div style={{ fontSize: "12px", color: "#e0e0e0", lineHeight: "1.5", marginBottom: "10px" }}>
            {enhanced.enhanced_thesis}
          </div>
          {enhanced.rationale && (
            <div style={{ fontSize: "10px", color: "#888", lineHeight: "1.5", marginBottom: "10px", paddingLeft: "8px", borderLeft: "2px solid #333" }}>
              {enhanced.rationale}
            </div>
          )}
          {enhanced.changes && enhanced.changes.length > 0 && (
            <div style={{ marginBottom: "10px" }}>
              <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "4px" }}>
                Changes
              </div>
              {enhanced.changes.map((c, i) => (
                <div key={i} style={{ fontSize: "10px", color: "#888", marginBottom: "3px", display: "flex", gap: "6px" }}>
                  <span style={{ color: changeTypeColors[c.type] || "#888", fontSize: "9px", textTransform: "uppercase", flexShrink: 0 }}>
                    {c.type}
                  </span>
                  <span>{c.description}</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: "6px" }}>
            <button onClick={handleAcceptEnhanced} disabled={accepting} style={{
              flex: 1, background: accepting ? "#a78bfa88" : "#a78bfa", border: "none", borderRadius: "3px",
              color: "#0A0A0A", padding: "8px", fontSize: "10px",
              cursor: accepting ? "default" : "pointer", fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600, letterSpacing: "1px",
            }}>
              {accepting ? "GENERATING..." : "ACCEPT & GENERATE NEW GRAPH"}
            </button>
            <button onClick={() => setEnhanced(null)} style={{
              background: "transparent", border: "1px solid #333", borderRadius: "3px",
              color: "#555", padding: "8px 16px", fontSize: "10px",
              cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
            }}>
              DISMISS
            </button>
          </div>
        </div>
      )}

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
