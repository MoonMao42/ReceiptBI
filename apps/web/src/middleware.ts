import { NextRequest, NextResponse } from "next/server";
import { locales, defaultLocale, type Locale } from "./i18n/config";

export function middleware(request: NextRequest) {
  const localeCookie = request.cookies.get("locale")?.value;

  if (localeCookie && locales.includes(localeCookie as Locale)) {
    return NextResponse.next();
  }

  const acceptLanguage = request.headers.get("accept-language") || "";
  const detectedLocale = acceptLanguage.match(/zh/i) ? "zh" : defaultLocale;

  const response = NextResponse.next();
  response.cookies.set("locale", detectedLocale, {
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
    sameSite: "lax",
  });
  return response;
}

export const config = {
  matcher: ["/((?!_next|api|.*\\..*).*)"],
};
