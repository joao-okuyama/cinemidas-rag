const BASE = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");
const TOKEN_KEY = "cinemidas-guest-token-v2";
let bootstrap;

async function request(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
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
  // Single-flight also avoids creating two visitors under React StrictMode.
  bootstrap: () => bootstrap ||= post("/guest-session").then((data) => {
    localStorage.setItem(TOKEN_KEY, data.token);
    return data;
  }).catch((error) => { bootstrap = undefined; throw error; }),
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
