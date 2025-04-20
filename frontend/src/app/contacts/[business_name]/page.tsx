"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface Customer {
  id: number;
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  latest_consent_status?: string;
}

export default function ContactsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [deleteCustomerId, setDeleteCustomerId] = useState<number | null>(null);
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

  const handleDelete = async (customerId: number) => {
    try {
      const customer = customers.find(c => c.id === customerId);
      
      // Allow deletion for pending, waiting, or no status
      if (customer?.latest_consent_status && 
          !["pending", "waiting"].includes(customer.latest_consent_status)) {
        alert("Cannot delete contacts that have already opted in or out.");
        setDeleteCustomerId(null);
        return;
      }

      await apiClient.delete(`/customers/${customerId}`);
      setCustomers(prev => prev.filter(c => c.id !== customerId));
      setDeleteCustomerId(null);
    } catch (err) {
      console.error("Failed to delete contact:", err);
      alert("Failed to delete contact. Please try again.");
    }
  };

  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-4 py-8">
      <div className="space-y-6">
        <h1 className="text-2xl font-bold mb-4">🖨️ {customers.length} Contact{customers.length !== 1 ? "s" : ""}</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
          {customers.map((customer) => (
            <div key={customer.id} className="rounded-xl border border-neutral p-5 bg-zinc-800 shadow-md">
              <h2 className="text-lg font-semibold">{customer.customer_name}</h2>
              <p className="text-sm mt-1">
                {customer.latest_consent_status === "opted_in" ? (
                  <span className="text-green-400">✅ Opted In</span>
                ) : customer.latest_consent_status === "opted_out" ? (
                  <span className="text-red-400">❌ Declined</span>
                ) : (
                  <span className="text-yellow-300">⏳ Waiting</span>
                )}
              </p>
              <p className="text-sm text-neutral">📞 {customer.phone}</p>
              <p className="text-sm text-red-300">📍 {customer.lifecycle_stage}</p>
              <p className="mt-2 text-sm">Pain: {customer.pain_points}</p>
              <p className="text-sm">History: {customer.interaction_history}</p>
              <div className="flex gap-2 mt-4">
                <Button variant="secondary" onClick={() => router.push(`/edit-contact/${customer.id}`)}>Edit</Button>
                <Button onClick={() => router.push(`/contacts-ui/${customer.id}`)}>See Engagement Plan</Button>
                {/* Show delete button for pending, waiting, or no status */}
                {(!customer.latest_consent_status || 
                  customer.latest_consent_status === "pending" || 
                  customer.latest_consent_status === "waiting") && (
                  <Button 
                    variant="destructive" 
                    onClick={() => setDeleteCustomerId(customer.id)}
                  >
                    Delete
                  </Button>
                )}
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

        {/* Delete Confirmation Dialog */}
        <AlertDialog open={deleteCustomerId !== null} onOpenChange={() => setDeleteCustomerId(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Contact?</AlertDialogTitle>
              <AlertDialogDescription>
                This will delete the contact that hasn't responded to the opt-in message yet. 
                You can add them again later if needed.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                className="bg-red-600 hover:bg-red-700"
                onClick={() => deleteCustomerId && handleDelete(deleteCustomerId)}
              >
                Delete
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}