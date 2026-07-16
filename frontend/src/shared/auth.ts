// Two-realm auth store (docs/AUTH_RBAC.md §1): admin and client sessions are
// separate pools with separate tokens — never mixed.

import { api, setTokens } from "./api";
import type { AdminMe, ClientMe, Tokens } from "./types";

interface LoginResult extends Tokens {
  password_reset_required?: boolean;
  user: { id: string; name: string; email: string };
}

export async function clientLogin(
  company: string, email: string, password: string,
): Promise<LoginResult> {
  const res = await api<LoginResult>("/auth/login", {
    method: "POST", body: { company, email, password }, skipAuth: true,
  });
  setTokens("client", {
    access_token: res.data.access_token,
    refresh_token: res.data.refresh_token,
  });
  return res.data;
}

export async function changePassword(
  currentPassword: string, newPassword: string,
): Promise<void> {
  await api("/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });
  setTokens("client", null); // password change revokes refresh tokens server-side
}

export async function clientMe(): Promise<ClientMe> {
  return (await api<ClientMe>("/auth/me")).data;
}

export async function clientLogout(): Promise<void> {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch {
    // best effort — clearing local tokens is what matters
  }
  setTokens("client", null);
}

export async function adminLogin(
  email: string, password: string,
): Promise<LoginResult> {
  const res = await api<LoginResult>("/admin/auth/login", {
    method: "POST", body: { email, password }, skipAuth: true, realm: "admin",
  });
  setTokens("admin", {
    access_token: res.data.access_token,
    refresh_token: res.data.refresh_token,
  });
  return res.data;
}

export async function adminMe(): Promise<AdminMe> {
  return (await api<AdminMe>("/admin/auth/me", { realm: "admin" })).data;
}

export async function adminLogout(): Promise<void> {
  try {
    await api("/admin/auth/logout", { method: "POST", realm: "admin" });
  } catch {
    // best effort
  }
  setTokens("admin", null);
}
