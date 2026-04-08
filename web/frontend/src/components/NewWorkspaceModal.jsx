import { useState } from "react";
import * as api from "../api.js";

export default function NewWorkspaceModal({ onClose, onCreated, setBusy }) {
  const [name, setName] = useState("");
  const [thesis, setThesis] = useState("");
  const [error, setError] = useState(null);

  const slugify = (s) =>
    s.toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 50);

  const handleCreate = async () => {
    setError(null);
    const finalName = name.trim() || slugify(thesis.slice(0, 40));
    if (!finalName) {
      setError("Provide a name or thesis text");
      return;
    }
    if (!thesis.trim()) {
      setError("Thesis is required");
      return;
    }

    onClose(); // close modal so the busy overlay shows
    setBusy && setBusy("Generating argument graph (this may take 30-60s)…");

    try {
      // /generate auto-creates the workspace
      await api.generate(finalName, thesis.trim());
      setBusy && setBusy(null);
      onCreated(finalName);
    } catch (err) {
      setBusy && setBusy(null);
      alert(`Generation failed: ${err.message}`);
    }
  };

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
          padding: "20px 24px", width: "540px", maxWidth: "92vw",
          fontFamily: "'JetBrains Mono', monospace", color: "#e0e0e0",
        }}>
        <div style={{
          fontSize: "10px", letterSpacing: "3px", color: "#FF6B35",
          textTransform: "uppercase", marginBottom: "16px",
        }}>
          New Workspace
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div>
            <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>
              Name (optional)
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={thesis ? slugify(thesis.slice(0, 40)) : "my-thesis"}
              style={{
                width: "100%", background: "#141414", border: "1px solid #222",
                borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
                fontSize: "12px", fontFamily: "'JetBrains Mono', monospace",
                outline: "none", marginTop: "4px", boxSizing: "border-box",
              }}
            />
            <div style={{ fontSize: "9px", color: "#444", marginTop: "2px" }}>
              Slug from thesis if blank.
            </div>
          </div>

          <div>
            <label style={{ fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" }}>
              Thesis Statement
            </label>
            <textarea
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
              placeholder="What do you want to argue?"
              rows={6}
              style={{
                width: "100%", background: "#141414", border: "1px solid #222",
                borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px",
                fontSize: "12px", fontFamily: "'JetBrains Mono', monospace",
                outline: "none", marginTop: "4px", boxSizing: "border-box",
                resize: "vertical", lineHeight: "1.5",
              }}
            />
          </div>

          {error && (
            <div style={{ fontSize: "10px", color: "#f87171" }}>{error}</div>
          )}

          <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
            <button
              onClick={handleCreate}
              disabled={!thesis.trim()}
              style={{
                flex: 1,
                background: thesis.trim() ? "#FF6B35" : "#222",
                color: thesis.trim() ? "#0A0A0A" : "#555",
                border: "none", borderRadius: "3px", padding: "10px",
                fontSize: "11px", cursor: thesis.trim() ? "pointer" : "default",
                fontFamily: "'JetBrains Mono', monospace", fontWeight: 600,
                letterSpacing: "1px",
              }}
            >
              GENERATE
            </button>
            <button
              onClick={onClose}
              style={{
                background: "transparent", border: "1px solid #333",
                color: "#888", borderRadius: "3px", padding: "10px 16px",
                fontSize: "11px", cursor: "pointer",
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: "1px",
              }}
            >
              CANCEL
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
