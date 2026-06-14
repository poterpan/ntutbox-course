import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",                 // static SPA for Cloudflare Pages (no server runtime)
  images: { unoptimized: true },    // required by output:'export'
  trailingSlash: true,              // stable static routing on Pages
};

export default nextConfig;
