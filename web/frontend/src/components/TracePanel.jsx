import { useState, useEffect } from "react";
import * as api from "../api.js";
import { STANCE, BeliefRow, BeliefDetail } from "./LibraryPanel.jsx";

// Where did this come from, and what produced it.

const mono = "'JetBrains Mono', monospace";
const label = { fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" };
const box = { background: "#141414", border: "1px solid #222", borderRadius: "4px", padding: "10px" };
const input = { width: "100%", background: "#0A0A0A", border: "1px solid #222", borderRadius: "3px", color: "#e0e0e0", padding: "9px 12px", fontSize: "12px", fontFamily: mono, outline: "none", boxSizing: "border-box" };
const RUN_COLORS = { generate: "#FF6B35", extract: "#a78bfa", curate: "#4ade80", "gate-check": "#60a5fa", "import-recall": "#fb923c", "ingest-apply": "#a78bfa" };

function EvidenceDetail({ id, onClose, onOpenBelief }) {
  const [e, setE] = useState(null); const [err, setErr] = useState(null);
  useEffect(() => { setE(null); api.getLibraryEvidence(id).then(setE).catch((x) => setErr(x.message)); }, [id]);
  if (err) return <div style={{ color: "#f87171", fontSize: "10px" }}>{err}</div>;
  if (!e) return <div style={{ color: "#555", fontSize: "10px" }}>Loading…</div>;
  return (
    <div style={{ ...box, borderLeft: `3px solid ${e.content_available ? "#4ade80" : "#f87171"}`, display: "flex", flexDirection: "column", gap: "8px" }}>
      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
        <span style={label}>evidence · {e.durability} · {e.media_type} · {(e.recorded_at || "").slice(0, 10)} · by {e.actor}</span>
        <button onClick={onClose} style={{ marginLeft: "auto", background: "transparent", border: "1px solid #333", color: "#888", borderRadius: "3px", padding: "3px 8px", fontSize: "9px", cursor: "pointer", fontFamily: mono }}>CLOSE</button>
      </div>
      <div style={{ fontSize: "12px", color: "#e0e0e0", wordBreak: "break-all" }}>{e.uri || e.evidence_id}</div>
      <div style={{ fontSize: "9px", color: "#555", fontFamily: mono }}>{e.evidence_id}{e.size ? ` · ${e.size} bytes` : ""}{e.content_available ? "" : " · content missing"}</div>
      {e.excerpt && <pre style={{ fontSize: "10px", color: "#999", background: "#0A0A0A", padding: "8px", borderRadius: "3px", whiteSpace: "pre-wrap", maxHeight: "220px", overflow: "auto", margin: 0 }}>{e.excerpt}</pre>}
      {Object.keys(e.metadata).length > 0 && <div style={{ fontSize: "9px", color: "#555", fontFamily: mono, wordBreak: "break-all" }}>{JSON.stringify(e.metadata)}</div>}
      <div>
        <div style={{ ...label, marginBottom: "4px" }}>Rests on it: {e.beliefs.length} beliefs · {e.interpretations.length} interpretations · {e.runs.length} runs</div>
        {e.beliefs.map((b) => <div key={b.id} onClick={() => onOpenBelief(b.id)} style={{ fontSize: "10px", color: "#ccc", cursor: "pointer", padding: "3px 0" }}>● {b.claim}{b.spans[0] ? <span style={{ color: "#666", fontStyle: "italic" }}> — “{b.spans[0]}”</span> : null}</div>)}
        {e.interpretations.map((i) => <div key={i.id} style={{ fontSize: "10px", color: "#aaa", padding: "3px 0" }}><span style={{ color: "#a78bfa", fontSize: "9px" }}>{i.kind}</span> {i.statement}</div>)}
        {e.runs.map((r) => <div key={r.run_id} style={{ fontSize: "10px", color: "#888", padding: "3px 0" }}><span style={{ color: RUN_COLORS[r.kind] || "#888", fontSize: "9px" }}>{r.kind}</span> {r.interpreter} · {(r.recorded_at || "").slice(0, 10)}</div>)}
      </div>
    </div>
  );
}

export default function TracePanel({ onSelectWorkspace, refreshKey }) {
  const [q, setQ] = useState("");
  const [trace, setTrace] = useState(null);
  const [runs, setRuns] = useState([]);
  const [runKind, setRunKind] = useState("");
  const [openBelief, setOpenBelief] = useState(null);
  const [openEvidence, setOpenEvidence] = useState(null);

  useEffect(() => {
    const t = setTimeout(() => {
      const s = q.trim();
      if (s.startsWith("evd_")) { setOpenEvidence(s); setTrace(null); return; }
      if (s.length >= 3) api.traceClaim(s).then(setTrace).catch(() => setTrace(null)); else setTrace(null);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => { api.getLibraryRuns(runKind).then(setRuns).catch(() => setRuns([])); }, [runKind, refreshKey]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px", maxWidth: "900px" }}>
      <div>
        <div style={{ fontSize: "20px", color: "#e0e0e0", fontFamily: mono, marginBottom: "4px" }}>Where did this come from?</div>
        <div style={{ fontSize: "11px", color: "#666", lineHeight: 1.5, maxWidth: "70ch" }}>
          Paste a claim to find it across beliefs, interpretations, workspaces and the runs that produced them, by exact content hash or by text. Paste an evidence id (evd_…) to see everything resting on one source. Below, every interpreter run the substrate has recorded.
        </div>
      </div>
      <input value={q} onChange={(e) => { setQ(e.target.value); setOpenBelief(null); if (!e.target.value.startsWith("evd_")) setOpenEvidence(null); }} placeholder="A claim, a phrase, or an evidence id…" style={input} />
      {openBelief && <BeliefDetail id={openBelief} onClose={() => setOpenBelief(null)} onSelectWorkspace={onSelectWorkspace} />}
      {openEvidence && !openBelief && <EvidenceDetail id={openEvidence} onClose={() => { setOpenEvidence(null); setQ(""); }} onOpenBelief={setOpenBelief} />}
      {trace && !openBelief && !openEvidence && (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <div style={{ fontSize: "9px", color: "#555", fontFamily: mono }}>hash {trace.claim_hash}</div>
          {[["Beliefs", trace.beliefs.length], ["Interpretations", trace.interpretations.length], ["Workspaces", trace.workspaces.length], ["Runs", trace.runs.length]].every(([, n]) => n === 0) && <div style={{ fontSize: "11px", color: "#444", fontStyle: "italic" }}>Nothing in the substrate carries this text.</div>}
          {trace.beliefs.length > 0 && <div style={box}><div style={{ ...label, marginBottom: "6px" }}>Beliefs ({trace.beliefs.length})</div>{trace.beliefs.map((b) => <BeliefRow key={b.id} b={b} onOpen={setOpenBelief} />)}</div>}
          {trace.interpretations.length > 0 && (
            <div style={box}><div style={{ ...label, marginBottom: "6px" }}>Interpretations ({trace.interpretations.length}) — derived, not beliefs</div>
              {trace.interpretations.map((i) => (
                <div key={i.id} style={{ fontSize: "10px", padding: "5px 8px", borderLeft: `3px dashed ${i.exact ? "#FF6B35" : "#555"}`, borderBottom: "1px solid #1a1a1a" }}>
                  <span style={{ color: "#a78bfa", fontSize: "9px", marginRight: "6px" }}>{i.kind}</span><span style={{ color: "#bbb" }}>{i.statement}</span>
                  <div style={{ color: "#555", fontSize: "9px" }}>{i.interpreter}{i.grounding.length ? ` · ${i.grounding.length} span${i.grounding.length === 1 ? "" : "s"}` : " · ungrounded"}{i.grounding[0] ? <span onClick={() => setOpenEvidence(i.grounding[0].evidence_id)} style={{ color: "#4ade80", cursor: "pointer" }}> · open evidence</span> : null}</div>
                </div>
              ))}
            </div>
          )}
          {trace.workspaces.length > 0 && (
            <div style={box}><div style={{ ...label, marginBottom: "6px" }}>Workspaces ({trace.workspaces.length})</div>
              {trace.workspaces.map((w, k) => (
                <div key={k} onClick={() => onSelectWorkspace(w.workspace)} style={{ fontSize: "10px", padding: "5px 8px", cursor: "pointer", borderLeft: `3px solid ${w.exact ? "#FF6B35" : "#555"}`, borderBottom: "1px solid #1a1a1a" }}>
                  <span style={{ color: "#FF6B35", marginRight: "6px" }}>{w.workspace}</span><span style={{ color: "#bbb" }}>{w.text}</span><span style={{ color: "#555", fontSize: "9px" }}> · {w.node_type}{w.is_root ? " (thesis)" : ""}{w.status ? ` · ${w.status}` : ""}</span>
                </div>
              ))}
            </div>
          )}
          {trace.runs.length > 0 && <div style={box}><div style={{ ...label, marginBottom: "6px" }}>Runs that produced these ({trace.runs.length})</div>{trace.runs.map((r) => <div key={r.run_id} style={{ fontSize: "10px", color: "#888" }}>{(r.recorded_at || "").slice(0, 10)} · <span style={{ color: RUN_COLORS[r.kind] || "#888" }}>{r.kind}</span> · {r.interpreter} · {r.actor}</div>)}</div>}
        </div>
      )}
      {!trace && !openBelief && !openEvidence && (
        <div style={box}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "8px" }}>
            <span style={label}>Interpreter runs · what produced what</span>
            <select value={runKind} onChange={(e) => setRunKind(e.target.value)} style={{ marginLeft: "auto", background: "#0A0A0A", border: "1px solid #222", color: "#aaa", fontSize: "10px", fontFamily: mono, padding: "3px 6px", borderRadius: "3px" }}>
              <option value="">all kinds</option>
              {["generate", "extract", "curate", "ingest-apply", "import-recall", "gate-check"].map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          {runs.length === 0 && <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic" }}>No runs recorded.</div>}
          {runs.map((r) => {
            const color = RUN_COLORS[r.kind] || "#888";
            const p = r.params || {};
            const what = r.kind === "gate-check" ? `${r.outputs[0]?.ok ? "passed" : "FAILED"} · anchors failed ${p.anchors_failed ?? 0} · unreviewed ${p.unreviewed ?? "?"}`
              : r.kind === "generate" ? `${p.workspace} · ${r.outputs[0]?.claims ?? "?"}c ${r.outputs[0]?.evidence ?? "?"}e ${r.outputs[0]?.arguments ?? "?"}a`
              : r.kind === "extract" ? `${p.workspace} · ${p.nodes ?? r.n_outputs} proposed${p.ungrounded_nodes ? `, ${p.ungrounded_nodes} ungrounded` : ""}`
              : r.kind === "curate" ? `${p.workspace} · ${p.accepted ?? r.n_outputs} accepted by ${p.accepted_by || r.actor}`
              : r.kind === "import-recall" ? `${r.n_outputs} interpretations from recall`
              : `${r.n_outputs} outputs`;
            return (
              <div key={r.run_id} style={{ display: "flex", gap: "10px", fontSize: "10px", padding: "4px 0", borderBottom: "1px solid #1a1a1a", alignItems: "baseline" }}>
                <span style={{ color: "#444", flexShrink: 0, width: "78px" }}>{(r.recorded_at || "").slice(0, 10)}</span>
                <span style={{ color, flexShrink: 0, fontSize: "9px", letterSpacing: "1px", textTransform: "uppercase", width: "84px" }}>{r.kind}</span>
                <span style={{ color: "#aaa", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>{what}</span>
                <span style={{ color: "#444", flexShrink: 0, fontFamily: mono, fontSize: "9px" }} title={r.interpreter}>{(r.interpreter || "").replace("epistemic-workbench/", "").slice(0, 34)} · {r.actor}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
