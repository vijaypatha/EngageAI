"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

export default function EngagementPage() {
  const { business_name } = useParams();
  const [businessId, setBusinessId] = useState<number | null>(null);

  useEffect(() => {
    const fetchBusiness = async () => {
      try {
        const res = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        setBusinessId(res.data.business_id);
      } catch (err) {
        console.error("Failed to fetch business ID", err);
      }
    };

    if (business_name) fetchBusiness();
  }, [business_name]);

  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-6 py-12">
      <h1 className="text-4xl font-bold mb-4">📤 Engagement Plans</h1>
      <p className="text-neutral mb-8">
        Manage and review SMS engagement plans for your contacts.
      </p>
      <div className="border border-neutral rounded-xl p-6 bg-zinc-800">
        <p>📊 This is where grouped SMS messages will appear for business ID: {businessId}</p>
        <p className="mt-2 text-sm text-neutral">(Pending API integration)</p>
      </div>
    </div>
  );
}
