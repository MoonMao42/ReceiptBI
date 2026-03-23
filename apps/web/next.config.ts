import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const publicApiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const internalApiUrl = process.env.INTERNAL_API_URL || publicApiUrl;

const nextConfig: NextConfig = {
  reactStrictMode: true,

  output: 'standalone',

  env: {
    NEXT_PUBLIC_API_URL: publicApiUrl,
  },

  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiUrl}/api/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
