// In dev, requests go to /api/* and Vite's proxy (vite.config.js) forwards
// them to FastAPI on :8000 — no CORS setup needed locally.
// In production, set VITE_API_URL to your deployed backend and requests
// go straight there (make sure CORS is enabled on the FastAPI side then).
const BASE_URL = import.meta.env.VITE_API_URL || "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  return res.blob();
}

export const api = {
  get: (path, params) => {
    const qs = params ? `?${new URLSearchParams(params)}` : "";
    return request(`${path}${qs}`);
  },
  post: (path, body) =>
    request(path, {
      method: "POST",
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),
  postForm: (path, formData) =>
    request(path, { method: "POST", body: formData }),
  delete: (path) => request(path, { method: "DELETE" }),
};

export { BASE_URL };
