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
    // Visitors see this on the live site, where "is it running on port 8000?" means
    // nothing, and the commonest cause is a free host that is still waking up.
    return "Couldn't reach the backend. If it was idle it may still be waking up (that can take up to a minute), so try again shortly. Running locally? Check that the backend is on port 8000.";
  }
  const detail = res.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg; // FastAPI validation errors
  // A gateway answering for a host that is waking up or restarting: no message of its own.
  if (res.status === 502 || res.status === 503 || res.status === 504) {
    return "The server is starting up or temporarily unavailable. Try again in a moment.";
  }
  return `The server returned an error (${res.status}). Check the backend log for details.`;
}
