/**
 * Turns an Axios error into a message that says what actually went wrong.
 *
 * The distinction that matters: "no response at all" (network down, backend
 * not running, CORS) is a different problem from "the server answered with
 * an error". Reporting both as "can't reach the backend" sent debugging in
 * the wrong direction when a server-side crash returned a 500.
 */
export function describeApiError(err) {
  const res = err?.response;
  if (!res) {
    return "Couldn't reach the backend. Is it running on port 8000?";
  }
  const detail = res.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg; // FastAPI validation errors
  return `The server returned an error (${res.status}). Check the backend log for details.`;
}
