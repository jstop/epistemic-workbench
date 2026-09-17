import { useState, useEffect } from "react";
import * as api from "../api.js";
import { STANCE, BeliefRow, BeliefDetail } from "./LibraryPanel.jsx";

// What do I believe, and how much should I rely on it.

const mono = "'JetBrains Mono', monospace";
const ORDER = ["CONTESTED", "SUSPECT", "HYPOTHESIS", "NOTE", "RELY"];
const GUIDE = {
  CONTESTED: "do not assert; reconcile or ask", SUSPECT: "verify before high-stakes use", HYPOTHESIS: "never as fact",
  NOTE: "use, state the basis", RELY: "use silently",
};

export default function BelievePanel({ onSelectWorkspace, refreshKey, initialFilter }) {
  const [q, setQ] = useState("");
  const [all, setAll] = useState([]);
  const [filter, setFilter] = useState(initialFilter || "all"); // all | unreviewed | <STANCE>
  const [open, setOpen] = useState(null);
  const [status, setStatus] = useState(null);

  useEffect(() => { api.libraryStatus().then(setStatus).catch(() => null); }, [refreshKey]);
  useEffect(() => {
    const t = setTimeout(() => api.searchBeliefs(q.trim()).then(setAll).catch(() => setAll([])), 200);
    return () => clearTimeout(t);
  }, [q, refreshKey]);
  useEffect(() => { if (initialFilter) setFilter(initialFilter); }, [initialFilter]);

  const shown = all.filter((b) => filter === "all" ? true : filter === "unreviewed" ? b.stood_behind_by !== "owner" : b.stance === filter);
  const byStance = ORDER.map((st) => [st, shown.filter((b) => b.stance === st)]).filter(([, xs]) => xs.length);
  const counts = (status?.counts?.stances) || {};
  const unreviewed = status?.counts?.unreviewed ?? 0;

  const chip = (key, label, color, n) => (
    <button key={key} onClick={() => { setFilter(key); setOpen(null); }} style={{
      background: filter === key ? `${color}22` : "transparent", border: `1px solid ${filter === key ? color : "#222"}`,
      color: filter === key ? color : "#777", padding: "5px 10px", borderRadius: "3px", fontSize: "10px",
      cursor: "pointer", fontFamily: mono, letterSpacing: "0.5px",
    }}>{label}{n != null ? <span style={{ color: "#555", marginLeft: "6px" }}>{n}</span> : null}</button>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px", maxWidth: "900px" }}>
      <div>
        <div style={{ fontSize: "20px", color: "#e0e0e0", fontFamily: mono, marginBottom: "4px" }}>What do I believe?</div>
        <div style={{ fontSize: "11px", color: "#666", lineHeight: 1.5, maxWidth: "70ch" }}>
          Every belief wears its stance. A belief nobody has stood behind is capped at NOTE until you confirm it, so the machine's guesses never pass as your word. Confirming, rephrasing and retiring happen in the library's review page, under your own channel.
        </div>
      </div>
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
        {chip("all", "All", "#e0e0e0", status?.counts?.beliefs)}
        {chip("unreviewed", "Unreviewed", "#fbbf24", unreviewed)}
        {ORDER.map((st) => chip(st, st, STANCE[st], counts[st] || 0))}
      </div>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by claim or id…" style={{ width: "100%", background: "#0A0A0A", border: "1px solid #222", borderRadius: "3px", color: "#e0e0e0", padding: "9px 12px", fontSize: "12px", fontFamily: mono, outline: "none", boxSizing: "border-box" }} />
      {open && <BeliefDetail id={open} onClose={() => setOpen(null)} onSelectWorkspace={onSelectWorkspace} />}
      {!open && byStance.map(([st, xs]) => (
        <div key={st}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "6px" }}>
            <span style={{ color: STANCE[st], fontSize: "11px", letterSpacing: "1.5px", fontFamily: mono }}>{st}</span>
            <span style={{ color: "#555", fontSize: "10px" }}>{xs.length} · {GUIDE[st]}</span>
          </div>
          <div style={{ background: "#141414", border: "1px solid #222", borderRadius: "4px" }}>
            {xs.map((b) => <BeliefRow key={b.id} b={b} onOpen={setOpen} />)}
          </div>
        </div>
      ))}
      {!open && shown.length === 0 && <div style={{ fontSize: "11px", color: "#444", fontStyle: "italic" }}>Nothing matches.</div>}
    </div>
  );
}
