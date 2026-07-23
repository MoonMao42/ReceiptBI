export const locales = ["en", "zh"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "zh";
export const localeCookieName = "locale";

export function isLocale(value: string | null | undefined): value is Locale {
  return locales.includes(value as Locale);
}

function localeForLanguageRange(range: string): Locale | null {
  const normalized = range.trim().toLocaleLowerCase();
  if (!normalized) return null;
  if (normalized === "*") return defaultLocale;
  return locales.find(
    (locale) => normalized === locale || normalized.startsWith(`${locale}-`)
  ) || null;
}

/** Resolve the highest-priority supported locale from an Accept-Language value. */
export function localeFromAcceptLanguage(
  acceptLanguage: string | null | undefined
): Locale | null {
  if (!acceptLanguage?.trim()) return null;

  const candidates = acceptLanguage
    .split(",")
    .map((entry, index) => {
      const [range = "", ...parameters] = entry.split(";");
      const qualityParameter = parameters.find((parameter) =>
        parameter.trim().toLocaleLowerCase().startsWith("q=")
      );
      const quality = qualityParameter
        ? Number(qualityParameter.trim().slice(2))
        : 1;
      return {
        range,
        quality:
          Number.isFinite(quality) && quality >= 0 && quality <= 1 ? quality : 0,
        index,
      };
    })
    .sort((left, right) => right.quality - left.quality || left.index - right.index);

  for (const candidate of candidates) {
    if (candidate.quality <= 0) continue;
    const locale = localeForLanguageRange(candidate.range);
    if (locale) return locale;
  }
  return null;
}

/** Cookie preference wins; otherwise browser preference and then Chinese default. */
export function resolveLocale(
  cookieLocale: string | null | undefined,
  acceptLanguage: string | null | undefined
): Locale {
  if (isLocale(cookieLocale)) return cookieLocale;
  return localeFromAcceptLanguage(acceptLanguage) || defaultLocale;
}
