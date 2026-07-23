// API client: envelope unwrap, typed errors, auto refresh-on-401 with
// rotating refresh tokens (docs/AUTH_RBAC.md §7). Two token stores — one per
// realm — so an admin session and a client session can coexist.

import type { Envelope, Realm, Tokens } from "./types";

export const API_BASE: string =
  (import.meta.env?.VITE_API_BASE as string | undefined) ??
  "http://localhost:8000/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  details: unknown;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

const tokensKey = (realm: Realm) => `erp.${realm}.tokens`;

export function getTokens(realm: Realm): Tokens | null {
  const raw = localStorage.getItem(tokensKey(realm));
  return raw ? (JSON.parse(raw) as Tokens) : null;
}

export function setTokens(realm: Realm, tokens: Tokens | null): void {
  if (tokens === null) localStorage.removeItem(tokensKey(realm));
  else localStorage.setItem(tokensKey(realm), JSON.stringify(tokens));
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  realm?: Realm;
  skipAuth?: boolean;
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const e = body.error ?? {};
    return new ApiError(
      e.code ?? "HTTP_ERROR", e.message ?? res.statusText, res.status, e.details,
    );
  } catch {
    return new ApiError("HTTP_ERROR", res.statusText, res.status);
  }
}

async function tryRefresh(realm: Realm): Promise<boolean> {
  const tokens = getTokens(realm);
  if (!tokens?.refresh_token) return false;
  const path = realm === "admin" ? "/admin/auth/refresh" : "/auth/refresh";
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!res.ok) {
    setTokens(realm, null);
    return false;
  }
  const body = (await res.json()) as Envelope<Tokens>;
  setTokens(realm, body.data);
  return true;
}

export async function api<T>(
  path: string,
  opts: RequestOptions = {},
): Promise<Envelope<T>> {
  const realm: Realm = opts.realm ?? "client";

  const doFetch = () => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (!opts.skipAuth) {
      const tokens = getTokens(realm);
      if (tokens) headers.Authorization = `Bearer ${tokens.access_token}`;
    }
    return fetch(`${API_BASE}${path}`, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  };

  let res = await doFetch();
  if (res.status === 401 && !opts.skipAuth && (await tryRefresh(realm))) {
    res = await doFetch(); // one retry with the rotated tokens
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as Envelope<T>;
}

function authHeader(realm: Realm): Record<string, string> {
  const tokens = getTokens(realm);
  return tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {};
}

/** Multipart file upload. The browser sets the multipart Content-Type itself,
 *  so we deliberately don't set it. Same 401→refresh→retry as `api`. */
export async function apiUpload<T>(
  path: string, file: File, realm: Realm = "client",
): Promise<Envelope<T>> {
  const doFetch = () => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}${path}`, {
      method: "POST", headers: authHeader(realm), body: form,
    });
  };
  let res = await doFetch();
  if (res.status === 401 && (await tryRefresh(realm))) res = await doFetch();
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as Envelope<T>;
}

/** Fetch an authenticated file and save it via a transient object URL — needed
 *  because a plain <a href> can't carry the bearer token. */
export async function apiDownload(
  path: string, fallbackName = "download", realm: Realm = "client",
): Promise<void> {
  const doFetch = () => fetch(`${API_BASE}${path}`, { headers: authHeader(realm) });
  let res = await doFetch();
  if (res.status === 401 && (await tryRefresh(realm))) res = await doFetch();
  if (!res.ok) throw await parseError(res);

  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const name = match ? match[1] : fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
