/**
 * API client.
 *
 * Every request carries the access token. When the access token expires the
 * client silently refreshes once and replays the original request; if the
 * refresh also fails the session is cleared and the app returns to login.
 * Concurrent 401s share a single refresh promise so a dashboard that fires
 * six requests at once does not fire six refreshes.
 */

import API_URL from "./config";

const ACCESS_KEY = "mw_access_token";
const REFRESH_KEY = "mw_refresh_token";
const USER_KEY = "user_id";
const SESSION_KEY = "session_id";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  save({ access_token, refresh_token, user_id, session_id }) {
    if (access_token) localStorage.setItem(ACCESS_KEY, access_token);
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
    if (user_id) localStorage.setItem(USER_KEY, user_id);
    if (session_id) localStorage.setItem(SESSION_KEY, session_id);
  },
  clear() {
    [ACCESS_KEY, REFRESH_KEY, USER_KEY, SESSION_KEY].forEach((k) =>
      localStorage.removeItem(k)
    );
  },
  get isAuthenticated() {
    return Boolean(localStorage.getItem(ACCESS_KEY));
  },
};

let refreshPromise = null;

function forceLogout() {
  tokens.clear();
  window.dispatchEvent(new CustomEvent("mindwell:logout"));
}

async function refreshAccessToken() {
  if (!tokens.refresh) return null;
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh }),
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.access_token) {
          localStorage.setItem(ACCESS_KEY, data.access_token);
          return data.access_token;
        }
        forceLogout();
        return null;
      })
      .catch(() => {
        forceLogout();
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

function buildInit(init = {}, token) {
  const headers = new Headers(init.headers || {});
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers };
}

/**
 * Drop-in replacement for fetch() against the MindWell API.
 * Returns the parsed JSON body, or throws ApiError.
 */
export async function apiFetch(input, init = {}) {
  const url = typeof input === "string" ? input : String(input);

  let response = await fetch(url, buildInit(init, tokens.access));

  if (response.status === 401 && tokens.refresh) {
    const fresh = await refreshAccessToken();
    if (fresh) {
      response = await fetch(url, buildInit(init, fresh));
    }
  }

  if (response.status === 401) {
    forceLogout();
    throw new ApiError("Your session expired. Please sign in again.", 401);
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const detail = body?.detail;
    const message =
      (typeof detail === "string" && detail) ||
      (Array.isArray(detail) && detail[0]?.msg) ||
      body?.message ||
      `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }

  // Components written against the old API check `data.success`, so keep
  // that contract for 2xx responses that don't carry the field.
  if (body && typeof body === "object" && !("success" in body)) {
    return { success: true, ...body };
  }
  return body ?? { success: true };
}

/** Convenience helpers. */
export const api = {
  get: (path) => apiFetch(`${API_URL}${path}`),
  post: (path, data) =>
    apiFetch(`${API_URL}${path}`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),
  put: (path, data) =>
    apiFetch(`${API_URL}${path}`, {
      method: "PUT",
      body: JSON.stringify(data ?? {}),
    }),
  del: (path) => apiFetch(`${API_URL}${path}`, { method: "DELETE" }),
};

export async function login(username, password) {
  const res = await fetch(`${API_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.detail || "Invalid username or password", res.status);
  }
  tokens.save(data);
  return data;
}

export async function logout() {
  try {
    if (tokens.refresh) {
      await apiFetch(`${API_URL}/auth/logout`, {
        method: "POST",
        body: JSON.stringify({ refresh_token: tokens.refresh }),
      });
    }
  } catch {
    // Logging out locally matters more than the server acknowledging it.
  } finally {
    tokens.clear();
  }
}

export default apiFetch;
