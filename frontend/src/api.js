const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "/api/v1"
).replace(/\/$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.detail || "Não foi possível concluir a solicitação.");
  }

  return payload;
}

export const bookingApi = {
  catalog: () => request("/catalog?limit=24&only_bookable=true"),
  sessions: (movieId) =>
    request(`/movies/${encodeURIComponent(movieId)}/sessions?limit=100`),
  seats: (sessionId, userId) =>
    request(
      `/sessions/${encodeURIComponent(sessionId)}/seats?user_id=${encodeURIComponent(userId)}`,
    ),
  checkout: (selection) =>
    request("/checkout", {
      method: "POST",
      body: JSON.stringify(selection),
    }),
  pay: (orderId, payment) =>
    request(`/orders/${encodeURIComponent(orderId)}/payments`, {
      method: "POST",
      body: JSON.stringify(payment),
    }),
  orders: (userId) =>
    request(`/users/${encodeURIComponent(userId)}/orders`),
};
