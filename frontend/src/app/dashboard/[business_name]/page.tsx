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
  CalendarClock,
  TrendingUp,
  LayoutDashboard,
  Loader2,
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Lightbulb, // Kept Lightbulb for AI Drafts
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface EngagementStats {
  communitySize: number;
  withoutPlanCount: number;
  scheduled: number;
  sent: number;
  rejected: number;
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

interface BusinessProfile {
  business_name: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const { business_name: businessSlug } = useParams();

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
    const formattedSlug = decodeURIComponent(currentBusinessSlug).replace(/-/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
    setBusinessDisplayName(formattedSlug);

    const fetchDashboardData = async () => {
      setLoading(true); setError(null);
      try {
        const businessRes = await apiClient.get<{ business_id: number }>(`/business-profile/business-id/slug/${currentBusinessSlug}`);
        const businessId = businessRes.data.business_id;
        if (!businessId) throw new Error("Could not retrieve business ID.");

        try {
            const profileRes = await apiClient.get<BusinessProfile>(`/business-profile/${businessId}`);
            if (profileRes.data?.business_name) setBusinessDisplayName(profileRes.data.business_name);
        } catch (profileError) { console.warn("Could not fetch business profile name.", profileError); }

        const [generalStatsRes, replyStatsRes] = await Promise.allSettled([
          apiClient.get(`/review/stats/${businessId}`),
          apiClient.get(`/review/reply-stats/${businessId}`),
        ]);

        const generalStats = generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data : {};
        const replyStats = replyStatsRes.status === "fulfilled" ? replyStatsRes.value.data : {};
        
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
          received: replyStats.received_count ?? 0,
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
            <Loader2 className="h-12 w-12 animate-spin text-purple-500 mb-4" />
            <p className="text-xl text-slate-300">Loading Dashboard...</p>
            <p className="text-sm text-slate-400">Fetching your latest engagement data.</p>
        </div>
    );
  }

  if (error) {
     return (
        <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6 text-center">
            <AlertTriangle className="h-16 w-16 text-red-500 mb-6" />
            <h2 className="text-2xl font-semibold text-red-400 mb-3">Dashboard Error</h2>
            <p className="text-slate-300 mb-6 max-w-md bg-slate-800 border border-red-700/50 p-4 rounded-md">{error}</p>
            <Button onClick={() => window.location.reload()}
              className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-6 py-2.5 rounded-lg shadow-md hover:shadow-purple-500/40 transition-all"
            >
                Try Again
            </Button>
        </div>
     );
  }

  const currentBusinessSlugForUrl = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;

  const StatCard = ({ title, icon: Icon, mainStat, mainStatColor = "text-teal-400", iconColorOverride, buttonText, buttonLink, children }: any) => (
    <div className="bg-slate-800 border border-slate-700/80 rounded-xl shadow-lg p-6 flex flex-col justify-between transition-shadow hover:shadow-xl hover:shadow-purple-500/10">
      <div>
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <Icon className={cn("w-7 h-7", iconColorOverride || mainStatColor)} />
            <h2 className="text-md font-semibold text-slate-200 pt-0.5">{title}</h2>
          </div>
          {mainStat !== undefined && (
            <span className={cn("text-5xl font-bold", mainStatColor)}>
              {mainStat}
            </span>
          )}
        </div>
        <div className="space-y-2.5 mb-6">
          {children}
        </div>
      </div>
      <Button
        onClick={() => router.push(buttonLink)}
        className="w-full bg-purple-600 hover:bg-purple-700 focus-visible:ring-2 focus-visible:ring-purple-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-800 text-white py-2.5 px-4 rounded-md transition-colors duration-200 flex items-center justify-center gap-1.5 text-sm font-medium"
      >
        {buttonText} <ArrowRight size={16} className="ml-1"/>
      </Button>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-10">
        <header className="mb-10 md:mb-12">
            <h1 className="text-4xl md:text-5xl font-bold mb-1.5 flex items-center">
                <LayoutDashboard size={38} className="mr-3 text-purple-400"/> {/* Main Icon Purple */}
                <span className="text-teal-400">{businessDisplayName || "Business"}</span>
                <span className="text-purple-400 ml-2">Dashboard</span>
            </h1>
            <p className="text-sm text-slate-400 md:ml-[50px]"> {/* Align with text start */}
                Here's a quick overview of your engagement activity.
            </p>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 md:gap-6">

          <StatCard
            title="Your Community"
            icon={Users}
            mainStat={stats.communitySize}
            mainStatColor="text-teal-400" // Teal for this card's main stat & icon
            buttonText="View Community"
            buttonLink={`/contacts/${currentBusinessSlugForUrl}`}
          >
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300 flex items-center gap-1.5"><CheckCircle size={15} className="text-green-500"/> Messages On</span>
              <span className="font-medium text-green-400">{stats.optedIn > 0 ? 'Active' : '0'}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Opt-in</span>
              <span className="font-medium text-green-400">{stats.optedIn}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Pending Opt-in</span>
              <span className="font-medium text-yellow-400">{stats.optInPending}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Opted Out</span>
              <span className="font-medium text-red-400">{stats.optedOut}</span>
            </div>
          </StatCard>

          <StatCard
            title="Nudge Pipeline"
            icon={Send}
            mainStat={stats.scheduled}
            mainStatColor="text-purple-400" // Purple for this card's main stat & icon
            buttonText="Manage Plans"
            buttonLink={`/all-engagement-plans/${currentBusinessSlugForUrl}`}
          >
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Scheduled Nudges</span>
              <span className="font-medium text-slate-200">{stats.scheduled}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Sent This Week</span>
              <span className="font-medium text-slate-200">{stats.sentLast7Days}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Total Sent</span>
              <span className="font-medium text-slate-200">{stats.sent}</span>
            </div>
          </StatCard>

          <StatCard
            title="Reply Center"
            icon={MailCheck}
            mainStat={stats.waitingReplies}
            mainStatColor="text-teal-400" // Teal for this card
            buttonText="Review & Reply"
            buttonLink={`/replies/${currentBusinessSlugForUrl}`}
          >
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Customers Waiting</span>
              <span className="font-medium text-slate-200">{stats.waitingReplies}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
               <span className="text-slate-300">AI Drafts Ready</span>
              <span className="font-medium text-slate-200">{stats.draftsReady}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Replies This Week</span>
              <span className="font-medium text-slate-200">{stats.repliesLast7Days}</span>
            </div>
          </StatCard>

          <StatCard
            title="Message History"
            icon={MessageSquare}
            mainStat={stats.sent + stats.received}
            mainStatColor="text-purple-400" // Purple for this card
            buttonText="Open Inbox"
            buttonLink={`/inbox/${currentBusinessSlugForUrl}`}
          >
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Total Received</span>
              <span className="font-medium text-slate-200">{stats.received}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Total Sent</span>
              <span className="font-medium text-slate-200">{stats.sent}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-300">Total Interactions</span>
              <span className="font-medium text-slate-200">{stats.sent + stats.received}</span>
            </div>
          </StatCard>

        </div>
      </div>
    </div>
  );
}