import { useState } from "react";
import * as api from "../api.js";

/**
 * Decompose a natural language sentence into subject/predicate/object.
 * The full text is always preserved in notes.
 */
function decompose(text) {
  const t = text.trim();
  // Try splitting on common verb phrases
  const verbs = [
    " are caused by ", " is caused by ", " are ", " is ",
    " requires ", " require ", " prevents ", " prevent ",
    " enables ", " enable ", " leads to ", " lead to ",
    " should ", " can ", " cannot ", " will ", " has ", " have ",
    " depends on ", " results from ", " implies ", " means ",
  ];
  for (const v of verbs) {
    const idx = t.toLowerCase().indexOf(v);
    if (idx > 0) {
      return {
        subject: t.slice(0, idx).trim().toLowerCase().replace(/\s+/g, "-"),
        predicate: v.trim().toLowerCase().replace(/\s+/g, "-"),
        object: t.slice(idx + v.length).trim().toLowerCase().replace(/\s+/g, "-"),
      };
    }
  }
  // Fallback: first few words as subject
  const words = t.split(/\s+/);
  if (words.length >= 3) {
    return {
      subject: words.slice(0, 2).join("-").toLowerCase(),
      predicate: "relates-to",
      object: words.slice(2).join("-").toLowerCase(),
    };
  }
  return { subject: t.toLowerCase().replace(/\s+/g, "-"), predicate: "is", object: "true" };
}

const STEPS = [
  {
    prompt: "What are you reasoning about?",
    sub: "State a thesis, question, or claim you want to examine.",
    placeholder: "e.g. Coordination failures are fundamentally epistemological",
  },
  {
    prompt: "What's your strongest reason for believing this?",
    sub: "What claim or argument supports your thesis?",
    placeholder: "e.g. Coordination requires shared facts, and shared facts require epistemic infrastructure",
  },
  {
    prompt: "What evidence supports that reasoning?",
    sub: "Concrete data, studies, observations, or experiences.",
    placeholder: "e.g. Only 36% of psychology studies replicate (Open Science Collaboration, 2015)",
  },
  {
    prompt: "What are you assuming that you haven't examined?",
    sub: "What unstated premise is your argument resting on?",
    placeholder: "e.g. People actually want to coordinate rather than compete",
  },
  {
    prompt: "What would change your mind?",
    sub: "If this objection held up, would you abandon your thesis?",
    placeholder: "e.g. Evidence that coordination failures are primarily caused by misaligned incentives, not epistemic gaps",
  },
];

