import type { Metadata } from "next";
import { AppProvider } from "@/components/AppContext";
import DashboardLayout from "@/components/DashboardLayout";
import "./globals.css";

export const metadata: Metadata = {
  title: "Orion AI Gateway - Admin Dashboard",
  description: "Enterprise Service Router and Key Management Panel",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full bg-[#121212] text-[#fafafa]">
        <AppProvider>
          <DashboardLayout>
            {children}
          </DashboardLayout>
        </AppProvider>
      </body>
    </html>
  );
}
