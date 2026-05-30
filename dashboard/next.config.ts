import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

const nextConfig: NextConfig = {
  output: isDev ? undefined : "export",
  basePath: "/dashboard",
  images: {
    unoptimized: true, 
  },
  
  // Olası tüm giriş yöntemlerine izin veriyoruz:
  allowedDevOrigins: [
    "localhost",
    "127.0.0.1",
    "192.168.1.105",
    "*.trycloudflare.com"
  ],

  async rewrites() {
    const backendUrl =
      process.env.BACKEND_URL ||
      `http://localhost:${process.env.ROUTER_PORT || "20128"}`;
    return [
      {
        source: "/v1/:path*",
        destination: `${backendUrl}/v1/:path*`,
        basePath: false,
      },
      {
        source: "/api/:path*",
        destination: `${backendUrl}/dashboard/api/:path*`,
      },
    ];
  },
};

export default nextConfig;