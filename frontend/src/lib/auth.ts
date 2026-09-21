export interface User {
  user_id: number;
  user_name: string;
  user_email: string;
  daily_caloric_target: number | null;
  created_at: string;
  updated_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

const TOKEN_KEY = "platter.accessToken";
const USER_KEY = "platter.user";

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function storeAuth(token: string, user: User) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail) && data.detail[0]?.msg) {
      return data.detail[0].msg;
    }
  } catch {
    // ignore
  }
  return `Request failed (${res.status})`;
}

export async function signup(payload: {
  user_name: string;
  user_email: string;
  password: string;
  daily_caloric_target?: number | null;
}): Promise<AuthResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await parseError(res));
  }

  return res.json();
}

export async function login(payload: {
  user_email: string;
  password: string;
}): Promise<AuthResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await parseError(res));
  }

  return res.json();
}

export async function fetchCurrentUser(token: string): Promise<User> {
  const res = await fetch(`${getApiBaseUrl()}/api/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    throw new Error(await parseError(res));
  }

  return res.json();
}

export async function updateCurrentUser(
  token: string,
  payload: {
    user_name?: string;
    daily_caloric_target?: number | null;
    password?: string;
  },
): Promise<User> {
  const res = await fetch(`${getApiBaseUrl()}/api/users/me`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await parseError(res));
  }

  return res.json();
}
