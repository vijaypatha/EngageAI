"use client";

import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { getCurrentBusiness } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Clock,
  XCircle,
  CalendarClock,
  Send,
  Users,
  Bot,
  MailCheck,
  MessageSquare,
} from "lucide-react";
import StatItem from "@/components/ui/StatItem";

// 📌 Type definitions
interface BusinessProfile {
  business_name: string;
}

interface Customer {
  id: number;
  customer_name: string;
  engagement_planned: boolean;
}

interface EngagementStats {
  pending: number;
  scheduled: number;
  sent: number;
  rejected: number;
}

const SMSStyleForm = ({ businessId, onComplete }: { businessId: string; onComplete: () => void }) => {
  const [styleText, setStyleText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await apiClient.post(`/sms-style/response/${businessId}`, {
        sms_style_text: styleText,
      });
      onComplete();
    } catch (err) {
      console.error("Failed to submit SMS style:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-black text-white flex items-center justify-center text-xl">
      <div className="max-w-md text-center">
        <h2 className="text-2xl font-bold mb-4">Train your SMS style</h2>
        <textarea
          className="w-full text-black p-2 mb-4"
          rows={4}
          placeholder="Type how you normally write your messages..."
          value={styleText}
          onChange={(e) => setStyleText(e.target.value)}
        />
        <Button onClick={handleSubmit} disabled={submitting || !styleText}>
          {submitting ? "Saving..." : "Save & Continue"}
        </Button>
      </div>
    </div>
  );
};

const AddCustomerForm = ({ businessId, onComplete }: { businessId: string; onComplete: () => void }) => {
  const [customerName, setCustomerName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleAddCustomer = async () => {
    setSubmitting(true);
    try {
      await apiClient.post("/customers/", {
        business_id: businessId,
        customer_name: customerName,
      });
      onComplete();
    } catch (err) {
      console.error("Failed to add customer:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-black text-white flex items-center justify-center text-xl">
      <div className="max-w-md text-center">
        <h2 className="text-2xl font-bold mb-4">Add your first customer</h2>
        <input
          type="text"
          className="w-full text-black p-2 mb-4"
          placeholder="Customer name"
          value={customerName}
          onChange={(e) => setCustomerName(e.target.value)}
        />
        <Button onClick={handleAddCustomer} disabled={submitting || !customerName}>
          {submitting ? "Adding..." : "Add & Continue"}
        </Button>
      </div>
    </div>
  );
};

export default function DashboardPage() {
  const params = useParams();
  const business_name = params?.business_name as string;
  const [businessId, setBusinessId] = useState<string | null>(null);
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [engagementStats, setEngagementStats] = useState<EngagementStats | null>(null);
  const [contactStats, setContactStats] = useState({ total_customers: 0, without_engagement: 0 });
  const [replyStats, setReplyStats] = useState({
    customers_waiting: 0,
    messages_total: 0,
  });
  const [aiStyleTrained, setAiStyleTrained] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);

  const router = useRouter();
  useEffect(() => {
    console.log("✅ API BASE =", process.env.NEXT_PUBLIC_API_BASE);
  
    if (!business_name) {
      window.location.href = "/";
      return;
    }

    const init = async () => {
      try {
        const res = await axios.get(
          `${process.env.NEXT_PUBLIC_API_BASE}/business-profile/business-id/${business_name}`
        );
        const businessId = res.data.business_id;
        setBusinessId(businessId);
  
        // ⏬ Move your existing fetch logic here
        const [profileRes, customersRes] = await Promise.all([
          apiClient.get(`/business-profile/${businessId}`),
          apiClient.get(`/customers/by-business/${businessId}`),
        ]);
  
        setBusinessProfile(profileRes.data);
        setCustomers(customersRes.data);
  
        const [statsRes, contactRes, styleRes, replyRes] = await Promise.all([
          apiClient.get(`/review/stats/${businessId}`).catch(() => null),
          apiClient.get(`/review/customers/without-engagement-count/${businessId}`).catch(() => null),
          apiClient.get(`/sms-style/response/${businessId}`).catch(() => null),
          apiClient.get(`/review/reply-stats/${businessId}`).catch(() => null),
        ]);
  
        if (statsRes) setEngagementStats(statsRes.data);
        if (contactRes) setContactStats(contactRes.data);
        if (styleRes) setAiStyleTrained(styleRes.data.length > 0);
        if (replyRes) setReplyStats(replyRes.data);
      } catch (err) {
        console.error("Failed to fetch business ID:", err);
        window.location.href = "/";
        return;
      } finally {
        setLoading(false);
      }
    };
  
    init(); // 🔁 Call the inner async function
  }, [business_name]);

  if (!businessId) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center text-xl">
        Loading dashboard...
      </div>
    );
  }

  // 📦 Utility render helpers
  const renderTileHeader = (icon: React.ReactNode, title: string) => (
    <h2 className="text-2xl font-extrabold text-zinc-100 mb-4 flex items-center gap-2">
      {icon} {title}
    </h2>
  );

  const renderTileButton = (label: string, onClick: () => void) => (
    <Button
      className="w-full bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600 text-white font-semibold transition duration-300 shadow-lg"
      onClick={onClick}
    >
      {label}
    </Button>
  );

  // ⏳ Show loading screen while data fetch is in progress
  if (loading) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center text-xl">
        Loading...
      </div>
    );
  }

  if (!aiStyleTrained) {
    return <SMSStyleForm businessId={businessId!} onComplete={() => setAiStyleTrained(true)} />;
  }

  if (customers.length === 0) {
    return <AddCustomerForm businessId={businessId!} onComplete={async () => {
      const customersRes = await apiClient.get(`/customers/by-business/${businessId}`);
      setCustomers(customersRes.data);
    }} />;
  }

  // ✅ Main dashboard layout with 4 tiles
  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-neutral-900 p-8 text-white font-sans">
      <h1 className="text-5xl font-bold mb-2 tracking-tight leading-tight">Welcome back 👋</h1>
      <p className="text-lg text-zinc-400 mb-6">Here’s your business overview</p>

      <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-6 mb-12">
        {/* 👥 Community Size */}
        <div className="flex flex-col justify-between rounded-xl bg-zinc-800 min-h-[240px] p-6 shadow-xl border border-zinc-700">
          <div>
            {renderTileHeader(<Users className="text-blue-400" size={24} />, "Community Size")}
            <p className="text-5xl font-bold text-green-400 mb-2">{contactStats.total_customers}</p>
            <p className="text-sm text-zinc-400 mb-6">{contactStats.without_engagement} without engagement plan</p>
          </div>
          {renderTileButton("Manage Community", () => router.push("/customers-ui"))}
        </div>

        {/* ✉️ Community Outreach Plan */}
        <div className="flex flex-col justify-between rounded-xl bg-zinc-800 min-h-[240px] p-6 shadow-xl border border-zinc-700">
          <div>
            {renderTileHeader(<Send className="text-blue-400" size={24} />, "Community Outreach Plan")}
            <div className="flex flex-wrap gap-6 mb-4 text-white">
              <StatItem label="Pending" value={engagementStats?.pending ?? 0} icon={<Clock size={16} className="text-yellow-400" />} tooltip="Messages waiting for approval" />
              <StatItem label="Rejected" value={engagementStats?.rejected ?? 0} icon={<XCircle size={16} className="text-red-500" />} tooltip="Messages that were rejected" />
              <StatItem label="Scheduled" value={engagementStats?.scheduled ?? 0} icon={<CalendarClock size={16} className="text-green-500" />} tooltip="Messages scheduled to be sent" />
              <StatItem label="Sent" value={engagementStats?.sent ?? 0} icon={<Send size={16} className="text-white" />} tooltip="Messages successfully sent" />
            </div>
          </div>
          {renderTileButton("Manage Plans", () => router.push("/all-engagement-plans"))}
        </div>

        {/* 🤖 Community Responses */}
        <div className="flex flex-col justify-between rounded-xl bg-zinc-800 min-h-[240px] p-6 shadow-xl border border-zinc-700">
          <div>
            {renderTileHeader(<Bot className="text-blue-400" size={24} />, "Community Responses")}
            <div className="flex items-center gap-2 mb-2">
              <MailCheck className="text-yellow-400" size={20} />
              <p className="text-4xl font-bold text-yellow-400">
                {replyStats.customers_waiting ?? 0}
              </p>
            </div>
            <p className="text-sm text-zinc-400 mb-4">
              {replyStats.customers_waiting === 1
                ? "1 customer waiting on your reply"
                : `${replyStats.customers_waiting} customers waiting on your reply`}
            </p>
            <div className="flex items-center gap-2 mb-6">
              <Send className="text-zinc-400" size={18} />
              <p className="text-sm text-zinc-400">
                {replyStats.messages_total ?? 0} response drafts ready for you ❤️
              </p>
            </div>
          </div>
          {renderTileButton("Review & Reply", () => router.push("/customer-replies"))}
        </div>

        {/* 💬 Open Conversations */}
        <div className="flex flex-col justify-between rounded-xl bg-zinc-800 min-h-[240px] p-6 shadow-xl border border-zinc-700">
          <div>
            {renderTileHeader(<MessageSquare className="text-blue-400" size={24} />, "Open Conversations")}
            <p className="text-5xl font-bold text-blue-400 mb-4">💬</p>
            <p className="text-sm text-zinc-400 mb-6">Chat threads with your community</p>
          </div>
          {renderTileButton("Go to Inbox", () => router.push("/conversations"))}
        </div>
      </div>
    </div>
  );
}
