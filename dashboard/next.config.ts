import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

const nextConfig: NextConfig = {
  output: isDev ? undefined : "export",
  basePath: "/dashboard",
  images: {
    unoptimized: true, // Required for static export
  },
};

export default nextConfig;
