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
import { TagInput } from "@/components/ui/TagInput"; // Assuming this component is styled or will be
import { Loader2, Info, UserPlus, AlertTriangle } from "lucide-react";
import { formatPhoneNumberForDisplay } from "@/lib/phoneUtils";

interface BusinessProfile {
  business_name: string;
  representative_name: string;
  id?: number;
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
  const [showConfirmation, setShowConfirmation] = useState(false); // This dialog seems unused currently based on handleSubmit logic
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingBusiness, setIsFetchingBusiness] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormData>({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
    timezone: "America/Denver", // Default, will be overridden
  });
  const [currentTags, setCurrentTags] = useState<Tag[]>([]);

  useEffect(() => {
    const slugParam = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;
    if (!slugParam) {
      setError("Business identifier is missing from URL.");
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
          if (profileRes.data.timezone) {
              setForm(prev => ({ ...prev, timezone: profileRes.data.timezone || "America/Denver"}));
          }
        } else {
            setError("Business not found for the provided identifier.");
        }
      } catch (err) {
        console.error("Failed to fetch business info:", err);
        setError("Failed to load business information. Please ensure the URL is correct.");
      } finally {
         setIsFetchingBusiness(false);
      }
    };
    fetchBusinessInfo();
  }, [businessSlug]);


  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    if (name === "phone") {
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
    // Consider adding phone validation using a more robust library or regex if needed

    setIsLoading(true); setError(null);
    let createdCustomerId: number | null = null;

    try {
      const customerResponse = await apiClient.post("/customers", {
        ...form,
        business_id: businessId,
        opted_in: false, // Defaulting to false, opt-in SMS will be sent
      });
      createdCustomerId = customerResponse.data.id;
      console.log(`Customer created with ID: ${createdCustomerId}`);

      if (createdCustomerId && currentTags.length > 0) {
        const tagIds = currentTags.map(tag => tag.id);
        await setCustomerTags(createdCustomerId, tagIds);
        console.log("Tags set successfully for new customer.");
      }
      // Instead of showing a dialog, we navigate directly as per original logic.
      // If dialog is desired, set setShowConfirmation(true) here instead of router.push
      router.push(`/contacts/${businessSlug}`);

    } catch (err: any) {
      console.error("❌ Failed to add contact or set tags:", err);
      const errorDetail = err?.response?.data?.detail || err.message || "An unexpected error occurred while saving.";
      setError(errorDetail);
      if(createdCustomerId) console.warn(`Customer ${createdCustomerId} created, but tag association or subsequent steps might have failed.`);
    } finally {
      setIsLoading(false);
    }
  };

  if (isFetchingBusiness) {
      return (
        <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6">
            <Loader2 className="h-12 w-12 animate-spin text-purple-400 mb-4" />
            <p className="text-xl text-slate-300">Loading Business Info...</p>
            <p className="text-sm text-slate-400">Please wait while we fetch the details.</p>
        </div>
      );
  }
  if (error && (!businessId || !businessProfile)) { // Show critical error if business info couldn't load
       return (
        <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6 text-center">
            <AlertTriangle className="h-16 w-16 text-red-500 mb-6" />
            <h2 className="text-2xl font-semibold text-red-400 mb-3">Failed to Load Business Information</h2>
            <p className="text-slate-300 mb-6 max-w-md bg-red-900/30 border border-red-700/50 p-3 rounded-md">{error}</p>
            <Button onClick={() => window.location.reload()}
              className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-6 py-2 rounded-lg shadow-md hover:shadow-purple-500/30 transition-all"
            >
                Retry
            </Button>
        </div>
       );
  }

  const previewCustomerName = form.customer_name.trim() || "[Customer Name]";
  const previewRepName = businessProfile?.representative_name?.trim() || "[Your Name]";
  const previewBusinessName = businessProfile?.business_name?.trim() || "[Your Business]";

  const inputBaseClasses = "w-full bg-slate-700 border-slate-600 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm p-2.5 text-sm";
  const labelBaseClasses = "block text-sm font-medium text-slate-300 mb-1.5";

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex items-center justify-center p-4 md:p-6 lg:p-8">
      <div className="w-full max-w-2xl bg-slate-800/70 border border-slate-700/80 rounded-xl shadow-2xl p-6 md:p-8 space-y-6 backdrop-blur-sm">
        <h1 className="text-3xl font-bold text-center text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-6 flex items-center justify-center">
            <UserPlus size={32} className="mr-3 opacity-80" /> Add New Contact
        </h1>
        <div className="space-y-5">
          <div>
            <Label htmlFor="customer_name" className={labelBaseClasses}>Full Name <span className="text-pink-500">*</span></Label>
            <Input id="customer_name" name="customer_name" placeholder="Enter customer's full name" value={form.customer_name} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading} />
          </div>
          <div>
            <Label htmlFor="phone" className={labelBaseClasses}>Phone Number <span className="text-pink-500">*</span></Label>
            <Input id="phone" name="phone" placeholder="e.g., (555) 123-4567" value={form.phone} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading} />
          </div>
          <div>
            <Label htmlFor="lifecycle_stage" className={labelBaseClasses}>Lifecycle Stage <span className="text-pink-500">*</span></Label>
            <Input id="lifecycle_stage" name="lifecycle_stage" placeholder="e.g., New Lead, Active Client, Past Customer" value={form.lifecycle_stage} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="timezone" className={labelBaseClasses}>Customer's Timezone</Label>
            <div className="relative">
                <select id="timezone" name="timezone" value={form.timezone} onChange={handleChange} className={`${inputBaseClasses} appearance-none pr-8`} disabled={isLoading}>
                    {US_TIMEZONES.map((tz) => (<option key={tz} value={tz}>{TIMEZONE_LABELS[tz]}</option>))}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-400">
                    <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M5.516 7.548c.436-.446 1.043-.48 1.576 0L10 10.405l2.908-2.857c.533-.48 1.14-.446 1.576 0 .436.445.408 1.197 0 1.615-.406.418-4.695 4.502-4.695 4.502a1.095 1.095 0 01-1.576 0S5.922 9.581 5.516 9.163c-.409-.418-.436-1.17 0-1.615z"/></svg>
                </div>
            </div>
            <p className="text-xs text-slate-400">Helps ensure messages are sent at appropriate local times.</p>
          </div>
          <div>
            <Label htmlFor="pain_points" className={labelBaseClasses}>Pain Points / Needs</Label>
            <Textarea id="pain_points" name="pain_points" placeholder="What challenges or needs does the customer have?" value={form.pain_points} onChange={handleChange} className={`${inputBaseClasses} min-h-[80px]`} disabled={isLoading}/>
          </div>
          <div>
            <Label htmlFor="interaction_history" className={labelBaseClasses}>Interaction History / Notes</Label>
            <Textarea id="interaction_history" name="interaction_history" placeholder="Log birthdays, preferences, past conversations, etc." value={form.interaction_history} onChange={handleChange} className={`${inputBaseClasses} min-h-[100px]`} disabled={isLoading}/>
          </div>

          {businessId && (
             <div>
               <Label className={`${labelBaseClasses} mb-2`}>Tags (Optional)</Label>
               <TagInput businessId={businessId} initialTags={currentTags} onChange={handleTagsChange} />
             </div>
           )}

          <div className="mt-6 p-4 rounded-lg bg-slate-700/40 border border-slate-600/50 space-y-3 shadow">
            <div className="flex items-center gap-2 mb-2">
              <Info size={20} className="text-sky-400 flex-shrink-0" />
              <h3 className="text-slate-200 font-semibold text-base">Initial Opt-in Message Preview</h3>
            </div>
            <p className="text-sm text-slate-400">
              Upon saving, an automated opt-in request similar to the following will be sent to the customer:
            </p>
            <div className="bg-slate-900/50 p-3.5 rounded-md border border-slate-700 space-y-1 text-sm shadow-inner">
              <p className="text-slate-200 leading-relaxed">
                Hi <span className="font-medium text-purple-300">{previewCustomerName}</span>! This is <span className="font-medium text-pink-300">{previewRepName}</span> from <span className="font-medium text-sky-300">{previewBusinessName}</span>. We'd love to send you helpful updates & special offers via SMS. To confirm, please reply YES 🙏.
              </p>
              <p className="text-slate-500 text-xs pt-1">
                Msg&Data rates may apply. Reply STOP at any time to unsubscribe.
              </p>
            </div>
          </div>

           {error && !isFetchingBusiness && <p className="text-red-400 text-sm text-center p-2 bg-red-900/20 border border-red-700/40 rounded-md">{error}</p>}

          <div className="flex flex-col sm:flex-row justify-end gap-3 pt-5 border-t border-slate-700/60 mt-8">
            <Button variant="outline" onClick={() => router.back()} className="border-slate-600 text-slate-300 hover:bg-slate-700 hover:text-slate-100 w-full sm:w-auto" disabled={isLoading}> Cancel </Button>
            <Button
                onClick={handleSubmit}
                className="bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold shadow-lg hover:shadow-pink-500/40 hover:scale-105 transition-all duration-200 rounded-lg px-6 py-2.5 text-sm w-full sm:w-auto flex items-center justify-center"
                disabled={isLoading || isFetchingBusiness || !form.customer_name || !form.phone || !form.lifecycle_stage || !businessId}
            >
              {isLoading ? <Loader2 className="h-5 w-5 animate-spin mr-2"/> : <UserPlus size={18} className="mr-2"/>} Save Contact
            </Button>
          </div>
        </div>
      </div>

       {/* Confirmation Dialog - can be enabled if needed */}
       <Dialog open={showConfirmation} onOpenChange={setShowConfirmation}>
         <DialogContent className="bg-slate-800 border-slate-700 text-slate-100 shadow-xl rounded-lg font-sans">
           <DialogHeader>
             <DialogTitle className="text-slate-100 text-xl font-semibold">Contact Added Successfully</DialogTitle>
             <DialogDescription className="text-slate-400 pt-2">
                The contact has been saved. An automated opt-in SMS has been dispatched.
             </DialogDescription>
           </DialogHeader>
           <DialogFooter className="mt-4">
             <Button
                onClick={() => { setShowConfirmation(false); router.push(`/contacts/${businessSlug}`); }}
                className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-5 py-2 rounded-md"
              >
                Done
              </Button>
           </DialogFooter>
         </DialogContent>
       </Dialog>
    </div>
  );
}