// 📄 src/app/layout.tsx
import "./../styles/globals.css";
import type { Metadata } from "next";
import { Navigation } from "@/components/Navigation";

export const metadata: Metadata = {
  title: "AI Nudge",
  description: "AI-powered SMS engagement platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Navigation />
        <div className="min-h-screen bg-nudge-gradient md:pl-64">
          <div className="max-w-6xl mx-auto p-4 md:p-8 pb-20 md:pb-8">
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}