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
  onArchive,
}) {
  const [forkInput, setForkInput] = useState("");
  const [showFork, setShowFork] = useState(false);
  const [filter, setFilter] = useState("");
  const [showArchived, setShowArchived] = useState(false);

  const archivedCount = workspaces.filter((w) => w.archived).length;
  const visible = workspaces.filter((w) => {
    if (w.archived && !showArchived && w.name !== currentWorkspace) return false;
    if (!filter.trim()) return true;
    const f = filter.toLowerCase();
    return w.name.toLowerCase().includes(f) || (w.thesis_text || "").toLowerCase().includes(f);
  });

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
          Workspaces ({visible.length}{archivedCount && !showArchived ? ` · ${archivedCount} archived` : ""})
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

      {/* Search + archived toggle */}
      <div style={{ padding: "6px 8px", borderBottom: `1px solid ${COLOR_BORDER}`, display: "flex", gap: "4px", flexShrink: 0 }}>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="filter by name or thesis…"
          style={{
            flex: 1, background: "#141414", border: "1px solid #222", borderRadius: "3px",
            color: COLOR_TEXT_BRIGHT, padding: "4px 6px", fontSize: "10px",
            fontFamily: "'JetBrains Mono', monospace", outline: "none", minWidth: 0,
          }}
        />
        {archivedCount > 0 && (
          <button onClick={() => setShowArchived(!showArchived)} title="Show archived workspaces"
            style={btn({ color: showArchived ? COLOR_ACCENT : COLOR_TEXT_DIM, borderColor: showArchived ? COLOR_ACCENT : "#333" })}>
            ▤
          </button>
        )}
      </div>

      {/* Workspace list */}
      <div style={{ flex: 1, overflow: "auto" }}>
        {visible.length === 0 && workspaces.length > 0 && (
          <div style={{ padding: "20px 12px", color: COLOR_TEXT_DIM, fontSize: "10px", textAlign: "center" }}>
            No match.
          </div>
        )}
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
        {visible.map((w) => {
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
                color: isCurrent ? COLOR_ACCENT : (w.archived ? COLOR_TEXT_DIM : COLOR_TEXT_BRIGHT),
                fontWeight: isCurrent ? 600 : 400,
                marginBottom: "2px",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                display: "flex", alignItems: "center", gap: "6px",
              }}>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>{w.archived ? "▤ " : ""}{w.name}</span>
                {isCurrent && onArchive && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onArchive(w.name, !w.archived); }}
                    title={w.archived ? "Unarchive" : "Archive (hide from the list; nothing is deleted)"}
                    style={btn({ padding: "1px 4px", fontSize: "8px" })}
                  >
                    {w.archived ? "unarchive" : "archive"}
                  </button>
                )}
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
