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
import { OptInStatusBadge } from "@/components/OptInStatus";

interface EngagementStats {
  communitySize: number;
  withoutPlanCount: number;
  pending: number;
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
}

const tooltipTextMap: Record<string, string> = {
  "Community Size": "Total number of contacts in your community.",
  "Community Outreach Plan": "Overview of your message delivery pipeline.",
  "Community Responses": "Contacts who replied and are waiting on your response.",
  "Open Conversations": "Full chat history with each contact.",
};

export default function DashboardPage() {
  const router = useRouter();
  const { business_name } = useParams();

  const [stats, setStats] = useState<EngagementStats>({
    communitySize: 0,
    withoutPlanCount: 0,
    pending: 0,
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
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const business = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);

        const [generalStatsRes, replyStatsRes, receivedStatsRes] = await Promise.allSettled([
          apiClient.get(`/review/stats/${business.data.business_id}`),
          apiClient.get(`/review/reply-stats/${business.data.business_id}`),
          apiClient.get(`/review/received-messages/${business.data.business_id}`)
        ]);

        setStats({
          communitySize: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.communitySize ?? 0 : 0,
          withoutPlanCount: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.withoutPlanCount ?? 0 : 0,
          pending: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.pending ?? 0 : 0,
          scheduled: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.scheduled ?? 0 : 0,
          sent: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.sent ?? 0 : 0,
          rejected: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.rejected ?? 0 : 0,
          optedIn: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.optedIn ?? 0 : 0,
          optedOut: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.optedOut ?? 0 : 0,
          optInPending: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.optInPending ?? 0 : 0,
          conversations: generalStatsRes.status === "fulfilled" ? generalStatsRes.value.data.conversations ?? 0 : 0,
          waitingReplies: replyStatsRes.status === "fulfilled" ? replyStatsRes.value.data.customers_waiting ?? 0 : 0,
          draftsReady: replyStatsRes.status === "fulfilled" ? replyStatsRes.value.data.messages_total ?? 0 : 0,
          received: receivedStatsRes.status === "fulfilled" ? receivedStatsRes.value.data.received_count ?? 0 : 0,
        });
      } catch (err) {
        console.error("Failed to fetch dashboard stats:", err);
        router.push("/error");
      }
    };
    fetchStats();
  }, [business_name, router]);

  return (
    <div className="min-h-screen bg-nudge-gradient">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Main Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Community Size Card */}
          <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 shadow-lg hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-emerald-400/10 to-blue-500/10 rounded-lg">
                  <Users className="w-5 h-5 text-emerald-400" />
                </div>
                <h2 className="text-lg font-semibold text-white">Community Size</h2>
              </div>
              <span className="text-4xl font-bold bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">
                {stats.communitySize}
              </span>
            </div>
            
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <OptInStatusBadge status="opted_in" size="sm" />
                <span className="font-medium text-emerald-400">{stats.optedIn}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <OptInStatusBadge status="waiting" size="sm" />
                <span className="font-medium text-yellow-400">{stats.optInPending}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <OptInStatusBadge status="opted_out" size="sm" />
                <span className="font-medium text-red-400">{stats.optedOut}</span>
              </div>
            </div>

            <button
              onClick={() => router.push(`/contacts/${business_name}`)}
              className="mt-6 w-full bg-[#242842] hover:bg-[#2A2F45] text-white py-2.5 px-4 rounded-lg 
                transition-colors duration-200 flex items-center justify-center gap-2 text-sm font-medium"
            >
              View Community
            </button>
          </div>

          {/* Outreach Plan Card */}
          <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 shadow-lg hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-blue-400/10 to-purple-500/10 rounded-lg">
                  <Send className="w-5 h-5 text-blue-400" />
                </div>
                <h2 className="text-lg font-semibold text-white">Community Nudge Plan</h2>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <Clock className="w-4 h-4 text-yellow-400" />
                  <span className="text-gray-300">Pending</span>
                </div>
                <span className="font-medium text-yellow-400">{stats.pending}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <CalendarClock className="w-4 h-4 text-emerald-400" />
                  <span className="text-gray-300">Scheduled</span>
                </div>
                <span className="font-medium text-emerald-400">{stats.scheduled}</span>
              </div>
            </div>

            <button
              onClick={() => router.push(`/all-engagement-plans/${business_name}`)}
              className="mt-6 w-full bg-[#242842] hover:bg-[#2A2F45] text-white py-2.5 px-4 rounded-lg 
                transition-colors duration-200 flex items-center justify-center gap-2 text-sm font-medium"
            >
              Manage Plans
            </button>
          </div>

          {/* Responses Card */}
          <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 shadow-lg hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-purple-400/10 to-pink-500/10 rounded-lg">
                  <MailCheck className="w-5 h-5 text-purple-400" />
                </div>
                <h2 className="text-lg font-semibold text-white">Community Responses</h2>
              </div>
              <span className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-pink-500 bg-clip-text text-transparent">
                {stats.waitingReplies}
              </span>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <MailCheck className="w-4 h-4 text-purple-400" />
                  <span className="text-gray-300">Waiting</span>
                </div>
                <span className="font-medium text-purple-400">{stats.waitingReplies}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <TrendingUp className="w-4 h-4 text-pink-400" />
                  <span className="text-gray-300">AI Drafts</span>
                </div>
                <span className="font-medium text-pink-400">{stats.draftsReady}</span>
              </div>
            </div>

            <button
              onClick={() => router.push(`/replies/${business_name}`)}
              className="mt-6 w-full bg-[#242842] hover:bg-[#2A2F45] text-white py-2.5 px-4 rounded-lg 
                transition-colors duration-200 flex items-center justify-center gap-2 text-sm font-medium"
            >
              Review & Reply
            </button>
          </div>

          {/* Inbox Card */}
          <div className="bg-[#1A1D2D] rounded-xl border border-[#2A2F45] p-6 shadow-lg hover:shadow-xl transition-all duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-gradient-to-br from-cyan-400/10 to-blue-500/10 rounded-lg">
                  <MessageSquare className="w-5 h-5 text-cyan-400" />
                </div>
                <h2 className="text-lg font-semibold text-white">Community Inbox</h2>
              </div>
              <span className="text-4xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                {stats.sent}
              </span>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <Send className="w-4 h-4 text-cyan-400" />
                  <span className="text-gray-300">Messages Received</span>
                </div>
                <span className="font-medium text-cyan-400">{stats.received}</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <Send className="w-4 h-4 text-cyan-400" />
                  <span className="text-gray-300">Messages Sent</span>
                </div>
                <span className="font-medium text-cyan-400">{stats.sent}</span>
              </div>
            </div>

            <button
              onClick={() => router.push(`/inbox/${business_name}`)}
              className="mt-6 w-full bg-[#242842] hover:bg-[#2A2F45] text-white py-2.5 px-4 rounded-lg 
                transition-colors duration-200 flex items-center justify-center gap-2 text-sm font-medium"
            >
              Open Inbox
            </button>
          </div>
        </div>

        {/* Instant Nudge Button */}
        <button
          onClick={() => router.push(`/instant-nudge/${business_name}`)}
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
