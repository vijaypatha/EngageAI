"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import {
  Users,
  Send,
  MailCheck,
  MessageSquare,
  Bot,
  Clock,
  CalendarClock,
  XCircle,
} from "lucide-react";

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
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const business = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);

        const [generalStatsRes, replyStatsRes] = await Promise.all([
          apiClient.get(`/review/stats/${business.data.business_id}`),
          apiClient.get(`/review/reply-stats/${business.data.business_id}`)
        ]);

        setStats({
          communitySize: generalStatsRes.data.communitySize ?? 0,
          withoutPlanCount: generalStatsRes.data.withoutPlanCount ?? 0,
          pending: generalStatsRes.data.pending ?? 0,
          scheduled: generalStatsRes.data.scheduled ?? 0,
          sent: generalStatsRes.data.sent ?? 0,
          rejected: generalStatsRes.data.rejected ?? 0,
          conversations: generalStatsRes.data.conversations ?? 0,
          waitingReplies: replyStatsRes.data.customers_waiting ?? 0,
          draftsReady: replyStatsRes.data.messages_total ?? 0,
        });
      } catch (err) {
        console.error("Failed to fetch dashboard stats:", err);
        router.push("/error");
      }
    };
    fetchStats();
  }, [business_name, router]);

  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-6 py-12">
      <h1 className="text-4xl font-bold mb-2">Welcome back 👋</h1>
      <p className="text-gray-400 mb-10">Here’s your business overview</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <Tile
          icon={<Users size={22} />}
          title="Community Size"
          stat={stats.communitySize ?? 0}
          subtitle={`${stats.withoutPlanCount ?? 0} contacts without engagement plan`}
          buttonText="Manage Community"
          onClick={() => router.push(`/contacts/${business_name}`)}
        />

        <Tile
          icon={<Send size={22} />}
          title="Community Outreach Plan"
          subtitle="Planned nudges to your community"
          statSection={
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-white">
              <span className="flex items-center gap-1 text-yellow-400"><Clock size={14} /> {stats.pending} Pending</span>
              <span className="flex items-center gap-1 text-green-400"><CalendarClock size={14} /> {stats.scheduled} Scheduled</span>
            </div>
          }
          buttonText="Manage Plans"
          onClick={() => router.push(`/all-engagement-plans/${business_name}`)}
        />

        <Tile
          icon={<MailCheck size={22} />}
          title="Community Responses"
          stat={stats.waitingReplies}
          subtitle={`${stats.waitingReplies ?? 0} contact waiting on your reply` + ((stats.draftsReady ?? 0) > 0 ? `\n${stats.draftsReady} response drafts ready for you ❤️` : '')}
          buttonText="Review & Reply"
          onClick={() => router.push(`/replies/${business_name}`)}
        />

        <Tile
          icon={<MessageSquare size={22} />}
          title="Community Inbox"
          subtitle="Nudge history with contacts in your community"
          statSection={
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-white">
              <span className="flex items-center gap-1 text-white"><Send size={14} /> {stats.sent} Sent</span>
            </div>
          }
          buttonText="Open Conversations"
          onClick={() => router.push(`/inbox/${business_name}`)}
        />
      </div>

      <button
        onClick={() => router.push(`/instant-nudge/${business_name}`)}
        className="fixed bottom-6 right-6 z-50 bg-gradient-to-r from-fuchsia-500 to-cyan-500 text-white px-6 py-3 rounded-full shadow-2xl hover:scale-105 transition-all duration-300 font-bold text-sm md:text-base tracking-wide"
      >
        ✨ Instant Nudge
      </button>
    </div>
  );
}

function Tile({
  icon,
  title,
  stat,
  statSection,
  subtitle,
  buttonText,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  stat?: number;
  statSection?: React.ReactNode;
  subtitle?: string;
  buttonText: string;
  onClick: () => void;
}) {
  return (
    <div className="rounded-xl bg-[#1f1f1f] p-6 shadow-md text-white flex flex-col justify-between min-h-[200px]">
      <div>
        <div className="flex items-center gap-2 mb-4">
          {icon}
          <h2 className="text-xl font-bold text-white">{title}</h2>
        </div>

        {typeof stat === "number" ? (
          <div className="text-3xl font-bold text-green-400 mb-1">{stat}</div>
        ) : null}

        {statSection && <div className="mb-2">{statSection}</div>}

        {subtitle && <p className="text-gray-400 text-sm whitespace-pre-line">{subtitle}</p>}
      </div>

      <button
        onClick={onClick}
        className="mt-4 bg-gradient-to-r from-blue-500 to-purple-500 hover:scale-105 transition-transform text-white py-2 px-4 rounded-lg font-semibold"
      >
        {buttonText}
      </button>
    </div>
  );
}
