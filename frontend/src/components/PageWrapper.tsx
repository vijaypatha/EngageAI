"use client";

import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export function PageWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLandingPage = pathname === "/";
  const isOnboardingPage = pathname === "/onboarding";
  const isAuthPage = pathname.startsWith("/auth");
  const isDashboardPage = !isLandingPage && !isOnboardingPage && !isAuthPage;

  return (
    <div className={cn(
      "min-h-screen bg-nudge-gradient relative",
      isDashboardPage && "md:pl-64" // Sidebar space for desktop
    )}>
      <div className={cn(
        "min-h-screen w-full relative",
        isDashboardPage && "pb-28 md:pb-8 px-4 md:px-8 pt-6 md:pt-8", // Increased bottom padding for mobile nav + consistent horizontal padding
        !isDashboardPage && "flex flex-col"
      )}>
        <div className="w-full max-w-7xl mx-auto">
          {children}
        </div>
      </div>
    </div>
  );
}
