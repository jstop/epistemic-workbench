import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import * as api from "../api.js";

const markdownStyles = {
  fontSize: "11px",
  lineHeight: "1.6",
  color: "#ccc",
  fontFamily: "'JetBrains Mono', monospace",
};

const markdownComponents = {
  h1: ({ node, ...props }) => (
    <h1 style={{ fontSize: "13px", color: "#FF6B35", marginTop: "16px", marginBottom: "8px",
      letterSpacing: "1px", textTransform: "uppercase", borderBottom: "1px solid #333",
      paddingBottom: "4px" }} {...props} />
  ),
  h2: ({ node, ...props }) => (
    <h2 style={{ fontSize: "12px", color: "#a78bfa", marginTop: "14px", marginBottom: "6px",
      letterSpacing: "1px", textTransform: "uppercase" }} {...props} />
  ),
  h3: ({ node, ...props }) => (
    <h3 style={{ fontSize: "11px", color: "#888", marginTop: "10px", marginBottom: "4px" }} {...props} />
  ),
  p: ({ node, ...props }) => (
    <p style={{ margin: "6px 0", color: "#ccc" }} {...props} />
  ),
  ul: ({ node, ...props }) => (
    <ul style={{ paddingLeft: "18px", margin: "4px 0" }} {...props} />
  ),
  li: ({ node, ...props }) => (
    <li style={{ margin: "2px 0", fontSize: "11px", color: "#aaa" }} {...props} />
  ),
  strong: ({ node, ...props }) => (
    <strong style={{ color: "#e0e0e0", fontWeight: 600 }} {...props} />
  ),
  em: ({ node, ...props }) => (
    <em style={{ color: "#888", fontStyle: "italic" }} {...props} />
  ),
  blockquote: ({ node, ...props }) => (
    <blockquote style={{
      borderLeft: "3px solid #FF6B35", paddingLeft: "10px", margin: "8px 0",
      color: "#ccc", fontStyle: "italic",
    }} {...props} />
  ),
  table: ({ node, ...props }) => (
    <table style={{
      borderCollapse: "collapse", margin: "8px 0", fontSize: "10px",
      width: "100%",
    }} {...props} />
  ),
  th: ({ node, ...props }) => (
    <th style={{
      border: "1px solid #333", padding: "4px 8px",
      textAlign: "left", color: "#FF6B35", background: "#141414",
      fontWeight: 600,
    }} {...props} />
  ),
  td: ({ node, ...props }) => (
    <td style={{
      border: "1px solid #333", padding: "4px 8px",
      color: "#ccc",
    }} {...props} />
  ),
  code: ({ node, inline, ...props }) =>
    inline ? (
      <code style={{
        background: "#141414", padding: "1px 4px", borderRadius: "2px",
        color: "#a78bfa", fontSize: "10px",
      }} {...props} />
    ) : (
      <code {...props} />
    ),
  del: ({ node, ...props }) => (
    <del style={{ color: "#666", textDecoration: "line-through" }} {...props} />
  ),
};

