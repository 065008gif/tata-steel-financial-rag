/* =========================================================
   API CLIENT
   Every call uses a relative /api/... path: the Vite dev server
   and nginx both proxy it to the FastAPI backend.
   ========================================================= */

const OFFLINE_MESSAGE =
  "Edith's backend is not reachable. Please check that it is running and try again.";
const ASK_TIMEOUT_MS = 300_000;

export class ApiError extends Error {
  constructor(message, { status = null, cancelled = false } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.cancelled = cancelled;
  }
}

function errorMessage(status, body) {
  if (body && typeof body.error === "string") return body.error;
  if (status === 422 && Array.isArray(body?.detail) && body.detail[0]?.msg) {
    return `Please check your question: ${body.detail[0].msg}.`;
  }
  if (typeof body?.detail === "string") return body.detail;
  // A proxy answering for a stopped backend returns 5xx without a JSON body.
  if (status >= 500) return OFFLINE_MESSAGE;
  return `The request failed (HTTP ${status}).`;
}

async function request(path, options = {}) {
  let response;

  try {
    response = await fetch(path, {
      ...options,
      headers: { Accept: "application/json", ...options.headers },
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError(OFFLINE_MESSAGE);
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(response.status, body), {
      status: response.status,
    });
  }

  if (body === null) throw new ApiError(OFFLINE_MESSAGE);
  return body;
}

/* Read-only endpoints are cached for the session: the data only
   changes when the backend is rebuilt. A failed call is dropped
   from the cache so that it can be retried. */
const cache = new Map();

function cachedGet(path) {
  if (!cache.has(path)) {
    const promise = request(path).catch((error) => {
      cache.delete(path);
      throw error;
    });
    cache.set(path, promise);
  }
  return cache.get(path);
}

export function getHealth() {
  return request("/api/health", { cache: "no-store" });
}

export function getReports() {
  return cachedGet("/api/reports");
}

export function getFinancials(items, scope = "consolidated") {
  const keys = encodeURIComponent(items.join(","));
  return cachedGet(`/api/financials?items=${keys}&scope=${scope}`);
}

export function getMetrics(scope = "consolidated") {
  return cachedGet(`/api/metrics?scope=${scope}`);
}

export function getScores(scope = "consolidated") {
  return cachedGet(`/api/scores?scope=${scope}`);
}

export function getSegments() {
  return cachedGet("/api/segments");
}

export function getStatements(scope = "consolidated") {
  return cachedGet(`/api/statements?scope=${scope}`);
}

export function getRegions() {
  return cachedGet("/api/regions");
}

export function getCompany() {
  return cachedGet("/api/company");
}

export function getEvaluation() {
  return cachedGet("/api/evaluation");
}

/**
 * Ask Edith a question.
 * history: earlier turns of this conversation, oldest first
 *          ([{ role: "user" | "assistant", content }], max 20).
 * signal:  optional AbortSignal; aborting it cancels the request.
 * Rejects with ApiError (cancelled: true when the user cancelled).
 */
export async function ask(question, history = [], signal) {
  const controller = new AbortController();
  let timedOut = false;

  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, ASK_TIMEOUT_MS);

  const onCancel = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onCancel, { once: true });
  }

  try {
    return await request("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: history.slice(-20) }),
      signal: controller.signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      if (timedOut) {
        throw new ApiError(
          "Edith did not answer within 5 minutes. Please try again, or ask a narrower question.",
        );
      }
      throw new ApiError("Question cancelled.", { cancelled: true });
    }
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onCancel);
  }
}
