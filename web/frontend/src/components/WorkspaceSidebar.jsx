import { useState } from "react";

const COLOR_BG = "#0d0d0d";
const COLOR_BORDER = "#1a1a1a";
const COLOR_TEXT = "#888";
const COLOR_TEXT_DIM = "#555";
const COLOR_TEXT_BRIGHT = "#e0e0e0";
const COLOR_ACCENT = "#FF6B35";
const COLOR_BRANCH = "#a78bfa";

function btn(extra = {}) {
  return {
    background: "transparent",
    border: "1px solid #333",
    borderRadius: "3px",
    color: COLOR_TEXT,
    padding: "3px 6px",
    fontSize: "8px",
    cursor: "pointer",
    fontFamily: "'JetBrains Mono', monospace",
    letterSpacing: "1px",
    textTransform: "uppercase",
    ...extra,
  };
}

export default function WorkspaceSidebar({
  workspaces,
  currentWorkspace,
  branches,
  currentBranch,
  onSelectWorkspace,
  onSwitchBranch,
  onFork,
  onCompare,
  onMerge,
  onNew,
  onRefresh,
}) {
  const [forkInput, setForkInput] = useState("");
  const [showFork, setShowFork] = useState(false);

  const handleFork = (e) => {
    e.preventDefault();
    if (!forkInput.trim()) return;
    onFork(forkInput.trim());
    setForkInput("");
    setShowFork(false);
  };

  return (
    <div style={{
      width: "280px",
      borderRight: `1px solid ${COLOR_BORDER}`,
      background: COLOR_BG,
      display: "flex",
      flexDirection: "column",
      flexShrink: 0,
      overflow: "hidden",
    }}>
      {/* Workspaces section */}
      <div style={{
        padding: "10px 12px",
        borderBottom: `1px solid ${COLOR_BORDER}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexShrink: 0,
      }}>
        <span style={{
          fontSize: "9px",
          letterSpacing: "2px",
          color: COLOR_TEXT_DIM,
          textTransform: "uppercase",
        }}>
          Workspaces ({workspaces.length})
        </span>
        <div style={{ display: "flex", gap: "4px" }}>
          <button onClick={onRefresh} style={btn()}>↻</button>
          <button
            onClick={onNew}
            style={btn({
              background: `${COLOR_ACCENT}22`,
              border: `1px solid ${COLOR_ACCENT}`,
              color: COLOR_ACCENT,
            })}
          >
            + New
          </button>
        </div>
      </div>

      {/* Workspace list */}
      <div style={{ flex: 1, overflow: "auto" }}>
        {workspaces.length === 0 && (
          <div style={{
            padding: "20px 12px",
            color: COLOR_TEXT_DIM,
            fontSize: "10px",
            textAlign: "center",
          }}>
            No workspaces yet. Click + New.
          </div>
        )}
        {workspaces.map((w) => {
          const isCurrent = w.name === currentWorkspace;
          return (
            <div
              key={w.name}
              onClick={() => onSelectWorkspace(w.name)}
              style={{
                padding: "8px 12px",
                borderBottom: "1px solid #141414",
                cursor: "pointer",
                background: isCurrent ? "#141414" : "transparent",
                borderLeft: isCurrent ? `2px solid ${COLOR_ACCENT}` : "2px solid transparent",
              }}
            >
              <div style={{
                fontSize: "10px",
                color: isCurrent ? COLOR_ACCENT : COLOR_TEXT_BRIGHT,
                fontWeight: isCurrent ? 600 : 400,
                marginBottom: "2px",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}>
                {w.name}
              </div>
              {w.thesis_text && (
                <div style={{
                  fontSize: "9px",
                  color: COLOR_TEXT_DIM,
                  lineHeight: "1.3",
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}>
                  {w.thesis_text.slice(0, 100)}
                </div>
              )}
              <div style={{
                fontSize: "8px",
                color: "#444",
                marginTop: "3px",
                display: "flex",
                gap: "8px",
              }}>
                <span>{w.claims}c · {w.evidence}e · {w.arguments}a</span>
                {w.is_git && w.branch && w.branch !== "master" && w.branch !== "main" && (
                  <span style={{ color: COLOR_BRANCH }}>⎇ {w.branch}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Branches section (only shown when a workspace is selected) */}
      {currentWorkspace && branches.length > 0 && (
        <div style={{
          borderTop: `1px solid ${COLOR_BORDER}`,
          flexShrink: 0,
          maxHeight: "40%",
          display: "flex",
          flexDirection: "column",
        }}>
          <div style={{
            padding: "10px 12px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}>
            <span style={{
              fontSize: "9px",
              letterSpacing: "2px",
              color: COLOR_TEXT_DIM,
              textTransform: "uppercase",
            }}>
              Branches ({branches.length})
            </span>
            <button
              onClick={() => setShowFork(!showFork)}
              style={btn({ color: COLOR_BRANCH, borderColor: `${COLOR_BRANCH}66` })}
            >
              + Fork
            </button>
          </div>

          {showFork && (
            <form onSubmit={handleFork} style={{ padding: "0 12px 8px" }}>
              <input
                type="text"
                value={forkInput}
                onChange={(e) => setForkInput(e.target.value)}
                placeholder="fork-name"
                autoFocus
                style={{
                  width: "100%",
                  background: "#141414",
                  border: "1px solid #333",
                  borderRadius: "3px",
                  color: COLOR_TEXT_BRIGHT,
                  padding: "4px 6px",
                  fontSize: "10px",
                  fontFamily: "'JetBrains Mono', monospace",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              />
              <div style={{ display: "flex", gap: "4px", marginTop: "4px" }}>
                <button
                  type="submit"
                  style={btn({
                    background: `${COLOR_BRANCH}22`,
                    border: `1px solid ${COLOR_BRANCH}`,
                    color: COLOR_BRANCH,
                    flex: 1,
                  })}
                >
                  Create
                </button>
                <button
                  type="button"
                  onClick={() => { setShowFork(false); setForkInput(""); }}
                  style={btn({ flex: 1 })}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}

          <div style={{ overflow: "auto", paddingBottom: "8px" }}>
            {branches.map((b) => {
              const isCurrent = b.is_current;
              return (
                <div
                  key={b.name}
                  style={{
                    padding: "6px 12px",
                    fontSize: "10px",
                    background: isCurrent ? "#141414" : "transparent",
                    borderLeft: isCurrent ? `2px solid ${COLOR_BRANCH}` : "2px solid transparent",
                  }}
                >
                  <div style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "4px",
                  }}>
                    <span style={{
                      color: isCurrent ? COLOR_BRANCH : COLOR_TEXT,
                      fontWeight: isCurrent ? 600 : 400,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      flex: 1,
                    }}>
                      {isCurrent ? "→ " : "  "}{b.name}
                    </span>
                    {b.commits_ahead > 0 && (
                      <span style={{ fontSize: "8px", color: "#666" }}>
                        +{b.commits_ahead}
                      </span>
                    )}
                  </div>
                  {!isCurrent && (
                    <div style={{ display: "flex", gap: "3px", marginTop: "3px" }}>
                      <button
                        onClick={() => onSwitchBranch(b.name)}
                        style={btn({ flex: 1 })}
                      >
                        Switch
                      </button>
                      <button
                        onClick={() => onCompare(b.name)}
                        style={btn({ flex: 1 })}
                      >
                        Diff
                      </button>
                      <button
                        onClick={() => onMerge(b.name)}
                        style={btn({
                          flex: 1,
                          background: `${COLOR_BRANCH}18`,
                          color: COLOR_BRANCH,
                          borderColor: `${COLOR_BRANCH}44`,
                        })}
                      >
                        Merge
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
