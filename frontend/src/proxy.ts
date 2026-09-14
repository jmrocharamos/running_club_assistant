import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_COOKIE_NAME = "access_token";
const PUBLIC_PATHS = ["/login", "/register", "/forgot-password", "/reset-password"];

/**
 * Optimistic only: this checks whether the auth cookie is present, not
 * whether the JWT inside it is still valid. An expired/invalid token still
 * passes through here and gets a real 401 from the API, which the client
 * session layer (SessionProvider + AuthGuard) handles by redirecting to
 * /login. This just avoids a flash of protected UI for the common case of
 * "no cookie at all".
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  // API authentication belongs to FastAPI. Login must reach it without a cookie,
  // and unauthenticated API calls must return JSON 401s, not page redirects.
  if (pathname === "/api" || pathname.startsWith("/api/")) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(AUTH_COOKIE_NAME);
  const isPublicPath = PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  if (!hasSession && !isPublicPath) {
    const loginUrl = new URL("/login", request.url);
    if (pathname !== "/") {
      loginUrl.searchParams.set("next", pathname);
    }
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
