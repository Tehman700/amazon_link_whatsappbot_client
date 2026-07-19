import type { Marketplace, ProcessResponse, User } from "./types";

// Dev: talk to the local FastAPI directly (VITE_API_URL can override).
// Prod: always same-origin /api/*, rewritten to the API deployment by
// vercel.json — deliberately not env-configurable so a stray dashboard
// env var can't break the wiring.
const BASE = import.meta.env.DEV
  ? (import.meta.env.VITE_API_URL ?? "http://localhost:8000")
  : "/api";

const TOKEN_KEY = "admin_token";
let token: string | null = localStorage.getItem(TOKEN_KEY);

export function setToken(value: string | null) {
  token = value;
  if (value) localStorage.setItem(TOKEN_KEY, value);
  else localStorage.removeItem(TOKEN_KEY);
}

export function hasToken(): boolean {
  return Boolean(token);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(BASE + path, { headers, ...options });
  if (res.status === 401 && path !== "/auth/login") {
    setToken(null);
    window.dispatchEvent(new Event("auth-expired"));
    throw new Error("Session expired — please log in again");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  login: async (username: string, password: string) => {
    const result = await request<{ token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(result.token);
  },

  listUsers: () => request<User[]>("/users"),
  createUser: (data: {
    name: string;
    whatsapp_number: string;
    email: string | null;
    link_preference?: "direct" | "hub";
    store_name?: string;
  }) => request<User>("/users", { method: "POST", body: JSON.stringify(data) }),
  updateUser: (
    id: number,
    data: {
      name: string;
      whatsapp_number: string;
      email: string | null;
      link_preference: "direct" | "hub";
      store_name: string;
    },
  ) => request<User>(`/users/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteUser: (id: number) => request<void>(`/users/${id}`, { method: "DELETE" }),

  setTrackingIds: (userId: number, items: { marketplace_id: number; tag: string }[]) =>
    request<User>(`/users/${userId}/tracking-ids`, { method: "PUT", body: JSON.stringify(items) }),
  deleteTrackingId: (userId: number, marketplaceId: number) =>
    request<void>(`/users/${userId}/tracking-ids/${marketplaceId}`, { method: "DELETE" }),

  listMarketplaces: () => request<Marketplace[]>("/marketplaces"),
  createMarketplace: (data: { code: string; name: string; domain: string }) =>
    request<Marketplace>("/marketplaces", { method: "POST", body: JSON.stringify(data) }),
  updateMarketplace: (id: number, data: { code: string; name: string; domain: string }) =>
    request<Marketplace>(`/marketplaces/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteMarketplace: (id: number) => request<void>(`/marketplaces/${id}`, { method: "DELETE" }),

  processMessage: (sender: string, text: string) =>
    request<ProcessResponse>("/process-message", {
      method: "POST",
      body: JSON.stringify({ sender, text }),
    }),
};

// --- Portal administration (gateway to the website's admin endpoints) ---
import type { PortalAdminData } from "./types";

export const portalAdmin = {
  data: () => request<PortalAdminData>("/portal-admin/accounts"),
  resetPassword: (id: number) =>
    request<{ temp_password: string; username: string }>(
      `/portal-admin/accounts/${id}/reset-password`, { method: "POST" }),
  setDisabled: (id: number, disabled: boolean) =>
    request<{ disabled: boolean }>(`/portal-admin/accounts/${id}/disabled`, {
      method: "POST", body: JSON.stringify({ disabled }),
    }),
  deleteAccount: (id: number) =>
    request<{ ok: boolean }>(`/portal-admin/accounts/${id}`, { method: "DELETE" }),
  unlinkNumber: (number: string) =>
    request<void>(`/portal-admin/linked/${encodeURIComponent(number)}`, { method: "DELETE" }),
};
