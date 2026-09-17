import { useState, useEffect } from "react";
import * as api from "../api.js";

// The Library lens: what do I believe, and where did it come from. Read-only
// here (confirm / rephrase / retire stay in the library's review page, which
// writes under the owner's channel). Trace joins beliefs, interpretations,
// workspaces and runs by content hash or text.

const mono = "'JetBrains Mono', monospace";
export const STANCE = { RELY: "#4ade80", NOTE: "#fbbf24", SUSPECT: "#fb923c", CONTESTED: "#f87171", HYPOTHESIS: "#60a5fa" };
const label = { fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" };
const box = { background: "#141414", border: "1px solid #222", borderRadius: "4px", padding: "10px" };
const input = { width: "100%", background: "#0A0A0A", border: "1px solid #222", borderRadius: "3px", color: "#e0e0e0", padding: "8px 10px", fontSize: "12px", fontFamily: mono, outline: "none", boxSizing: "border-box" };

export function Stance({ s }) {
  return <span style={{ color: STANCE[s] || "#888", fontSize: "9px", letterSpacing: "1px", flexShrink: 0 }}>{s}</span>;
}

export function BeliefRow({ b, onOpen }) {
  return (
    <div onClick={() => onOpen(b.id)} style={{ padding: "9px 12px", cursor: "pointer", fontSize: "11.5px", borderLeft: `3px solid ${STANCE[b.stance] || "#555"}`, borderBottom: "1px solid #1a1a1a" }}>
      <div style={{ display: "flex", gap: "10px", alignItems: "baseline" }}>
        <Stance s={b.stance} />
        <span style={{ color: "#d6d6d6", lineHeight: 1.5 }}>{b.claim}</span>
        {b.exact === true && <span style={{ color: "#FF6B35", fontSize: "9px", marginLeft: "auto", flexShrink: 0 }}>exact hash</span>}
      </div>
      <div style={{ color: "#555", fontSize: "9.5px", marginTop: "3px" }}>{b.id} · {b.method} · {b.freshness}{b.unsupported ? " · unsupported" : ""}{b.stood_behind_by ? ` · stood behind by ${b.stood_behind_by}` : <span style={{ color: "#fbbf24" }}> · unreviewed</span>}</div>
    </div>
  );
}

export function BeliefDetail({ id, onClose, onSelectWorkspace }) {
  const [b, setB] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { setB(null); setErr(null); api.getBelief(id).then(setB).catch((e) => setErr(e.message)); }, [id]);
  if (err) return <div style={{ color: "#f87171", fontSize: "10px" }}>{err}</div>;
  if (!b) return <div style={{ color: "#555", fontSize: "10px" }}>Loading…</div>;
  const a = b.authorship || {};
  return (
    <div style={{ ...box, borderLeft: `3px solid ${STANCE[b.stance] || "#555"}`, display: "flex", flexDirection: "column", gap: "10px" }}>
      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
        <Stance s={b.stance} />
        <span style={{ ...label }}>{b.method} · {b.volatility} · {b.freshness}{b.verified_at ? ` · verified ${b.verified_at}` : ""}{b.contested ? " · contested" : ""}{b.retired ? " · retired" : ""}</span>
        <button onClick={onClose} style={{ marginLeft: "auto", background: "transparent", border: "1px solid #333", color: "#888", borderRadius: "3px", padding: "3px 8px", fontSize: "9px", cursor: "pointer", fontFamily: mono }}>CLOSE</button>
      </div>
      <div style={{ fontSize: "13px", color: "#e0e0e0", lineHeight: 1.5 }}>{b.claim}</div>
      <div style={{ fontSize: "9px", color: "#555", fontFamily: mono, wordBreak: "break-all" }}>{b.id} · {b.cluster} · hash {b.claim_hash.slice(0, 16)}…</div>
      <div style={{ fontSize: "10px", color: "#888", lineHeight: 1.5 }}>
        <span style={label}>Whose word · </span>composed by <span style={{ color: "#ccc" }}>{a.composed_by}</span>{a.corrected ? " (attribution corrected)" : ""}; {a.stood_behind_by ? <span style={{ color: "#4ade80" }}>stood behind by {a.stood_behind_by}</span> : <span style={{ color: "#fbbf24" }}>not yet stood behind by the owner — a draft in the owner's record</span>}
        {b.guidance && <div style={{ color: "#666", marginTop: "2px" }}>guidance: {b.guidance}</div>}
      </div>
      {b.anchor && <div style={{ fontSize: "9px", color: "#666", fontFamily: mono, wordBreak: "break-all" }}><span style={label}>Anchor · </span>{b.anchor}</div>}
      <div>
        <div style={{ ...label, marginBottom: "4px" }}>Evidence ({b.evidence.length})</div>
        {b.evidence.length === 0 && <div style={{ fontSize: "10px", color: "#fbbf24" }}>No evidence. This belief is unsupported.</div>}
        {b.evidence.map((e) => (
          <div key={e.evidence_id} style={{ padding: "5px 8px", background: "#0A0A0A", borderRadius: "3px", marginBottom: "4px", fontSize: "10px", borderLeft: `3px solid ${e.content_available ? "#4ade80" : "#f87171"}` }}>
            <div style={{ color: "#bbb", wordBreak: "break-all" }}>{e.uri || e.evidence_id} <span style={{ color: "#555" }}>· {e.kind || e.media_type} · {(e.recorded_at || "").slice(0, 10)}{e.content_available ? "" : " · content missing"}</span></div>
            {e.spans.map((q, i) => <div key={i} style={{ color: "#777", fontStyle: "italic", marginTop: "2px", paddingLeft: "8px", borderLeft: "2px solid #333" }}>“{q}”</div>)}
            {e.uri && e.uri.startsWith("epist-workspace://") && (
              <button onClick={() => onSelectWorkspace(e.uri.replace("epist-workspace://", "").split("@")[0])} style={{ marginTop: "4px", background: "transparent", border: "1px solid #333", color: "#FF6B35", borderRadius: "3px", padding: "2px 6px", fontSize: "9px", cursor: "pointer", fontFamily: mono }}>OPEN WORKSPACE</button>
            )}
          </div>
        ))}
      </div>
      {b.claim_history.length > 1 && (
        <div>
          <div style={{ ...label, marginBottom: "4px" }}>Claim history ({b.claim_history.length})</div>
          {b.claim_history.map((h, i) => (
            <div key={i} style={{ fontSize: "10px", color: "#888", padding: "3px 0", borderBottom: "1px solid #1a1a1a" }}>
              <span style={{ color: "#444" }}>{(h.at || "").slice(0, 10)} · {h.origin} · {h.actor}</span> {h.claim}{h.note ? <span style={{ color: "#555" }}> — {h.note}</span> : null}
            </div>
          ))}
        </div>
      )}
      {(b.runs.length > 0 || b.interpretations.length > 0) && (
        <div style={{ fontSize: "10px", color: "#888" }}>
          {b.runs.map((r) => <div key={r.run_id}><span style={label}>run · </span>{r.kind} · {r.interpreter} · {(r.recorded_at || "").slice(0, 10)}</div>)}
          {b.interpretations.map((i) => <div key={i.id}><span style={label}>interpretation · </span>{i.kind} · {i.statement}</div>)}
        </div>
      )}
      <div style={{ fontSize: "9px", color: "#444" }}>
        {b.events.length} events · Confirm / Rephrase / Retire happen in the library's review page, under your own channel.
      </div>
    </div>
  );
}

export default function LibraryPanel({ onSelectWorkspace, refreshKey }) {
  const [status, setStatus] = useState(null);
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("beliefs"); // beliefs | trace
  const [results, setResults] = useState([]);
  const [trace, setTrace] = useState(null);
  const [open, setOpen] = useState(null);

  useEffect(() => { api.libraryStatus().then(setStatus).catch(() => setStatus({ available: false })); }, [refreshKey]);

  useEffect(() => {
    if (!status?.available) return;
    const t = setTimeout(() => {
      if (mode === "beliefs") api.searchBeliefs(q.trim()).then(setResults).catch(() => setResults([]));
      else if (q.trim().length >= 3) api.traceClaim(q.trim()).then(setTrace).catch(() => setTrace(null));
      else setTrace(null);
    }, 250);
    return () => clearTimeout(t);
  }, [q, mode, status]);

  if (!status) return null;
  if (!status.available) return <div style={{ color: "#f87171", fontSize: "10px" }}>Living library unavailable: {status.reason}</div>;
  const c = status.counts || {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px", maxWidth: "820px" }}>
      <div style={{ display: "flex", gap: "12px", alignItems: "baseline", fontSize: "10px", color: "#555" }}>
        <span style={label}>Living library</span>
        <span>branch <span style={{ color: status.branch === "main" ? "#4ade80" : "#a78bfa" }}>{status.branch}</span></span>
        <span>{c.beliefs} beliefs · {c.evidence} evidence · {c.interpretations} interpretations · {c.runs} runs</span>
        <span style={{ marginLeft: "auto", fontFamily: mono }}>lib {status.library_code} · wb {status.workbench_code}</span>
      </div>
      <div style={{ display: "flex", gap: "4px" }}>
        {["beliefs", "trace"].map((m) => (
          <button key={m} onClick={() => { setMode(m); setOpen(null); }} style={{
            background: mode === m ? "#FF6B3522" : "#141414", border: `1px solid ${mode === m ? "#FF6B35" : "#222"}`,
            color: mode === m ? "#FF6B35" : "#666", padding: "6px 14px", borderRadius: "3px", fontSize: "10px",
            cursor: "pointer", fontFamily: mono, textTransform: "uppercase", letterSpacing: "1px",
          }}>{m === "beliefs" ? "What do I believe" : "Where did this come from"}</button>
        ))}
      </div>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={mode === "beliefs" ? "Search beliefs by claim or id… (empty = all, by stance)" : "Paste a claim or a phrase to trace it across beliefs, interpretations, workspaces and runs"} style={input} />
      {open && <BeliefDetail id={open} onClose={() => setOpen(null)} onSelectWorkspace={onSelectWorkspace} />}
      {mode === "beliefs" && !open && (
        <div style={{ ...box, padding: 0, maxHeight: "60vh", overflow: "auto" }}>
          {results.map((b) => <BeliefRow key={b.id} b={b} onOpen={setOpen} />)}
          {results.length === 0 && <div style={{ padding: "10px", fontSize: "10px", color: "#444", fontStyle: "italic" }}>No beliefs match.</div>}
        </div>
      )}
      {mode === "trace" && trace && (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <div style={{ fontSize: "9px", color: "#555", fontFamily: mono }}>hash {trace.claim_hash}</div>
          <div style={box}>
            <div style={{ ...label, marginBottom: "6px" }}>Beliefs ({trace.beliefs.length})</div>
            {trace.beliefs.map((b) => <BeliefRow key={b.id} b={b} onOpen={setOpen} />)}
            {trace.beliefs.length === 0 && <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic" }}>none</div>}
          </div>
          <div style={box}>
            <div style={{ ...label, marginBottom: "6px" }}>Interpretations ({trace.interpretations.length}) — derived, not beliefs</div>
            {trace.interpretations.map((i) => (
              <div key={i.id} style={{ fontSize: "10px", padding: "5px 8px", borderLeft: `3px dashed ${i.exact ? "#FF6B35" : "#555"}`, borderBottom: "1px solid #1a1a1a" }}>
                <span style={{ color: "#a78bfa", fontSize: "9px", marginRight: "6px" }}>{i.kind}</span><span style={{ color: "#bbb" }}>{i.statement}</span>
                <div style={{ color: "#555", fontSize: "9px" }}>{i.interpreter}{i.run_id ? ` · run ${i.run_id.slice(4, 12)}` : ""}{i.grounding.length ? ` · grounded in ${i.grounding.length} span${i.grounding.length === 1 ? "" : "s"}` : " · ungrounded"}</div>
              </div>
            ))}
            {trace.interpretations.length === 0 && <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic" }}>none</div>}
          </div>
          <div style={box}>
            <div style={{ ...label, marginBottom: "6px" }}>Workspaces ({trace.workspaces.length})</div>
            {trace.workspaces.map((w, k) => (
              <div key={k} onClick={() => onSelectWorkspace(w.workspace)} style={{ fontSize: "10px", padding: "5px 8px", cursor: "pointer", borderLeft: `3px solid ${w.exact ? "#FF6B35" : "#555"}`, borderBottom: "1px solid #1a1a1a" }}>
                <span style={{ color: "#FF6B35", marginRight: "6px" }}>{w.workspace}</span><span style={{ color: "#bbb" }}>{w.text}</span>
                <span style={{ color: "#555", fontSize: "9px" }}> · {w.node_type}{w.is_root ? " (thesis)" : ""}{w.status ? ` · ${w.status}` : ""}</span>
              </div>
            ))}
            {trace.workspaces.length === 0 && <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic" }}>none</div>}
          </div>
          {trace.runs.length > 0 && (
            <div style={box}>
              <div style={{ ...label, marginBottom: "6px" }}>Runs that produced these ({trace.runs.length})</div>
              {trace.runs.map((r) => <div key={r.run_id} style={{ fontSize: "10px", color: "#888" }}>{(r.recorded_at || "").slice(0, 10)} · {r.kind} · {r.interpreter} · {r.actor}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
