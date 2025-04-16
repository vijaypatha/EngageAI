"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api";

export default function AddContactPage() {
  const { business_name } = useParams();
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [form, setForm] = useState({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
  });

  const router = useRouter();

  useEffect(() => {
    const fetchBusinessId = async () => {
      try {
        const res = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        setBusinessId(res.data.business_id);
      } catch (err) {
        console.error("❌ Failed to fetch business_id:", err);
      }
    };
    if (business_name) fetchBusinessId();
  }, [business_name]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async () => {
    if (!businessId) return console.error("No business ID available");

    try {
      const res = await apiClient.post("/customers", {
        ...form,
        business_id: businessId,
      });
      console.log("✅ Contact added:", res.data);
      router.back();
    } catch (err) {
      console.error("❌ Failed to add contact:", err);
    }
  };

  return (
    <div className="max-w-xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold">➕ Add New Contact</h1>
      <Input name="customer_name" placeholder="Full Name" value={form.customer_name} onChange={handleChange} />
      <Input name="phone" placeholder="Phone Number" value={form.phone} onChange={handleChange} />
      <Input name="lifecycle_stage" placeholder="Lifecycle Stage (e.g. Lead)" value={form.lifecycle_stage} onChange={handleChange} />
      <Textarea name="pain_points" placeholder="Pain Points" value={form.pain_points} onChange={handleChange} />
      <Textarea name="interaction_history" placeholder="Interaction History" value={form.interaction_history} onChange={handleChange} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => router.back()}>Cancel</Button>
        <Button onClick={handleSubmit}>Save Contact</Button>
      </div>
    </div>
  );
}