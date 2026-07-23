"use server";

import { cookies } from "next/headers";
import { localeCookieName, locales, type Locale } from "@/i18n/config";

export async function setLocale(locale: string) {
  if (!locales.includes(locale as Locale)) return;
  const cookieStore = await cookies();
  cookieStore.set(localeCookieName, locale, {
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
    sameSite: "lax",
  });
}
