import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";
import { inlineThemeStorageMigration } from "@/lib/storage/legacy";
import { RECEIPTBI_BRAND_ICON_SRC } from "@/lib/brand";
import "./globals.css";
import { Providers } from "./providers";

const themeStorageMigration = inlineThemeStorageMigration();

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("metadata");
  return {
    title: t("title"),
    description: t("description"),
    icons: {
      icon: [{ url: RECEIPTBI_BRAND_ICON_SRC, type: "image/png", sizes: "256x256" }],
      apple: [{ url: RECEIPTBI_BRAND_ICON_SRC, type: "image/png", sizes: "256x256" }],
    },
  };
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var r=${themeStorageMigration};var d=JSON.parse(r||"{}");var t=d.state&&d.state.theme;if(t==="dawn"||t==="midnight")document.documentElement.classList.add("theme-"+t);}catch(e){}})();`,
          }}
        />
      </head>
      <body>
        <NextIntlClientProvider messages={messages}>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
