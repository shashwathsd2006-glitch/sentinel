import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import { MobileNav, Sidebar, Topbar } from "@/components/nav";

export const metadata: Metadata = {
  title: "SENTINEL-X · Agent Runtime Gateway",
  description:
    "Runtime security gateway detecting dangerous multi-step action sequences of autonomous AI agents.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <Suspense fallback={null}>
          <Sidebar />
        </Suspense>
        <div className="flex min-h-screen flex-col md:pl-60">
          <Suspense
            fallback={
              <div className="h-[57px] border-b border-slate-800 bg-slate-950" />
            }
          >
            <Topbar />
          </Suspense>
          <main className="flex-1 px-4 py-5 pb-20 md:px-6 md:pb-8">
            <div className="mx-auto max-w-7xl space-y-5">{children}</div>
          </main>
        </div>
        <Suspense fallback={null}>
          <MobileNav />
        </Suspense>
      </body>
    </html>
  );
}
