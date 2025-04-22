"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { US_TIMEZONES, TIMEZONE_LABELS } from "@/lib/timezone";

export default function EditContactPage() {
  const [form, setForm] = useState({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
    timezone: "America/New_York",
  });
  const { id } = useParams();
  const router = useRouter();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await apiClient.get(`/customers/${id}`);
        setForm({
          ...res.data,
          timezone: res.data.timezone || "America/New_York"
        });
      } catch (err) {
        console.error("Failed to load contact", err);
      }
    };
    if (id) fetchData();
  }, [id]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleUpdate = async () => {
    await apiClient.put(`/customers/${id}`, form);
    router.back();
  };

  return (
    <div className="flex min-h-screen bg-[#0C0F1F] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-2xl rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-8 space-y-6">
        <h1 className="text-3xl font-bold text-center text-white">✏️ Edit Contact</h1>
        <div className="space-y-6">
          <Input 
            name="customer_name" 
            placeholder="Full Name" 
            value={form.customer_name} 
            onChange={handleChange}
            className="bg-white text-black" 
          />
          <Input 
            name="phone" 
            placeholder="Phone Number" 
            value={form.phone} 
            onChange={handleChange}
            className="bg-white text-black" 
          />
          <Input 
            name="lifecycle_stage" 
            placeholder="Lifecycle Stage" 
            value={form.lifecycle_stage} 
            onChange={handleChange}
            className="bg-white text-black" 
          />
          <div className="space-y-2">
            <label className="block text-sm font-medium text-white">
              Customer's Timezone
            </label>
            <select
              name="timezone"
              value={form.timezone}
              onChange={handleChange}
              className="w-full border border-gray-300 rounded-md p-3 text-black bg-white"
            >
              {US_TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {TIMEZONE_LABELS[tz]}
                </option>
              ))}
            </select>
            <p className="text-sm text-gray-400">
              This helps us send messages at appropriate times for your customer
            </p>
          </div>
          <Textarea 
            name="pain_points" 
            placeholder="Pain Points" 
            value={form.pain_points} 
            onChange={handleChange}
            className="bg-white text-black" 
          />
          <Textarea 
            name="interaction_history" 
            placeholder="Interaction History" 
            value={form.interaction_history} 
            onChange={handleChange}
            className="bg-white text-black" 
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => router.back()} className="text-white">
              Cancel
            </Button>
            <Button onClick={handleUpdate} className="bg-gradient-to-r from-green-400 to-blue-500 text-white">
              Save Changes
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}