// frontend/src/app/add-contact/[business_name]/page.tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiClient, setCustomerTags } from "@/lib/api";
import { US_TIMEZONES, TIMEZONE_LABELS } from "@/lib/timezone";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tag } from "@/types";
import { TagInput } from "@/components/ui/TagInput";
import { Loader2, Info } from "lucide-react";
// Import the new utility function
import { formatPhoneNumberForDisplay } from "@/lib/phoneUtils"; // Adjust path if needed

interface BusinessProfile {
  business_name: string;
  representative_name: string;
  id?: number; // The business ID
  timezone?: string | null;
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
  const { business_name: businessSlug } = useParams();
  const router = useRouter();
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingBusiness, setIsFetchingBusiness] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormData>({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
    timezone: "America/New_York",
  });
  const [currentTags, setCurrentTags] = useState<Tag[]>([]);

  useEffect(() => {
    const slugParam = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;
    if (!slugParam) {
      setError("Business identifier is missing.");
      setIsFetchingBusiness(false);
      return;
    }

    const fetchBusinessInfo = async () => {
      setIsFetchingBusiness(true);
      setError(null);
      try {
        const idRes = await apiClient.get<{ business_id: number }>(`/business-profile/business-id/slug/${slugParam}`);
        const fetchedBusinessId = idRes.data.business_id;
        setBusinessId(fetchedBusinessId);

        if (fetchedBusinessId) {
          const profileRes = await apiClient.get<BusinessProfile>(`/business-profile/${fetchedBusinessId}`);
          setBusinessProfile(profileRes.data);
          // Set default timezone from fetched profile if available
          if (profileRes.data.timezone) {
              setForm(prev => ({ ...prev, timezone: profileRes.data.timezone || "America/Denver"}));
          }
        }
      } catch (err) {
        console.error("Failed to fetch business info:", err);
        setError("Failed to load business information.");
      } finally {
         setIsFetchingBusiness(false);
      }
    };
    fetchBusinessInfo();
  }, [businessSlug]);

  // Removed the old formatPhoneInput function

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    if (name === "phone") {
      // Use the imported utility function for display formatting
      setForm((prev) => ({ ...prev, [name]: formatPhoneNumberForDisplay(value) }));
    } else {
      setForm((prev) => ({ ...prev, [name]: value }));
    }
  };

  const handleTagsChange = useCallback((updatedTags: Tag[]) => {
     setCurrentTags(updatedTags);
  }, []);

  const handleSubmit = async () => {
    if (!businessId) { setError("Business information is missing. Cannot save contact."); return; }
    if (!form.customer_name.trim() || !form.phone.trim() || !form.lifecycle_stage.trim()) {
        setError("Full Name, Phone, and Lifecycle Stage are required.");
        return;
    }
    // Optional: Add stricter frontend validation for the final phone format before sending
    // e.g., using a regex or the ensureE164Format utility if you created it
    // if (!/^\+1\d{10}$/.test(form.phone)) {
    //    setError("Please enter a valid US phone number starting with +1.");
    //    return;
    // }

    setIsLoading(true); setError(null);
    let createdCustomerId: number | null = null;

    try {
      // Send the form data - backend schema validator will handle final normalization
      const customerResponse = await apiClient.post("/customers", {
        ...form,
        business_id: businessId,
        opted_in: false,
      });
      createdCustomerId = customerResponse.data.id;
      console.log(`Customer created with ID: ${createdCustomerId}`);

      if (createdCustomerId && currentTags.length > 0) {
        const tagIds = currentTags.map(tag => tag.id);
        await setCustomerTags(createdCustomerId, tagIds);
        console.log("Tags set successfully for new customer.");
      }

      router.push(`/contacts/${businessSlug}`);

    } catch (err: any) {
      console.error("❌ Failed to add contact or set tags:", err);
      const errorDetail = err?.response?.data?.detail || err.message || "An unexpected error occurred.";
      setError(errorDetail);
      if(createdCustomerId) console.warn(`Customer ${createdCustomerId} created, but tag association or subsequent steps might have failed.`);
    } finally {
      setIsLoading(false);
    }
  };

  if (isFetchingBusiness) {
      return <div className="flex min-h-screen bg-[#0C0F1F] items-center justify-center text-white"><Loader2 className="h-8 w-8 animate-spin"/> Loading Business Info...</div>;
  }
  if (error && !businessId) {
       return <div className="flex min-h-screen bg-[#0C0F1F] items-center justify-center text-red-400 p-4 text-center">{error}</div>;
  }

  const previewCustomerName = form.customer_name.trim() || "[Customer Name]";
  const previewRepName = businessProfile?.representative_name?.trim() || "[Your Name]";
  const previewBusinessName = businessProfile?.business_name?.trim() || "[Your Business]";

  return (
    <div className="flex min-h-screen bg-[#0C0F1F] items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-2xl rounded-xl border border-white/10 bg-gradient-to-b from-[#0C0F1F] to-[#111629] shadow-2xl p-8 space-y-6">
        <h1 className="text-3xl font-bold text-center text-white">➕ Add New Contact</h1>
        <div className="space-y-4">
          <div> <Label htmlFor="customer_name" className="text-white">Full Name</Label> <Input id="customer_name" name="customer_name" placeholder="Full Name" value={form.customer_name} onChange={handleChange} className="bg-white text-black" required disabled={isLoading} /> </div>
          {/* Phone Input remains the same, handleChange handles formatting */}
          <div> <Label htmlFor="phone" className="text-white">Phone Number</Label> <Input id="phone" name="phone" placeholder="e.g., 4155552671 or +14155552671" value={form.phone} onChange={handleChange} className="bg-white text-black" required disabled={isLoading} /> </div>
          <div> <Label htmlFor="lifecycle_stage" className="text-white">Lifecycle Stage</Label> <Input id="lifecycle_stage" name="lifecycle_stage" placeholder="e.g., Lead, Current Customer" value={form.lifecycle_stage} onChange={handleChange} className="bg-white text-black" required disabled={isLoading} /> </div>
          <div className="space-y-2"> <Label className="block text-sm font-medium text-white">Customer's Timezone</Label> <select name="timezone" value={form.timezone} onChange={handleChange} className="w-full border border-gray-300 rounded-md p-3 text-black bg-white" disabled={isLoading}> {US_TIMEZONES.map((tz) => (<option key={tz} value={tz}>{TIMEZONE_LABELS[tz]}</option>))} </select> <p className="text-sm text-gray-400">Helps send messages at appropriate times.</p> </div>
          <div> <Label htmlFor="pain_points" className="text-white">Pain Points</Label> <Textarea id="pain_points" name="pain_points" placeholder="Pain Points" value={form.pain_points} onChange={handleChange} className="bg-white text-black" disabled={isLoading}/> </div>
          <div> <Label htmlFor="interaction_history" className="text-white">Interaction History / Notes</Label> <Textarea id="interaction_history" name="interaction_history" placeholder="Birthdays, preferences, past interactions..." value={form.interaction_history} onChange={handleChange} className="bg-white text-black" disabled={isLoading}/> </div>

          {businessId && (
             <div>
               <Label className="text-white mb-1 block">Tags</Label>
               <TagInput businessId={businessId} initialTags={currentTags} onChange={handleTagsChange} />
             </div>
           )}

          <div className="mt-6 p-4 rounded-lg bg-black/30 border border-white/10 space-y-3">
            <div className="flex items-center gap-2 mb-2">
              <Info size={20} className="text-blue-400 flex-shrink-0" />
              <h3 className="text-white font-medium">Initial Opt-in Message</h3>
            </div>
            <p className="text-sm text-white/70">
              When you save, an opt-in request like this will be sent:
            </p>
            <div className="bg-[#1A1D2D] p-3 rounded-md border border-white/5 space-y-1 text-sm">
              <p className="text-white">
                Hi {previewCustomerName}! This is {previewRepName} from {previewBusinessName}. We'd love to send you helpful updates & special offers via SMS. To confirm, please reply YES 🙏.
              </p>
              <p className="text-white/70 text-xs">
                Msg&Data rates may apply. Reply STOP at any time to unsubscribe.
              </p>
            </div>
          </div>

           {error && <p className="text-red-500 text-sm text-center mt-2">{error}</p>}

          <div className="flex justify-end gap-2 pt-4">
            <Button variant="ghost" onClick={() => router.back()} className="text-white" disabled={isLoading}> Cancel </Button>
            <Button onClick={handleSubmit} className="bg-gradient-to-r from-green-400 to-blue-500 text-white" disabled={isLoading || isFetchingBusiness || !form.customer_name || !form.phone || !form.lifecycle_stage || !businessId}>
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2"/> : null} Save Contact
            </Button>
          </div>
        </div>
      </div>

       {/* Confirmation Dialog (keep as is or adjust purpose if needed) */}
       <Dialog open={showConfirmation} onOpenChange={setShowConfirmation}>
         <DialogContent className="bg-card border-border">
           <DialogHeader> <DialogTitle>Contact Added</DialogTitle> <DialogDescription className="pt-4 space-y-4">
             <p> The contact has been saved. An opt-in SMS has been sent. </p>
           </DialogDescription> </DialogHeader>
           <DialogFooter className="mt-4"> <Button onClick={() => { setShowConfirmation(false); router.push(`/contacts/${businessSlug}`); }}> Done </Button> </DialogFooter>
         </DialogContent>
       </Dialog>
    </div>
  );
}