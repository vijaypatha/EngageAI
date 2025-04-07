// /add-business/page.tsx — Create Business Profile Page (Updated for session)

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export default function AddBusinessProfilePage() {
  const router = useRouter();
  const [form, setForm] = useState({
    business_name: "",
    industry: "",
    business_goal: "",
    primary_services: "",
    representative_name: "",
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async () => {
    try {
      // ✅ Create business profile
      const res = await apiClient.post("/business-profile/", form);
      const businessId = res.data.id;

      // ✅ Set session cookie
      await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/auth/session?business_id=${businessId}`, {
        method: "POST",
        credentials: "include",
      });
      

      // ✅ Go to next step
      router.push("/train-style");
    } catch (err) {
      alert("Failed to create business profile");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-neutral-900 text-white p-8 pb-32">
      <h1 className="text-4xl font-bold mb-4">🏢 Add Your Business Profile</h1>
      <p className="text-zinc-400 text-sm mb-10">We’ll use this to personalize messages and tone.</p>

      <div className="space-y-6 max-w-xl">
        <Input name="business_name" placeholder="Business Name" value={form.business_name} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />
        <Input name="industry" placeholder="Industry" value={form.industry} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />
        <Input name="business_goal" placeholder="Business Goal" value={form.business_goal} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />
        <Textarea name="primary_services" placeholder="Primary Services" value={form.primary_services} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />
        <Input name="representative_name" placeholder="Representative Name" value={form.representative_name} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />

        <Button
          className="mt-4 bg-black text-white border border-zinc-600 hover:bg-zinc-900 hover:border-zinc-500 transition"
          onClick={handleSubmit}
        >
          🚀 Save & Continue
        </Button>
      </div>
    </div>
  );
}
