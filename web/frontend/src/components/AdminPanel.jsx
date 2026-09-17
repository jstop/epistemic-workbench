import { useState, useEffect } from "react";
import * as api from "../api.js";

// Admin: the operational side of a corrigible system, in one place.
// Builds (branches, gate, rebuild, promote), scheduled jobs (backup, archive,
// gate) with their last outcomes and a run-now, what each Claude surface is
// wired to, the source archive, and the library's health and authorship
// census. Nothing here is hidden behind a terminal any more; the one thing
// that stays terminal-only is the attribution correction, because the library
// refuses it from any channel but the owner's.

const mono = "'JetBrains Mono', monospace";
const label = { fontSize: "9px", color: "#555", letterSpacing: "1px", textTransform: "uppercase" };
const box = { background: "#141414", border: "1px solid #222", borderRadius: "4px", padding: "12px 14px" };
const btn = (color = "#888", solid = false) => ({
  background: solid ? color : "transparent", border: `1px solid ${solid ? color : "#333"}`, color: solid ? "#0A0A0A" : color,
  borderRadius: "3px", padding: "5px 10px", fontSize: "9.5px", cursor: "pointer", fontFamily: mono, letterSpacing: "1px", textTransform: "uppercase",
});

function Section({ title, hint, children, right }) {
  return (
    <div style={box}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "10px", marginBottom: "10px" }}>
        <span style={{ fontSize: "12px", color: "#e0e0e0", letterSpacing: "1px" }}>{title}</span>
        {hint && <span style={{ fontSize: "10px", color: "#555" }}>{hint}</span>}
        {right && <div style={{ marginLeft: "auto" }}>{right}</div>}
      </div>
      {children}
    </div>
  );
}

