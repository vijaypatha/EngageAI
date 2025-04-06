// Enhanced /customers-ui/page.tsx with dashboard-aligned buttons and floating animated Add button

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

interface Customer {
  id: number;
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  interaction_history: string;
  pain_points: string;
  engagement_planned: boolean;
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Customer | null>(null);
  const router = useRouter();

  useEffect(() => {
    const businessId = localStorage.getItem("business_id");
    if (!businessId) return;

    apiClient.get(`/customers/by-business/${businessId}`)
      .then((res) => setCustomers(res.data))
      .catch((error) => console.error("Error fetching customers:", error));
  }, []);

  const filteredCustomers = customers.filter((c) =>
    c.customer_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-950 via-zinc-900 to-neutral-900 p-8 text-white font-sans pb-32">
      <h1 className="text-5xl font-extrabold tracking-tight text-white mb-4">👥 Your Contacts</h1>

      <input
        type="text"
        placeholder="🔍 Search customers..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full mb-10 px-4 py-2 rounded-lg bg-zinc-800 text-white border border-zinc-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />

      <div className="grid sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 auto-rows-fr">
        {filteredCustomers.map((customer) => (
          <div
            key={customer.id}
            className="rounded-xl border border-zinc-700 p-6 bg-zinc-800 shadow-md hover:shadow-xl flex flex-col justify-between min-h-[320px]"
          >
            <div>
              <h2 className="text-2xl font-bold text-white mb-2">{customer.customer_name}</h2>
              <p className="text-sm text-zinc-400 mb-1">📞 {customer.phone}</p>
              <p className="text-sm text-zinc-400">🔄 Lifecycle Stage: <span className="text-white font-semibold">{customer.lifecycle_stage}</span></p>
              <p className="text-sm text-zinc-400 mt-1">💬 Notes: {customer.interaction_history}</p>
              <p className="text-sm text-zinc-400 mt-1">🧠 Pain Points: {customer.pain_points}</p>
            </div>
            <div className="flex gap-3 mt-6">
              <Button
                className="flex-1 bg-black text-white border border-zinc-600 font-medium hover:bg-zinc-900 hover:border-zinc-500 transition"
                onClick={() => router.push(`/customers-ui/${customer.id}`)}
              >
                📩 See Engagement Plan
              </Button>
              <Button
                variant="outline"
                className="flex-1 text-sm border-zinc-600 text-zinc-300 hover:text-white"
                onClick={() => setEditing(customer)}
              >
                ✏️ Edit
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Sticky Add Contact Button Bottom Right */}
      <div className="fixed bottom-6 right-6 z-50 animate-bounce">
        <Button
          className="bg-black text-white border border-zinc-600 hover:bg-zinc-900 hover:border-zinc-500 transition px-6 py-3 rounded-full shadow-xl"
          onClick={() => router.push("/add-customer")} /* Redirect to add customer page */
        >
          ➕ Add New Contact
        </Button>
      </div>

      {/* Edit Dialog */}
      {editing && (
        <Dialog open={!!editing} onOpenChange={() => setEditing(null)}>
          <DialogContent className="bg-zinc-900 text-white border-zinc-700">
            <DialogTitle>Edit Contact</DialogTitle>
            <p className="text-sm text-zinc-400">Coming soon: contact editing form will appear here.</p>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
