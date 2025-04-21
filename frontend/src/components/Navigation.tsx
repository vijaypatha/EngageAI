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

export function Navigation() {
  const params = useParams();
  const pathname = usePathname();
  const business_name = params?.business_name;
  const [isMobile, setIsMobile] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
      setIsLoading(false);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  if (isLoading) return null;

  if (!business_name || pathname === "/" || pathname.startsWith("/auth") || pathname.startsWith("/onboarding")) {
    return null;
  }

  const navItems = [
    {
      group: "Inputs",
      items: [
        {
          icon: <Users size={isMobile ? 24 : 20} />,
          label: "Contacts",
          path: `/contacts/${business_name}`,
          description: "Manage your community"
        },
        {
          icon: <CalendarCheck size={isMobile ? 24 : 20} />,
          label: "Nudge Plans",
          path: `/all-engagement-plans/${business_name}`,
          description: "Schedule engagements"
        },
      ]
    },
    {
      group: "Outputs",
      items: [
        {
          icon: <MessageSquare size={isMobile ? 24 : 20} />,
          label: "Inbox",
          path: `/inbox/${business_name}`,
          description: "View conversations"
        },
        {
          icon: <BarChart size={isMobile ? 24 : 20} />,
          label: "Analytics",
          path: `/dashboard/${business_name}`,
          description: "Track performance"
        },
      ]
    }
  ];

  // Desktop sidebar navigation
  if (!isMobile) {
    return (
      <div className="fixed left-0 top-0 h-screen w-64 bg-[#1f1f1f] border-r border-gray-800 z-40">
        {/* Logo/Brand section */}
        <div className="h-16 border-b border-gray-800 flex items-center px-6">
          <span className="text-xl font-bold text-white">AI Nudge</span>
        </div>
        
        {/* Navigation items grouped */}
        <nav className="p-4 space-y-6">
          {navItems.map((group) => (
            <div key={group.group} className="space-y-2">
              <div className="px-4 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                {group.group}
              </div>
              {group.items.map((item) => {
                const isActive = pathname === item.path;
                
                return (
                  <Link
                    key={item.label}
                    href={item.path}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 rounded-lg transition-colors group",
                      isActive 
                        ? "bg-white/10 text-white" 
                        : "text-gray-400 hover:bg-white/5 hover:text-gray-300"
                    )}
                  >
                    {item.icon}
                    <div>
                      <div className="font-medium">{item.label}</div>
                      <div className="text-xs text-gray-500 group-hover:text-gray-400">
                        {item.description}
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Profile section */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-800">
          <div className="flex items-center gap-3 px-4 py-2 text-gray-400 hover:text-gray-300 transition-colors cursor-pointer">
            <UserCircle size={32} />
            <div className="flex-1">
              <div className="text-sm font-medium text-white truncate">
                {business_name}
              </div>
              <div className="text-xs">View Profile</div>
            </div>
            <Settings size={20} className="text-gray-500" />
          </div>
        </div>
      </div>
    );
  }

  // Mobile bottom navigation (simplified version)
  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 md:hidden">
      <div className="h-4 bg-gradient-to-t from-[#1f1f1f] to-transparent" />
      <div className="bg-[#1f1f1f] border-t border-gray-800">
        <div className="flex justify-around items-center h-16 max-w-lg mx-auto px-4">
          {navItems.flatMap(group => group.items).map((item) => {
            const isActive = pathname === item.path;
            
            return (
              <Link
                key={item.label}
                href={item.path}
                className={cn(
                  "flex flex-col items-center justify-center flex-1 h-full transition-colors",
                  isActive 
                    ? "text-white" 
                    : "text-gray-400 hover:text-gray-300"
                )}
              >
                {item.icon}
                <span className="text-xs mt-1">{item.label}</span>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}