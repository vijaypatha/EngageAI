// /add-customer/page.tsx — Add Customer (Drop-in with apiClient + session fix)

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { getCurrentBusiness } from "@/lib/utils"; // ✅ pulls from session
import { apiClient } from "@/lib/api"; // ✅ drop-in axios client with cookies

export default function AddCustomerPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    interaction_history: "",
    pain_points: "",
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async () => {
    const session = await getCurrentBusiness();
    if (!session?.business_id) {
      alert("Missing business ID. Please complete the business profile setup first.");
      return;
    }

    try {
      const payload = {
        ...form,
        business_id: session.business_id, // ✅ ensure it's passed
      };

      await apiClient.post("/customers/", payload); // ✅ uses axios with cookies
      router.push("/dashboard");
    } catch (err: any) {
      console.error("❌ Customer save failed:", err);
      alert("There was an error adding the customer.");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-neutral-900 text-white p-8">
      <div className="max-w-xl mx-auto space-y-6">
        <h1 className="text-4xl font-bold mb-6">➕ Add New Contact</h1>

        <Input name="customer_name" placeholder="Customer Name" value={form.customer_name} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />
        <Input name="phone" placeholder="Phone Number (e.g. +1234567890)" value={form.phone} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />
        <Input name="lifecycle_stage" placeholder="Lifecycle Stage (e.g., lead, repeat buyer)" value={form.lifecycle_stage} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />
        <Textarea name="interaction_history" placeholder="Interaction History" value={form.interaction_history} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />
        <Textarea name="pain_points" placeholder="Pain Points" value={form.pain_points} onChange={handleChange} className="bg-zinc-900 border-zinc-700 text-white" />

        <div className="text-right">
          <Button onClick={handleSubmit} className="bg-black text-white border border-zinc-600 hover:bg-zinc-900 hover:border-zinc-500 transition px-6 py-2 rounded-lg">
            Save Contact
          </Button>
        </div>
      </div>
    </div>
  );
}
