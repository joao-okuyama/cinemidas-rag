import { createVisitSession } from "./visitSession";

const BASE = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");
// Discard only the legacy visitor credential, not unrelated browser data.
try { localStorage.removeItem("cinemidas-guest-token-v2"); } catch { /* Storage may be blocked. */ }
const visit = createVisitSession(() => post("/guest-session"));

async function request(path, options = {}) {
  const token = visit.token;
  const response = await fetch(BASE + path, {
    ...options,
    headers: { "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    const problem = new Error(typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((item) => item.msg).join("; ")
      : "Não foi possível concluir a solicitação.");
    problem.status = response.status;
    throw problem;
  }
  return payload;
}
const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body) });

export const bookingApi = {
  bootstrap: () => visit.start(),
  catalog: (signal) => request("/catalog?limit=24&only_bookable=true", { signal }),
  booking: () => request("/booking"),
  select: (selection) => post("/booking/selection", selection),
  reset: () => post("/booking/reset"),
  sessions: (id, signal) => request(`/movies/${encodeURIComponent(id)}/sessions?limit=100`, { signal }),
  seats: (id) => request(`/sessions/${encodeURIComponent(id)}/seats`),
  checkout: (selection) => post("/checkout", selection),
  pay: (id, payment) => post(`/orders/${encodeURIComponent(id)}/payments`, payment),
  orders: () => request("/me/orders"),
  history: () => request("/agent/history"),
  chat: (message, requestId) => post("/agent/chat", { message, request_id: requestId }),
};
