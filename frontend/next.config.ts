import type { NextConfig } from "next";

const backendUrl = (process.env.API_BACKEND_URL ?? "http://localhost:5002").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/:path*` }];
  },
};

export default nextConfig;
