// frontend/src/components/Navigation.tsx
"use client";

import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  Users,
  CalendarCheck,
  MessageSquare,
  UserCircle,
  Settings,
  MoreHorizontal,
  LayoutDashboard,
  Sparkles,
  Edit3 // Icon for Composer
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";
import { useBusinessNavigationProfile } from "@/lib/api";

export function Navigation() {
  const params = useParams();
  const pathname = usePathname();
  const business_name_param = params?.business_name;
  const business_name = Array.isArray(business_name_param) ? business_name_param[0] : business_name_param;

  const { data: businessProfileData, error, isLoading: swrIsLoading } = useBusinessNavigationProfile(business_name ?? null);
  
  const [isMobile, setIsMobile] = useState(false);
  const [showMobileMenu, setShowMobileMenu] = useState(false);

  useEffect(() => {
    const checkMobile = () => {
      if (typeof window !== 'undefined') {
         setIsMobile(window.innerWidth < 768);
      }
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const shouldRenderNav = !swrIsLoading && business_name && typeof business_name === 'string' &&
                         !(pathname === "/" || pathname.startsWith("/auth") || pathname.startsWith("/onboarding"));

  if (error) {
    console.error("Navigation: Error fetching business profile:", error);
  }

  if (!shouldRenderNav) {
    return null;
  }

  const display_business_name = businessProfileData?.business_name || "Business";
  
  // REFACTORED: Updated navigation items to match the new UI structure.
  const mainNavItems = [
    {
      name: "Inbox",
      href: `/inbox/${business_name}`,
      icon: MessageSquare,
      description: "React to live conversations"
    },
    {
      name: "Composer",
      href: `/composer/${business_name}`, // New Route
      icon: Edit3,
      description: "Create proactive messages"
    },
    {
      name: "Autopilot",
      href: `/autopilot/${business_name}`, // New Route
      icon: CalendarCheck,
      description: "Review scheduled messages"
    },
    {
      name: "Contacts",
      href: `/contacts/${business_name}`,
      icon: Users,
      description: "Manage your community"
    },
  ];

  const secondaryNavItems = [
    {
        name: "Co-Pilot",
        href: `/copilot/${business_name}`,
        icon: Sparkles,
        description: "Business growth assistant"
    },
    {
      name: "Dashboard",
      href: `/dashboard/${business_name}`,
      icon: LayoutDashboard,
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

  const activeTextGradient = "bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent";

  return (
    <>
      {/* Desktop Navigation Sidebar */}
      <nav className="fixed left-0 top-0 bottom-0 hidden md:flex flex-col w-64 bg-[#131625] border-r border-gray-700/50 z-[40]">
        <div className="p-6 border-b border-gray-700/30">
          <Link href={`/dashboard/${business_name}`} className="flex items-center space-x-2 group">
            <Image
              src="/AI Nudge Logo.png"
              alt="AI Nudge Logo"
              width={150}
              height={30}
              priority
            />
          </Link>
        </div>

        <div className="flex-1 px-4 pt-4 space-y-6 overflow-y-auto">
          {/* Main Navigation Section */}
          <div className="space-y-1">
            {mainNavItems.map((item) => {
              const safeHref = item.href || '#';
              const isActive = pathname === safeHref || pathname.startsWith(safeHref + '/');
              return (
                <Link
                  key={item.name}
                  href={safeHref}
                  className={cn(
                    "flex flex-col p-3 rounded-lg transition-all duration-150 group",
                    isActive
                      ? "bg-gradient-to-r from-emerald-600/15 to-blue-700/15"
                      : "text-gray-400 hover:bg-gray-700/60 hover:text-white"
                  )}
                >
                  <div className="flex items-center space-x-3">
                    <item.icon className={cn(
                        "w-5 h-5 transition-colors duration-150",
                        isActive ? "text-emerald-400" : "text-gray-500 group-hover:text-gray-300"
                    )} />
                    <span className={cn(
                        "font-medium text-sm transition-colors duration-150",
                        isActive ? activeTextGradient : "group-hover:text-white"
                    )}>{item.name}</span>
                  </div>
                  <span className="text-xs text-gray-500 mt-1 ml-8 group-hover:text-gray-400 transition-colors duration-150">
                    {item.description}
                  </span>
                </Link>
              );
            })}
          </div>

          {/* Secondary Navigation Section */}
          <div className="space-y-1">
            <h2 className="px-3 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">Analytics</h2>
            {secondaryNavItems.map((item) => {
               const safeHref = item.href || '#';
               const isActive = pathname === safeHref || pathname.startsWith(safeHref + '/');
              return (
                <Link
                  key={item.name}
                  href={safeHref}
                  className={cn(
                    "flex flex-col p-3 rounded-lg transition-all duration-150 group",
                    isActive
                      ? "bg-gradient-to-r from-emerald-600/15 to-blue-700/15"
                      : "text-gray-400 hover:bg-gray-700/60 hover:text-white"
                  )}
                >
                  <div className="flex items-center space-x-3">
                     <item.icon className={cn(
                         "w-5 h-5 transition-colors duration-150",
                         isActive ? "text-emerald-400" : "text-gray-500 group-hover:text-gray-300"
                     )} />
                    <span className={cn(
                        "font-medium text-sm transition-colors duration-150",
                        isActive ? activeTextGradient : "group-hover:text-white"
                     )}>{item.name}</span>
                  </div>
                   <span className="text-xs text-gray-500 mt-1 ml-8 group-hover:text-gray-400 transition-colors duration-150">
                    {item.description}
                  </span>
                </Link>
              );
            })}
          </div>
        </div>

        <div className="mt-auto border-t border-gray-700/50">
          {profileNavItems.map((item)=>(
             <Link
             key={item.name}
             href={item.href || '#'}
             className={cn(
               "flex items-center justify-between p-4 transition-all duration-150 group",
               pathname.startsWith(item.href || '/profile')
                 ? "bg-gradient-to-r from-emerald-600/15 to-blue-700/15"
                 : "text-gray-400 hover:bg-gray-700/60"
             )}
          >
            <div className="flex items-center space-x-3">
              <UserCircle className="w-7 h-7 text-gray-400 group-hover:text-gray-200" />
              <div className="flex flex-col">
                <span className="font-medium text-sm text-white group-hover:text-emerald-300 transition-colors">
                  {swrIsLoading ? "Loading..." : (display_business_name)}
                </span>
              </div>
            </div>
            <Settings className="w-5 h-5 text-gray-500 group-hover:text-gray-300 transition-colors" />
          </Link>
          ))}
        </div>
      </nav>

      {/* REFACTORED: Mobile Navigation Bar */}
      <nav className="fixed bottom-0 left-0 right-0 md:hidden bg-[#131625]/95 backdrop-blur-sm border-t border-gray-700/50 z-[40]">
        <div className="flex justify-around items-stretch h-16">
          {[
              { name: "Inbox", href: `/inbox/${business_name}`, icon: MessageSquare },
              { name: "Composer", href: `/composer/${business_name}`, icon: Edit3 },
              { name: "Autopilot", href: `/autopilot/${business_name}`, icon: CalendarCheck },
              { name: "Contacts", href: `/contacts/${business_name}`, icon: Users },
              { name: "Dashboard", href: `/dashboard/${business_name}`, icon: LayoutDashboard },
          ].map((item) => {
            const safeHref = item.href || '#';
            const isActive = pathname === safeHref || pathname.startsWith(safeHref + '/');
            return (
              <Link
                key={item.name}
                href={safeHref}
                className={cn(
                  "flex flex-col items-center justify-center flex-1 px-1 py-2 rounded-md transition-colors duration-200",
                  isActive
                    ? "text-emerald-400 bg-emerald-500/10"
                    : "text-gray-400 hover:text-white hover:bg-gray-700/50"
                )}
                style={{ minWidth: '0' }}
              >
                <>
                  <item.icon className="w-5 h-5 mb-0.5" />
                  <span className="text-[10px] leading-tight text-center font-medium">{item.name}</span>
                </>
              </Link>
            );
          })}
          <button
            onClick={() => setShowMobileMenu(!showMobileMenu)}
            className={cn(
              "flex flex-col items-center justify-center flex-1 px-1 py-2 rounded-md transition-colors duration-200",
              showMobileMenu
                ? "text-emerald-400 bg-emerald-500/10"
                : "text-gray-400 hover:text-white hover:bg-gray-700/50"
            )}
            style={{ minWidth: '0' }}
          >
            <MoreHorizontal className="w-5 h-5 mb-0.5" />
            <span className="text-[10px] leading-tight text-center font-medium">More</span>
          </button>
        </div>
      </nav>

      {/* Mobile "More" Menu Popup */}
      {isMobile && showMobileMenu && (
        <div className="fixed inset-0 bg-black/50 z-[45]" onClick={() => setShowMobileMenu(false)}>
          <div
            className="fixed bottom-16 left-4 right-4 mb-2 p-4 bg-[#1A1D2E] border border-gray-700/50 rounded-lg shadow-xl z-[50]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="grid grid-cols-1 gap-2">
              <div className="flex justify-center items-center py-3 border-b border-gray-700/30 mb-2">
                <Link href={`/dashboard/${business_name}`} onClick={() => setShowMobileMenu(false)}>
                  <Image
                    src="/AI Nudge Logo.png"
                    alt="AI Nudge Logo"
                    width={400}
                    height={80}
                  />
                </Link>
              </div>
              {[
                { name: "Co-Pilot", href: `/copilot/${business_name}`, icon: Sparkles },
                { name: "Profile", href: `/profile/${business_name}`, icon: UserCircle },
              ].map((item) => (
                <Link
                  key={item.name}
                  href={item.href || '#'}
                  onClick={() => setShowMobileMenu(false)}
                  className={cn("flex items-center p-3 rounded-md transition-colors duration-150 text-gray-300 hover:bg-gray-700/60 hover:text-white group")}
                >
                  <item.icon className="w-5 h-5 mr-3 text-gray-400 group-hover:text-emerald-400" />
                  <span className="text-sm font-medium">{item.name}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}