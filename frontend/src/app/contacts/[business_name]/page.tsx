"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
// Ensure API client and specific functions are imported
import { apiClient, getCustomersByBusiness } from "@/lib/api"; // Use your updated apiClient
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
import { OptInStatusBadge, OptInStatus } from "@/components/OptInStatus";
// --- Import Customer and Tag types ---
import { Customer, Tag } from "@/types"; // Adjust path if needed

export default function ContactsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [isLoading, setIsLoading] = useState(true); // Add loading state
  const [deleteCustomerId, setDeleteCustomerId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { business_name: businessSlug } = useParams(); // Use slug from params
  const router = useRouter();

  // State for opt-in request feedback
  const [optInRequestStatus, setOptInRequestStatus] = useState<{ [customerId: number]: string | null }>({});
  const [isRequestingOptIn, setIsRequestingOptIn] = useState<number | null>(null);


  // Fetch data on mount and when businessSlug changes
  useEffect(() => {
    const load = async () => {
      // Ensure slug is a string before proceeding
      const currentSlug = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;
      if (!currentSlug || typeof currentSlug !== 'string') {
          setError("Invalid business identifier.");
          setIsLoading(false);
          return;
      };

      setIsLoading(true);
      setError(null); // Clear previous errors
      try {
        // Fetch business ID using slug
        const idRes = await apiClient.get<{ business_id: number }>(`/business-profile/business-id/slug/${currentSlug}`);
        const business_id = idRes.data.business_id;

        // Fetch customers for that business ID (includes tags now)
        const fetchedCustomers = await getCustomersByBusiness(business_id);
        setCustomers(fetchedCustomers as Customer[]);

      } catch (err: any) {
        console.error("Failed to load contacts:", err);
        setError(err?.response?.data?.detail || "Failed to load contacts. Please try again.");
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [businessSlug]);

  // --- Delete Contact Logic ---
  const handleDelete = async (customerId: number) => {
    setIsLoading(true); 
    try {
      setError(null);
      await apiClient.delete(`/customers/${customerId}`);
      setCustomers(prev => prev.filter(c => c.id !== customerId));
      setDeleteCustomerId(null); 
    } catch (err: any) {
      console.error("Failed to delete contact:", err);
      setError(err?.response?.data?.detail || "Failed to delete contact. Please try again.");
    } finally {
        setIsLoading(false);
    }
  };

  // --- Opt-In Status Logic ---
  const getOptInStatus = (customer: Customer): OptInStatus => {
      if (!customer.latest_consent_status) return "waiting"; 
      switch (customer.latest_consent_status) {
        case "opted_in": return "opted_in"; 
        case "opted_out": return "opted_out";
        case "pending": return "pending";
        case "pending_confirmation": return "pending"; // Treat as pending
        case "declined": return "opted_out"; // Treat declined as opted_out
        case "waiting": 
             return "waiting";
        default:
             console.warn(`Unknown consent status '${customer.latest_consent_status}' for customer ${customer.id}`);
             return "error"; 
      }
  };

  // --- Handle Request Opt-In ---
  const handleRequestOptIn = async (customerId: number) => {
    setIsRequestingOptIn(customerId);
    setOptInRequestStatus(prev => ({ ...prev, [customerId]: "Sending..." }));
    setError(null);

    try {
      await apiClient.post(`/consent/resend-optin/${customerId}`);
      setOptInRequestStatus(prev => ({ ...prev, [customerId]: "Opt-in request sent!" }));
      // Consider fetching customer list again or updating the specific customer's status locally
      // For now, clear message after a delay.
      setTimeout(() => {
          setOptInRequestStatus(prev => ({ ...prev, [customerId]: null }));
          // Trigger a reload of customers to get the latest consent status
          // This is a simple way; more sophisticated state management could update just the one customer
          const currentSlug = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;
          if (currentSlug && typeof currentSlug === 'string') {
              apiClient.get<{ business_id: number }>(`/business-profile/business-id/slug/${currentSlug}`)
                  .then(idRes => getCustomersByBusiness(idRes.data.business_id))
                  .then(fetchedCustomers => setCustomers(fetchedCustomers as Customer[]))
                  .catch(err => console.error("Error refreshing customer list after opt-in request:", err));
          }

      }, 3000);
    } catch (err: any) {
      console.error("Failed to send opt-in request:", err);
      const errorMessage = err?.response?.data?.detail || "Failed to send opt-in request.";
      setOptInRequestStatus(prev => ({ ...prev, [customerId]: errorMessage }));
      setTimeout(() => setOptInRequestStatus(prev => ({ ...prev, [customerId]: null })), 5000);
    } finally {
      setIsRequestingOptIn(null);
    }
  };


  // --- Loading State UI ---
  if (isLoading && customers.length === 0) { 
      return (
          <div className="flex min-h-screen bg-nudge-gradient items-center justify-center text-white">
              Loading contacts... 
          </div>
       );
  }

  // --- Error State UI ---
  if (error && customers.length === 0) { 
    return (
      <div className="min-h-screen bg-nudge-gradient text-white px-4 py-8">
        <div className="max-w-6xl mx-auto text-center">
          <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 text-red-300 inline-block">
            Error: {error}
          </div>
           <Button onClick={() => window.location.reload()} variant="secondary" className="mt-4">Retry</Button>
        </div>
      </div>
    );
  }

  // --- Main Content UI ---
  return (
    <div className="min-h-screen bg-nudge-gradient text-white px-4 py-8">
      <div className="space-y-6 max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-4">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent">
              📇 {customers.length} Contact{customers.length !== 1 ? "s" : ""}
            </h1>
            <Button
                onClick={() => router.push(`/add-contact/${businessSlug}`)}
                className="bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white font-semibold shadow-lg hover:scale-105 transition-transform duration-200"
                size="lg"
                title="Add New Contact"
            >
                + Add Contact
            </Button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {customers.map((customer) => (
            <div key={customer.id} className="rounded-lg border border-neutral-700 p-4 bg-zinc-800/80 shadow-md flex flex-col justify-between h-full hover:border-neutral-500 transition-colors duration-200">
              <div>
                  <h2 className="text-lg font-semibold truncate text-gray-100" title={customer.customer_name}>{customer.customer_name}</h2>
                  <div className="mt-1 mb-2 space-y-1">
                      <OptInStatusBadge
                        status={getOptInStatus(customer)}
                        size="sm"
                        lastUpdated={customer.latest_consent_updated}
                      />
                      <p className="text-sm text-neutral-400 flex items-center gap-1.5">📞 <span>{customer.phone || 'No phone'}</span></p>
                  </div>
                  {customer.lifecycle_stage && <p className="text-sm text-blue-300/80 mb-1">📍 {customer.lifecycle_stage}</p>}
                  {customer.tags && customer.tags.length > 0 && (
                    <div className="mt-2 mb-3 flex flex-wrap gap-1 items-center">
                      {customer.tags.slice(0, 3).map((tag) => ( 
                        <span
                          key={tag.id}
                          className="bg-gray-600/80 hover:bg-gray-500/80 cursor-default text-gray-200 text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
                          title={tag.name}
                        >
                          {tag.name}
                        </span>
                      ))}
                      {customer.tags.length > 3 && (
                          <span className="text-xs text-gray-400 ml-1" title={customer.tags.slice(3).map(t=>t.name).join(', ')}>+{customer.tags.length - 3} more</span>
                      )}
                    </div>
                  )}
              </div>

              {/* Action Buttons */}
              <div className="flex flex-col gap-2 mt-4 pt-3 border-t border-neutral-700/50">
                <div className="flex flex-row gap-2">
                  <Button size="sm" variant="secondary" className="flex-1" onClick={() => router.push(`/edit-contact/${customer.id}`)}>Edit</Button>
                  <Button size="sm" variant="ghost" className="text-white flex-1" onClick={() => router.push(`/contacts-ui/${customer.id}`)}>Plan</Button>
                </div>

                {/* Conditional Opt-In Request Button */}
                {(getOptInStatus(customer) === "waiting" || getOptInStatus(customer) === "pending") && (
                  <>
                    <Button
                      size="sm"
                      variant="secondary" 
                      className="w-full bg-sky-900/40 border border-sky-500 text-sky-200 hover:bg-sky-700/60 hover:text-white transition disabled:opacity-70"
                      onClick={() => handleRequestOptIn(customer.id)}
                      disabled={isRequestingOptIn === customer.id}
                    >
                      {isRequestingOptIn === customer.id
                        ? "Sending..."
                        : optInRequestStatus[customer.id] && optInRequestStatus[customer.id] !== "Opt-in request sent!" && optInRequestStatus[customer.id] !== "Sending..."
                          ? "Retry Opt-In"
                          : "💌 Request Opt-In"}
                    </Button>
                    {optInRequestStatus[customer.id] && (
                      <p className={`text-xs mt-1 text-center ${optInRequestStatus[customer.id] === "Opt-in request sent!" ? 'text-green-400' : optInRequestStatus[customer.id] === "Sending..." ? 'text-sky-400' : 'text-red-400'}`}>
                        {optInRequestStatus[customer.id]}
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

            {customers.length === 0 && !isLoading && (
                <div className="col-span-full text-center text-gray-400 py-16">
                    <p className="text-lg mb-2">No contacts yet!</p>
                    <p>Click the "+ Add Contact" button to get started.</p>
                </div>
            )}
        </div>

        <AlertDialog open={deleteCustomerId !== null} onOpenChange={(open) => !open && setDeleteCustomerId(null)}>
          <AlertDialogContent className="bg-zinc-900 border-neutral-700 text-white">
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Contact?</AlertDialogTitle>
              <AlertDialogDescription className="text-neutral-400">
                This action cannot be undone. Are you sure you want to permanently delete this contact?
                {deleteCustomerId && customers.find(c=>c.id===deleteCustomerId) && (
                    <span className="block font-medium text-white mt-2">{customers.find(c=>c.id===deleteCustomerId)?.customer_name}</span>
                )}
              </AlertDialogDescription>
            </AlertDialogHeader>
             {error && deleteCustomerId !== null && (
                <p className="text-red-400 text-sm mt-2">{error}</p>
             )}
            <AlertDialogFooter>
              <AlertDialogCancel className="text-white border-neutral-600 hover:bg-neutral-700" onClick={() => { setDeleteCustomerId(null); setError(null);}}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                className="bg-red-600 hover:bg-red-700 text-white"
                disabled={isLoading} 
                onClick={() => deleteCustomerId && handleDelete(deleteCustomerId)}
              >
                {isLoading && deleteCustomerId ? "Deleting..." : "Delete"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}