import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";
import { defaultLocale, locales, type Locale } from "./config";

const messageImports = {
  en: () => import("../messages/en.json"),
  zh: () => import("../messages/zh.json"),
} as const;

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const stored = cookieStore.get("locale")?.value;
  const locale = locales.includes(stored as Locale) ? (stored as Locale) : defaultLocale;
  return {
    locale,
    messages: (await messageImports[locale]()).default,
  };
});
