// frontend/src/app/dashboard/[business_name]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import {
  Users,
  Send,
  MailCheck,
  MessageSquare,
  Clock, // Kept for potential future use
  CalendarClock,
  TrendingUp,
  LayoutDashboard, // Added for page title
  Loader2,       // Added for loading state
  AlertTriangle,  // Added for error state
  ArrowRight,
  Lightbulb  // Add this line
} from "lucide-react";
import { OptInStatusBadge } from "@/components/OptInStatus";
import { cn } from "@/lib/utils"; // Assuming you have this utility
import { Button } from "@/components/ui/button";

interface EngagementStats {
  communitySize: number;
  withoutPlanCount: number;
  scheduled: number;
  sent: number;
  rejected: number; // Consider if this needs to be displayed, or how
  conversations: number;
  waitingReplies: number;
  draftsReady: number;
  optedIn: number;
  optedOut: number;
  optInPending: number;
  received: number;
  sentLast7Days?: number;
  repliesLast7Days?: number;
}

interface BusinessProfile { // To fetch the display name
  business_name: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const { business_name: businessSlug } = useParams(); // Slug from URL

  const [stats, setStats] = useState<EngagementStats>({
    communitySize: 0, withoutPlanCount: 0, scheduled: 0, sent: 0, rejected: 0,
    conversations: 0, waitingReplies: 0, draftsReady: 0, optedIn: 0, optedOut: 0,
    optInPending: 0, received: 0, sentLast7Days: 0, repliesLast7Days: 0,
  });
  const [businessDisplayName, setBusinessDisplayName] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const currentBusinessSlug = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;
    if (!currentBusinessSlug) {
      setError("Business identifier is missing from URL.");
      setLoading(false);
      return;
    }
    // Format slug for display initially, will be overridden by fetched name
    const formattedSlug = currentBusinessSlug.replace(/-/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
    setBusinessDisplayName(formattedSlug);


    const fetchDashboardData = async () => {
      setLoading(true);
      setError(null);
      try {
        const businessRes = await apiClient.get<{ business_id: number }>(`/business-profile/business-id/slug/${currentBusinessSlug}`);
        const businessId = businessRes.data.business_id;

        if (!businessId) {
            throw new Error("Could not retrieve business ID.");
        }

        // Fetch business display name
        try {
            const profileRes = await apiClient.get<BusinessProfile>(`/business-profile/${businessId}`);
            if (profileRes.data?.business_name) {
                setBusinessDisplayName(profileRes.data.business_name);
            }
        } catch (profileError) {
            console.warn("Could not fetch full business profile for display name, using formatted slug.", profileError);
            // Keep formatted slug as display name
        }


        const [generalStatsRes, replyStatsRes] = await Promise.allSettled([
          apiClient.get(`/review/stats/${businessId}`),
          apiClient.get(`/review/reply-stats/${businessId}`),
        ]);

        const generalStats = generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data : {};
        const replyStats = replyStatsRes.status === "fulfilled" ? replyStatsRes.value.data : {};
        const receivedCount = replyStats.received_count ?? 0;

        setStats({
          communitySize: generalStats.communitySize ?? 0,
          withoutPlanCount: generalStats.withoutPlanCount ?? 0,
          scheduled: generalStats.scheduled ?? 0,
          sent: generalStats.sent ?? 0,
          rejected: generalStats.rejected ?? 0,
          optedIn: generalStats.optedIn ?? 0,
          optedOut: generalStats.optedOut ?? 0,
          optInPending: generalStats.optInPending ?? 0,
          conversations: generalStats.conversations ?? 0,
          waitingReplies: replyStats.customers_waiting ?? 0,
          draftsReady: replyStats.messages_total ?? 0,
          received: receivedCount,
          sentLast7Days: generalStats.sentLast7Days ?? 0,
          repliesLast7Days: generalStats.repliesLast7Days ?? 0,
        });

      } catch (err: any) {
        console.error("Failed to fetch dashboard stats:", err);
        setError(err.message || "Failed to load dashboard data. Please try refreshing.");
      } finally {
         setLoading(false);
      }
    };
    fetchDashboardData();
  }, [businessSlug]);

  if (loading) {
    return (
        <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6">
            <Loader2 className="h-12 w-12 animate-spin text-purple-400 mb-4" />
            <p className="text-xl text-slate-300">Loading Dashboard...</p>
            <p className="text-sm text-slate-400">Crunching the latest numbers for you.</p>
        </div>
    );
  }

  if (error) {
     return (
        <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6 text-center">
            <AlertTriangle className="h-16 w-16 text-red-500 mb-6" />
            <h2 className="text-2xl font-semibold text-red-400 mb-3">Oops! Dashboard Error</h2>
            <p className="text-slate-300 mb-6 max-w-md bg-red-900/30 border border-red-700/50 p-3 rounded-md">{error}</p>
            <Button onClick={() => window.location.reload()}
              className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-6 py-2 rounded-lg shadow-md hover:shadow-purple-500/30 transition-all"
            >
                Try Again
            </Button>
        </div>
     );
  }

  const currentBusinessSlugForUrl = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;

  // Card component for reusability (optional, but good for complex pages)
  const StatCard = ({ title, icon: Icon, iconColor, mainStat, statGradient, children, buttonText, buttonLink }: any) => (
    <div className="bg-slate-800/70 border border-slate-700/80 backdrop-blur-sm rounded-xl shadow-2xl p-6 flex flex-col justify-between transition-all duration-300 hover:shadow-purple-500/20 hover:border-purple-500/50">
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={cn("p-2.5 rounded-lg", statGradient.iconBg)}> {/* Dynamic icon bg */}
              <Icon className={cn("w-6 h-6", iconColor)} /> {/* Dynamic icon color */}
            </div>
            <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
          </div>
          {mainStat !== undefined && (
            <span className={cn("text-5xl font-bold bg-clip-text text-transparent", statGradient.text)}> {/* Dynamic stat gradient */}
              {mainStat}
            </span>
          )}
        </div>
        <div className="space-y-3 mb-6">
          {children}
        </div>
      </div>
      <Button
        onClick={() => router.push(buttonLink)}
        className="w-full bg-purple-600/90 hover:bg-purple-600 text-white py-2.5 px-4 rounded-lg transition-colors duration-200 flex items-center justify-center gap-2 text-sm font-medium shadow-md hover:shadow-purple-500/30"
      >
        {buttonText} <ArrowRight size={16} className="ml-1 group-hover:translate-x-1 transition-transform"/>
      </Button>
    </div>
  );


  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 md:py-12">
        <header className="mb-12 text-center md:text-left">
            <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-purple-400 via-pink-500 to-fuchsia-500 mb-2 flex items-center justify-center md:justify-start">
                <LayoutDashboard size={36} className="mr-4 opacity-90"/> Dashboard
            </h1>
            <p className="text-xl text-slate-300">
                Welcome to AI Nudge, <span className="font-semibold text-purple-300">{businessDisplayName || "Valued User"}</span>!
            </p>
            <p className="text-sm text-slate-400 mt-1">Here's an overview of your engagement activity.</p>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 md:gap-8">

          <StatCard
            title="Your Community"
            icon={Users}
            iconColor="text-sky-300"
            mainStat={stats.communitySize}
            statGradient={{ text: "bg-gradient-to-r from-sky-400 to-blue-500", iconBg: "bg-gradient-to-br from-sky-500/20 to-blue-600/20" }}
            buttonText="View Community"
            buttonLink={`/contacts/${currentBusinessSlugForUrl}`}
          >
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300 flex items-center gap-1.5"><OptInStatusBadge status="opted_in" size="sm" /> Opted-In</span>
              <span className="font-medium text-green-400">{stats.optedIn}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300 flex items-center gap-1.5"><OptInStatusBadge status="pending" size="sm" /> Pending Opt-in</span>
              <span className="font-medium text-yellow-400">{stats.optInPending}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300 flex items-center gap-1.5"><OptInStatusBadge status="opted_out" size="sm" /> Opted Out</span>
              <span className="font-medium text-red-400">{stats.optedOut}</span>
            </div>
          </StatCard>

          <StatCard
            title="Nudge Pipeline"
            icon={Send} // Or CalendarClock for scheduling focus
            iconColor="text-purple-300"
            mainStat={stats.scheduled} // Main stat is upcoming scheduled
            statGradient={{ text: "bg-gradient-to-r from-purple-400 to-pink-500", iconBg: "bg-gradient-to-br from-purple-500/20 to-pink-600/20" }}
            buttonText="Manage Plans"
            buttonLink={`/all-engagement-plans/${currentBusinessSlugForUrl}`}
          >
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <CalendarClock className="w-4 h-4 text-purple-400" />
                <span className="text-slate-300">Scheduled Nudges</span>
              </div>
              <span className="font-medium text-purple-300">{stats.scheduled}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Send className="w-4 h-4 text-sky-400" />
                <span className="text-slate-300">Sent This Week</span>
              </div>
              <span className="font-medium text-sky-400">{stats.sentLast7Days}</span>
            </div>
             <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-slate-400" />
                <span className="text-slate-300">Total Sent</span>
              </div>
              <span className="font-medium text-slate-400">{stats.sent}</span>
            </div>
          </StatCard>

          <StatCard
            title="Reply Center"
            icon={MailCheck}
            iconColor="text-pink-300"
            mainStat={stats.waitingReplies}
            statGradient={{ text: "bg-gradient-to-r from-pink-400 to-fuchsia-500", iconBg: "bg-gradient-to-br from-pink-500/20 to-fuchsia-600/20" }}
            buttonText="Review & Reply"
            buttonLink={`/replies/${currentBusinessSlugForUrl}`}
          >
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-1.5">
                <MailCheck className="w-4 h-4 text-pink-400" />
                <span className="text-slate-300">Customers Waiting</span>
              </div>
              <span className="font-medium text-pink-400">{stats.waitingReplies}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                 <Lightbulb className="w-4 h-4 text-yellow-400" /> {/* Changed Icon */}
                 <span className="text-slate-300">AI Drafts Ready</span>
               </div>
              <span className="font-medium text-yellow-400">{stats.draftsReady}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-slate-400" />
                <span className="text-slate-300">Replies This Week</span>
              </div>
              <span className="font-medium text-slate-400">{stats.repliesLast7Days}</span>
            </div>
          </StatCard>

          <StatCard
            title="Message History"
            icon={MessageSquare}
            iconColor="text-teal-300"
            mainStat={stats.received + stats.sent} // Combined for total interactions
            statGradient={{ text: "bg-gradient-to-r from-teal-400 to-cyan-500", iconBg: "bg-gradient-to-br from-teal-500/20 to-cyan-600/20" }}
            buttonText="Open Inbox"
            buttonLink={`/inbox/${currentBusinessSlugForUrl}`}
          >
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-1.5">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-teal-400">
                  <path fillRule="evenodd" d="M3.25 4.5A.75.75 0 002.5 5.25v9.5c0 .414.336.75.75.75h11.5a.75.75 0 000-1.5H3.25V5.25A.75.75 0 003.25 4.5z" clipRule="evenodd" />
                  <path d="M6.25 2.5a.75.75 0 00-.75.75vrasında.5a.75.75 0 00.75.75h11.5a.75.75 0 00.75-.75v-9.5a.75.75 0 00-.75-.75H6.25zM7 4a.5.5 0 01.5-.5h10a.5.5 0 01.5.5v8.5a.5.5 0 01-.5.5h-10a.5.5 0 01-.5-.5V4z" />
                </svg> {/* Inbox icon-like for received */}
                <span className="text-slate-300">Total Received</span>
              </div>
              <span className="font-medium text-teal-400">{stats.received}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <Send className="w-4 h-4 text-sky-400" />
                <span className="text-slate-300">Total Sent</span>
              </div>
              <span className="font-medium text-sky-400">{stats.sent}</span>
            </div>
             <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-slate-400" />
                <span className="text-slate-300">Total Interactions</span>
              </div>
              <span className="font-medium text-slate-400">{stats.sent + stats.received}</span>
            </div>
          </StatCard>

        </div>
      </div>
    </div>
  );
}