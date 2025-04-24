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
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { OptInStatusBadge, OptInStatus } from "@/components/OptInStatus";

interface Customer {
  id: number;
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  opted_in: boolean;
  latest_consent_status?: string;
  latest_consent_updated?: string;
}

export default function ContactsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [deleteCustomerId, setDeleteCustomerId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { business_name } = useParams();
  const router = useRouter();

  useEffect(() => {
    const load = async () => {
      try {
        setError(null);
        const idRes = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
        const business_id = idRes.data.business_id;

        const custRes = await apiClient.get(`/customers/by-business/${business_id}`);
        setCustomers(custRes.data);
      } catch (err) {
        console.error("Failed to load contacts:", err);
        setError("Failed to load contacts. Please try again.");
      }
    };

    if (business_name) load();
  }, [business_name]);

  const handleDelete = async (customerId: number) => {
    try {
      setError(null);
      await apiClient.delete(`/customers/${customerId}`);
      setCustomers(prev => prev.filter(c => c.id !== customerId));
      setDeleteCustomerId(null);
    } catch (err) {
      console.error("Failed to delete contact:", err);
      setError("Failed to delete contact. Please try again.");
    }
  };

  const getOptInStatus = (customer: Customer): OptInStatus => {
    if (!customer.latest_consent_status) {
      return "waiting";
    }
    
    switch (customer.latest_consent_status) {
      case "opted_in":
        return customer.opted_in ? "opted_in" : "error";
      case "opted_out":
        return !customer.opted_in ? "opted_out" : "error";
      case "pending":
        return "pending";
      case "waiting":
        return "waiting";
      default:
        return "error";
    }
  };

  if (error) {
    return (
      <div className="min-h-screen bg-nudge-gradient text-white px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-red-400">
            {error}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-4 py-8">
      <div className="space-y-6">
        <h1 className="text-3xl font-bold mb-2 bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">
          🖨️ {customers.length} Contact{customers.length !== 1 ? "s" : ""}
        </h1>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
          {customers.map((customer) => (
            <div key={customer.id} className="rounded-xl border border-neutral p-5 bg-zinc-800 shadow-md">
              <h2 className="text-lg font-semibold">{customer.customer_name}</h2>
              <div className="mt-1">
                <OptInStatusBadge 
                  status={getOptInStatus(customer)}
                  size="sm"
                  lastUpdated={customer.latest_consent_updated}
                />
              </div>
              <p className="text-sm text-neutral">📞 {customer.phone}</p>
              <p className="text-sm text-red-300">📍 {customer.lifecycle_stage}</p>
              <p className="mt-2 text-sm">Pain: {customer.pain_points}</p>
              <p className="text-sm">History: {customer.interaction_history}</p>
              <div className="flex gap-2 mt-4">
                <Button variant="secondary" onClick={() => router.push(`/edit-contact/${customer.id}`)}>Edit</Button>
                <Button onClick={() => router.push(`/contacts-ui/${customer.id}`)}>See Engagement Plan</Button>
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

        <AlertDialog open={deleteCustomerId !== null} onOpenChange={(open) => !open && setDeleteCustomerId(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Contact?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently delete this contact. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel onClick={() => setDeleteCustomerId(null)}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                className="bg-red-600 hover:bg-red-700 text-white"
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