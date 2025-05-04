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
  Settings,
  Zap,       // Icon for Instant Nudge
  MailCheck  // Icon for Replies
} from "lucide-react";
import { cn } from "@/lib/utils"; // Assuming you have this utility function
import { useState, useEffect } from "react";
import { apiClient } from "@/lib/api"; // Assuming you have this API client

export function Navigation() {
  const params = useParams();
  const pathname = usePathname();
  // Ensure business_name is consistently treated as a string
  const business_name_param = params?.business_name;
  const business_name = Array.isArray(business_name_param) ? business_name_param[0] : business_name_param;

  const [isMobile, setIsMobile] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [businessProfile, setBusinessProfile] = useState({
    representative_name: "",
    business_name: ""
  });

  useEffect(() => {
    const checkMobile = () => {
      if (typeof window !== 'undefined') {
         setIsMobile(window.innerWidth < 768);
      }
      setIsLoading(false);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    const fetchBusinessProfile = async () => {
      if (!business_name || typeof business_name !== 'string') {
        // If business name isn't valid yet, maybe wait or set default
        return;
      }
      setIsLoading(true); // Set loading true when fetching
      try {
        const response = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        if (response?.data) {
            setBusinessProfile({
              representative_name: response.data.representative_name || "User", // Add fallback
              business_name: response.data.business_name || "Business" // Add fallback
            });
        } else {
           setBusinessProfile({ representative_name: "User", business_name: "Business" }); // Set fallback on bad response
        }
      } catch (error) {
        console.error("Failed to fetch business profile:", error);
        setBusinessProfile({ representative_name: "User", business_name: "Business" }); // Set fallback on error
      } finally {
        // Consider delaying isLoading false slightly if needed for smoother transition
        setIsLoading(false);
      }
    };
    fetchBusinessProfile();
  }, [business_name]);


  // Navigation should render if not loading AND business_name is a valid string
  // AND we are not on auth/onboarding pages
  const shouldRenderNav = !isLoading && business_name && typeof business_name === 'string' &&
                         !(pathname === "/" || pathname.startsWith("/auth") || pathname.startsWith("/onboarding"));

  if (!shouldRenderNav) {
    return null;
  }


  // --- Define Navigation Items ---
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
    },
    // --- Instant Nudge Item ---
    {
      name: "Instant Nudge",
      href: `/instant-nudge/${business_name}`,
      icon: Zap, // Using Zap icon
      description: "Send quick messages"
    }
    // --- End Instant Nudge Item ---
  ];

  const outputNavItems = [
    {
      name: "Inbox",
      href: `/inbox/${business_name}`,
      icon: MessageSquare,
      description: "View conversations"
    },
    {
        name: "Replies", // Added Replies link explicitly
        href: `/replies/${business_name}`,
        icon: MailCheck, // Use MailCheck icon consistent with dashboard
        description: "Review & reply"
    },
    {
      name: "Analytics",
      href: `/dashboard/${business_name}`, // Links to the main dashboard page
      icon: BarChart,
      description: "Track performance"
    }
  ];

  // Keep profile separate for bottom placement
  const profileNavItems = [
    {
      name: "Profile",
      href: `/profile/${business_name}`,
      icon: UserCircle,
      description: "View profile"
    }
  ];

  // --- Styling Variables ---
  const activeTextGradient = "bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent";

  return (
    <>
      {/* ====================== */}
      {/* Desktop Navigation Sidebar */}
      {/* ====================== */}
      <nav className="fixed left-0 top-0 bottom-0 hidden md:flex flex-col w-64 bg-[#131625] border-r border-gray-700/50 z-[40]"> {/* Adjusted bg and border */}
        {/* Logo/Header Area */}
        <div className="p-6 border-b border-gray-700/30"> {/* Added bottom border */}
          <Link href={`/dashboard/${business_name}`} className="flex items-center space-x-2 group">
            {/* Replace with your actual logo if you have one */}
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="text-emerald-400 group-hover:text-emerald-300 transition-colors">
                <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span className="text-xl font-semibold text-white group-hover:text-gray-200 transition-colors">AI Nudge</span>
          </Link>
        </div>

        {/* Main Navigation Links */}
        <div className="flex-1 px-4 pt-4 space-y-6 overflow-y-auto"> {/* Added padding-top */}
          {/* Inputs Section */}
          <div className="space-y-1">
            <h2 className="px-3 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">Inputs</h2>
            {inputNavItems.map((item) => {
              const safeHref = item.href || '#'; // Fallback href
              // More specific active check: Exact match OR startsWith for nested routes, excluding root if others match
              const isActive = pathname === safeHref || (safeHref !== `/contacts/${business_name}` && pathname.startsWith(safeHref + '/'));

              return (
                <Link
                  key={item.name}
                  href={safeHref}
                  className={cn(
                    "flex flex-col p-3 rounded-lg transition-all duration-150 group",
                    isActive
                      ? "bg-gradient-to-r from-emerald-600/15 to-blue-700/15" // Adjusted active bg
                      : "text-gray-400 hover:bg-gray-700/60 hover:text-white" // Adjusted hover
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

          {/* Outputs Section */}
          <div className="space-y-1">
            <h2 className="px-3 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">Outputs</h2>
            {outputNavItems.map((item) => {
               const safeHref = item.href || '#';
               const isActive = pathname === safeHref || pathname.startsWith(safeHref + '/'); // Check startsWith for nested routes

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

        {/* Profile Section at Bottom */}
        <div className="mt-auto border-t border-gray-700/50">
          {profileNavItems.map((item)=>( // Use map for consistency, though only one item
             <Link
             key={item.name}
             href={item.href || '#'}
             className={cn(
               "flex items-center justify-between p-4 transition-all duration-150 group",
               pathname.startsWith(item.href || '/profile') // Use startsWith for profile subpages
                 ? "bg-gradient-to-r from-emerald-600/15 to-blue-700/15"
                 : "text-gray-400 hover:bg-gray-700/60"
             )}
          >
            <div className="flex items-center space-x-3">
              {/* Consider using an Avatar component if you have one */}
              <UserCircle className="w-7 h-7 text-gray-400 group-hover:text-gray-200" /> {/* Adjusted size/color */}
              <div className="flex flex-col">
                <span className="font-medium text-sm text-white group-hover:text-emerald-300 transition-colors">{businessProfile.representative_name}</span>
                <span className="text-xs text-gray-400">{businessProfile.business_name}</span>
              </div>
            </div>
            <Settings className="w-5 h-5 text-gray-500 group-hover:text-gray-300 transition-colors" />
          </Link>
          ))}
        </div>
      </nav>

      {/* ====================== */}
      {/* Mobile Navigation Bar */}
      {/* ====================== */}
      <nav className="fixed bottom-0 left-0 right-0 md:hidden bg-[#131625]/95 backdrop-blur-sm border-t border-gray-700/50 z-[40]">
        <div className="flex justify-around items-stretch h-16"> {/* Ensure items stretch */}
          {[ // Define mobile items directly here
              { name: "Dashboard", href: `/dashboard/${business_name}`, icon: BarChart },
              { name: "Plans", href: `/all-engagement-plans/${business_name}`, icon: CalendarCheck },
              { name: "Instant", href: `/instant-nudge/${business_name}`, icon: Zap },
              { name: "Replies", href: `/replies/${business_name}`, icon: MailCheck },
              { name: "Contacts", href: `/contacts/${business_name}`, icon: Users },
              // Add Profile link if needed, maybe replace Contacts?
              // { name: "Profile", href: `/profile/${business_name}`, icon: UserCircle },
          ].map((item) => {
            const safeHref = item.href || '#';
            const isActive = pathname === safeHref || pathname.startsWith(safeHref + '/');
            return (
              <Link
                key={item.name}
                href={safeHref}
                className={cn(
                  "flex flex-col items-center justify-center flex-1 px-1 py-2 rounded-md transition-colors duration-200", // Adjusted padding
                  isActive
                    ? "text-emerald-400 bg-emerald-500/10" // Active state
                    : "text-gray-400 hover:text-white hover:bg-gray-700/50" // Hover state
                )}
                style={{ minWidth: '0' }} // Let flexbox handle width
              >
                <item.icon className="w-5 h-5 mb-0.5" />
                <span className="text-[10px] leading-tight text-center font-medium">{item.name}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}