import { useState, useRef, useEffect } from "react";
import * as d3 from "d3";

export const EDGE_TYPES = {
  supports: { label: "supports", color: "#4ade80", dash: "none" },
  grounds: { label: "grounds", color: "#4ade80", dash: "2,3" },
  attacks: { label: "attacks", color: "#f87171", dash: "8,4" },
  refutes: { label: "refutes", color: "#f87171", dash: "8,4" },
  rebuts: { label: "rebuts", color: "#f87171", dash: "8,4" },
  concedes: { label: "concedes", color: "#fb923c", dash: "6,3" },
  narrows: { label: "narrows", color: "#a78bfa", dash: "3,3" },
  supersedes: { label: "supersedes", color: "#a78bfa", dash: "10,4" },
  assumes: { label: "assumes", color: "#fbbf24", dash: "4,4" },
};

// node.type is the storage kind (claim | evidence); node.node_type is the
// dialectical role (claim | thesis | objection | concession | evidence).
export const NODE_TYPES = {
  claim: { label: "Claim", color: "#60a5fa", symbol: "●" },
  thesis: { label: "Thesis", color: "#FF6B35", symbol: "◉" },
  objection: { label: "Objection", color: "#f87171", symbol: "◆" },
  concession: { label: "Concession", color: "#fb923c", symbol: "◇" },
  evidence: { label: "Evidence", color: "#4ade80", symbol: "■" },
};

const REJECTED = new Set(["superseded", "defeated", "rebutted", "conceded", "retired"]);

const ATMS_BORDER = {
  accepted: "#4ade80",
  provisional: "#fbbf24",
  defeated: "#f87171",
  unknown: "#555",
};

const DEFEATER_CHIP_COLORS = {
  active: "#f87171",
  conceded: "#fb923c",
  answered: "#4ade80",
  withdrawn: "#666",
};

const edgeSourceId = (e) => e.source.id || e.source;
const edgeTargetId = (e) => e.target.id || e.target;

// Layer assignment for the layered layout. Argument graphs are rooted DAGs:
// the thesis sits on top, its premises one layer down, their premises below,
// evidence at the bottom. Objections sit beside what they attack; superseded
// positions sit beside what replaced them.
function assignLayers(nodes, edges) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const layer = new Map();
  const roots = nodes.filter((n) => n.is_root || n.node_type === "thesis");
  const seeds = roots.length ? roots : nodes.filter((n) => !edges.some((e) => edgeSourceId(e) === n.id && (e.type === "supports" || e.type === "grounds")));
  const premisesOf = new Map();
  const attackersOf = new Map();
  const supersededBy = new Map();
  edges.forEach((e) => {
    const src = edgeSourceId(e), tgt = edgeTargetId(e);
    if (e.type === "supports" || e.type === "grounds" || e.type === "assumes") {
      if (!premisesOf.has(tgt)) premisesOf.set(tgt, []);
      premisesOf.get(tgt).push(src);
    } else if (e.type === "supersedes") {
      supersededBy.set(tgt, src);
    } else {
      if (!attackersOf.has(tgt)) attackersOf.set(tgt, []);
      attackersOf.get(tgt).push(src);
    }
  });
  const queue = seeds.map((n) => [n.id, 0]);
  while (queue.length) {
    const [id, d] = queue.shift();
    if (layer.has(id) && layer.get(id) >= d) continue;
    layer.set(id, d);
    (premisesOf.get(id) || []).forEach((p) => queue.push([p, d + 1]));
    (attackersOf.get(id) || []).forEach((a) => queue.push([a, d]));
  }
  supersededBy.forEach((newer, older) => { if (layer.has(newer) && !layer.has(older)) layer.set(older, layer.get(newer)); });
  let maxLayer = 0;
  layer.forEach((d) => { if (d > maxLayer) maxLayer = d; });
  nodes.forEach((n) => {
    if (!layer.has(n.id)) layer.set(n.id, n.type === "evidence" ? maxLayer + 1 : maxLayer);
  });
  // Evidence never sits above the claims it grounds; push it to the bottom band.
  let deepest = 0;
  layer.forEach((d) => { if (d > deepest) deepest = d; });
  nodes.forEach((n) => { if (n.type === "evidence") layer.set(n.id, Math.max(layer.get(n.id), deepest)); });
  return layer;
}