export default function AdminPanel({ onChanged }) {
  const [o, setO] = useState(null);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const [result, setResult] = useState(null);
  const [rebuildName, setRebuildName] = useState("dev");

  const load = () => api.adminOverview().then(setO).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, []);

  const act = async (name, fn) => {
    setBusy(name); setMsg(null); setResult(null);
    try {
      const r = await fn();
      setResult({ name, r });
      setMsg(`${name}: done`);
      load(); if (onChanged) onChanged();
    } catch (e) { setMsg(`${name}: ${e.message}`); }
    finally { setBusy(null); }
  };

  if (!o) return <div style={{ color: "#555", fontSize: "10px" }}>{msg || "Loading…"}</div>;
  const served = o.served_branch;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "14px", maxWidth: "980px" }}>
      <div>
        <div style={{ fontSize: "20px", color: "#e0e0e0", fontFamily: mono, marginBottom: "4px" }}>Admin</div>
        <div style={{ fontSize: "11px", color: "#666", lineHeight: 1.5, maxWidth: "76ch" }}>
          The operational side: builds and the gate, the scheduled jobs and whether they ran, what each Claude surface is wired to, the source archive, and the library's health. This app writes as <span style={{ color: "#aaa" }}>{o.writes_as}</span> and is reading build <span style={{ color: served === "main" ? "#4ade80" : "#a78bfa" }}>{served}</span>.
        </div>
      </div>
      {msg && <div style={{ fontSize: "10px", color: msg.includes("done") ? "#4ade80" : "#f87171", fontFamily: mono }}>{msg}{busy ? " …" : ""}</div>}

      <Section title="Builds" hint="the library is a build artifact; main is served, branches are where change happens"
        right={<div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          <input value={rebuildName} onChange={(e) => setRebuildName(e.target.value)} style={{ width: "80px", background: "#0A0A0A", border: "1px solid #222", color: "#e0e0e0", fontSize: "10px", fontFamily: mono, padding: "4px 6px", borderRadius: "3px" }} />
          <button disabled={!!busy || rebuildName === "main"} onClick={() => act(`rebuild ${rebuildName}`, () => api.adminRebuild(rebuildName))} style={btn("#a78bfa")}>Rebuild from main</button>
        </div>}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "10.5px" }}>
          <thead><tr style={{ color: "#555" }}>{["build", "events", "beliefs", "interpretations", "runs", "last gate", "last event", ""].map((h) => <th key={h} style={{ textAlign: "left", fontWeight: 400, padding: "4px 8px 6px 0", ...label }}>{h}</th>)}</tr></thead>
          <tbody>
            {o.builds.map((b) => {
              const g = b.last_gate;
              return (
                <tr key={b.name} style={{ borderTop: "1px solid #1f1f1f" }}>
                  <td style={{ padding: "7px 8px 7px 0", color: b.name === "main" ? "#4ade80" : "#a78bfa" }}>{b.name}{b.served ? <span style={{ color: "#555" }}> · served here</span> : ""}</td>
                  <td style={{ color: "#aaa" }}>{b.events ?? "—"}</td><td style={{ color: "#aaa" }}>{b.beliefs ?? "—"}</td>
                  <td style={{ color: "#aaa" }}>{b.interpretations ?? "—"}</td><td style={{ color: "#aaa" }}>{b.runs ?? "—"}</td>
                  <td style={{ color: !g ? "#555" : g.ok ? "#4ade80" : "#f87171" }}>{!g ? "never" : `${g.ok ? "passed" : "FAILED"} ${(g.recorded_at || "").slice(0, 16).replace("T", " ")}`}{g?.unreviewed != null ? <span style={{ color: "#555" }}> · {g.unreviewed} unreviewed</span> : null}</td>
                  <td style={{ color: "#555" }}>{(b.last_event_at || "").slice(0, 16).replace("T", " ")}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <div style={{ display: "flex", gap: "4px", justifyContent: "flex-end" }}>
                      <button disabled={!!busy} onClick={() => act(`gate ${b.name}`, () => api.adminCheck(b.name))} style={btn("#60a5fa")}>Run gate</button>
                      <button disabled={!!busy} onClick={() => act(`project ${b.name}`, () => api.adminProject(b.name))} style={btn()}>Reproject</button>
                      {b.name !== "main" && (
                        <button disabled={!!busy || !(g && g.ok)} title={g && g.ok ? "Replace main's database with this branch's (main is backed up first)" : "Needs a passing gate run first"}
                          onClick={() => { if (confirm(`Promote ${b.name} to main? Main's current database is backed up under builds/_backups first, and the promotion is recorded as a run.`)) act(`promote ${b.name}`, () => api.adminPromote(b.name)); }}
                          style={btn("#FF6B35", !!(g && g.ok))}>Promote</button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Section>

      <Section title="Scheduled jobs" hint="launchd · a run's last line is shown; silence is never success">
        {o.jobs.map((j) => {
          const ok = j.last_exit === "0";
          return (
            <div key={j.key} style={{ display: "grid", gridTemplateColumns: "90px 1fr auto", gap: "10px", alignItems: "start", padding: "7px 0", borderTop: "1px solid #1f1f1f", fontSize: "10.5px" }}>
              <div><div style={{ color: "#e0e0e0" }}>{j.key}</div><div style={{ color: "#555", fontSize: "9px" }}>{j.when}</div></div>
              <div>
                <div style={{ color: "#888" }}>{j.what}</div>
                <div style={{ color: ok ? "#4ade80" : j.loaded ? "#f87171" : "#fbbf24", fontFamily: mono, fontSize: "9.5px", marginTop: "3px" }}>
                  {!j.loaded ? "not loaded in launchd" : `last exit ${j.last_exit ?? "?"} · ${j.runs ?? "?"} runs · ${j.state ?? ""}`}
                </div>
                {j.last_line && <div style={{ color: "#666", fontFamily: mono, fontSize: "9px", marginTop: "2px", wordBreak: "break-all" }}>{j.last_line}</div>}
              </div>
              <button disabled={!!busy} onClick={() => act(`run ${j.key}`, () => api.adminRunJob(j.key))} style={btn()}>Run now</button>
            </div>
          );
        })}
      </Section>

      <Section title="Servers" hint="what each Claude surface is wired to">
        {Object.entries(o.servers).map(([surface, list]) => (
          <div key={surface} style={{ marginBottom: "8px" }}>
            <div style={{ ...label, marginBottom: "4px" }}>{surface.replace("_", " ")}</div>
            {list.filter((s) => s.epistemic).map((s) => (
              <div key={s.name} style={{ display: "flex", gap: "12px", fontSize: "10.5px", padding: "3px 0", alignItems: "baseline" }}>
                <span style={{ color: s.name.startsWith("episteme") ? "#FF6B35" : "#aaa", width: "180px" }}>{s.name}</span>
                <span style={{ color: s.branch === "main" ? "#4ade80" : "#a78bfa", width: "60px" }}>{s.branch}</span>
                <span style={{ color: "#666" }}>{s.agent ? `agent:${s.agent}` : <span style={{ color: "#fbbf24" }}>no agent named → agent:unknown</span>}</span>
                <span style={{ color: "#444", fontFamily: mono, fontSize: "9px", marginLeft: "auto" }}>{(s.script || "").replace("/Users/jstein/workspace/", "~/workspace/")}</span>
              </div>
            ))}
            {list.filter((s) => s.epistemic).length === 0 && <div style={{ fontSize: "10px", color: "#444", fontStyle: "italic" }}>none</div>}
          </div>
        ))}
        <div style={{ fontSize: "9.5px", color: "#555", marginTop: "4px" }}>At promotion: point episteme at main, remove the per-system servers. Restart the app for config changes to load.</div>
      </Section>

      <Section title="Source archive" hint={`s3://${o.archive.bucket} · ${o.archive.manifest_rows} manifest rows`}>
        {o.archive.latest.map((r) => (
          <div key={r.s3_key} style={{ display: "flex", gap: "10px", fontSize: "10px", padding: "3px 0", borderTop: "1px solid #1a1a1a", alignItems: "baseline" }}>
            <span style={{ color: "#555", width: "150px", flexShrink: 0 }}>{(r.archived_at || "").slice(0, 16).replace("T", " ")}</span>
            <span style={{ color: r.kind === "human-input" ? "#4ade80" : r.kind === "derived" ? "#fb923c" : "#60a5fa", width: "84px", flexShrink: 0 }}>{r.kind}</span>
            <span style={{ color: "#bbb", flex: 1, wordBreak: "break-all" }}>{r.s3_key}</span>
            <span style={{ color: "#555", flexShrink: 0 }}>{Number(r.bytes || 0) >= 1e6 ? `${(Number(r.bytes) / 1e6).toFixed(1)} MB` : `${r.bytes} B`}</span>
          </div>
        ))}
        {o.archive.recent_commits.length > 0 && <div style={{ fontSize: "9px", color: "#555", marginTop: "6px", fontFamily: mono }}>{o.archive.recent_commits.join(" · ")}</div>}
      </Section>

      {o.health && o.health.total != null && (
        <Section title="Library health" hint={`${o.health.total} beliefs · chain ${o.health.chain_valid ? "valid" : "BROKEN"}`}>
          <div style={{ display: "flex", gap: "16px", fontSize: "10.5px", marginBottom: "8px" }}>
            {Object.entries(o.health.by_stance || {}).map(([k, v]) => <span key={k}><span style={{ color: "#888" }}>{k}</span> <span style={{ color: "#e0e0e0" }}>{v}</span></span>)}
          </div>
          {o.health.authorship && (
            <div style={{ fontSize: "10px", color: "#888", lineHeight: 1.6 }}>
              <div style={{ ...label, marginBottom: "3px" }}>Authorship census</div>
              beliefs by composer: {Object.entries(o.health.authorship.beliefs_by_composer || {}).map(([k, v]) => `${k} ${v}`).join(" · ")}<br />
              stood behind by owner: {o.health.authorship.stood_behind_by_owner} · events by recorded actor: {Object.entries(o.health.authorship.events_by_recorded_actor || {}).map(([k, v]) => `${k} ${v}`).join(" · ")}<br />
              attribution corrections: {(o.health.authorship.attribution_corrections || []).length}
              {(o.health.authorship.attribution_corrections || []).length === 0 && (
                <div style={{ marginTop: "6px", padding: "8px 10px", background: "#0A0A0A", borderLeft: "3px solid #fbbf24", color: "#aaa" }}>
                  Events 39–2695 are recorded as <span style={{ color: "#e0e0e0" }}>owner</span> from before actors were channel-derived; all but event 1403 were Claude Code. The correction is refused from any channel but yours, so it runs from your terminal:
                  <pre style={{ margin: "6px 0 0", fontSize: "9px", color: "#888", whiteSpace: "pre-wrap" }}>{`cd ~/workspace/epistemic/memory && source ~/python/global/bin/activate
python engine.py correct-attribution --from 39 --through 1402 --recorded owner --actual agent:claude-code --reason "backlog ingestion via MCP before actors were channel-derived"
python engine.py correct-attribution --from 1404 --through 2695 --recorded owner --actual agent:claude-code --reason "backlog ingestion via MCP before actors were channel-derived"`}</pre>
                </div>
              )}
            </div>
          )}
          {o.health.needs_attention?.length > 0 && (
            <div style={{ marginTop: "8px" }}>
              <div style={{ ...label, marginBottom: "3px" }}>Needs attention ({o.health.needs_attention.length})</div>
              <div style={{ fontSize: "9.5px", color: "#777", lineHeight: 1.6 }}>{o.health.needs_attention.map((n) => `${n.id} (${n.stance})`).join(" · ")}</div>
            </div>
          )}
        </Section>
      )}

      {result && (
        <Section title={`Result · ${result.name}`}>
          <pre style={{ margin: 0, fontSize: "9.5px", color: "#999", whiteSpace: "pre-wrap", maxHeight: "300px", overflow: "auto" }}>{JSON.stringify(result.r, null, 1)}</pre>
        </Section>
      )}
    </div>
  );
}
