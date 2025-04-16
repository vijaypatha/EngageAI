"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export default function EditContactPage() {
  const [form, setForm] = useState({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
  });
  const { id } = useParams();
  const router = useRouter();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await apiClient.get(`/customers/${id}`);
        setForm(res.data);
      } catch (err) {
        console.error("Failed to load contact", err);
      }
    };
    if (id) fetchData();
  }, [id]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleUpdate = async () => {
    await apiClient.put(`/customers/${id}`, form);
    router.back();
  };

  return (
    <div className="max-w-xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold">✏️ Edit Contact</h1>
      <Input name="customer_name" placeholder="Full Name" value={form.customer_name} onChange={handleChange} />
      <Input name="phone" placeholder="Phone Number" value={form.phone} onChange={handleChange} />
      <Input name="lifecycle_stage" placeholder="Lifecycle Stage" value={form.lifecycle_stage} onChange={handleChange} />
      <Textarea name="pain_points" placeholder="Pain Points" value={form.pain_points} onChange={handleChange} />
      <Textarea name="interaction_history" placeholder="Interaction History" value={form.interaction_history} onChange={handleChange} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => router.back()}>Cancel</Button>
        <Button onClick={handleUpdate}>Save Changes</Button>
      </div>
    </div>
  );
}