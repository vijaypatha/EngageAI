"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient, getCustomersByBusiness } from "@/lib/api";
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
import { Customer, Tag } from "@/types";
import { Loader2, UserPlus, Edit3, ClipboardList, Send, AlertTriangle, Users, Trash2 } from "lucide-react"; // Added icons

export default function ContactsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deleteCustomerId, setDeleteCustomerId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { business_name: businessSlug } = useParams();
  const router = useRouter();

  const [optInRequestStatus, setOptInRequestStatus] = useState<{ [customerId: number]: string | null }>({});
  const [isRequestingOptIn, setIsRequestingOptIn] = useState<number | null>(null);

  useEffect(() => {
    const load = async () => {
      const currentSlug = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;
      if (!currentSlug || typeof currentSlug !== 'string') {
          setError("Invalid business identifier.");
          setIsLoading(false);
          return;
      };

      setIsLoading(true);
      setError(null);
      try {
        const idRes = await apiClient.get<{ business_id: number }>(`/business-profile/business-id/slug/${currentSlug}`);
        const business_id = idRes.data.business_id;
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

  const getOptInStatus = (customer: Customer): OptInStatus => {
      if (!customer.latest_consent_status) return "waiting";
      switch (customer.latest_consent_status) {
        case "opted_in": return "opted_in";
        case "opted_out": return "opted_out";
        case "pending": return "pending";
        case "pending_confirmation": return "pending";
        case "declined": return "opted_out";
        case "waiting": return "waiting";
        default:
             console.warn(`Unknown consent status '${customer.latest_consent_status}' for customer ${customer.id}`);
             return "error";
      }
  };

  const handleRequestOptIn = async (customerId: number) => {
    setIsRequestingOptIn(customerId);
    setOptInRequestStatus(prev => ({ ...prev, [customerId]: "Sending..." }));
    setError(null);
    try {
      await apiClient.post(`/consent/resend-optin/${customerId}`);
      setOptInRequestStatus(prev => ({ ...prev, [customerId]: "Opt-in request sent!" }));
      setTimeout(() => {
          setOptInRequestStatus(prev => ({ ...prev, [customerId]: null }));
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

  if (isLoading && customers.length === 0) {
      return (
          <div className="flex-1 p-6 bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center font-sans">
            <div className="text-center">
                <Loader2 className="animate-spin h-12 w-12 text-purple-400 mx-auto mb-6" />
                <h1 className="text-2xl font-bold text-slate-300">Loading Contacts...</h1>
                <p className="text-slate-400">Please wait while we fetch your customer data.</p>
            </div>
          </div>
       );
  }

  if (error && customers.length === 0) {
    return (
      <div className="flex-1 p-6 bg-slate-900 text-slate-100 min-h-screen flex items-center justify-center font-sans">
        <div className="max-w-md mx-auto text-center bg-slate-800 p-8 rounded-xl shadow-2xl border border-slate-700">
          <AlertTriangle className="h-16 w-16 text-red-500 mx-auto mb-6" />
          <h2 className="text-2xl font-semibold text-red-400 mb-3">Oops! Something went wrong.</h2>
          <p className="text-slate-300 mb-6 bg-red-900/30 border border-red-700/50 p-3 rounded-md">
            {error}
          </p>
           <Button
            onClick={() => window.location.reload()}
            className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-6 py-2 rounded-lg shadow-md hover:shadow-purple-500/30 transition-all"
           >
            Try Again
           </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 px-4 py-8 md:px-6 md:py-10 font-sans">
      <div className="space-y-8 max-w-7xl mx-auto">
        <div className="flex flex-col sm:flex-row justify-between items-center mb-8">
            <h1 className="text-4xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-4 sm:mb-0 flex items-center">
              <Users className="mr-3 h-10 w-10 opacity-80" />
              {customers.length} Contact{customers.length !== 1 ? "s" : ""}
            </h1>
            <Button
                onClick={() => router.push(`/add-contact/${businessSlug}`)}
                className="bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold shadow-lg hover:shadow-pink-500/40 hover:scale-105 transition-all duration-200 rounded-lg text-base px-6 py-3 flex items-center"
                size="lg"
                title="Add New Contact"
            >
                <UserPlus className="mr-2 h-5 w-5" /> Add Contact
            </Button>
        </div>

        {/* Inline error display if customers are already loaded but a subsequent error occurs */}
        {error && customers.length > 0 && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-300 px-4 py-3 rounded-lg relative mb-6 shadow-lg" role="alert">
            <div className="flex">
                <div className="py-1"><AlertTriangle className="fill-current h-6 w-6 text-red-400 mr-4" /></div>
                <div>
                    <p className="font-bold">Error Occurred</p>
                    <p className="text-sm">{error}</p>
                </div>
            </div>
            <button onClick={() => setError(null)} className="absolute top-0 bottom-0 right-0 px-4 py-3 text-red-300 hover:text-red-100 font-bold text-2xl">&times;</button>
          </div>
        )}

        {customers.length === 0 && !isLoading ? (
            <div className="text-center py-20 col-span-full">
                <svg xmlns="http://www.w3.org/2000/svg" className="mx-auto h-20 w-20 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                     <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zM6.75 9.75A2.25 2.25 0 112.25 7.5a2.25 2.25 0 014.5 0z" />
                </svg>
                <p className="mt-6 text-2xl text-slate-400 font-semibold">No Contacts Found</p>
                <p className="text-slate-500 mt-2">Click the "+ Add Contact" button to start building your contact list.</p>
            </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {customers.map((customer) => (
              <div key={customer.id} className="rounded-xl border border-slate-700/80 p-5 bg-slate-800/70 shadow-lg flex flex-col justify-between h-full hover:shadow-purple-500/20 hover:border-purple-500/60 transition-all duration-300 backdrop-blur-sm">
                <div>
                    <h2 className="text-lg font-semibold truncate text-slate-100 mb-1" title={customer.customer_name}>{customer.customer_name}</h2>
                    <div className="mt-1 mb-3 space-y-1.5">
                        <OptInStatusBadge
                          status={getOptInStatus(customer)}
                          size="sm" // Can be 'default' or 'sm'
                          lastUpdated={customer.latest_consent_updated}
                        />
                        <p className="text-sm text-slate-400 flex items-center gap-1.5">📞 <span className="font-medium">{customer.phone || 'No phone'}</span></p>
                    </div>
                    {customer.lifecycle_stage && <p className="text-sm text-purple-400/90 mb-2">📍 {customer.lifecycle_stage}</p>}
                    {customer.tags && customer.tags.length > 0 && (
                      <div className="mt-2 mb-4 flex flex-wrap gap-1.5 items-center">
                        {customer.tags.slice(0, 3).map((tag) => (
                          <span
                            key={tag.id}
                            className="bg-purple-600 text-white text-xs font-semibold px-3 py-1 rounded-full                    whitespace-nowrap uppercase tracking-wider cursor-default"
                            title={tag.name}
                          >
                            {tag.name} {/* The `uppercase` class will handle text transformation */}
                          </span>
                          ))}
                          {customer.tags.length > 3 && (
                              <span className="text-xs text-slate-500 ml-1" title={customer.tags.slice(3).map(t=>t.name).join                     (', ')}>+{customer.tags.length - 3} more</span>
                          )}
                        </div>
                      )}
                </div>

                <div className="flex flex-col gap-2.5 mt-4 pt-4 border-t border-slate-700/70">
                  <div className="flex flex-row gap-2.5">
                    <Button
                        size="sm"
                        className="flex-1 bg-blue-600/20 hover:bg-blue-500/40 border border-blue-500/50 text-blue-300 hover:text-blue-100 transition-all rounded-md"
                        onClick={() => router.push(`/edit-contact/${customer.id}`)}
                    >
                        <Edit3 className="mr-1.5 h-3.5 w-3.5"/> Edit
                    </Button>
                    <Button
                        size="sm"
                        className="flex-1 bg-indigo-600/20 hover:bg-indigo-500/40 border border-indigo-500/50 text-indigo-300 hover:text-indigo-100 transition-all rounded-md"
                        onClick={() => router.push(`/contacts-ui/${customer.id}`)} // Assuming this route is correct
                    >
                        <ClipboardList className="mr-1.5 h-3.5 w-3.5"/> Plan
                    </Button>
                  </div>

                  {(getOptInStatus(customer) === "waiting" || getOptInStatus(customer) === "pending") && (
                    <>
                      <Button
                        size="sm"
                        className="w-full bg-teal-600/60 hover:bg-teal-500/80 border border-teal-500/70 text-teal-100 hover:text-white transition-all disabled:opacity-70 rounded-md flex items-center justify-center"
                        onClick={() => handleRequestOptIn(customer.id)}
                        disabled={isRequestingOptIn === customer.id}
                      >
                        {isRequestingOptIn === customer.id
                          ? <><Loader2 className="mr-2 h-4 w-4 animate-spin"/> Sending...</>
                          : optInRequestStatus[customer.id] && optInRequestStatus[customer.id] !== "Opt-in request sent!" && optInRequestStatus[customer.id] !== "Sending..."
                            ? "Retry Opt-In"
                            : <><Send className="mr-2 h-4 w-4"/> Request Opt-In</>}
                      </Button>
                      {optInRequestStatus[customer.id] && (
                        <p className={`text-xs mt-1.5 text-center ${optInRequestStatus[customer.id] === "Opt-in request sent!" ? 'text-green-400' : optInRequestStatus[customer.id] === "Sending..." ? 'text-sky-400' : 'text-red-400'}`}>
                          {optInRequestStatus[customer.id]}
                        </p>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <AlertDialog open={deleteCustomerId !== null} onOpenChange={(open) => !open && setDeleteCustomerId(null)}>
          <AlertDialogContent className="bg-slate-800 border-slate-700 text-slate-100 shadow-xl rounded-lg font-sans">
            <AlertDialogHeader>
              <AlertDialogTitle className="text-xl flex items-center">
                <Trash2 className="mr-2 h-5 w-5 text-red-500"/> Delete Contact?
              </AlertDialogTitle>
              <AlertDialogDescription className="text-slate-400 pt-2">
                This action cannot be undone. Are you sure you want to permanently delete this contact?
                {deleteCustomerId && customers.find(c=>c.id===deleteCustomerId) && (
                    <span className="block font-medium text-slate-200 mt-3 bg-slate-700/50 p-2 rounded-md">
                        {customers.find(c=>c.id===deleteCustomerId)?.customer_name}
                    </span>
                )}
              </AlertDialogDescription>
            </AlertDialogHeader>
             {error && deleteCustomerId !== null && ( // Show error related to delete operation
                <p className="text-red-400 text-sm mt-2 p-2 bg-red-900/30 rounded-md">{error}</p>
             )}
            <AlertDialogFooter className="mt-4">
              <AlertDialogCancel
                className="text-slate-300 border-slate-600 hover:bg-slate-700 hover:text-slate-100 focus:ring-slate-500"
                onClick={() => { setDeleteCustomerId(null); setError(null);}} // Clear specific delete error on cancel
              >
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                className="bg-red-600 hover:bg-red-700 text-white focus:ring-red-500 disabled:opacity-75"
                disabled={isLoading && deleteCustomerId !== null} // Disable only if loading for this specific action
                onClick={() => deleteCustomerId && handleDelete(deleteCustomerId)}
              >
                {isLoading && deleteCustomerId ? <Loader2 className="mr-2 h-4 w-4 animate-spin"/> : null}
                {isLoading && deleteCustomerId ? "Deleting..." : "Delete"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}