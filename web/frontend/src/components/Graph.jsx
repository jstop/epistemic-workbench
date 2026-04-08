import { useState, useRef, useEffect } from "react";
import * as d3 from "d3";

const EDGE_TYPES = {
  supports: { label: "supports", color: "#4ade80", dash: "none" },
  attacks: { label: "attacks", color: "#f87171", dash: "8,4" },
  assumes: { label: "assumes", color: "#fbbf24", dash: "4,4" },
};

const NODE_TYPES = {
  claim: { label: "Claim", color: "#60a5fa", symbol: "●" },
  evidence: { label: "Evidence", color: "#4ade80", symbol: "■" },
};

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

export default function Graph({ nodes, edges, selectedId, highlightIds, onSelectNode, onSelectDefeater }) {
  const svgRef = useRef(null);
  const simRef = useRef(null);
  const [, setTick] = useState(0);

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

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(validEdges).id((d) => d.id).distance(160).strength(0.3))
      .force("charge", d3.forceManyBody().strength(-500))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(55))
      .alphaDecay(0.02)
      .on("tick", () => {
        nodes.forEach((n) => {
          n.x = Math.max(50, Math.min(width - 50, n.x));
          n.y = Math.max(50, Math.min(height - 50, n.y));
        });
        setTick((t) => t + 1);
      });

    simRef.current = sim;
    return () => sim.stop();
  }, [nodes, edges]);

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
        const cfg = NODE_TYPES[node.type] || NODE_TYPES.claim;
        const isSelected = node.id === selectedId;
        const isHighlighted = highlightSet.has(node.id);
        const atmsColor = ATMS_BORDER[node.atms] || ATMS_BORDER.unknown;
        const radius = 20;
        const dimmed = highlightSet.size > 0 && !isHighlighted && !isSelected;

        return (
          <g
            key={node.id}
            style={{ cursor: "grab" }}
            opacity={dimmed ? 0.25 : 1}
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
            {/* Node body */}
            <circle
              cx={node.x} cy={node.y} r={radius}
              fill={isSelected ? cfg.color : "#1a1a1a"}
              stroke={isSelected ? "#fff" : cfg.color}
              strokeWidth={isSelected ? 2.5 : 1.5}
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
            {/* ATMS badge */}
            <text
              x={node.x} y={node.y - radius - 8}
              fill={atmsColor} fontSize="8" fontFamily="'JetBrains Mono', monospace"
              textAnchor="middle" opacity={0.6} style={{ pointerEvents: "none" }}
            >
              {node.atms}
            </text>
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
  );
}
