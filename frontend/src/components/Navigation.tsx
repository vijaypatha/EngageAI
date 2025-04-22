// frontend/src/components/Navigation.tsx
"use client";

import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import { 
  Users, 
  CalendarCheck, 
  MessageSquare, 
  BarChart,
  UserCircle,
  Settings
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";

export function Navigation() {
  const params = useParams();
  const pathname = usePathname();
  const business_name = params?.business_name;
  const [isMobile, setIsMobile] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [businessProfile, setBusinessProfile] = useState({
    representative_name: "",
    business_name: ""
  });
  const router = useRouter();

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
      setIsLoading(false);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    const fetchBusinessProfile = async () => {
      if (!business_name) return;
      try {
        const response = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        setBusinessProfile({
          representative_name: response.data.representative_name || "",
          business_name: response.data.business_name || ""
        });
      } catch (error) {
        console.error("Failed to fetch business profile:", error);
      }
    };
    fetchBusinessProfile();
  }, [business_name]);

  if (isLoading) return null;

  if (!business_name || pathname === "/" || pathname.startsWith("/auth") || pathname.startsWith("/onboarding")) {
    return null;
  }

  const inputNavItems = [
    {
      name: "Contacts",
      href: `/contacts/${business_name}`,
      icon: Users,
      description: "Manage your community"
    },
    {
      name: "Nudge Plans",
      href: `/all-engagement-plans/${business_name}`,
      icon: CalendarCheck,
      description: "Schedule engagements"
    }
  ];

  const outputNavItems = [
    {
      name: "Inbox",
      href: `/inbox/${business_name}`,
      icon: MessageSquare,
      description: "View conversations"
    },
    {
      name: "Analytics",
      href: `/dashboard/${business_name}`,
      icon: BarChart,
      description: "Track performance"
    }
  ];

  const profileNavItems = [
    {
      name: "Profile",
      href: `/profile/${business_name}`,
      icon: UserCircle,
      description: "View profile"
    }
  ];

  const activeGradient = "bg-gradient-to-r from-emerald-400 to-blue-500";
  const activeTextGradient = "bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent";

  return (
    <>
      {/* Desktop Navigation */}
      <nav className="fixed left-0 top-0 bottom-0 hidden md:flex flex-col w-64 bg-dark-lighter/80 backdrop-blur-sm border-r border-white/10 z-[40]">
        <div className="p-6">
          <Link href={`/dashboard/${business_name}`} className="flex items-center space-x-2">
            <span className="text-4xl font-bold text-gradient">AI Nudge</span>
          </Link>
        </div>

        <div className="flex-1 px-4 space-y-8">
          {/* Inputs Section */}
          <div className="space-y-1">
            <h2 className="px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Inputs</h2>
            {inputNavItems.map((item) => {
              const isActive = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={cn(
                    "flex flex-col p-3 rounded-lg transition-all duration-200",
                    isActive
                      ? "bg-gradient-to-r from-emerald-400/10 to-blue-500/10"
                      : "text-gray-400 hover:bg-white/5 hover:text-white"
                  )}
                >
                  <div className="flex items-center space-x-3">
                    <item.icon className={cn("w-5 h-5", isActive && "text-emerald-400")} />
                    <span className={cn("font-medium", isActive && activeTextGradient)}>{item.name}</span>
                  </div>
                  <span className="text-sm text-gray-500 mt-1 ml-8">
                    {item.description}
                  </span>
                </Link>
              );
            })}
          </div>

          {/* Outputs Section */}
          <div className="space-y-1">
            <h2 className="px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Outputs</h2>
            {outputNavItems.map((item) => {
              const isActive = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={cn(
                    "flex flex-col p-3 rounded-lg transition-all duration-200",
                    isActive
                      ? "bg-gradient-to-r from-emerald-400/10 to-blue-500/10"
                      : "text-gray-400 hover:bg-white/5 hover:text-white"
                  )}
                >
                  <div className="flex items-center space-x-3">
                    <item.icon className={cn("w-5 h-5", isActive && "text-emerald-400")} />
                    <span className={cn("font-medium", isActive && activeTextGradient)}>{item.name}</span>
                  </div>
                  <span className="text-sm text-gray-500 mt-1 ml-8">
                    {item.description}
                  </span>
                </Link>
              );
            })}
          </div>
        </div>

        {/* Profile Section at Bottom */}
        <div className="mt-auto border-t border-white/10">
          <Link
            href={`/profile/${business_name}`}
            className={cn(
              "flex items-center justify-between p-4 transition-all duration-200 bg-[#1A1D2D] hover:bg-[#242842]",
              pathname.startsWith(`/profile/${business_name}`) && "bg-[#242842]"
            )}
          >
            <div className="flex items-center gap-3">
              <div className="p-1 rounded-full">
                <UserCircle className="w-6 h-6 text-gray-400" />
              </div>
              <div className="flex flex-col items-start">
                <span className="text-white font-medium">{businessProfile.representative_name}</span>
                <span className="text-gray-500 text-sm">{businessProfile.business_name}</span>
                <span className="text-gray-400 text-sm">View Profile</span>
              </div>
            </div>
            <Settings className="w-5 h-5 text-gray-400" />
          </Link>
        </div>
      </nav>

      {/* Mobile Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 md:hidden bg-dark-lighter/80 backdrop-blur-sm border-t border-white/10 z-[40]">
        <div className="flex justify-around p-2">
          {[...inputNavItems, ...outputNavItems, ...profileNavItems].map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "flex flex-col items-center p-2 rounded-lg transition-all duration-200",
                  isActive
                    ? "text-emerald-400"
                    : "text-gray-400 hover:text-white"
                )}
              >
                <item.icon className={cn("w-5 h-5", isActive && "text-emerald-400")} />
                <span className="text-xs mt-1">{item.name}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}