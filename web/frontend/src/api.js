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

const post = (path, body) =>
  request(path, { method: "POST", body: JSON.stringify(body) });
const put = (path, body) =>
  request(path, { method: "PUT", body: JSON.stringify(body) });
const del = (path) => request(path, { method: "DELETE" });

const ws = (name) => `/workspaces/${encodeURIComponent(name)}`;

// ── Workspaces (top-level) ──────────────────────────────────────────
export const listWorkspaces = () => request("/workspaces");
export const createWorkspace = (name) => post("/workspaces", { name });
export const getWorkspaceInfo = (name) => request(ws(name));

// ── Claims ──────────────────────────────────────────────────────────
export const getClaims = (name) => request(`${ws(name)}/claims`);
export const createClaim = (name, data) => post(`${ws(name)}/claims`, data);
export const updateClaim = (name, id, data) => put(`${ws(name)}/claims/${id}`, data);
export const deleteClaim = (name, id) => del(`${ws(name)}/claims/${id}`);

// ── Evidence ────────────────────────────────────────────────────────
export const getEvidence = (name) => request(`${ws(name)}/evidence`);
export const createEvidence = (name, data) => post(`${ws(name)}/evidence`, data);
export const deleteEvidence = (name, id) => del(`${ws(name)}/evidence/${id}`);

// ── Arguments ───────────────────────────────────────────────────────
export const getArguments = (name) => request(`${ws(name)}/arguments`);
export const createArgument = (name, data) => post(`${ws(name)}/arguments`, data);
export const deleteArgument = (name, id) => del(`${ws(name)}/arguments/${id}`);
export const getArgumentsForNode = (name, id) =>
  request(`${ws(name)}/arguments/for-node/${id}`);

// ── Defeaters ───────────────────────────────────────────────────────
export const addDefeater = (name, argId, data) =>
  post(`${ws(name)}/arguments/${argId}/defeaters`, data);
export const updateDefeater = (name, argId, idx, data) =>
  put(`${ws(name)}/arguments/${argId}/defeaters/${idx}`, data);

// ── Graph ───────────────────────────────────────────────────────────
export const getGraph = (name) => request(`${ws(name)}/graph`);

// ── Analysis ────────────────────────────────────────────────────────
export const getAtms = (name) => request(`${ws(name)}/analysis/atms`);
export const getCoherence = (name) => request(`${ws(name)}/analysis/coherence`);
export const getBlindSpots = (name) => request(`${ws(name)}/analysis/blind-spots`);
export const getAssumptions = (name, id) => request(`${ws(name)}/analysis/assumptions/${id}`);
export const getStressTest = (name, id) => request(`${ws(name)}/analysis/stress-test/${id}`);
export const bayesianUpdate = (name, data) => post(`${ws(name)}/analysis/bayesian-update`, data);

// ── Summary / theses / versions ─────────────────────────────────────
export const getTheses = (name) => request(`${ws(name)}/summary/theses`);
export const getSummary = (name, thesisId) =>
  request(`${ws(name)}/summary${thesisId ? `?thesis_id=${thesisId}` : ""}`);
export const getThesisVersions = (name, id) => request(`${ws(name)}/thesis-versions/${id}`);
export const getGitLog = (name) => request(`${ws(name)}/git-log`);

// ── LLM (async, slow — 30-60s) ──────────────────────────────────────
export const generate = (name, thesis) => post(`${ws(name)}/generate`, { thesis });
export const enhanceThesis = (name, thesisId) =>
  post(`${ws(name)}/enhance-thesis`, { thesis_id: thesisId });
export const acceptEnhancedThesis = (name, data) =>
  post(`${ws(name)}/accept-enhanced-thesis`, data);

// ── Manual interventions ────────────────────────────────────────────
export const respondToDefeater = (name, data) =>
  post(`${ws(name)}/respond-to-defeater`, data);
export const concedeDefeater = (name, data) =>
  post(`${ws(name)}/concede-defeater`, data);
export const addEvidenceToClaim = (name, data) =>
  post(`${ws(name)}/add-evidence-to-claim`, data);
export const challengeClaim = (name, data) =>
  post(`${ws(name)}/challenge-claim`, data);
export const setConfidence = (name, data) =>
  post(`${ws(name)}/set-confidence`, data);

// ── Forks ───────────────────────────────────────────────────────────
export const listBranches = (name) => request(`${ws(name)}/branches`);
export const fork = (name, forkName) => post(`${ws(name)}/fork`, { fork_name: forkName });
export const switchBranch = (name, forkName) =>
  post(`${ws(name)}/switch`, { fork_name: forkName });
export const compareBranches = (name, other) =>
  request(`${ws(name)}/compare/${encodeURIComponent(other)}`);
export const mergeBranches = (name, sourceBranch, mode = "synthesize") =>
  post(`${ws(name)}/merge`, { source_branch: sourceBranch, mode });