export default function Graph({ nodes, edges, selectedId, highlightIds, onSelectNode, onSelectDefeater }) {
  const svgRef = useRef(null);
  const simRef = useRef(null);
  const [, setTick] = useState(0);
  const [layout, setLayout] = useState(() => {
    try { return localStorage.getItem("epist.graph.layout") || "layered"; } catch { return "layered"; }
  });
  useEffect(() => { try { localStorage.setItem("epist.graph.layout", layout); } catch { /* ignore */ } }, [layout]);

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;
    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    // Assign initial positions so nothing starts at NaN
    const nodeIds = new Set(nodes.map((n) => n.id));
    nodes.forEach((n) => {
      if (n.x == null || isNaN(n.x)) n.x = width / 2 + (Math.random() - 0.5) * 200;
      if (n.y == null || isNaN(n.y)) n.y = height / 2 + (Math.random() - 0.5) * 200;
    });

    // Filter edges to only those whose source and target are actual nodes
    const validEdges = edges.filter((e) => {
      const src = e.source?.id || e.source;
      const tgt = e.target?.id || e.target;
      return nodeIds.has(src) && nodeIds.has(tgt);
    });

    if (simRef.current) simRef.current.stop();

    let sim;
    if (layout === "layered") {
      const layers = assignLayers(nodes, validEdges);
      let deepest = 0;
      layers.forEach((d) => { if (d > deepest) deepest = d; });
      const bandH = Math.max(120, Math.min(180, (height - 140) / (deepest + 1)));
      const top = 80;
      const yOf = (id) => top + (layers.get(id) || 0) * bandH;
      // Spread each band evenly across the width, keeping a node near the
      // nodes it connects to: order a band by the mean x-slot of its
      // neighbours in the band above (barycenter), thesis in the middle.
      const bands = new Map();
      nodes.forEach((n) => { const d = layers.get(n.id) || 0; if (!bands.has(d)) bands.set(d, []); bands.get(d).push(n); });
      const slot = new Map();
      const neighbours = new Map();
      validEdges.forEach((e) => {
        const a = edgeSourceId(e), b = edgeTargetId(e);
        if (!neighbours.has(a)) neighbours.set(a, []); neighbours.get(a).push(b);
        if (!neighbours.has(b)) neighbours.set(b, []); neighbours.get(b).push(a);
      });
      [...bands.keys()].sort((a, b) => a - b).forEach((d) => {
        const band = bands.get(d);
        const key = (n) => {
          const above = (neighbours.get(n.id) || []).filter((m) => slot.has(m)).map((m) => slot.get(m));
          if (above.length) return above.reduce((x, y) => x + y, 0) / above.length;
          return n.is_root || n.node_type === "thesis" ? 0.5 : 0.5 + (n.node_type === "objection" ? 0.2 : n.node_type === "concession" ? 0.3 : n.status ? -0.3 : 0);
        };
        band.map((n) => [n, key(n)]).sort((a, b) => a[1] - b[1]).forEach(([n], i) => slot.set(n.id, (i + 1) / (band.length + 1)));
      });
      const margin = 90;
      const xOf = (id) => margin + (slot.get(id) ?? 0.5) * (width - 2 * margin);
      // Release pins from a previous free-layout drag so the bands can take over.
      nodes.forEach((n) => { n.fy = null; n.fx = null; });
      sim = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(validEdges).id((d) => d.id).distance(110).strength(0.05))
        .force("charge", d3.forceManyBody().strength(-120))
        .force("x", d3.forceX((d) => xOf(d.id)).strength(0.6))
        .force("y", d3.forceY((d) => yOf(d.id)).strength(1))
        .force("collision", d3.forceCollide().radius(70))
        .alphaDecay(0.04);
    } else {
      sim = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(validEdges).id((d) => d.id).distance(160).strength(0.3))
        .force("charge", d3.forceManyBody().strength(-500))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide().radius(55))
        .alphaDecay(0.02);
    }
    sim
      .on("tick", () => {
        nodes.forEach((n) => {
          n.x = Math.max(50, Math.min(width - 50, n.x));
          n.y = Math.max(50, Math.min(height - 50, n.y));
        });
        setTick((t) => t + 1);
      });

    simRef.current = sim;
    return () => sim.stop();
  }, [nodes, edges, layout]);

  const handleDragStart = (e, node) => {
    const sim = simRef.current;
    if (!sim) return;
    sim.alphaTarget(0.1).restart();
    node.fx = node.x;
    node.fy = node.y;
    const onMove = (ev) => {
      const rect = svgRef.current.getBoundingClientRect();
      node.fx = ev.clientX - rect.left;
      node.fy = ev.clientY - rect.top;
    };
    const onUp = () => {
      sim.alphaTarget(0);
      node.fx = null;
      node.fy = null;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  const highlightSet = new Set(highlightIds || []);

  return (
    <>
    <div style={{ position: "absolute", top: "10px", right: "12px", display: "flex", gap: "2px", zIndex: 2 }}>
      {["layered", "free"].map((m) => (
        <button key={m} onClick={() => setLayout(m)} style={{
          background: layout === m ? "#FF6B3522" : "#141414",
          border: `1px solid ${layout === m ? "#FF6B35" : "#222"}`,
          color: layout === m ? "#FF6B35" : "#666", padding: "4px 8px", borderRadius: "3px",
          fontSize: "9px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
          letterSpacing: "1px", textTransform: "uppercase",
        }}>{m}</button>
      ))}
    </div>
    <svg ref={svgRef} style={{ width: "100%", height: "100%", background: "transparent" }}>
      <defs>
        {Object.entries(EDGE_TYPES).map(([key, cfg]) => (
          <marker key={key} id={`arrow-${key}`} viewBox="0 0 10 6" refX="30" refY="3" markerWidth="8" markerHeight="6" orient="auto">
            <path d={`M0,0 L10,3 L0,6 Z`} fill={cfg.color} />
          </marker>
        ))}
      </defs>

      {/* Edges */}
      {edges.map((e, i) => {
        const src = nodes.find((n) => n.id === edgeSourceId(e));
        const tgt = nodes.find((n) => n.id === edgeTargetId(e));
        if (!src || !tgt || isNaN(src.x) || isNaN(tgt.x)) return null;
        const cfg = EDGE_TYPES[e.type] || EDGE_TYPES.supports;
        return (
          <g key={`${edgeSourceId(e)}-${edgeTargetId(e)}-${i}`}>
            <line
              x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
              stroke={cfg.color} strokeWidth={1.5} strokeDasharray={cfg.dash}
              markerEnd={`url(#arrow-${e.type})`} opacity={0.7}
            />
            <text
              x={(src.x + tgt.x) / 2} y={(src.y + tgt.y) / 2 - 8}
              fill={cfg.color} fontSize="9" fontFamily="'JetBrains Mono', monospace"
              textAnchor="middle" opacity={0.5}
            >
              {e.label ? (e.label.length > 30 ? e.label.slice(0, 28) + "…" : e.label) : cfg.label}
            </text>
          </g>
        );
      })}

      {/* Nodes */}
      {nodes.map((node) => {
        const role = node.node_type || (node.is_root ? "thesis" : node.type);
        const cfg = NODE_TYPES[role] || NODE_TYPES[node.type] || NODE_TYPES.claim;
        const isSelected = node.id === selectedId;
        const isHighlighted = highlightSet.has(node.id);
        const atmsColor = ATMS_BORDER[node.atms] || ATMS_BORDER.unknown;
        const radius = 20;
        const rejected = REJECTED.has(node.status);
        const asserted = node.type === "evidence" && node.provenance !== "recorded";
        const dimmed = (highlightSet.size > 0 && !isHighlighted && !isSelected) || (rejected && !isSelected);

        return (
          <g
            key={node.id}
            style={{ cursor: "grab" }}
            opacity={dimmed ? (rejected ? 0.4 : 0.25) : 1}
            onMouseDown={(ev) => handleDragStart(ev, node)}
            onClick={(ev) => { ev.stopPropagation(); onSelectNode(node.id); }}
          >
            {/* ATMS status ring */}
            <circle cx={node.x} cy={node.y} r={radius + 5} fill="none" stroke={atmsColor} strokeWidth={1.5} opacity={0.5} />
            {/* Confidence arc */}
            <circle
              cx={node.x} cy={node.y} r={radius + 5}
              fill="none" stroke={atmsColor} strokeWidth={2.5}
              strokeDasharray={`${node.confidence * 2 * Math.PI * (radius + 5)} ${2 * Math.PI * (radius + 5)}`}
              transform={`rotate(-90 ${node.x} ${node.y})`}
              opacity={0.7}
            />
            {/* Node body — asserted (unsourced) evidence gets a dashed outline */}
            <circle
              cx={node.x} cy={node.y} r={radius}
              fill={isSelected ? cfg.color : "#1a1a1a"}
              stroke={isSelected ? "#fff" : cfg.color}
              strokeWidth={isSelected ? 2.5 : 1.5}
              strokeDasharray={asserted ? "3,3" : "none"}
            />
            {/* Defeated X overlay */}
            {node.atms === "defeated" && (
              <>
                <line x1={node.x - 7} y1={node.y - 7} x2={node.x + 7} y2={node.y + 7} stroke="#f87171" strokeWidth={2} opacity={0.8} />
                <line x1={node.x + 7} y1={node.y - 7} x2={node.x - 7} y2={node.y + 7} stroke="#f87171" strokeWidth={2} opacity={0.8} />
              </>
            )}
            {/* Type symbol */}
            <text
              x={node.x} y={node.y + 1}
              fill={isSelected ? "#0A0A0A" : cfg.color}
              fontSize="13" fontFamily="'JetBrains Mono', monospace"
              textAnchor="middle" dominantBaseline="middle"
              style={{ pointerEvents: "none" }}
            >
              {cfg.symbol}
            </text>
            {/* Label */}
            <text
              x={node.x} y={node.y + radius + 16}
              fill="#a0a0a0" fontSize="10" fontFamily="'JetBrains Mono', monospace"
              textAnchor="middle" style={{ pointerEvents: "none" }}
            >
              {node.label.length > 28 ? node.label.slice(0, 26) + "…" : node.label}
            </text>
            {/* ATMS badge (+ stored status when it has been overridden) */}
            <text
              x={node.x} y={node.y - radius - 8}
              fill={rejected ? "#a78bfa" : atmsColor} fontSize="8" fontFamily="'JetBrains Mono', monospace"
              textAnchor="middle" opacity={0.7} style={{ pointerEvents: "none" }}
            >
              {rejected ? node.status : node.atms}
            </text>
            {/* Derived confidence, when propagation moved it from the stored value */}
            {node.derived != null && Math.abs(node.derived - node.confidence) >= 0.05 && (
              <text
                x={node.x + radius + 6} y={node.y - radius + 2}
                fill="#FF6B35" fontSize="8" fontFamily="'JetBrains Mono', monospace"
                textAnchor="start" opacity={0.8} style={{ pointerEvents: "none" }}
              >
                {`→${Math.round(node.derived * 100)}%`}
              </text>
            )}
            {/* Per-defeater chips below the label */}
            {(node.defeaters || []).slice(0, 5).map((d, i) => {
              const color = DEFEATER_CHIP_COLORS[d.status] || "#666";
              const chipW = 12;
              const gap = 3;
              const total = Math.min(node.defeaters.length, 5);
              const startX = node.x - (total * (chipW + gap) - gap) / 2;
              const cx = startX + i * (chipW + gap);
              const cy = node.y + radius + 22;
              return (
                <g
                  key={`${d.argument_id}-${d.index}`}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    if (onSelectDefeater) onSelectDefeater(d);
                  }}
                  style={{ cursor: "pointer" }}
                >
                  <rect
                    x={cx} y={cy}
                    width={chipW} height={6}
                    rx={1.5}
                    fill={color}
                    opacity={d.status === "active" ? 0.95 : 0.7}
                    stroke={d.status === "active" ? "#fff" : "none"}
                    strokeWidth={d.status === "active" ? 0.5 : 0}
                  >
                    <title>{`[${d.status}] ${d.type}: ${d.description}`}</title>
                  </rect>
                </g>
              );
            })}
            {node.defeaters && node.defeaters.length > 5 && (
              <text
                x={node.x + 40} y={node.y + radius + 28}
                fill="#888" fontSize="8" fontFamily="'JetBrains Mono', monospace"
                style={{ pointerEvents: "none" }}
              >
                +{node.defeaters.length - 5}
              </text>
            )}
          </g>
        );
      })}
    </svg>
    </>
  );
}
