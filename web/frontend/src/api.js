const BASE = "/api";

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// Workspace
export const getWorkspace = () => request("/workspace");

// Claims
export const getClaims = () => request("/claims");
export const createClaim = (data) => request("/claims", { method: "POST", body: JSON.stringify(data) });
export const updateClaim = (id, data) => request(`/claims/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteClaim = (id) => request(`/claims/${id}`, { method: "DELETE" });

// Evidence
export const getEvidence = () => request("/evidence");
export const createEvidence = (data) => request("/evidence", { method: "POST", body: JSON.stringify(data) });
export const deleteEvidence = (id) => request(`/evidence/${id}`, { method: "DELETE" });

// Arguments
export const getArguments = () => request("/arguments");
export const createArgument = (data) => request("/arguments", { method: "POST", body: JSON.stringify(data) });
export const deleteArgument = (id) => request(`/arguments/${id}`, { method: "DELETE" });
export const getArgumentsForNode = (id) => request(`/arguments/for-node/${id}`);

// Defeaters
export const addDefeater = (argId, data) => request(`/arguments/${argId}/defeaters`, { method: "POST", body: JSON.stringify(data) });
export const updateDefeater = (argId, idx, data) => request(`/arguments/${argId}/defeaters/${idx}`, { method: "PUT", body: JSON.stringify(data) });

// Graph
export const getGraph = () => request("/graph");

// Analysis
export const getAtms = () => request("/analysis/atms");
export const getCoherence = () => request("/analysis/coherence");
export const getBlindSpots = () => request("/analysis/blind-spots");
export const getAssumptions = (id) => request(`/analysis/assumptions/${id}`);
export const getStressTest = (id) => request(`/analysis/stress-test/${id}`);
export const bayesianUpdate = (data) => request("/analysis/bayesian-update", { method: "POST", body: JSON.stringify(data) });

// Summary
export const getTheses = () => request("/summary/theses");
export const getSummary = (thesisId) => request(`/summary${thesisId ? `?thesis_id=${thesisId}` : ""}`);

// Auto-generate
export const generate = (thesis) => request("/generate", { method: "POST", body: JSON.stringify({ thesis }) });

// Enhance thesis
export const enhanceThesis = (thesisId) => request("/enhance-thesis", { method: "POST", body: JSON.stringify({ thesis_id: thesisId }) });

// Accept enhanced thesis (creates new version with fresh graph)
export const acceptEnhancedThesis = (data) => request("/accept-enhanced-thesis", { method: "POST", body: JSON.stringify(data) });

// Thesis version history
export const getThesisVersions = (id) => request(`/thesis-versions/${id}`);
