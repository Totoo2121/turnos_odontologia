/** Versioned token storage (key `turnos.auth.v1`), browser boundary isolated.
 *
 * C-03 (D2): the refresh token travels ONLY in the HttpOnly cookie
 * (`Path=/api/auth`) and is NEVER persisted in JS storage — only the short
 * access token lives here. Legacy payloads from C-01 carrying `refreshToken`
 * are migrated on load (refresh dropped, access kept).
 */

export const AUTH_STORAGE_KEY = "turnos.auth.v1";

export interface AuthTokens {
  accessToken: string;
}

/** Raw legacy shape (C-01 persisted both tokens); refresh is dropped. */
interface LegacyAuthTokens {
  accessToken?: unknown;
  refreshToken?: unknown;
  access_token?: unknown;
}

export interface TokenStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
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

function pickAccess(parsed: LegacyAuthTokens): string | null {
  const candidate = parsed.accessToken ?? parsed.access_token;
  return typeof candidate === "string" && candidate.length > 0 ? candidate : null;
}

export function loadTokens(store: TokenStore = defaultStore()): AuthTokens | null {
  const raw = store.getItem(AUTH_STORAGE_KEY);
  if (raw === null) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as LegacyAuthTokens;
    const accessToken = pickAccess(parsed);
    if (accessToken === null) {
      return null;
    }
    // Migrate legacy payloads: rewrite access-only so the persisted refresh
    // never survives on disk (C-03 D2).
    if (typeof parsed.refreshToken === "string") {
      saveTokens({ accessToken }, store);
    }
    return { accessToken };
  } catch {
    return null;
  }
}

export function saveTokens(tokens: AuthTokens, store: TokenStore = defaultStore()): void {
  store.setItem(AUTH_STORAGE_KEY, JSON.stringify({ accessToken: tokens.accessToken }));
}

export function clearTokens(store: TokenStore = defaultStore()): void {
  store.removeItem(AUTH_STORAGE_KEY);
}
