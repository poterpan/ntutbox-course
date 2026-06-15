import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",                 // static SPA for Cloudflare Pages (no server runtime)
  images: { unoptimized: true },    // required by output:'export'
  trailingSlash: true,              // stable static routing on Pages
  // Dev-only: allow testing on a phone/tablet over the LAN. Next 16 blocks non-localhost
  // origins from /_next/* dev resources by default, which breaks HMR/hydration on the
  // device. Wildcards cover common private LAN ranges + mDNS (.local) hostnames so the
  // host's IP can change freely. Ignored by the static export build.
  allowedDevOrigins: ["10.*.*.*", "192.168.*.*", "*.local"],
};

export default nextConfig;
