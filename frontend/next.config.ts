import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  reactStrictMode: true,
  // AI教材生成はapp-serverの応答に時間がかかるため、Next.jsの
  // rewrite proxy既定値（30秒）で接続を切らない。
  experimental: {
    proxyTimeout: 300_000,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000"}/api/:path*`
      }
    ];
  }
};

export default nextConfig;
