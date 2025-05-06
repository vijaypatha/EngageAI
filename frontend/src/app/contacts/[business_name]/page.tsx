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
        // --- Use Type Assertion here to satisfy linter if needed ---
        setCustomers(fetchedCustomers as Customer[]);
        // --- Or if confident API matches type, simply: ---
        // setCustomers(fetchedCustomers);

      } catch (err: any) {
        console.error("Failed to load contacts:", err);
        setError(err?.response?.data?.detail || "Failed to load contacts. Please try again.");
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [businessSlug]); // Depend only on the slug

  // --- Delete Contact Logic ---
  const handleDelete = async (customerId: number) => {
    setIsLoading(true); // Indicate loading during delete
    try {
      setError(null);
      await apiClient.delete(`/customers/${customerId}`);
      setCustomers(prev => prev.filter(c => c.id !== customerId));
      setDeleteCustomerId(null); // Close dialog on success
    } catch (err: any) {
      console.error("Failed to delete contact:", err);
      setError(err?.response?.data?.detail || "Failed to delete contact. Please try again.");
      // Keep dialog open on error by not setting deleteCustomerId to null here
    } finally {
        setIsLoading(false);
    }
  };

  // --- Opt-In Status Logic ---
  const getOptInStatus = (customer: Customer): OptInStatus => {
      if (!customer.latest_consent_status) return "waiting"; // Default if no log yet
      switch (customer.latest_consent_status) {
        case "opted_in": return "opted_in"; // Rely solely on log status for display consistency
        case "opted_out": return "opted_out";
        case "pending": return "pending";
        case "waiting": // Treat waiting same as pending or make distinct?
             return "waiting";
        default:
             console.warn(`Unknown consent status '${customer.latest_consent_status}' for customer ${customer.id}`);
             return "error"; // Indicate unexpected status
      }
  };

  // --- Loading State UI ---
  if (isLoading && customers.length === 0) { // Show loading only on initial load
      return (
          <div className="flex min-h-screen bg-nudge-gradient items-center justify-center text-white">
              Loading contacts... {/* Replace with spinner if desired */}
          </div>
       );
  }

  // --- Error State UI ---
  if (error && customers.length === 0) { // Show error prominently if loading failed completely
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
            {/* Add Contact Button (moved here from FAB for better layout control) */}
            <Button
                onClick={() => router.push(`/add-contact/${businessSlug}`)}
                className="bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white font-semibold shadow-lg hover:scale-105 transition-transform duration-200"
                size="lg"
                title="Add New Contact"
            >
                + Add Contact
            </Button>
        </div>


         {/* --- Add Filtering Controls Here (Placeholder for Future) --- */}
         {/* <div className="mb-4 p-4 bg-zinc-800/50 rounded-lg border border-neutral-700"> Filter Dropdown Placeholder </div> */}

        {/* --- Contact Cards Grid --- */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {customers.map((customer) => (
            <div key={customer.id} className="rounded-lg border border-neutral-700 p-4 bg-zinc-800/80 shadow-md flex flex-col justify-between h-full hover:border-neutral-500 transition-colors duration-200">
              {/* Card Content */}
              <div>
                  <h2 className="text-lg font-semibold truncate text-gray-100" title={customer.customer_name}>{customer.customer_name}</h2>
                  {/* Status and Phone */}
                  <div className="mt-1 mb-2 space-y-1">
                      <OptInStatusBadge
                        status={getOptInStatus(customer)}
                        size="sm"
                        lastUpdated={customer.latest_consent_updated}
                      />
                      <p className="text-sm text-neutral-400 flex items-center gap-1.5">📞 <span>{customer.phone || 'No phone'}</span></p>
                  </div>

                  {/* Optional Details */}
                  {customer.lifecycle_stage && <p className="text-sm text-blue-300/80 mb-1">📍 {customer.lifecycle_stage}</p>}

                  {/* --- Render Tags --- */}
                  {customer.tags && customer.tags.length > 0 && (
                    <div className="mt-2 mb-3 flex flex-wrap gap-1 items-center">
                      {customer.tags.slice(0, 3).map((tag) => ( // Limit displayed tags
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
                  {/* --- End Render Tags --- */}

                  {/* Tooltip or Collapsible for Pain/History could be better */}
                  {/* <p className="mt-2 text-sm text-gray-300 truncate" title={customer.pain_points}>Pain: {customer.pain_points || '-'}</p> */}
                  {/* <p className="text-sm text-gray-300 truncate" title={customer.interaction_history}>History: {customer.interaction_history || '-'}</p> */}
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-neutral-700/50">
                <Button size="sm" variant="secondary" className="flex-1" onClick={() => router.push(`/edit-contact/${customer.id}`)}>Edit</Button>
                <Button size="sm" variant="ghost" className="text-white flex-1" onClick={() => router.push(`/contacts-ui/${customer.id}`)}>Plan</Button>
                {/* Keep delete confirmation for safety */}
                 {/* <Button size="sm" variant="destructive" className="flex-grow-0" onClick={() => setDeleteCustomerId(customer.id)}>Delete</Button> */}
              </div>
            </div>
          ))}

           {/* Handle empty state */}
            {customers.length === 0 && !isLoading && (
                <div className="col-span-full text-center text-gray-400 py-16">
                    <p className="text-lg mb-2">No contacts yet!</p>
                    <p>Click the "+ Add Contact" button to get started.</p>
                </div>
            )}
        </div>

        {/* Removed FAB - Button moved to top */}

        {/* --- Delete Confirmation Dialog --- */}
        <AlertDialog open={deleteCustomerId !== null} onOpenChange={(open) => !open && setDeleteCustomerId(null)}>
          <AlertDialogContent className="bg-zinc-900 border-neutral-700 text-white">
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Contact?</AlertDialogTitle>
              <AlertDialogDescription className="text-neutral-400">
                This action cannot be undone. Are you sure you want to permanently delete this contact?
                {/* Display name if available */}
                {deleteCustomerId && customers.find(c=>c.id===deleteCustomerId) && (
                    <span className="block font-medium text-white mt-2">{customers.find(c=>c.id===deleteCustomerId)?.customer_name}</span>
                )}
              </AlertDialogDescription>
            </AlertDialogHeader>
             {/* Show error within dialog if delete fails */}
             {error && deleteCustomerId !== null && (
                <p className="text-red-400 text-sm mt-2">{error}</p>
             )}
            <AlertDialogFooter>
              <AlertDialogCancel className="text-white border-neutral-600 hover:bg-neutral-700" onClick={() => setDeleteCustomerId(null)}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                className="bg-red-600 hover:bg-red-700 text-white"
                disabled={isLoading} // Disable button during delete operation
                onClick={() => deleteCustomerId && handleDelete(deleteCustomerId)}
              >
                {isLoading ? "Deleting..." : "Delete"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}