/** Shared fetch stubs for C-15 component tests. Datos ficticios. */
import { vi } from "vitest";
import { AUTH_STORAGE_KEY } from "../../shared/storage";

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export function pdfResponse(content = "pdf-ficticio"): Response {
  // String body + content-type: happy-dom mis-handles a Blob body and
  // `response.blob()` would stringify it as "[object Blob]".
  return new Response(content, {
    status: 200,
    headers: { "content-type": "application/pdf" },
  });
}

export function seedSession(): void {
  localStorage.setItem(
    AUTH_STORAGE_KEY,
    JSON.stringify({ accessToken: "access-clinica-test" }),
  );
}

export type FetchHandler = (
  url: string,
  init?: RequestInit,
) => Response | Promise<Response>;

/** Stubs global fetch and fails loudly on unexpected URLs. */
export function stubFetch(handler: FetchHandler): ReturnType<typeof vi.fn> {
  const fetchImpl = vi.fn(
    async (input: string | URL | Request, init?: RequestInit) =>
      handler(String(input), init),
  );
  vi.stubGlobal("fetch", fetchImpl);
  return fetchImpl;
}

export function callsFor(
  fetchImpl: ReturnType<typeof vi.fn>,
  method: string,
): [string | URL | Request, RequestInit | undefined][] {
  return (fetchImpl.mock.calls as [
    string | URL | Request,
    RequestInit | undefined,
  ][]).filter(([, init]) => (init?.method ?? "GET") === method);
}
