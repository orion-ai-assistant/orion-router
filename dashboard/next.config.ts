import type { NextConfig } from "next";
import os from "os";

const isDev = process.env.NODE_ENV !== "production";

// Sistemdeki tüm yerel IP adreslerini dinamik olarak alıyoruz
const getLocalIPs = (): string[] => {
  const ips: string[] = [];
  const interfaces = os.networkInterfaces();
  for (const name of Object.keys(interfaces)) {
    const ifaces = interfaces[name];
    if (ifaces) {
      for (const iface of ifaces) {
        if (iface.family === "IPv4") {
          ips.push(iface.address);
        }
      }
    }
  }
  return ips;
};

const nextConfig: NextConfig = {
  output: isDev ? undefined : "export",
  basePath: "/dashboard",
  images: {
    unoptimized: true, 
  },
  
  // Olası tüm giriş yöntemlerine (dinamik IP'ler dahil) izin veriyoruz:
  allowedDevOrigins: [
    "localhost",
    "127.0.0.1",
    "*.trycloudflare.com",
    ...getLocalIPs()
  ],
};

if (isDev) {
  nextConfig.rewrites = async () => {
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
  };

  nextConfig.redirects = async () => {
    return [
      {
        source: "/",
        destination: "/dashboard",
        permanent: true,
        basePath: false,
      },
    ];
  };
}

export default nextConfig;