import api from "./api";

/** { login, avatarUrl } if signed in, else null. Never rejects - "signed
 * out" and "couldn't reach the backend" are both reported as null; callers
 * that need to distinguish those can check the thrown error themselves. */
export async function getCurrentUser() {
  const { data } = await api.get("/auth/me");
  return data.user;
}

/** Full-page redirect, not an API call - this has to leave the SPA
 * entirely so the browser follows GitHub's own redirect chain. */
export function redirectToGitHubLogin() {
  const base = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
  window.location.href = `${base}/auth/github/login`;
}

export async function logout() {
  await api.post("/auth/logout");
}
