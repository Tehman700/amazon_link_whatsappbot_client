import type { Marketplace, ProcessResponse, User } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
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
  listUsers: () => request<User[]>("/users"),
  createUser: (data: { name: string; whatsapp_number: string; email: string | null }) =>
    request<User>("/users", { method: "POST", body: JSON.stringify(data) }),
  updateUser: (id: number, data: { name: string; whatsapp_number: string; email: string | null }) =>
    request<User>(`/users/${id}`, { method: "PUT", body: JSON.stringify(data) }),
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
