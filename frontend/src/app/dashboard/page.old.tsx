// Updated dashboard/page.tsx — Fixed loading hang by handling API errors individually

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";

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
}

export default function DashboardPage() {
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [engagementStats, setEngagementStats] = useState<EngagementStats | null>(null);
  const [aiStyleTrained, setAiStyleTrained] = useState<boolean>(false);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const businessId = localStorage.getItem("business_id");
    if (!businessId) return;

    const fetchData = async () => {
      try {
        const [profileRes, customersRes] = await Promise.all([
          apiClient.get(`/business/${businessId}`),
          apiClient.get(`/customers/by-business/${businessId}`),
        ]);

        setBusinessProfile(profileRes.data);
        setCustomers(customersRes.data);

        try {
          const statsRes = await apiClient.get(`/review/stats/${businessId}`);
          setEngagementStats(statsRes.data);
        } catch (err) {
          console.warn("⚠️ Could not load engagement stats");
        }

        try {
          const styleRes = await apiClient.get(`/sms-style/response/${businessId}`);
          setAiStyleTrained(styleRes.data.length > 0);
        } catch (err) {
          console.warn("⚠️ Could not load style response");
        }
      } catch (err) {
        console.error("Dashboard load error:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const showDashboard = businessProfile && aiStyleTrained && customers.length > 0;

  if (loading) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center text-xl animate-pulse">
        Loading your dashboard...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-neutral-900 p-8 text-white font-sans">
      <h1 className="text-5xl font-bold mb-2 tracking-tight leading-tight">
        {showDashboard ? "Welcome back 👋" : "🚀 Let's Get Started"}
      </h1>
      <p className="text-lg text-zinc-400 mb-10">
        {showDashboard ? "Here’s your business overview" : "Complete the steps below to activate your dashboard."}
      </p>

      {!showDashboard ? (
        <div className="space-y-6 max-w-xl">
          {!businessProfile && (
            <div className="rounded-xl bg-zinc-800 p-6 border border-zinc-700">
              <h2 className="text-xl font-bold mb-2">📝 Create Your Business Profile</h2>
              <p className="text-zinc-400 mb-4 text-sm">Let’s start by understanding your business.</p>
              <Button onClick={() => router.push("/add-business")}>Create Profile</Button>
            </div>
          )}

          {businessProfile && !aiStyleTrained && (
            <div className="rounded-xl bg-zinc-800 p-6 border border-zinc-700">
              <h2 className="text-xl font-bold mb-2">🤖 Train Your SMS Style</h2>
              <p className="text-zinc-400 mb-4 text-sm">Answer a few prompts so we can learn your communication tone.</p>
              <Button onClick={() => router.push("/train-style")}>Start Training</Button>
            </div>
          )}

          {businessProfile && aiStyleTrained && customers.length === 0 && (
            <div className="rounded-xl bg-zinc-800 p-6 border border-zinc-700">
              <h2 className="text-xl font-bold mb-2">👥 Add Your First Customer</h2>
              <p className="text-zinc-400 mb-4 text-sm">You need at least one customer to begin engagement planning.</p>
              <Button onClick={() => router.push("/add-customer")}>Add Customer</Button>
            </div>
          )}
        </div>
      ) : (
        <>
          <h2 className="text-3xl font-extrabold text-white mb-6">📈 Business Overview</h2>
          <div className="grid md:grid-cols-3 gap-6 mb-12">
            <div className="flex flex-col justify-between rounded-xl bg-zinc-800 min-h-[240px] p-6 shadow-xl border border-zinc-700">
              <div>
                <h2 className="text-2xl font-extrabold text-zinc-100 mb-4">👥 Contacts Health</h2>
                <p className="text-4xl font-bold text-white mb-1">{customers.length}</p>
                <p className="text-sm text-zinc-400 mb-4">
                  {customers.filter((c) => !c.engagement_planned).length} without engagement plan
                </p>
              </div>
              <Button onClick={() => router.push("/customers-ui")}>Manage Contacts</Button>
            </div>

            <div className="flex flex-col justify-between rounded-xl bg-zinc-800 min-h-[240px] p-6 shadow-xl border border-zinc-700">
              <div>
                <h2 className="text-2xl font-extrabold text-zinc-100 mb-4">📊 Engagement Health</h2>
                <div className="text-xl font-bold flex gap-6 mb-2">
                  <div><p className="text-xs text-zinc-400">Pending</p><p>{engagementStats?.pending}</p></div>
                  <div><p className="text-xs text-zinc-400">Scheduled</p><p>{engagementStats?.scheduled}</p></div>
                  <div><p className="text-xs text-zinc-400">Sent</p><p>{engagementStats?.sent}</p></div>
                </div>
              </div>
              <Button onClick={() => router.push("/all-engagement-plans")}>Manage Plans</Button>
            </div>

            <div className="flex flex-col justify-between rounded-xl bg-zinc-800 min-h-[240px] p-6 shadow-xl border border-zinc-700">
              <div>
                <h2 className="text-2xl font-extrabold text-zinc-100 mb-4">🧠 Next Best Action</h2>
                <p className="text-sm text-zinc-400 mb-6">AI-recommended actions coming soon</p>
              </div>
              <Button disabled className="opacity-50">Coming Soon</Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
