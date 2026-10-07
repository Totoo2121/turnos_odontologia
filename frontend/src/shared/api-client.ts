import { clearTokens, loadTokens, saveTokens, type TokenStore } from "./storage";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export type FetchImpl = typeof fetch;

export interface ApiClientOptions {
  baseUrl?: string;
  store?: TokenStore;
  fetchImpl?: FetchImpl;
}

interface RefreshPayload {
  accessToken?: string;
  access_token?: string;
}

const REFRESH_PATH = "/api/auth/refresh";

function resolveBaseUrl(): string {
  const fromEnv =
    typeof import.meta !== "undefined" &&
    typeof import.meta.env?.VITE_API_BASE_URL === "string" &&
    import.meta.env.VITE_API_BASE_URL.length > 0
      ? import.meta.env.VITE_API_BASE_URL
      : "http://localhost:8000";
  return fromEnv.replace(/\/+$/, "");
}

function defaultStore(): TokenStore {
  if (typeof localStorage !== "undefined") {
    return localStorage;
  }
  const memory = new Map<string, string>();
  return {
    getItem: (key) => memory.get(key) ?? null,
    setItem: (key, value) => {
      memory.set(key, value);
    },
    removeItem: (key) => {
      memory.delete(key);
    },
  };
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly store: TokenStore;
  private readonly fetchImpl: FetchImpl;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? resolveBaseUrl()).replace(/\/+$/, "");
    this.store = options.store ?? defaultStore();
    this.fetchImpl = options.fetchImpl ?? fetch.bind(globalThis);
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("POST", path, false, body);
  }

  private async request<T>(method: string, path: string, retried = false, body?: unknown): Promise<T> {
    const tokens = loadTokens(this.store);
    const headers = new Headers({ "content-type": "application/json" });
    if (tokens !== null) {
      headers.set("authorization", `Bearer ${tokens.accessToken}`);
    }
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 401 && !retried && tokens !== null) {
      // C-03 (D2): single cookie-refresh attempt, then give up.
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        return this.request<T>(method, path, true, body);
      }
      clearTokens(this.store);
      throw new ApiError(401, "unauthorized (refresh rejected)");
    }
    if (!response.ok) {
      throw new ApiError(response.status, `request failed: ${response.status}`);
    }
    return (await response.json()) as T;
  }

  private async tryRefresh(): Promise<boolean> {
    // C-03 (D2): the refresh token travels in the HttpOnly cookie —
    // no body, no Authorization header, exactly one attempt.
    const response = await this.fetchImpl(`${this.baseUrl}${REFRESH_PATH}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
    });
    if (!response.ok) {
      return false;
    }
    const payload = (await response.json()) as RefreshPayload;
    const accessToken = payload.accessToken ?? payload.access_token;
    if (typeof accessToken !== "string" || accessToken.length === 0) {
      return false;
    }
    saveTokens({ accessToken }, this.store);
    return true;
  }
}
