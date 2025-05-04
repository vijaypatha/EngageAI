"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import {
  Users,
  Send,
  MailCheck,
  MessageSquare,
  Clock,
  CalendarClock,
  TrendingUp,
} from "lucide-react";
import { OptInStatusBadge } from "@/components/OptInStatus"; // Ensure path is correct

interface EngagementStats {
  communitySize: number;
  withoutPlanCount: number;
  // pending: number; // Removed pending for outgoing messages
  scheduled: number; // Upcoming scheduled messages
  sent: number; // Total historical sent messages
  rejected: number;
  conversations: number; // Placeholder or future use
  waitingReplies: number; // Unique customers with pending AI drafts
  draftsReady: number; // Total count of pending AI drafts
  optedIn: number;
  optedOut: number;
  optInPending: number;
  received: number; // Total historical received messages
  sentLast7Days?: number; // Optional: recent sent
  repliesLast7Days?: number; // Optional: recent replies
}

export default function DashboardPage() {
  const router = useRouter();
  const { business_name } = useParams(); // This should be type string | string[]

  const [stats, setStats] = useState<EngagementStats>({
    communitySize: 0,
    withoutPlanCount: 0,
    // pending: 0, // Removed
    scheduled: 0,
    sent: 0,
    rejected: 0,
    conversations: 0,
    waitingReplies: 0,
    draftsReady: 0,
    optedIn: 0,
    optedOut: 0,
    optInPending: 0,
    received: 0,
    sentLast7Days: 0,
    repliesLast7Days: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Ensure business_name is a string before making API calls
    const currentBusinessName = Array.isArray(business_name) ? business_name[0] : business_name;
    if (!currentBusinessName) {
      // Handle case where business_name is missing, maybe redirect or show error
      console.error("Business name is missing from URL params.");
      setError("Business identifier is missing.");
      setLoading(false);
      return;
    }

    const fetchStats = async () => {
      setLoading(true);
      setError(null);
      try {
        // Fetch business ID first
        const businessRes = await apiClient.get(`/business-profile/business-id/slug/${currentBusinessName}`);
        const businessId = businessRes.data.business_id;

        if (!businessId) {
            throw new Error("Could not retrieve business ID.");
        }

         // Fetch stats concurrently (only two calls now)
         const [generalStatsRes, replyStatsRes] = await Promise.allSettled([ // <<< Only expect 2 results
          apiClient.get(`/review/stats/${businessId}`), // Gets main stats including recent activity
          apiClient.get(`/review/reply-stats/${businessId}`), // Gets draft/waiting/received counts
        ]);

        // Process results and update state
        const generalStats = generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data : {};
        const replyStats = replyStatsRes.status === "fulfilled" ? replyStatsRes.value.data : {};
        // receivedStats is now included in replyStats or generalStats potentially
        // Let's assume received count comes from replyStats now based on backend refactor
        const receivedCount = replyStats.received_count ?? 0;

        setStats({
          communitySize: generalStats.communitySize ?? 0,
          withoutPlanCount: generalStats.withoutPlanCount ?? 0,
          // pending: generalStats.pending ?? 0, // Removed pending
          scheduled: generalStats.scheduled ?? 0, // Upcoming scheduled
          sent: generalStats.sent ?? 0, // Total historical sent
          rejected: generalStats.rejected ?? 0,
          optedIn: generalStats.optedIn ?? 0,
          optedOut: generalStats.optedOut ?? 0,
          optInPending: generalStats.optInPending ?? 0,
          conversations: generalStats.conversations ?? 0, // Placeholder
          waitingReplies: replyStats.customers_waiting ?? 0, // Unique customers waiting
          draftsReady: replyStats.messages_total ?? 0, // Total drafts ready
          received: receivedCount, // Total received from replyStats
          sentLast7Days: generalStats.sentLast7Days ?? 0, // Recent activity
          repliesLast7Days: generalStats.repliesLast7Days ?? 0, // Recent activity
        });

      } catch (err: any) {
        console.error("Failed to fetch dashboard stats:", err);
        setError(err.message || "Failed to load dashboard data.");
        // Optionally redirect to an error page or show error state
        // router.push("/error");
      } finally {
         setLoading(false);
      }
    };
    fetchStats();
  }, [business_name, router]); // Depend on business_name

  // Handle Loading and Error States
  if (loading) {
    return <div className="min-h-screen bg-nudge-gradient flex items-center justify-center"><p className="text-white text-xl">Loading Dashboard...</p></div>;
  }

  if (error) {
     return <div className="min-h-screen bg-nudge-gradient flex items-center justify-center"><p className="text-red-400 text-xl">Error: {error}</p></div>;
  }

  const currentBusinessNameStr = Array.isArray(business_name) ? business_name[0] : business_name;

  return (
    <div className="min-h-screen bg-nudge-gradient">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Main Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">

          {/* Community Card */}
          <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 shadow-lg hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-emerald-400/10 to-blue-500/10 rounded-lg">
                  <Users className="w-5 h-5 text-emerald-400" />
                </div>
                <h2 className="text-lg font-semibold text-white">Your Community</h2>
              </div>
              <span className="text-4xl font-bold bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">
                {stats.communitySize}
              </span>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                 <span className="text-gray-300 flex items-center gap-1.5"><OptInStatusBadge status="opted_in" size="sm" /> Engaged</span>
                <span className="font-medium text-emerald-400">{stats.optedIn}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                 <span className="text-gray-300 flex items-center gap-1.5"><OptInStatusBadge status="waiting" size="sm" /> Pending Opt-in</span>
                <span className="font-medium text-yellow-400">{stats.optInPending}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                 <span className="text-gray-300 flex items-center gap-1.5"><OptInStatusBadge status="opted_out" size="sm" /> Opted Out</span>
                <span className="font-medium text-red-400">{stats.optedOut}</span>
              </div>
            </div>

            <button
              onClick={() => router.push(`/contacts/${currentBusinessNameStr}`)}
              className="mt-6 w-full bg-[#242842] hover:bg-[#2A2F45] text-white py-2.5 px-4 rounded-lg
                transition-colors duration-200 flex items-center justify-center gap-2 text-sm font-medium"
            >
              View Community
            </button>
          </div>

          {/* Nudge Pipeline Card */}
          <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 shadow-lg hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-blue-400/10 to-purple-500/10 rounded-lg">
                  <Send className="w-5 h-5 text-blue-400" />
                </div>
                <h2 className="text-lg font-semibold text-white">Nudge Pipeline</h2>
              </div>
               {/* Optionally show total scheduled count if desired */}
               {/* <span className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                 {stats.scheduled}
               </span> */}
            </div>

            <div className="space-y-3">
              {/* Removed the 'Pending' row */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <CalendarClock className="w-4 h-4 text-emerald-400" />
                  <span className="text-gray-300">Scheduled Nudges</span>
                </div>
                <span className="font-medium text-emerald-400">{stats.scheduled}</span>
              </div>
               {/* Optionally add 'Sent Recently' */}
               <div className="flex items-center justify-between">
                 <div className="flex items-center gap-2 text-sm">
                   <Send className="w-4 h-4 text-cyan-400" />
                   <span className="text-gray-300">Sent This Week</span>
                 </div>
                 <span className="font-medium text-cyan-400">{stats.sentLast7Days}</span>
               </div>
            </div>

            <button
              onClick={() => router.push(`/all-engagement-plans/${currentBusinessNameStr}`)}
              className="mt-6 w-full bg-[#242842] hover:bg-[#2A2F45] text-white py-2.5 px-4 rounded-lg
                transition-colors duration-200 flex items-center justify-center gap-2 text-sm font-medium"
            >
              Manage Plans
            </button>
          </div>

          {/* Reply Center Card */}
          <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 shadow-lg hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-purple-400/10 to-pink-500/10 rounded-lg">
                  <MailCheck className="w-5 h-5 text-purple-400" />
                </div>
                <h2 className="text-lg font-semibold text-white">Reply Center</h2>
              </div>
              <span className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">
                {stats.waitingReplies}
              </span> {/* Shows unique customers waiting */}
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-sm">
                  <MailCheck className="w-4 h-4 text-purple-400" />
                  <span className="text-gray-300">Customers Waiting</span>
                </div>
                <span className="font-medium text-purple-400">{stats.waitingReplies}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                   <TrendingUp className="w-4 h-4 text-pink-400" />
                   <span className="text-gray-300">AI Drafts Ready</span>
                 </div>
                <span className="font-medium text-pink-400">{stats.draftsReady}</span> {/* Shows total drafts */}
              </div>
               {/* Optionally add 'Received Recently' */}
               <div className="flex items-center justify-between">
                 <div className="flex items-center gap-2 text-sm">
                   <MessageSquare className="w-4 h-4 text-gray-400" /> {/* Consistent icon */}
                   <span className="text-gray-300">Replies This Week</span>
                 </div>
                 <span className="font-medium text-gray-400">{stats.repliesLast7Days}</span>
               </div>
            </div>

            <button
              onClick={() => router.push(`/replies/${currentBusinessNameStr}`)}
              className="mt-6 w-full bg-[#242842] hover:bg-[#2A2F45] text-white py-2.5 px-4 rounded-lg
                transition-colors duration-200 flex items-center justify-center gap-2 text-sm font-medium"
            >
              Review & Reply
            </button>
          </div>

          {/* Message History Card */}
          <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 shadow-lg hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-cyan-400/10 to-blue-500/10 rounded-lg">
                  <MessageSquare className="w-5 h-5 text-cyan-400" />
                </div>
                <h2 className="text-lg font-semibold text-white">Message History</h2>
              </div>
              <span className="text-4xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                {stats.received}
              </span> {/* Shows total received */}
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-sm">
                  <MessageSquare className="w-4 h-4 text-cyan-400" /> {/* Use MessageSquare */}
                  <span className="text-gray-300">Total Received</span>
                </div>
                <span className="font-medium text-cyan-400">{stats.received}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <Send className="w-4 h-4 text-emerald-400" />
                  <span className="text-gray-300">Total Sent</span>
                </div>
                <span className="font-medium text-emerald-400">{stats.sent}</span>
              </div>
            </div>

            <button
              onClick={() => router.push(`/inbox/${currentBusinessNameStr}`)}
              className="mt-6 w-full bg-[#242842] hover:bg-[#2A2F45] text-white py-2.5 px-4 rounded-lg
                transition-colors duration-200 flex items-center justify-center gap-2 text-sm font-medium"
            >
              Open Inbox
            </button>
          </div>
        </div>

        {/* Instant Nudge Button */}
        <button
          onClick={() => router.push(`/instant-nudge/${currentBusinessNameStr}`)}
          className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-emerald-400 to-blue-500
            text-white px-6 py-3 rounded-full shadow-xl hover:shadow-2xl hover:scale-105
            transition-all duration-300 font-medium text-sm md:text-base"
        >
          ✨ Instant Nudge
        </button>
      </div>
    </div>
  );
}