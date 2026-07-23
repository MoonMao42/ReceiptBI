import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";
import { localeCookieName, resolveLocale } from "./config";

const messageImports = {
  en: () => import("../messages/en.json"),
  zh: () => import("../messages/zh.json"),
} as const;

export default getRequestConfig(async () => {
  const [cookieStore, headerStore] = await Promise.all([cookies(), headers()]);
  const locale = resolveLocale(
    cookieStore.get(localeCookieName)?.value,
    headerStore.get("accept-language")
  );
  return {
    locale,
    messages: (await messageImports[locale]()).default,
  };
});
