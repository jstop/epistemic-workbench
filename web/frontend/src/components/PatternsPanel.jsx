const mono = "'JetBrains Mono', monospace";

// Where do people disagree. The mapper answers this for public discourse; it
// is dormant since January and joins under the interpreter contract when it
// is next worked on. Shown, not hidden, so the fourth question stays asked.
export default function PatternsPanel() {
  return (
    <div style={{ maxWidth: "70ch", display: "flex", flexDirection: "column", gap: "10px" }}>
      <div style={{ fontSize: "20px", color: "#e0e0e0", fontFamily: mono }}>Where do people disagree?</div>
      <div style={{ fontSize: "11px", color: "#666", lineHeight: 1.6 }}>
        This lens is reserved for the epistemic mapper: typed atoms extracted from public discussions and the forks where positions split, with the shared ground between them. The mapper has had no development since January 2026 and is not wired into the substrate. When it is next worked on it joins under the same contract as the workbench: read evidence from the library, write interpretations back with run identity, never write beliefs directly.
      </div>
      <div style={{ fontSize: "10px", color: "#444", fontFamily: mono }}>~/workspace/epistemic/mapper · VISION.md · PATTERN-LIBRARY.md</div>
    </div>
  );
}