export default function CompareModal({ workspace, other, mode, onClose, onMerged, setBusy }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mergeMode, setMergeMode] = useState("synthesize");
  const [merging, setMerging] = useState(false);
  const [mergeResult, setMergeResult] = useState(null);

  useEffect(() => {
    if (mode === "compare") {
      setLoading(true);
      api.compareBranches(workspace, other)
        .then(setData)
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace, other, mode]);

  const runMerge = async () => {
    setMerging(true);
    setError(null);
    if (mergeMode === "synthesize") {
      setBusy && setBusy("Synthesizing forks (this may take 30-60s)…");
    }
    try {
      const result = await api.mergeBranches(workspace, other, mergeMode);
      setMergeResult(result);
      setBusy && setBusy(null);
      if (mergeMode === "pick") {
        if (onMerged) onMerged();
      }
    } catch (err) {
      setBusy && setBusy(null);
      setError(err.message);
    } finally {
      setMerging(false);
    }
  };

  const title = mode === "compare"
    ? `Compare with ${other}`
    : `Merge ${other} into current`;

  const markdown = mergeResult?.markdown || data?.markdown;

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 1000,
    }} onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0d0d0d", border: "1px solid #333", borderRadius: "4px",
          width: "780px", maxWidth: "92vw", maxHeight: "85vh",
          display: "flex", flexDirection: "column",
          fontFamily: "'JetBrains Mono', monospace", color: "#e0e0e0",
        }}
      >
        {/* Header */}
        <div style={{
          padding: "14px 20px",
          borderBottom: "1px solid #333",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexShrink: 0,
        }}>
          <div style={{
            fontSize: "10px", letterSpacing: "3px",
            color: mode === "merge" ? "#a78bfa" : "#FF6B35",
            textTransform: "uppercase",
          }}>
            {title}
          </div>
          <button
            onClick={onClose}
            style={{
              background: "transparent", border: "1px solid #333",
              color: "#888", borderRadius: "3px", padding: "4px 10px",
              fontSize: "10px", cursor: "pointer",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            ✕ Close
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
          {loading && (
            <div style={{ color: "#666", fontSize: "11px", textAlign: "center", padding: "30px" }}>
              Loading…
            </div>
          )}
          {error && (
            <div style={{ color: "#f87171", fontSize: "11px", padding: "12px" }}>
              {error}
            </div>
          )}

          {mode === "merge" && !mergeResult && !merging && (
            <div style={{ marginBottom: "20px" }}>
              <div style={{ fontSize: "10px", color: "#888", marginBottom: "10px" }}>
                Choose merge mode:
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <label style={{
                  display: "flex", alignItems: "flex-start", gap: "8px",
                  padding: "10px", background: "#141414", borderRadius: "3px",
                  border: `1px solid ${mergeMode === "synthesize" ? "#a78bfa" : "#222"}`,
                  cursor: "pointer",
                }}>
                  <input
                    type="radio"
                    checked={mergeMode === "synthesize"}
                    onChange={() => setMergeMode("synthesize")}
                    style={{ marginTop: "2px" }}
                  />
                  <div>
                    <div style={{ fontSize: "11px", color: "#a78bfa", fontWeight: 600 }}>
                      Synthesize
                    </div>
                    <div style={{ fontSize: "10px", color: "#888", marginTop: "2px" }}>
                      Use the LLM to synthesize a new thesis incorporating the strongest insights
                      from both forks. Creates a new <code>merge/...</code> branch with a regenerated
                      argument graph. ~30-60s.
                    </div>
                  </div>
                </label>
                <label style={{
                  display: "flex", alignItems: "flex-start", gap: "8px",
                  padding: "10px", background: "#141414", borderRadius: "3px",
                  border: `1px solid ${mergeMode === "pick" ? "#a78bfa" : "#222"}`,
                  cursor: "pointer",
                }}>
                  <input
                    type="radio"
                    checked={mergeMode === "pick"}
                    onChange={() => setMergeMode("pick")}
                    style={{ marginTop: "2px" }}
                  />
                  <div>
                    <div style={{ fontSize: "11px", color: "#a78bfa", fontWeight: 600 }}>
                      Pick wholesale
                    </div>
                    <div style={{ fontSize: "10px", color: "#888", marginTop: "2px" }}>
                      Adopt the source fork wholesale. The current branch is left as-is in git
                      history; you switch to the source branch.
                    </div>
                  </div>
                </label>
              </div>
              <button
                onClick={runMerge}
                style={{
                  marginTop: "12px",
                  background: "#a78bfa22",
                  border: "1px solid #a78bfa",
                  color: "#a78bfa",
                  borderRadius: "3px", padding: "10px 16px",
                  fontSize: "11px", cursor: "pointer",
                  fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: "1px", textTransform: "uppercase",
                  width: "100%",
                }}
              >
                Run Merge
              </button>
            </div>
          )}

          {merging && (
            <div style={{ color: "#a78bfa", fontSize: "11px", textAlign: "center", padding: "30px" }}>
              ⟳ Synthesizing…
            </div>
          )}

          {markdown && (
            <div style={markdownStyles}>
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {markdown}
              </ReactMarkdown>
            </div>
          )}

          {mode === "merge" && mergeResult && (
            <button
              onClick={() => { onMerged && onMerged(); }}
              style={{
                marginTop: "16px",
                background: "#a78bfa22",
                border: "1px solid #a78bfa",
                color: "#a78bfa",
                borderRadius: "3px", padding: "10px 16px",
                fontSize: "11px", cursor: "pointer",
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: "1px", textTransform: "uppercase",
                width: "100%",
              }}
            >
              ✓ Done — refresh workspace
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
