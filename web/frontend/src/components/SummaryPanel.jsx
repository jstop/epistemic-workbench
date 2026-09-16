import { useState, useEffect } from "react";
import * as api from "../api.js";

const linkBtnStyle = (color) => ({
  background: `${color}18`,
  border: `1px solid ${color}66`,
  color,
  borderRadius: "3px",
  padding: "3px 8px",
  fontSize: "9px",
  cursor: "pointer",
  fontFamily: "'JetBrains Mono', monospace",
  letterSpacing: "1px",
  textTransform: "uppercase",
});

export default function SummaryPanel({ workspace, onThesisChange, activeThesisId, onSelectNode, onUpdated }) {
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

  const refreshAfterAction = () => {
    if (onUpdated) onUpdated();
    fetch();
  };

  const handleRespond = async (d) => {
    const response = prompt("Response (rebuts the defeater):");
    if (response === null) return;
    try {
      await api.respondToDefeater(workspace, {
        argument_id: d.argument_id,
        response,
        defeater_index: d.index,
      });
      refreshAfterAction();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleConcede = async (d) => {
    const note = prompt("Concede this defeater (accept it as valid). What part of your thesis are you conceding?");
    if (note === null) return;
    try {
      await api.concedeDefeater(workspace, {
        argument_id: d.argument_id,
        note,
        defeater_index: d.index,
      });
      refreshAfterAction();
    } catch (err) {
      alert(err.message);
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
  const concededDefeaters = summary.objections.filter((d) => d.status === "conceded");
  const answeredDefeaters = summary.objections.filter((d) => d.status === "answered");
  const coherenceIssues = summary.unresolved_issues?.coherence || [];
  const blindSpots = summary.unresolved_issues?.blind_spots || [];
  const assumptions = summary.assumptions || [];

  const changeTypeColors = {
    scope: "#60a5fa", precision: "#a78bfa", qualifier: "#fbbf24",
    strength: "#4ade80", acknowledgment: "#f97316",
  };

  const linkBtnStyle = (color) => ({
    background: `${color}18`,
    border: `1px solid ${color}66`,
    color,
    borderRadius: "3px",
    padding: "3px 8px",
    fontSize: "9px",
    cursor: "pointer",
    fontFamily: "'JetBrains Mono', monospace",
    letterSpacing: "1px",
    textTransform: "uppercase",
  });

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
      <div style={{ background: "#141414", borderRadius: "4px", padding: "14px", borderLeft: "3px solid #FF6B35" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
          <div style={{ fontSize: "9px", color: "#FF6B35", letterSpacing: "1px", textTransform: "uppercase" }}>
            Thesis
          </div>
          {onSelectNode && thesis.id && (
            <button
              onClick={() => onSelectNode(thesis.id)}
              style={linkBtnStyle("#888")}
            >
              Inspect
            </button>
          )}
        </div>
        <div
          onClick={() => onSelectNode && thesis.id && onSelectNode(thesis.id)}
          style={{
            fontSize: "13px", color: "#e0e0e0", lineHeight: "1.6", marginBottom: "8px",
            cursor: onSelectNode ? "pointer" : "default",
          }}
        >
          {thesis.notes || thesis.label}
        </div>
        <div style={{ display: "flex", gap: "12px", fontSize: "10px" }}>
          <span style={{ color: "#888" }}>Confidence: <span style={{ color: "#FF6B35" }}>{(thesis.confidence * 100).toFixed(0)}%</span></span>
          <span style={{ color: atmsColor, textTransform: "uppercase" }}>{thesis.atms_status}</span>
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
            <div key={i} style={{ background: "#141414", borderRadius: "4px", padding: "12px", marginBottom: "8px" }}>
              <div style={{ fontSize: "12px", color: "#e0e0e0", marginBottom: "4px", lineHeight: "1.4" }}>
                {arg.label}
              </div>
              <div style={{ fontSize: "9px", color: "#555", marginBottom: "8px", letterSpacing: "1px", textTransform: "uppercase" }}>
                {arg.pattern} · {(arg.confidence * 100).toFixed(0)}%
              </div>
              {arg.premises.map((p, j) => (
                <div
                  key={j}
                  onClick={() => p.id && onSelectNode && onSelectNode(p.id)}
                  style={{
                    fontSize: "11px", color: "#aaa",
                    paddingLeft: "10px", borderLeft: "2px solid #222",
                    marginBottom: "4px", lineHeight: "1.5",
                    cursor: p.id && onSelectNode ? "pointer" : "default",
                  }}
                >
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
      {(activeDefeaters.length > 0 || concededDefeaters.length > 0 || answeredDefeaters.length > 0) && (
        <div>
          <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "6px" }}>
            Known Objections ({activeDefeaters.length + concededDefeaters.length + answeredDefeaters.length})
          </div>
          {activeDefeaters.map((d, i) => (
            <div key={`a-${i}`} style={{
              background: "#141414", borderRadius: "4px", padding: "10px",
              borderLeft: "3px solid #f87171", marginBottom: "6px",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                <span style={{ fontSize: "9px", color: "#f87171", letterSpacing: "1px", textTransform: "uppercase" }}>
                  Unresolved · {d.type}
                </span>
                <div style={{ display: "flex", gap: "4px" }}>
                  <button onClick={() => handleRespond(d)} style={linkBtnStyle("#4ade80")}>
                    Rebut
                  </button>
                  <button onClick={() => handleConcede(d)} style={linkBtnStyle("#fb923c")}>
                    Concede
                  </button>
                </div>
              </div>
              <div style={{ fontSize: "11px", color: "#ccc", lineHeight: "1.5", marginBottom: "4px" }}>
                {d.description}
              </div>
              <div style={{ fontSize: "9px", color: "#555" }}>
                on: {d.argument_label}
              </div>
            </div>
          ))}
          {concededDefeaters.map((d, i) => (
            <div key={`c-${i}`} style={{
              background: "#141414", borderRadius: "4px", padding: "10px",
              borderLeft: "3px solid #fb923c", marginBottom: "6px",
            }}>
              <div style={{ fontSize: "9px", color: "#fb923c", marginBottom: "4px", letterSpacing: "1px", textTransform: "uppercase" }}>
                Conceded · {d.type}
              </div>
              <div style={{ fontSize: "11px", color: "#ccc", lineHeight: "1.5" }}>
                {d.description}
              </div>
              {d.response && (
                <div style={{ fontSize: "10px", color: "#fb923c", marginTop: "4px", paddingLeft: "8px", borderLeft: "2px solid #333", lineHeight: "1.5" }}>
                  Conceded: {d.response}
                </div>
              )}
              <div style={{ fontSize: "9px", color: "#555", marginTop: "4px" }}>
                on: {d.argument_label}
              </div>
            </div>
          ))}
          {answeredDefeaters.map((d, i) => (
            <div key={`r-${i}`} style={{
              background: "#141414", borderRadius: "4px", padding: "10px",
              borderLeft: "3px solid #4ade80", marginBottom: "6px",
            }}>
              <div style={{ fontSize: "9px", color: "#4ade80", marginBottom: "4px", letterSpacing: "1px", textTransform: "uppercase" }}>
                Answered · {d.type}
              </div>
              <div style={{ fontSize: "11px", color: "#666", lineHeight: "1.5", textDecoration: "line-through" }}>
                {d.description}
              </div>
              {d.response && (
                <div style={{ fontSize: "10px", color: "#4ade80", marginTop: "4px", paddingLeft: "8px", borderLeft: "2px solid #333", lineHeight: "1.5" }}>
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
            Assumptions ({assumptions.length})
          </div>
          {assumptions.map((a, i) => (
            <div
              key={i}
              onClick={() => a.id && onSelectNode && onSelectNode(a.id)}
              style={{
                display: "flex", gap: "8px", alignItems: "baseline",
                padding: "6px 8px", marginBottom: "3px",
                background: "#141414", borderRadius: "3px",
                cursor: a.id && onSelectNode ? "pointer" : "default",
              }}
            >
              <span style={{ fontSize: "10px" }}>{a.type === "explicit" ? "📌" : "👁"}</span>
              <span style={{ fontSize: "11px", color: "#aaa", flex: 1, lineHeight: "1.4" }}>{a.label}</span>
              <span style={{ fontSize: "9px", color: a.supported ? "#4ade80" : "#f87171", flexShrink: 0 }}>
                {a.supported ? "supported" : "UNSUPPORTED"}
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
          {assessment.derived_confidence != null && (
            <>
              <span style={{ color: "#888" }}>Derived confidence (propagated)</span>
              <span style={{ color: Math.abs(assessment.derived_confidence - assessment.thesis_confidence) >= 0.05 ? "#fbbf24" : "#FF6B35", textAlign: "right" }}>
                {(assessment.derived_confidence * 100).toFixed(0)}%
              </span>
            </>
          )}
          {assessment.evidence_recorded != null && (
            <>
              <span style={{ color: "#888" }}>Evidence recorded / asserted</span>
              <span style={{ textAlign: "right" }}>
                <span style={{ color: "#4ade80" }}>{assessment.evidence_recorded}</span>
                <span style={{ color: "#555" }}> / </span>
                <span style={{ color: assessment.evidence_asserted > 0 ? "#fbbf24" : "#888" }}>{assessment.evidence_asserted}</span>
              </span>
            </>
          )}
        </div>

        {assessment.confidence_gap && (
          <div style={{ marginTop: "10px", padding: "8px", background: "#0A0A0A", borderRadius: "3px", borderLeft: "3px solid #fbbf24", fontSize: "10px" }}>
            <div style={{ color: "#fbbf24", fontSize: "9px", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "4px" }}>Confidence gap</div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "#999", lineHeight: 1.5 }}>
              <span>
                Stored {(assessment.confidence_gap.stored * 100).toFixed(0)}% vs derived {(assessment.confidence_gap.derived * 100).toFixed(0)}%.
                {assessment.confidence_gap.binding_objections?.length > 0 && " Binding objections:"}
              </span>
              <button
                onClick={async () => {
                  await api.setConfidence(workspace, {
                    claim_id: assessment.confidence_gap.claim_id,
                    confidence: Math.round(assessment.confidence_gap.derived * 100) / 100,
                    note: `adopted derived confidence (was ${(assessment.confidence_gap.stored * 100).toFixed(0)}%)`,
                  });
                  fetch(selectedThesis);
                  if (onUpdated) onUpdated();
                }}
                style={{ ...linkBtnStyle("#fbbf24"), marginLeft: "auto", flexShrink: 0 }}
              >
                Adopt derived
              </button>
            </div>
            {(assessment.confidence_gap.binding_objections || []).map((o) => (
              <div key={o.id} onClick={() => onSelectNode && onSelectNode(o.id)} style={{ color: "#f87171", cursor: "pointer", marginTop: "3px" }}>
                ◆ {o.label} <span style={{ color: "#555" }}>({o.rel}, {(o.strength * 100).toFixed(0)}%)</span>
              </div>
            ))}
          </div>
        )}

        {assessment.conjunction && (
          <div style={{ marginTop: "10px", padding: "8px", background: "#0A0A0A", borderRadius: "3px", borderLeft: "3px solid #a78bfa", fontSize: "10px" }}>
            <div style={{ color: "#a78bfa", fontSize: "9px", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "4px" }}>
              Conjunction · {assessment.conjunction.n_premises} premises ({assessment.conjunction.support_mode})
            </div>
            <div style={{ color: "#999", lineHeight: 1.5 }}>
              Average {(assessment.conjunction.average * 100).toFixed(0)}% · product {(assessment.conjunction.product * 100).toFixed(0)}% · derived {(assessment.conjunction.derived * 100).toFixed(0)}%.
              {(assessment.conjunction.weakest_links || []).length > 0 && " Weakest links:"}
            </div>
            {(assessment.conjunction.weakest_links || []).map((w) => (
              <div key={w.id} onClick={() => onSelectNode && onSelectNode(w.id)} style={{ color: "#ccc", cursor: "pointer", marginTop: "3px" }}>
                ● {w.label} <span style={{ color: "#555" }}>({(w.confidence * 100).toFixed(0)}%)</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <LibrarySection workspace={workspace} thesis={thesis} onUpdated={onUpdated} />
      <HistorySection workspace={workspace} refreshKey={summary} />
    </div>
  );
}

// ── Living-library bridge ───────────────────────────────────────────

const STANCE_COLORS = { RELY: "#4ade80", NOTE: "#fbbf24", SUSPECT: "#fb923c", CONTESTED: "#f87171", HYPOTHESIS: "#60a5fa" };

function LibrarySection({ workspace, thesis, onUpdated }) {
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [mode, setMode] = useState(null); // null | "ground" | "capture"
  const [capId, setCapId] = useState("");
  const [capCluster, setCapCluster] = useState("Positions & writing");
  const [capNote, setCapNote] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    if (!workspace) return;
    api.getWorkspaceBeliefs(workspace).then(setData).catch(() => setData(null));
  };
  useEffect(load, [workspace]);

  useEffect(() => {
    if (mode !== "ground" || q.trim().length < 2) { setResults([]); return; }
    const t = setTimeout(() => api.searchBeliefs(q.trim()).then(setResults).catch(() => setResults([])), 250);
    return () => clearTimeout(t);
  }, [q, mode]);

  if (!data) return null;
  const slug = (t) => (t || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48);
  const grounded = data.beliefs || [];

  const ground = async (id) => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.groundBelief(workspace, { belief_id: id, note: "" });
      setMsg(`Grounded ${r.belief.id} in this workspace at ${r.commit || "(uncommitted)"}. Its anchor now re-runs this argument.`);
      setMode(null); setQ(""); load();
    } catch (err) { setMsg(err.message); }
    finally { setBusy(false); }
  };
  const capture = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.captureBelief(workspace, { belief_id: capId || `wb-${slug(workspace)}`, cluster: capCluster, note: capNote });
      setMsg(r.warning ? `Captured with warning: ${r.warning}` : `Captured ${r.belief.id} (${r.belief.stance}) grounded in this workspace at ${r.commit || "(uncommitted)"}. Recorded under the web channel's agent identity; stand behind it from your own terminal to make it your word.`);
      setMode(null); load();
      if (onUpdated) onUpdated();
    } catch (err) { setMsg(err.message); }
    finally { setBusy(false); }
  };

  const inputStyle = { width: "100%", background: "#0A0A0A", border: "1px solid #222", borderRadius: "3px", color: "#e0e0e0", padding: "7px 9px", fontSize: "11px", fontFamily: "'JetBrains Mono', monospace", outline: "none", boxSizing: "border-box" };

  return (
    <div style={{ background: "#141414", borderRadius: "4px", padding: "10px" }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: "8px", gap: "6px" }}>
        <span style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>
          Living library · beliefs grounded in this workspace ({grounded.length})
        </span>
        {!data.available && <span style={{ fontSize: "9px", color: "#f87171" }} title={data.reason || ""}>library unavailable</span>}
        {data.available && (
          <div style={{ marginLeft: "auto", display: "flex", gap: "4px" }}>
            <button onClick={() => setMode(mode === "ground" ? null : "ground")} style={linkBtnStyle("#60a5fa")}>Ground a belief here</button>
            {thesis && <button onClick={() => { setMode(mode === "capture" ? null : "capture"); setCapId(`wb-${slug(workspace)}`); }} style={linkBtnStyle("#FF6B35")}>Capture thesis as belief</button>}
          </div>
        )}
      </div>
      <div style={{ fontSize: "9px", color: "#555", lineHeight: 1.5, marginBottom: "8px" }}>
        The library is the substrate. A belief grounds in this workspace: a snapshot at the current commit becomes evidence under it, and its anchor re-runs the argument (<span style={{ fontFamily: "'JetBrains Mono', monospace" }}>verify-thesis</span>). The workspace keeps no list of beliefs; this is a query.
      </div>
      {grounded.length === 0 && mode === null && (
        <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic" }}>No library belief cites this workspace yet.</div>
      )}
      {grounded.map((b) => (
        <div key={b.id} style={{ padding: "6px 8px", background: "#0A0A0A", borderRadius: "3px", marginBottom: "4px", fontSize: "10px", borderLeft: `3px solid ${STANCE_COLORS[b.stance] || "#555"}` }}>
          <div style={{ display: "flex", gap: "6px", alignItems: "baseline" }}>
            <span style={{ color: STANCE_COLORS[b.stance] || "#888", fontSize: "9px", letterSpacing: "1px", flexShrink: 0 }}>{b.stance}</span>
            <span style={{ color: "#ccc", lineHeight: 1.4 }}>{b.claim}</span>
          </div>
          <div style={{ color: "#555", fontSize: "9px", marginTop: "2px" }}>
            {b.id} · {b.method} · {b.freshness}{b.stood_behind_by ? ` · stood behind by ${b.stood_behind_by}` : " · not yet stood behind by the owner"}
            {b.snapshots?.length ? ` · ${b.snapshots.length} snapshot${b.snapshots.length === 1 ? "" : "s"}, latest ${b.snapshots[b.snapshots.length - 1].uri.split("@")[1] || ""}` : ""}
          </div>
          {b.anchor && <div style={{ color: "#444", fontSize: "9px", marginTop: "2px", fontFamily: "'JetBrains Mono', monospace", wordBreak: "break-all" }}>anchor: {b.anchor}</div>}
        </div>
      ))}
      {mode === "ground" && (
        <div style={{ marginTop: "8px" }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search beliefs by claim or id, then pick one to ground here…" autoFocus style={inputStyle} />
          <div style={{ maxHeight: "220px", overflow: "auto", marginTop: "4px" }}>
            {results.map((b) => (
              <div key={b.id} onClick={() => !busy && ground(b.id)} style={{ padding: "5px 8px", cursor: busy ? "wait" : "pointer", fontSize: "10px", borderLeft: `3px solid ${STANCE_COLORS[b.stance] || "#555"}`, borderBottom: "1px solid #1a1a1a" }}>
                <span style={{ color: STANCE_COLORS[b.stance] || "#888", fontSize: "9px", marginRight: "6px" }}>{b.stance}</span>
                <span style={{ color: "#bbb" }}>{b.claim}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {mode === "capture" && (
        <div style={{ marginTop: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
          <div style={{ fontSize: "9px", color: "#777", lineHeight: 1.5 }}>
            Captures the thesis as a <b>derived</b> belief whose evidence is this workspace at its current commit, anchored to the argument. Written under the web channel's agent identity; it becomes your word only when you stand behind it from your own terminal.
          </div>
          <input value={capId} onChange={(e) => setCapId(e.target.value)} placeholder="belief id (kebab-case)" style={inputStyle} />
          <input value={capCluster} onChange={(e) => setCapCluster(e.target.value)} placeholder="cluster" style={inputStyle} />
          <input value={capNote} onChange={(e) => setCapNote(e.target.value)} placeholder="note (optional)" style={inputStyle} />
          <div style={{ display: "flex", gap: "4px" }}>
            <button onClick={capture} disabled={!capId || busy} style={linkBtnStyle("#FF6B35")}>{busy ? "Capturing…" : "Capture"}</button>
            <button onClick={() => setMode(null)} style={linkBtnStyle("#555")}>Cancel</button>
          </div>
        </div>
      )}
      {msg && <div style={{ fontSize: "10px", color: msg.startsWith("Grounded") || msg.startsWith("Captured ") ? "#4ade80" : "#fbbf24", marginTop: "6px", lineHeight: 1.5 }}>{msg}</div>}
    </div>
  );
}

// ── Recent history with actor attribution ───────────────────────────

const ACTOR_COLORS = (a) => a === "owner" ? "#4ade80" : a?.startsWith("owner:") ? "#86efac" : a?.startsWith("agent:") ? "#a78bfa" : "#555";

function HistorySection({ workspace, refreshKey }) {
  const [log, setLog] = useState([]);
  useEffect(() => {
    if (!workspace) return;
    api.getGitLog(workspace).then((l) => setLog(l.slice(0, 10))).catch(() => setLog([]));
  }, [workspace, refreshKey]);
  if (log.length === 0) return null;
  return (
    <div style={{ background: "#141414", borderRadius: "4px", padding: "10px" }}>
      <div style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase", marginBottom: "8px" }}>Recent history · who wrote what</div>
      {log.map((c) => (
        <div key={c.hash} style={{ display: "flex", gap: "8px", fontSize: "10px", padding: "3px 0", borderBottom: "1px solid #1a1a1a", alignItems: "baseline" }}>
          <span style={{ color: "#444", flexShrink: 0 }}>{c.date.slice(0, 10)}</span>
          <span style={{ color: ACTOR_COLORS(c.actor), flexShrink: 0, fontSize: "9px", letterSpacing: "1px" }}>{c.actor}</span>
          <span style={{ color: "#999", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.subject}</span>
        </div>
      ))}
    </div>
  );
}
