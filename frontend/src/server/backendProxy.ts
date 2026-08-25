import type { NextRequest } from "next/server";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function backendOrigin() {
  return (
    process.env.BACKEND_INTERNAL_URL ||
    process.env.BACKEND_PROXY_TARGET ||
    process.env.VITE_BACKEND_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
}

function forwardHeaders(request: NextRequest) {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  });
  return headers;
}

function responseHeaders(response: Response) {
  const headers = new Headers(response.headers);
  HOP_BY_HOP_HEADERS.forEach((header) => headers.delete(header));

  const extendedHeaders = response.headers as Headers & { getSetCookie?: () => string[] };
  const setCookies = extendedHeaders.getSetCookie?.() ?? [];
  if (setCookies.length > 0) {
    headers.delete("set-cookie");
    for (const cookie of setCookies) headers.append("set-cookie", cookie);
  }
  return headers;
}

export async function proxyBackendRequest(request: NextRequest, pathname: string) {
  const target = new URL(`${backendOrigin()}${pathname}`);
  target.search = request.nextUrl.search;

  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : await request.arrayBuffer();

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers: forwardHeaders(request),
      body,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { detail: "Backend is unavailable. Check BACKEND_INTERNAL_URL or the backend service status." },
      { status: 502 },
    );
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders(upstream),
  });
}

export function routeHandlers(prefix: "/api" | "/uploads") {
  return async function handle(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
    const { path = [] } = await context.params;
    const pathname = `${prefix}/${path.map((part) => encodeURIComponent(part)).join("/")}`;
    return proxyBackendRequest(request, pathname);
  };
}
