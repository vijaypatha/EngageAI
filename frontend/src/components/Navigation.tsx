// frontend/src/components/Navigation.tsx
"use client";

import { useParams, usePathname } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  Users,
  CalendarCheck,
  MessageSquare,
  BarChart,
  UserCircle,
  Settings,
  Zap,            // Icon for Instant Nudge
  MailCheck,      // Icon for Replies
  MoreHorizontal, // Icon for "More" on mobile
  LogIn,          // Example for Logout, if needed in "More"
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";
import { apiClient } from "@/lib/api";

export function Navigation() {
  const params = useParams();
  const pathname = usePathname();
  const business_name_param = params?.business_name;
  const business_name = Array.isArray(business_name_param) ? business_name_param[0] : business_name_param;

  const [isMobile, setIsMobile] = useState(false);
  const [isLoading, setIsLoading] = useState(true); // Default to true
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [businessProfile, setBusinessProfile] = useState({
    representative_name: "",
    business_name: ""
  });

  // Log initial params
  console.log("Navigation params:", params);
  console.log("Derived business_name for API:", business_name);

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

  useEffect(() => {
    const fetchBusinessProfile = async () => {
      console.log("fetchBusinessProfile called. business_name:", business_name);
      if (!business_name || typeof business_name !== 'string') {
        console.log("fetchBusinessProfile: Invalid or missing business_name, setting isLoading false.");
        setIsLoading(false);
        setBusinessProfile({ representative_name: "User", business_name: "Business" }); // Explicitly set default on invalid
        return;
      }
      console.log("fetchBusinessProfile: Setting isLoading true.");
      setIsLoading(true); // Ensure loading is true before fetch
      try {
        console.log(`WorkspaceBusinessProfile: Attempting to fetch /business-profile/business-id/slug/${business_name}`);
        const response = await apiClient.get(`/business-profile/navigation-profile/slug/${business_name}`);
        console.log("fetchBusinessProfile: API response received", response);
        if (response?.data && response.data.business_name) { // Check specifically for business_name in response data
            console.log("fetchBusinessProfile: Successfully fetched business_name:", response.data.business_name);
            setBusinessProfile({
              representative_name: response.data.representative_name || "User",
              business_name: response.data.business_name // Use the fetched name
            });
        } else {
           console.log("fetchBusinessProfile: API response missing data or business_name. response.data:", response?.data);
           setBusinessProfile({ representative_name: "User", business_name: "Business" }); // Fallback if no name
        }
      } catch (error) {
        console.error("fetchBusinessProfile: Failed to fetch business profile:", error);
        setBusinessProfile({ representative_name: "User", business_name: "Business" }); // Fallback on error
      } finally {
        console.log("fetchBusinessProfile: Setting isLoading false in finally block.");
        setIsLoading(false);
      }
    };

    // Only fetch if business_name is valid
    if (business_name && typeof business_name === 'string') {
        fetchBusinessProfile();
    } else {
        // If business_name is not valid from the start, stop loading and use defaults
        console.log("fetchBusinessProfile useEffect: business_name initially invalid. Setting isLoading false.");
        setIsLoading(false);
        setBusinessProfile({ representative_name: "User", business_name: "Business" });
    }
  }, [business_name]); // Dependency on business_name

  const shouldRenderNav = !isLoading && business_name && typeof business_name === 'string' &&
                         !(pathname === "/" || pathname.startsWith("/auth") || pathname.startsWith("/onboarding"));

  // Log state before rendering decision
  console.log("Navigation state before render check: isLoading:", isLoading, "businessProfile:", businessProfile, "shouldRenderNav:", shouldRenderNav, "pathname:", pathname);


  if (!shouldRenderNav) {
    // You might want a more specific loading indicator here if isLoading is true but other conditions fail
    if (isLoading && business_name && typeof business_name === 'string' && !(pathname === "/" || pathname.startsWith("/auth") || pathname.startsWith("/onboarding"))) {
        console.log("Navigation: Rendering loading spinner for business profile fetch.");
        // return <div>Loading Business Profile...</div>; // Example loading spinner
    }
    console.log("Navigation: shouldRenderNav is false, returning null.");
    return null;
  }

  // --- Define Navigation Items (rest of your component remains the same) ---
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
    {
      name: "Instant Nudge",
      href: `/instant-nudge/${business_name}`,
      icon: Zap,
      description: "Send quick messages"
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
        name: "Replies",
        href: `/replies/${business_name}`,
        icon: MailCheck,
        description: "Review & reply"
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

  const activeTextGradient = "bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent";

  return (
    <>
      {/* Desktop Navigation Sidebar */}
      <nav className="fixed left-0 top-0 bottom-0 hidden md:flex flex-col w-64 bg-[#131625] border-r border-gray-700/50 z-[40]">
        <div className="p-6 border-b border-gray-700/30">
          <Link href={`/dashboard/${business_name}`} className="flex items-center space-x-2 group">
          <Image
              src="/AI Nudge Logo.png" // Assuming the logo is in frontend/public/
              alt="AI Nudge Logo"
              width={150} // Adjust width as needed for the sidebar
              height={30}  // Adjust height as needed, ensure it maintains aspect ratio
              priority
            />
          </Link>
        </div>

        <div className="flex-1 px-4 pt-4 space-y-6 overflow-y-auto">
          <div className="space-y-1">
            <h2 className="px-3 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">Inputs</h2>
            {inputNavItems.map((item) => {
              const safeHref = item.href || '#';
              const isActive = pathname === safeHref || (safeHref !== `/contacts/${business_name}` && pathname.startsWith(safeHref + '/'));
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

          <div className="space-y-1">
            <h2 className="px-3 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">Outputs</h2>
            {outputNavItems.map((item) => {
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
                  {/* Using the fix suggested previously */}
                  {isLoading ? "Loading..." : (businessProfile.business_name || "Business")}
                </span>
              </div>
            </div>
            <Settings className="w-5 h-5 text-gray-500 group-hover:text-gray-300 transition-colors" />
          </Link>
          ))}
        </div>
      </nav>

      {/* Mobile Navigation Bar */}
      <nav className="fixed bottom-0 left-0 right-0 md:hidden bg-[#131625]/95 backdrop-blur-sm border-t border-gray-700/50 z-[40] ">
        <div className="flex justify-around items-stretch h-16">
          {[
              { name: "Contacts", href: `/contacts/${business_name}`, icon: Users },
              { name: "Plans", href: `/all-engagement-plans/${business_name}`, icon: CalendarCheck },
              { name: "Instant", href: `/instant-nudge/${business_name}`, icon: Zap },
              { name: "Inbox", href: `/inbox/${business_name}`, icon: MessageSquare },
              {
                name: "LogoToDashboard", // A unique name for the key
                href: `/dashboard/${business_name}`, // Link destination
                icon: () => ( // Render function for the icon
                  <Image
                    src="/AI Nudge Logo.png"
                    alt="AI Nudge Dashboard"
                    width={60}  // Adjust for compact mobile view
                    height={12} // Adjust for compact mobile view
                    className="opacity-90 group-hover:opacity-100" // Example styling
                  />
                ),
                isLogo: true // Custom flag to identify this item
              },
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
                {item.isLogo ? (
                  <item.icon /> // Render the Image component directly
                ) : (
                  <>
                    <item.icon className="w-5 h-5 mb-0.5" />
                    {/* Only render the name span if it's not the logo item */}
                    <span className="text-[10px] leading-tight text-center font-medium">{item.name}</span>
                  </>
                )}
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
                    width={220} // Adjust as needed for the "More" menu
                    height={44}
                  />
                </Link>
              </div>
              {[
                { name: "Replies", href: `/replies/${business_name}`, icon: MailCheck },
                { name: "Profile", href: `/profile/${business_name}`, icon: UserCircle },
              ].map((item) => (
                <Link
                  key={item.name}
                  href={item.href || '#'}
                  onClick={() => {
                    if ((item as any).onClick) (item as any).onClick();
                    setShowMobileMenu(false);
                  }}
                  className={cn(
                    "flex items-center p-3 rounded-md transition-colors duration-150 text-gray-300 hover:bg-gray-700/60 hover:text-white group"
                  )}
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