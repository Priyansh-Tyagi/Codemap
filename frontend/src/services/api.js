import axios from "axios";

// In dev this defaults to the local backend. For a deployed frontend, set
// VITE_API_BASE_URL at build time to point at the deployed backend's URL
// (see the README's deployment section).
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api",
  // Required for the session cookie (set by /auth/github/callback) to be
  // sent on every request - without this, a signed-in user's GitHub token
  // never actually gets used for /analyze.
  withCredentials: true,
});

/**
 * File paths are used as URL path segments (e.g. "src/my file.js"). Encode
 * each segment individually - encodeURIComponent alone would also escape
 * "/" and break multi-segment matching against the backend's
 * {file_path:path} route.
 */
function encodeFilePath(filePath) {
  return filePath.split("/").map(encodeURIComponent).join("/");
}

/** source: { path } for a local filesystem path, or { githubUrl } for a GitHub repo URL. */
export async function analyzeRepository(source) {
  const { data } = await api.post("/analyze", source);
  return data;
}

export async function getProjectGraph(projectId) {
  const { data } = await api.get(`/projects/${projectId}/graph`);
  return data;
}

export async function getProjectSummary(projectId) {
  const { data } = await api.get(`/projects/${projectId}`);
  return data;
}

export async function getProjectCycles(projectId) {
  const { data } = await api.get(`/projects/${projectId}/cycles`);
  return data;
}

export async function getProjectMetrics(projectId) {
  const { data } = await api.get(`/projects/${projectId}/metrics`);
  return data;
}

export async function getFileImpact(projectId, filePath) {
  const { data } = await api.get(
    `/projects/${projectId}/files/${encodeFilePath(filePath)}/impact`
  );
  return data;
}

export default api;
