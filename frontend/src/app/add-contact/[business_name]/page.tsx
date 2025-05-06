// frontend/src/app/add-contact/[business_name]/page.tsx
"use client";

import { useState, useEffect, useCallback } from "react"; // Added useCallback
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label"; // Import Label
import { Textarea } from "@/components/ui/textarea";
import { apiClient, setCustomerTags } from "@/lib/api"; // Import setCustomerTags
import { US_TIMEZONES, TIMEZONE_LABELS } from "@/lib/timezone";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tag } from "@/types"; // Import Tag type
import { TagInput } from "@/components/ui/TagInput"; // Import TagInput component
import { Loader2 } from "lucide-react"; // Import Loader

interface BusinessProfile {
  business_name: string;
  representative_name: string;
  // Add id if it comes from the profile endpoint, otherwise we get it separately
  id?: number;
}

interface FormData {
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  timezone: string;
}

export default function AddContactPage() {
  const { business_name: businessSlug } = useParams(); // Rename to slug for clarity
  const router = useRouter();
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
  const [businessId, setBusinessId] = useState<number | null>(null); // State for business ID
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [isLoading, setIsLoading] = useState(false); // Add loading state
  const [error, setError] = useState<string | null>(null); // Add error state

  // --- State for core form fields ---
  const [form, setForm] = useState<FormData>({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
    timezone: "America/New_York", // Default timezone
  });

  // --- State for Tags ---
  const [currentTags, setCurrentTags] = useState<Tag[]>([]);

  // Fetch business ID and profile
  useEffect(() => {
    const fetchBusinessInfo = async () => {
      if (!businessSlug || typeof businessSlug !== 'string') return;
      setIsLoading(true); // Start loading
      try {
        // Fetch ID first using the slug
        const idRes = await apiClient.get<{ business_id: number }>(`/business-profile/business-id/slug/${businessSlug}`);
        const fetchedBusinessId = idRes.data.business_id;
        setBusinessId(fetchedBusinessId); // Store the ID

        // Fetch full profile using the ID (if needed for representative_name etc.)
        if (fetchedBusinessId) {
          const profileRes = await apiClient.get<BusinessProfile>(`/business-profile/${fetchedBusinessId}`);
          setBusinessProfile(profileRes.data);
        }
      } catch (err) {
        console.error("Failed to fetch business info:", err);
        setError("Failed to load business information."); // Set error message
      } finally {
         setIsLoading(false); // Stop loading
      }
    };

    fetchBusinessInfo();
  }, [businessSlug]);

  // --- Keep formatPhoneInput and handleChange as they are ---
  const formatPhoneInput = (value: string) => {
    // ... (your existing phone formatting logic)
    const digits = value.replace(/\D/g, '');
    if (digits.length === 10) return `+1${digits}`;
    if (value.startsWith('+')) return `+${digits}`;
    return digits;
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    // ... (your existing handle change logic)
    if (e.target.name === "phone") {
      setForm((prev) => ({
        ...prev,
        [e.target.name]: formatPhoneInput(e.target.value),
      }));
    } else {
      setForm((prev) => ({
        ...prev,
        [e.target.name]: e.target.value,
      }));
    }
  };

  // --- Handler for TagInput changes ---
   const handleTagsChange = useCallback((updatedTags: Tag[]) => {
     setCurrentTags(updatedTags);
   }, []);

  // --- Modified handleSubmit ---
  const handleSubmit = async () => {
    if (!businessId) {
        setError("Business ID not found. Cannot save contact.");
        return;
    }
    setIsLoading(true);
    setError(null);
    let createdCustomerId: number | null = null;

    try {
      // Step 1: Create the customer
      const customerResponse = await apiClient.post("/customers", {
        ...form,
        business_id: businessId,
        opted_in: false, // Explicitly set on creation
      });

      createdCustomerId = customerResponse.data.id; // Get ID from response
      console.log(`Customer created with ID: ${createdCustomerId}`);

      // Step 2: Set the tags for the newly created customer
      if (createdCustomerId && currentTags.length > 0) {
        const tagIds = currentTags.map(tag => tag.id);
        console.log(`Setting tags for new customer ${createdCustomerId}:`, tagIds);
        await setCustomerTags(createdCustomerId, tagIds);
        console.log("Tags set successfully for new customer.");
      }

      // Step 3: Show confirmation (optional) or navigate back
      //setShowConfirmation(true); // Keep if you want the dialog
      router.back(); // Or navigate to contacts list: router.push(`/contacts/${businessSlug}`);

    } catch (err: any) {
      console.error("❌ Failed to add contact or set tags:", err);
      // Provide more specific error feedback if possible
      const errorDetail = err?.response?.data?.detail || err.message || "An unexpected error occurred.";
      setError(errorDetail);
      // If customer was created but tags failed, we might need cleanup or retry logic,
      // but for now just show the error.
      if(createdCustomerId) {
          console.warn(`Customer ${createdCustomerId} was created, but setting tags failed.`);
      }
    } finally {
        setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-[#0C0F1F] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-2xl rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-8 space-y-6">
        <h1 className="text-3xl font-bold text-center text-white">➕ Add New Contact</h1>
        {/* Wrap form elements for better structure if needed */}
        <div className="space-y-4">
          {/* --- Standard Fields --- */}
          <div>
            <Label htmlFor="customer_name" className="text-white">Full Name</Label>
            <Input id="customer_name" name="customer_name" placeholder="Full Name" value={form.customer_name} onChange={handleChange} className="bg-white text-black" required disabled={isLoading} />
          </div>
          <div>
            <Label htmlFor="phone" className="text-white">Phone Number</Label>
            <Input id="phone" name="phone" placeholder="e.g. +13856268825" value={form.phone} onChange={handleChange} maxLength={15} className="bg-white text-black" required disabled={isLoading} />
          </div>
           <div>
             <Label htmlFor="lifecycle_stage" className="text-white">Lifecycle Stage</Label>
             <Input id="lifecycle_stage" name="lifecycle_stage" placeholder="e.g. Lead, Current Customer" value={form.lifecycle_stage} onChange={handleChange} className="bg-white text-black" required disabled={isLoading} />
           </div>
          {/* ... Timezone Select ... */}
           <div className="space-y-2">
             <Label className="block text-sm font-medium text-white">Customer's Timezone</Label>
             <select name="timezone" value={form.timezone} onChange={handleChange} className="w-full border border-gray-300 rounded-md p-3 text-black bg-white" disabled={isLoading}>
               {US_TIMEZONES.map((tz) => (<option key={tz} value={tz}>{TIMEZONE_LABELS[tz]}</option>))}
             </select>
             <p className="text-sm text-gray-400">Helps us send messages at appropriate times.</p>
           </div>
          <div>
             <Label htmlFor="pain_points" className="text-white">Pain Points</Label>
             <Textarea id="pain_points" name="pain_points" placeholder="Pain Points" value={form.pain_points} onChange={handleChange} className="bg-white text-black" disabled={isLoading}/>
           </div>
          <div>
            <Label htmlFor="interaction_history" className="text-white">Interaction History / Notes</Label>
            <Textarea id="interaction_history" name="interaction_history" placeholder="Birthday, Holidays, Work Situation, # of Dogs, etc." value={form.interaction_history} onChange={handleChange} className="bg-white text-black" disabled={isLoading}/>
          </div>

          {/* --- Tag Input Integration --- */}
          {businessId && ( // Only render if businessId is loaded
             <div>
               <Label className="text-white">Tags</Label>
               <TagInput
                 businessId={businessId}
                 initialTags={currentTags} // Starts empty for new contact
                 onChange={handleTagsChange} // Update local state
               />
             </div>
           )}
          {/* --- End Tag Input --- */}

          {/* Opt-in Message Preview (Keep as is) */}
          {/* ... your existing preview div ... */}
           <div className="mt-8 p-4 rounded-lg bg-black/30 border border-white/10 space-y-3">
             {/* ... preview content ... */}
           </div>

           {/* Error Display */}
           {error && <p className="text-red-500 text-sm text-center">{error}</p>}

          {/* Action Buttons */}
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="ghost" onClick={() => router.back()} className="text-white" disabled={isLoading}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              className="bg-gradient-to-r from-green-400 to-blue-500 text-white"
              disabled={isLoading || !form.customer_name || !form.phone || !form.lifecycle_stage || !businessId}
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2"/> : null}
              Save Contact
            </Button>
          </div>
        </div>
      </div>

      {/* Confirmation Dialog (Keep as is) */}
       {/* ... your existing Dialog component ... */}
       <Dialog open={showConfirmation} onOpenChange={setShowConfirmation}>
         {/* ... Dialog content ... */}
       </Dialog>
    </div>
  );
}