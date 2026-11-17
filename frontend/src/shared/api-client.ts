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
  private readonly fetchImpl: FetchImpl | undefined;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? resolveBaseUrl()).replace(/\/+$/, "");
    this.store = options.store ?? defaultStore();
    // Resolved lazily so test stubs and late polyfills see the current global.
    this.fetchImpl = options.fetchImpl;
  }

  private resolveFetch(): FetchImpl {
    return this.fetchImpl ?? fetch.bind(globalThis);
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("POST", path, false, body);
  }

  async patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("PATCH", path, false, body);
  }

  async delete<T = void>(path: string): Promise<T> {
    return this.request<T>("DELETE", path);
  }

  /** Multipart upload: never set content-type (the browser owns the boundary). */
  async upload<T>(path: string, form: FormData): Promise<T> {
    return this.request<T>("POST", path, false, form);
  }

  /** Authenticated binary download (receipts and signed PDFs). */
  async download(path: string): Promise<Blob> {
    const response = await this.authorizedFetch("GET", path);
    return response.blob();
  }

  private async request<T>(method: string, path: string, retried = false, body?: unknown): Promise<T> {
    const response = await this.authorizedFetch(method, path, body, retried);
    if (response.status === 204) {
      return undefined as T;
    }
    const text = await response.text();
    if (!text) {
      return undefined as T;
    }
    try {
      return JSON.parse(text) as T;
    } catch {
      return text as unknown as T;
    }
  }

  private async authorizedFetch(
    method: string,
    path: string,
    body?: unknown,
    retried = false,
  ): Promise<Response> {
    const tokens = loadTokens(this.store);
    const isForm = typeof FormData !== "undefined" && body instanceof FormData;
    const headers = new Headers();
    if (!isForm) {
      headers.set("content-type", "application/json");
    }
    if (tokens !== null) {
      headers.set("authorization", `Bearer ${tokens.accessToken}`);
    }
    const response = await this.resolveFetch()(`${this.baseUrl}${path}`, {
      method,
      headers,
      body:
        body === undefined
          ? undefined
          : isForm
            ? (body as FormData)
            : JSON.stringify(body),
    });
    if (response.status === 401 && !retried && tokens !== null) {
      // C-03 (D2): single cookie-refresh attempt, then give up.
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        return this.authorizedFetch(method, path, body, true);
      }
      clearTokens(this.store);
      throw new ApiError(401, "unauthorized (refresh rejected)");
    }
    if (!response.ok) {
      throw new ApiError(response.status, await this.errorMessage(response));
    }
    return response;
  }

  /** Business `detail` from the backend wins over the generic status text. */
  private async errorMessage(response: Response): Promise<string> {
    const fallback = `request failed: ${response.status}`;
    try {
      const text = await response.text();
      if (!text) {
        return fallback;
      }
      const payload = JSON.parse(text) as {
        detail?: unknown;
        message?: unknown;
      };
      if (typeof payload.detail === "string" && payload.detail.trim().length > 0) {
        return payload.detail;
      }
      if (typeof payload.message === "string" && payload.message.trim().length > 0) {
        return payload.message;
      }
    } catch {
      // Non-JSON error body: keep the status fallback.
    }
    return fallback;
  }

  private async tryRefresh(): Promise<boolean> {
    // C-03 (D2): the refresh token travels in the HttpOnly cookie —
    // no body, no Authorization header, exactly one attempt.
    const response = await this.resolveFetch()(`${this.baseUrl}${REFRESH_PATH}`, {
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
