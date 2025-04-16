"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface Customer {
  id: number;
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
}

export default function ContactsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const { business_name } = useParams();
  const router = useRouter();

  useEffect(() => {
    const load = async () => {
      try {
        const idRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const business_id = idRes.data.business_id;

        const custRes = await apiClient.get(`/customers/by-business/${business_id}`);
        setCustomers(custRes.data);
      } catch (err) {
        console.error("Failed to load contacts:", err);
      }
    };

    if (business_name) load();
  }, [business_name]);

  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-4 py-8">
      <div className="space-y-6">
        <h1 className="text-2xl font-bold mb-4">🖨️ {customers.length} Contact{customers.length !== 1 ? "s" : ""}</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
          {customers.map((customer) => (
            <div key={customer.id} className="rounded-xl border border-neutral p-5 bg-zinc-800 shadow-md">
              <h2 className="text-lg font-semibold">{customer.customer_name}</h2>
              <p className="text-sm text-neutral">📞 {customer.phone}</p>
              <p className="text-sm text-red-300">📍 {customer.lifecycle_stage}</p>
              <p className="mt-2 text-sm">Pain: {customer.pain_points}</p>
              <p className="text-sm">History: {customer.interaction_history}</p>
              <div className="flex gap-2 mt-4">
                <Button variant="secondary" onClick={() => router.push(`/edit-contact/${customer.id}`)}>Edit</Button>
                <Button onClick={() => router.push(`/contacts-ui/${customer.id}`)}>See Engagement Plan</Button>
              </div>
            </div>
          ))}
        </div>

        <Button
          onClick={() => router.push(`/add-contact/${business_name}`)}
          className="fixed bottom-6 right-6 z-50 rounded-full h-16 w-16 text-white text-3xl font-bold shadow-xl bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 animate-pulse hover:scale-110 transition-transform duration-300"
          variant="default"
        >
          +
        </Button>
      </div>
    </div>
  );
}