export default function GuidedFlow({ onAdded, onComplete }) {
  const [step, setStep] = useState(0);
  const [input, setInput] = useState("");
  const [creating, setCreating] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState(null);

  // Track created IDs for wiring
  const [thesisId, setThesisId] = useState(null);
  const [reasonId, setReasonId] = useState(null);
  const [mainArgId, setMainArgId] = useState(null);

  const canSubmit = input.trim().length > 0;

  const handleAutoGenerate = async () => {
    if (!canSubmit || generating) return;
    setGenerating(true);
    setGenError(null);
    try {
      await api.generate(input.trim());
      onAdded();
      onComplete();
    } catch (err) {
      console.error("Auto-generate error:", err);
      setGenError(err.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const handleSubmit = async () => {
    if (!canSubmit || creating) return;
    setCreating(true);
    const text = input.trim();

    try {
      if (step === 0) {
        // Create thesis claim
        const spo = decompose(text);
        const c = await api.createClaim({
          subject: spo.subject, predicate: spo.predicate, object: spo.object,
          confidence: 0.7, modality: "empirical", notes: text,
        });
        setThesisId(c.id);
      } else if (step === 1) {
        // Create supporting claim + argument linking to thesis
        const spo = decompose(text);
        const c = await api.createClaim({
          subject: spo.subject, predicate: spo.predicate, object: spo.object,
          confidence: 0.7, modality: "empirical", notes: text,
        });
        setReasonId(c.id);
        if (thesisId) {
          const a = await api.createArgument({
            conclusion: thesisId, premises: [c.id],
            pattern: "abduction", label: text.slice(0, 60), confidence: 0.7,
          });
          setMainArgId(a.id);
        }
      } else if (step === 2) {
        // Create evidence + argument linking to reason
        const title = text.length > 60 ? text.slice(0, 58) + "…" : text;
        const e = await api.createEvidence({
          title, description: text,
          evidence_type: "observation", reliability: 0.7,
        });
        const target = reasonId || thesisId;
        if (target) {
          await api.createArgument({
            conclusion: target, premises: [e.id],
            pattern: "induction", label: `Evidence: ${title.slice(0, 40)}`, confidence: 0.7,
          });
        }
      } else if (step === 3) {
        // Create assumption claim + link via assumes
        const spo = decompose(text);
        const c = await api.createClaim({
          subject: spo.subject, predicate: spo.predicate, object: spo.object,
          confidence: 0.5, modality: "empirical", notes: `Assumption: ${text}`,
        });
        if (thesisId) {
          await api.updateClaim(thesisId, { assumes: [c.id] });
        }
      } else if (step === 4) {
        // Create defeater on the main argument
        const argTarget = mainArgId;
        if (argTarget) {
          await api.addDefeater(argTarget, { type: "rebutting", description: text });
        }
      }
    } catch (err) {
      console.error("Guided flow error:", err);
    }

    setCreating(false);
    setInput("");
    onAdded();

    if (step < STEPS.length - 1) {
      setStep(step + 1);
    } else {
      onComplete();
    }
  };

  const handleSkip = () => {
    setInput("");
    if (step < STEPS.length - 1) {
      setStep(step + 1);
    } else {
      onComplete();
    }
  };

  const stepInfo = STEPS[step];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", justifyContent: "center" }}>
      {/* Progress dots */}
      <div style={{ display: "flex", gap: "6px", justifyContent: "center", marginBottom: "24px" }}>
        {STEPS.map((_, i) => (
          <div key={i} style={{
            width: "8px", height: "8px", borderRadius: "50%",
            background: i === step ? "#FF6B35" : i < step ? "#4ade80" : "#333",
          }} />
        ))}
      </div>

      {/* Step number */}
      <div style={{ fontSize: "9px", color: "#555", letterSpacing: "2px", textTransform: "uppercase", textAlign: "center", marginBottom: "8px" }}>
        Step {step + 1} of {STEPS.length}
      </div>

      {/* Prompt */}
      <div style={{ fontSize: "14px", color: "#e0e0e0", textAlign: "center", marginBottom: "6px", fontWeight: 300 }}>
        {stepInfo.prompt}
      </div>
      <div style={{ fontSize: "10px", color: "#555", textAlign: "center", marginBottom: "20px", lineHeight: "1.5" }}>
        {stepInfo.sub}
      </div>

      {/* Input */}
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); } }}
        placeholder={stepInfo.placeholder}
        rows={3}
        autoFocus
        style={{
          width: "100%", background: "#141414", border: "1px solid #222",
          borderRadius: "4px", color: "#e0e0e0", padding: "12px 14px",
          fontSize: "12px", fontFamily: "'JetBrains Mono', monospace",
          outline: "none", resize: "none", boxSizing: "border-box",
          lineHeight: "1.5",
        }}
      />

      {/* Auto-generate option on step 0 */}
      {step === 0 && (
        <>
          <button
            onClick={handleAutoGenerate}
            disabled={!canSubmit || generating}
            style={{
              width: "100%", marginTop: "12px",
              background: canSubmit ? "#FF6B35" : "#222",
              color: canSubmit ? "#0A0A0A" : "#555",
              border: "none", borderRadius: "3px", padding: "12px",
              fontSize: "11px", cursor: canSubmit ? "pointer" : "default",
              fontFamily: "'JetBrains Mono', monospace", fontWeight: 600,
              letterSpacing: "1px",
            }}
          >
            {generating ? "GENERATING..." : "AUTO-GENERATE"}
          </button>
          {generating && (
            <div style={{ fontSize: "9px", color: "#555", textAlign: "center", marginTop: "6px" }}>
              Decomposing thesis into claims, evidence, arguments...
            </div>
          )}
          {genError && (
            <div style={{ fontSize: "9px", color: "#f87171", textAlign: "center", marginTop: "6px" }}>
              {genError}
            </div>
          )}
          <div style={{ fontSize: "9px", color: "#333", textAlign: "center", marginTop: "8px" }}>
            — or build manually —
          </div>
        </>
      )}

      {/* Buttons */}
      <div style={{ display: "flex", gap: "8px", marginTop: step === 0 ? "4px" : "12px" }}>
        {step > 0 && (
          <button
            onClick={() => { setStep(step - 1); setInput(""); }}
            style={{
              background: "transparent", border: "1px solid #333", color: "#666",
              borderRadius: "3px", padding: "10px 16px", fontSize: "10px",
              cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            BACK
          </button>
        )}
        <button
          onClick={handleSubmit}
          disabled={!canSubmit || creating || generating}
          style={{
            flex: 1, background: step === 0 ? "#222" : canSubmit ? "#FF6B35" : "#222",
            color: step === 0 ? (canSubmit ? "#aaa" : "#555") : (canSubmit ? "#0A0A0A" : "#555"),
            border: step === 0 ? "1px solid #333" : "none", borderRadius: "3px", padding: "10px",
            fontSize: "11px", cursor: canSubmit ? "pointer" : "default",
            fontFamily: "'JetBrains Mono', monospace", fontWeight: 600,
            letterSpacing: "1px",
          }}
        >
          {creating ? "…" : step === 0 ? "MANUAL STEP-BY-STEP" : step === STEPS.length - 1 ? "FINISH" : "CONTINUE"}
        </button>
        {step > 0 && (
          <button
            onClick={handleSkip}
            style={{
              background: "transparent", border: "1px solid #333", color: "#555",
              borderRadius: "3px", padding: "10px 16px", fontSize: "10px",
              cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            SKIP
          </button>
        )}
      </div>

      {/* Skip all */}
      <button
        onClick={onComplete}
        style={{
          background: "transparent", border: "none", color: "#444",
          fontSize: "9px", cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
          marginTop: "16px", textAlign: "center",
        }}
      >
        skip to full workbench →
      </button>
    </div>
  );
}
