import { useState, useEffect } from "react";
import * as api from "../api.js";

// Always-visible state of a corrigible system: which build is being read,
// what the nightly gate last said, how much of the library nobody has stood
// behind yet, and what this channel writes as. If any of these is wrong, you
// should see it before you read anything else.

const mono = "'JetBrains Mono', monospace";

function Chip({ color, label, value, title }) {
  return (
    <span title={title} style={{ display: "inline-flex", alignItems: "baseline", gap: "5px", fontSize: "10px", fontFamily: mono }}>
      <span style={{ color: "#555", letterSpacing: "1px", textTransform: "uppercase", fontSize: "8.5px" }}>{label}</span>
      <span style={{ color }}>{value}</span>
    </span>
  );
}

export default function StatusStrip({ refreshKey, onGoto }) {
  const [s, setS] = useState(null);
  useEffect(() => { api.libraryStatus().then(setS).catch(() => setS({ available: false })); }, [refreshKey]);
  if (!s) return null;
  if (!s.available) return <Chip color="#f87171" label="library" value="unavailable" title={s.reason || ""} />;
  const c = s.counts || {};
  const g = s.last_gate;
  const gateColor = !g ? "#555" : g.ok ? "#4ade80" : "#f87171";
  const gateText = !g ? "never run" : `${g.ok ? "passed" : "FAILED"} ${(g.recorded_at || "").slice(0, 10)}`;
  return (
    <div style={{ display: "flex", gap: "18px", alignItems: "baseline", flexWrap: "wrap" }}>
      <Chip color={s.branch === "main" ? "#4ade80" : "#a78bfa"} label="build" value={s.branch} title={s.db} />
      <Chip color={gateColor} label="gate" value={gateText} title={g ? `anchors failed: ${g.anchors_failed ?? 0}` : "run: make check"} />
      <span onClick={() => onGoto && onGoto("believe", "unreviewed")} style={{ cursor: "pointer" }}>
        <Chip color={c.unreviewed > 0 ? "#fbbf24" : "#4ade80"} label="unreviewed" value={`${c.unreviewed ?? 0} / ${c.beliefs ?? 0}`} title="beliefs no person has stood behind — capped at NOTE" />
      </span>
      <Chip color="#666" label="writes as" value={s.writes_as} title="the channel this app writes to the library as" />
      <Chip color="#444" label="code" value={`${(s.library_code || "").slice(0, 7)} · ${(s.workbench_code || "").slice(0, 7)}`} title={`library ${s.library_code} · workbench ${s.workbench_code}`} />
    </div>
  );
}
