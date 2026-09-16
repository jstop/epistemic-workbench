import { useState, useEffect, useCallback, useRef } from "react";
import * as api from "../api.js";

// F2 (provenance) + F5 (ingestion). Two questions this panel answers:
//   1. Which evidence is merely asserted, and can I ground it in a real source?
//   2. What argumentation does a document contain — proposed, then curated,
//      never auto-committed.

const mono = "'JetBrains Mono', monospace";
const label = { fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" };
const box = { background: "#141414", border: "1px solid #222", borderRadius: "4px", padding: "10px" };
const input = {
  width: "100%", background: "#0A0A0A", border: "1px solid #222", borderRadius: "3px",
  color: "#e0e0e0", padding: "7px 9px", fontSize: "11px", fontFamily: mono,
  outline: "none", boxSizing: "border-box",
};
const btn = (extra = {}) => ({
  background: "transparent", border: "1px solid #333", color: "#888", borderRadius: "3px",
  padding: "5px 9px", fontSize: "9px", cursor: "pointer", fontFamily: mono,
  letterSpacing: "1px", textTransform: "uppercase", ...extra,
});
const ROLE_COLORS = { claim: "#60a5fa", thesis: "#FF6B35", objection: "#f87171", concession: "#fb923c", evidence: "#4ade80", argument: "#a78bfa" };

// ── Unsourced evidence ──────────────────────────────────────────────

function UnsourcedSection({ workspace, onSelectNode, onUpdated, refreshKey }) {
  const [data, setData] = useState(null);
  const [attaching, setAttaching] = useState(null); // evidence id
  const [url, setUrl] = useState("");
  const [quote, setQuote] = useState("");
  const [msg, setMsg] = useState(null);

  const load = useCallback(() => {
    if (!workspace) return;
    api.getUnsourced(workspace).then(setData).catch(() => setData(null));
  }, [workspace]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const submit = async () => {
    setMsg(null);
    try {
      const r = await api.attachSource(workspace, { node_id: attaching, url, quote });
      if (r.ok) { setAttaching(null); setUrl(""); setQuote(""); load(); onUpdated(); }
      else setMsg(`Still asserted — ${r.reason}`);
    } catch (err) { setMsg(err.message); }
  };

  if (!data) return null;
  const { rows, counts } = data;
  return (
    <div style={box}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: "8px" }}>
        <span style={label}>Evidence provenance</span>
        <span style={{ marginLeft: "auto", fontSize: "10px" }}>
          <span style={{ color: "#4ade80" }}>{counts.recorded} recorded</span>
          <span style={{ color: "#333" }}> · </span>
          <span style={{ color: counts.asserted > 0 ? "#fbbf24" : "#555" }}>{counts.asserted} asserted</span>
        </span>
      </div>
      {rows.length === 0 ? (
        <div style={{ fontSize: "10px", color: "#4ade80" }}>
          {counts.total === 0 ? "No evidence nodes yet." : "Every evidence node is grounded in a recorded source."}
        </div>
      ) : (
        <>
          <div style={{ fontSize: "9px", color: "#777", marginBottom: "8px", lineHeight: 1.5 }}>
            These evidence nodes carry a source string but no recorded source. Generated graphs invent authoritative-looking citations; nothing here is verified until a real source is attached.
          </div>
          {rows.map((r) => (
            <div key={r.id} style={{ padding: "6px 8px", background: "#0A0A0A", borderRadius: "3px", borderLeft: "3px solid #fbbf24", marginBottom: "4px", fontSize: "10px" }}>
              <div onClick={() => onSelectNode(r.id)} style={{ color: "#ccc", cursor: "pointer" }}>{r.title}</div>
              <div style={{ color: "#555", fontSize: "9px", marginTop: "2px", wordBreak: "break-all" }}>claimed: {r.source || "(none)"}</div>
              {attaching === r.id ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "6px" }}>
                  <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Real source URL" style={input} />
                  <input value={quote} onChange={(e) => setQuote(e.target.value)} placeholder="Supporting quote (optional)" style={input} />
                  {msg && <div style={{ fontSize: "9px", color: "#f87171" }}>{msg}</div>}
                  <div style={{ display: "flex", gap: "4px" }}>
                    <button onClick={submit} disabled={!url} style={btn({ background: "#4ade8022", borderColor: "#4ade80", color: "#4ade80" })}>Record</button>
                    <button onClick={() => { setAttaching(null); setMsg(null); }} style={btn()}>Cancel</button>
                  </div>
                </div>
              ) : (
                <button onClick={() => { setAttaching(r.id); setUrl(""); setQuote(""); }} style={btn({ marginTop: "6px" })}>+ Attach source</button>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ── Ingestion ───────────────────────────────────────────────────────

function IngestSection({ workspace, onProposalCreated }) {
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [job, setJob] = useState(null); // {job_id, status, error, result}
  const timer = useRef(null);

  useEffect(() => () => clearInterval(timer.current), []);

  const start = async () => {
    if (!text.trim() && !url.trim()) return;
    try {
      const r = await api.ingest(workspace, { source_text: text, url, title });
      setJob({ job_id: r.job_id, status: "running" });
      timer.current = setInterval(async () => {
        try {
          const j = await api.getJob(r.job_id);
          setJob(j);
          if (j.status !== "running") {
            clearInterval(timer.current);
            if (j.status === "completed") { setText(""); setUrl(""); setTitle(""); onProposalCreated(); }
          }
        } catch { /* keep polling */ }
      }, 3000);
    } catch (err) { alert(err.message); }
  };

  const running = job?.status === "running";
  return (
    <div style={box}>
      <div style={{ ...label, marginBottom: "8px" }}>Ingest a document</div>
      <div style={{ fontSize: "9px", color: "#777", marginBottom: "8px", lineHeight: 1.5 }}>
        The source is registered in recall and an LLM proposes the claims, arguments and objections it contains, each tied to a verbatim span. Nothing enters the live graph until you commit the nodes you accept below. Extraction takes a minute or two.
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (optional)" style={input} disabled={running} />
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Source URL (stored as provenance; paste the text below)" style={input} disabled={running} />
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the document or transcript text…" rows={7} disabled={running}
          style={{ ...input, resize: "vertical" }} />
        <button onClick={start} disabled={running || (!text.trim() && !url.trim())} style={{
          background: running || (!text.trim() && !url.trim()) ? "#222" : "#FF6B35",
          color: running || (!text.trim() && !url.trim()) ? "#555" : "#0A0A0A",
          border: "none", borderRadius: "3px", padding: "9px", fontSize: "10px",
          cursor: running ? "default" : "pointer", fontFamily: mono, fontWeight: 600, letterSpacing: "1px",
        }}>
          {running ? "⟳ EXTRACTING…" : "PROPOSE ARGUMENTATION"}
        </button>
        {job && job.status === "failed" && <div style={{ fontSize: "10px", color: "#f87171" }}>Failed: {job.error}</div>}
        {job && job.status === "completed" && (
          <div style={{ fontSize: "10px", color: "#4ade80" }}>
            Proposal {job.result?.proposal_id} created: {job.result?.counts?.nodes} nodes, {job.result?.counts?.edges} edges (recall source #{job.result?.source_id}).
          </div>
        )}
      </div>
    </div>
  );
}

// ── Proposals ───────────────────────────────────────────────────────

function ProposalReview({ workspace, proposalId, onCommitted, onClose }) {
  const [pr, setPr] = useState(null);
  const [accepted, setAccepted] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    api.getProposal(workspace, proposalId).then((p) => {
      setPr(p);
      setAccepted(new Set(p.status === "committed" ? [] : (p.nodes || []).map((n) => n.id)));
    }).catch((e) => setMsg(e.message));
  }, [workspace, proposalId]);

  if (!pr) return <div style={{ fontSize: "10px", color: "#555" }}>{msg || "Loading…"}</div>;

  const toggle = (id) => setAccepted((prev) => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const committed = pr.status === "committed";

  const commit = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.commitProposal(workspace, proposalId, [...accepted]);
      const c = r.committed;
      setMsg(`Committed ${c.claims} claims, ${c.evidence} evidence, ${c.arguments} arguments, ${c.edges} edges (${r.skipped} skipped).`);
      onCommitted();
    } catch (err) { setMsg(err.message); }
    finally { setBusy(false); }
  };

  return (
    <div style={{ marginTop: "8px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
        <span style={{ fontSize: "10px", color: "#ccc" }}>{pr.title || proposalId}</span>
        <span style={{ fontSize: "9px", color: committed ? "#4ade80" : "#fbbf24", textTransform: "uppercase" }}>{pr.status}</span>
        <span style={{ fontSize: "9px", color: "#555" }}>{(pr.nodes || []).length} nodes · {(pr.edges || []).length} edges · source #{pr.source_id}</span>
        <button onClick={onClose} style={btn({ marginLeft: "auto" })}>Close</button>
      </div>
      {!committed && (
        <div style={{ display: "flex", gap: "4px", marginBottom: "6px" }}>
          <button onClick={() => setAccepted(new Set(pr.nodes.map((n) => n.id)))} style={btn()}>All</button>
          <button onClick={() => setAccepted(new Set())} style={btn()}>None</button>
        </div>
      )}
      <div style={{ maxHeight: "320px", overflow: "auto", border: "1px solid #222", borderRadius: "3px" }}>
        {(pr.nodes || []).map((n) => {
          const on = accepted.has(n.id);
          const color = ROLE_COLORS[n.type] || "#60a5fa";
          return (
            <div key={n.id} onClick={() => !committed && toggle(n.id)} style={{
              padding: "6px 8px", cursor: committed ? "default" : "pointer", fontSize: "10px",
              background: on ? `${color}12` : "transparent",
              borderLeft: `3px solid ${on ? color : "#222"}`, borderBottom: "1px solid #1a1a1a",
            }}>
              <div style={{ display: "flex", gap: "6px", alignItems: "baseline" }}>
                <span style={{ color, fontSize: "9px", textTransform: "uppercase", letterSpacing: "1px", flexShrink: 0 }}>{n.type || "claim"}</span>
                <span style={{ color: on ? "#e0e0e0" : "#777", lineHeight: 1.4 }}>{n.text}</span>
                {n.confidence != null && <span style={{ color: "#555", marginLeft: "auto", flexShrink: 0 }}>{Math.round(n.confidence * 100)}%</span>}
              </div>
              {typeof n.span === "string" && n.span && (
                <div style={{ color: "#555", fontStyle: "italic", fontSize: "9px", marginTop: "2px", paddingLeft: "8px", borderLeft: "2px solid #333" }}>“{n.span.slice(0, 160)}{n.span.length > 160 ? "…" : ""}”</div>
              )}
            </div>
          );
        })}
      </div>
      {(pr.edges || []).length > 0 && (
        <div style={{ fontSize: "9px", color: "#555", marginTop: "6px", lineHeight: 1.6 }}>
          {pr.edges.map((e, i) => (
            <span key={i} style={{ marginRight: "10px" }}>{e.from || e.from_id} <span style={{ color: "#a78bfa" }}>—{e.rel}→</span> {e.to}</span>
          ))}
        </div>
      )}
      {msg && <div style={{ fontSize: "10px", color: msg.startsWith("Committed") ? "#4ade80" : "#f87171", marginTop: "6px" }}>{msg}</div>}
      {!committed && (
        <button onClick={commit} disabled={busy || accepted.size === 0} style={{
          marginTop: "8px", width: "100%",
          background: busy || accepted.size === 0 ? "#222" : "#FF6B35",
          color: busy || accepted.size === 0 ? "#555" : "#0A0A0A",
          border: "none", borderRadius: "3px", padding: "9px", fontSize: "10px",
          cursor: "pointer", fontFamily: mono, fontWeight: 600, letterSpacing: "1px",
        }}>
          {busy ? "COMMITTING…" : `COMMIT ${accepted.size} ACCEPTED NODE${accepted.size === 1 ? "" : "S"}`}
        </button>
      )}
    </div>
  );
}

function ProposalsSection({ workspace, refreshKey, onUpdated }) {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(null);

  const load = useCallback(() => {
    if (!workspace) return;
    api.listProposals(workspace).then(setList).catch(() => setList([]));
  }, [workspace]);
  useEffect(() => { load(); }, [load, refreshKey]);

  return (
    <div style={box}>
      <div style={{ ...label, marginBottom: "8px" }}>Proposals ({list.length})</div>
      {list.length === 0 && <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic" }}>No ingestion proposals yet.</div>}
      {list.map((p) => (
        <div key={p.proposal_id} onClick={() => setOpen(open === p.proposal_id ? null : p.proposal_id)} style={{
          display: "flex", gap: "8px", alignItems: "center", padding: "6px 8px", cursor: "pointer", fontSize: "10px",
          background: open === p.proposal_id ? "#FF6B3512" : "#0A0A0A", borderRadius: "3px", marginBottom: "4px",
          borderLeft: `3px solid ${p.status === "committed" ? "#4ade80" : "#fbbf24"}`,
        }}>
          <span style={{ color: "#ccc", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.title || p.proposal_id}</span>
          <span style={{ color: "#555" }}>{p.nodes} nodes</span>
          <span style={{ color: p.status === "committed" ? "#4ade80" : "#fbbf24", fontSize: "9px", textTransform: "uppercase" }}>{p.status}</span>
        </div>
      ))}
      {open && (
        <ProposalReview
          workspace={workspace}
          proposalId={open}
          onCommitted={() => { load(); onUpdated(); }}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}

// ── Panel ───────────────────────────────────────────────────────────

export default function SourcesPanel({ workspace, onSelectNode, onUpdated }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const bump = () => setRefreshKey((k) => k + 1);
  if (!workspace) return <div style={{ color: "#555", fontSize: "10px" }}>Select a workspace first.</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px", maxWidth: "760px" }}>
      <UnsourcedSection workspace={workspace} onSelectNode={onSelectNode} onUpdated={() => { bump(); onUpdated(); }} refreshKey={refreshKey} />
      <IngestSection workspace={workspace} onProposalCreated={bump} />
      <ProposalsSection workspace={workspace} refreshKey={refreshKey} onUpdated={() => { bump(); onUpdated(); }} />
    </div>
  );
}
