// frontend/src/app/edit-contact/[id]/page.tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { apiClient, setCustomerTags, getCustomerById } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { US_TIMEZONES, TIMEZONE_LABELS } from "@/lib/timezone";
import { Tag } from "@/types";
import { TagInput } from "@/components/ui/TagInput";
import { Loader2, Edit3, AlertTriangle, Save } from "lucide-react";

interface ContactFormData {
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  timezone: string;
}

export default function EditContactPage() {
  const [form, setForm] = useState<ContactFormData>({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
    timezone: "America/Denver", // Default, will be overridden
  });

  const [currentTags, setCurrentTags] = useState<Tag[]>([]);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { id: customerId } = useParams(); // Gets customerId, not business_name slug
  const router = useRouter();

  useEffect(() => {
    const fetchData = async () => {
        const idParam = Array.isArray(customerId) ? customerId[0] : customerId;
        const idNum = idParam ? parseInt(idParam, 10) : null;

        if (!idNum) {
             setError("Invalid Customer ID provided in URL."); // Error specific to this page's logic
             setIsFetching(false);
             return;
        }

        setIsFetching(true);
        setError(null);
        try {
            const customer = await getCustomerById(idNum);
            setForm({
                customer_name: customer.customer_name || "",
                phone: customer.phone || "",
                lifecycle_stage: customer.lifecycle_stage || "",
                pain_points: customer.pain_points || "",
                interaction_history: customer.interaction_history || "",
                timezone: customer.timezone || "America/Denver",
            });
            setCurrentTags(customer.tags || []);
            setBusinessId(customer.business_id); // businessId is fetched via customer data
        } catch (err: any) {
            console.error("Failed to load contact", err);
            setError(err?.response?.data?.detail || err.message || "Failed to load contact data. Please try again.");
        } finally {
            setIsFetching(false);
        }
    };
    fetchData();
  }, [customerId]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleTagsChange = useCallback((updatedTags: Tag[]) => {
     setCurrentTags(updatedTags);
  }, []);

  const handleSubmit = async () => {
    const idParam = Array.isArray(customerId) ? customerId[0] : customerId;
    const idNum = idParam ? parseInt(idParam, 10) : null;

    if (!idNum) {
        setError("Cannot update: Invalid Customer ID.");
        return;
    }
    if (!form.customer_name.trim() || !form.phone.trim() || !form.lifecycle_stage.trim()) {
        setError("Full Name, Phone, and Lifecycle Stage are required.");
        return;
    }

    setIsLoading(true);
    setError(null);
    try {
      await apiClient.put(`/customers/${idNum}`, form);
      const tagIds = currentTags.map(tag => tag.id);
      await setCustomerTags(idNum, tagIds);
      router.back();
    } catch (err: any) {
      console.error("❌ Failed to update contact or tags:", err);
      const errorDetail = err?.response?.data?.detail || err.message || "An unexpected error occurred while saving changes.";
      setError(errorDetail);
    } finally {
      setIsLoading(false);
    }
  };

  if (isFetching) {
      return (
        <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6">
            <Loader2 className="h-12 w-12 animate-spin text-purple-400 mb-4" />
            <p className="text-xl text-slate-300">Loading Contact Details...</p>
            <p className="text-sm text-slate-400">Please wait while we fetch the information.</p>
        </div>
      );
  }

  // This will display any error content, including the one you mentioned if it ends up in the 'error' state
  if (error && !isFetching && !form.customer_name) {
       return (
        <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6 text-center">
            <AlertTriangle className="h-16 w-16 text-red-500 mb-6" />
            {/* The title here is generic; the specific error message comes from the 'error' state variable */}
            <h2 className="text-2xl font-semibold text-red-400 mb-3">Failed to Load Contact Information</h2>
            <p className="text-slate-300 mb-6 max-w-md bg-red-900/30 border border-red-700/50 p-3 rounded-md">{error}</p>
            <Button onClick={() => window.location.reload()} // Or router.back()
              className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-6 py-2 rounded-lg shadow-md hover:shadow-purple-500/30 transition-all"
            >
                Retry
            </Button>
        </div>
       );
  }

  const inputBaseClasses = "w-full bg-slate-700 border-slate-600 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm p-2.5 text-sm";
  const labelBaseClasses = "block text-sm font-medium text-slate-300 mb-1.5";

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex items-center justify-center p-4 md:p-6 lg:p-8">
      <div className="w-full max-w-2xl bg-slate-800/70 border border-slate-700/80 rounded-xl shadow-2xl p-6 md:p-8 space-y-6 backdrop-blur-sm">
        <h1 className="text-3xl font-bold text-center text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-6 flex items-center justify-center">
            <Edit3 size={30} className="mr-3 opacity-80" /> Edit Contact Details
        </h1>
        <div className="space-y-5">
           <div>
             <Label htmlFor="customer_name" className={labelBaseClasses}>Full Name <span className="text-pink-500">*</span></Label>
             <Input id="customer_name" name="customer_name" value={form.customer_name} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading}/>
           </div>
           <div>
             <Label htmlFor="phone" className={labelBaseClasses}>Phone Number <span className="text-pink-500">*</span></Label>
             <Input id="phone" name="phone" value={form.phone} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading}/>
           </div>
           <div>
             <Label htmlFor="lifecycle_stage" className={labelBaseClasses}>Lifecycle Stage <span className="text-pink-500">*</span></Label>
             <Input id="lifecycle_stage" name="lifecycle_stage" value={form.lifecycle_stage} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading}/>
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
             <Textarea id="pain_points" name="pain_points" value={form.pain_points} onChange={handleChange} className={`${inputBaseClasses} min-h-[80px]`} disabled={isLoading}/>
           </div>
           <div>
             <Label htmlFor="interaction_history" className={labelBaseClasses}>Interaction History / Notes</Label>
             <Textarea id="interaction_history" name="interaction_history" value={form.interaction_history} onChange={handleChange} className={`${inputBaseClasses} min-h-[100px]`} disabled={isLoading}/>
           </div>

          {businessId ? (
             <div>
               <Label className={`${labelBaseClasses} mb-2`}>Tags</Label>
               <TagInput
                 businessId={businessId}
                 initialTags={currentTags}
                 onChange={handleTagsChange}
               />
             </div>
           ) : (
            // Show a styled loading/disabled state for TagInput if businessId isn't ready
            // This state might appear briefly if customer data is fetched but businessId is pending, or if fetch fails.
            <div>
                <Label className={labelBaseClasses}>Tags</Label>
                <div className={`${inputBaseClasses} h-[40px] flex items-center justify-center text-slate-500 italic`}>
                    {isFetching ? <Loader2 className="h-4 w-4 animate-spin text-slate-400 mr-2"/> : null}
                    {isFetching ? 'Loading tags...' : 'Tag editor unavailable (missing business context)'}
                </div>
            </div>
           )}

          {error && <p className="text-red-400 text-sm text-center p-2 bg-red-900/20 border border-red-700/40 rounded-md mt-1">{error}</p>}

          <div className="flex flex-col sm:flex-row justify-end gap-3 pt-5 border-t border-slate-700/60 mt-8">
            <Button variant="outline" onClick={() => router.back()} className="border-slate-600 text-slate-300 hover:bg-slate-700 hover:text-slate-100 w-full sm:w-auto" disabled={isLoading}>
              Cancel
            </Button>
            <Button
                onClick={handleSubmit}
                className="bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold shadow-lg hover:shadow-pink-500/40 hover:scale-105 transition-all duration-200 rounded-lg px-6 py-2.5 text-sm w-full sm:w-auto flex items-center justify-center"
                disabled={isLoading || isFetching || !businessId || !form.customer_name || !form.phone || !form.lifecycle_stage}
            >
              {isLoading ? <Loader2 className="h-5 w-5 animate-spin mr-2"/> : <Save size={18} className="mr-2"/>}
              Save Changes
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}