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
import { Loader2, Edit3, AlertTriangle, Save, Zap, MessageSquareText, Tags, Lightbulb } from "lucide-react"; // Added more icons
import { cn } from "@/lib/utils"; // Ensure cn is imported

interface ContactFormData {
  customer_name: string;
  phone: string;
  lifecycle_stage: string;
  pain_points: string;
  interaction_history: string;
  timezone: string;
}

// Consistent suggestions with AddContactPage
const LIFECYCLE_STAGES = ["New Lead", "Active Client", "Past Client", "Prospect", "VIP"];
const COMMON_PAIN_POINTS_SUGGESTIONS = [
  "Price sensitivity",
  "Too busy to find time",
  "Afraid of contracts",
  "Needs Follow-ups",
  "Needs more detailed info",
  "Budget is a key concern",
  "Looking for quick turnaround",
  "Currently comparing options"
];
const COMMON_INTERACTION_SUGGESTIONS = [
  "Birthday is on [Date]",
  "Send a SMS Nudge once a Quarter",
  "Send SMS in Spanish",
  "Send a SMS nudge on big holidays",
  "Called, left voicemail on [Date]",
  "Emailed about [Topic] on [Date]",
  "Follow-up needed by [Date]",
  "Key interest: [Specify Topic]"
];

export default function EditContactPage() {
  const [form, setForm] = useState<ContactFormData>({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
    timezone: "America/Denver",
  });

  const [currentTags, setCurrentTags] = useState<Tag[]>([]);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false); // For API calls (save)
  const [isFetching, setIsFetching] = useState(true); // For initial data load
  const [error, setError] = useState<string | null>(null);

  const { id: customerId } = useParams();
  const router = useRouter();

  useEffect(() => {
    const fetchData = async () => {
        const idParam = Array.isArray(customerId) ? customerId[0] : customerId;
        const idNum = idParam ? parseInt(idParam, 10) : null;
        if (!idNum) { setError("Invalid Customer ID provided in URL."); setIsFetching(false); return; }

        setIsFetching(true); setError(null);
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
            setBusinessId(customer.business_id);
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

  const handleLifecycleStageClick = (stage: string) => {
    setForm(prev => ({ ...prev, lifecycle_stage: stage }));
    setError(null);
  };

  const appendToTextarea = (fieldName: "pain_points" | "interaction_history", text: string) => {
    setForm(prev => ({
        ...prev,
        [fieldName]: prev[fieldName] + (prev[fieldName].trim() ? "\n- " : "- ") + text + (text.endsWith("]") ? "" : " ")
    }));
  };

  const handleTagsChange = useCallback((updatedTags: Tag[]) => {
     setCurrentTags(updatedTags);
  }, []);

  const handleSubmit = async () => {
    const idParam = Array.isArray(customerId) ? customerId[0] : customerId;
    const idNum = idParam ? parseInt(idParam, 10) : null;
    if (!idNum) { setError("Cannot update: Invalid Customer ID."); return; }
    if (!form.customer_name.trim() || !form.phone.trim() || !form.lifecycle_stage.trim()) {
        setError("Full Name, Phone, and Lifecycle Stage are required.");
        return;
    }

    setIsLoading(true); setError(null);
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

  if (error && !isFetching && !form.customer_name) { // Critical error if customer data couldn't be loaded
       return (
        <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6 text-center">
            <AlertTriangle className="h-16 w-16 text-red-500 mb-6" />
            <h2 className="text-2xl font-semibold text-red-400 mb-3">Failed to Load Contact Information</h2>
            <p className="text-slate-300 mb-6 max-w-md bg-red-900/30 border border-red-700/50 p-3 rounded-md">{error}</p>
            <Button onClick={() => router.back()} // Changed to router.back() for better UX on error
              className="bg-slate-600 hover:bg-slate-700 text-white font-semibold px-6 py-2 rounded-lg shadow-md transition-all"
            >
                Go Back
            </Button>
        </div>
       );
  }

  const inputBaseClasses = "w-full bg-slate-700 border-slate-600 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm p-2.5 text-sm";
  const labelBaseClasses = "block text-sm font-medium text-slate-300 mb-1.5";
  const sectionClasses = "p-5 bg-slate-800/50 border border-slate-700/70 rounded-lg shadow-lg space-y-4";

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex items-center justify-center p-4 md:p-6 lg:p-8">
      <div className="w-full max-w-2xl bg-slate-800/70 border border-slate-700/80 rounded-xl shadow-2xl p-6 md:p-8 space-y-8 backdrop-blur-sm">
        <h1 className="text-3xl font-bold text-center text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-4 flex items-center justify-center">
            <Edit3 size={30} className="mr-3 opacity-80" /> Edit Contact Details
        </h1>

        {/* Core Information Section */}
        <div className={cn(sectionClasses, "border-purple-500/30")}>
            <h2 className="text-lg font-semibold text-purple-300 border-b border-slate-700 pb-2 mb-4">Core Information</h2>
            <div>
             <Label htmlFor="customer_name" className={labelBaseClasses}>Full Name <span className="text-pink-500">*</span></Label>
             <Input id="customer_name" name="customer_name" value={form.customer_name} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading}/>
           </div>
           <div>
             <Label htmlFor="phone" className={labelBaseClasses}>Phone Number <span className="text-pink-500">*</span></Label>
             <Input id="phone" name="phone" value={form.phone} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading}/>
           </div>
           <div>
             <Label className={labelBaseClasses}>Lifecycle Stage <span className="text-pink-500">*</span></Label>
             <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-1">
                {LIFECYCLE_STAGES.map((stage) => (
                    <Button key={stage} variant="outline" onClick={() => handleLifecycleStageClick(stage)}
                        className={cn("w-full justify-center text-xs py-2 px-1 h-auto sm:text-sm transition-all duration-200 ease-in-out transform hover:scale-105 focus:z-10",
                            form.lifecycle_stage === stage
                            ? "bg-gradient-to-r from-purple-500 to-pink-600 text-white border-transparent shadow-lg ring-2 ring-pink-400"
                            : "bg-slate-700 border-slate-600 text-slate-300 hover:bg-slate-600 hover:border-slate-500"
                        )} disabled={isLoading} >{stage}
                    </Button>
                ))}
             </div>
           </div>
        </div>

        {/* Personalization Insights Section */}
        <div className={cn(sectionClasses, "border-sky-500/30")}>
            <h2 className="text-lg font-semibold text-sky-300 border-b border-slate-700 pb-2 mb-4 flex items-center"><Lightbulb size={20} className="mr-2 text-yellow-400"/>Personalization Insights <span className="ml-auto text-xs text-slate-400">(Refine for better nudges)</span></h2>
            <div>
             <Label htmlFor="pain_points" className={labelBaseClasses}><Zap size={14} className="inline mr-1.5 text-yellow-400"/>Key Topics / Customer Needs</Label>
             <Textarea id="pain_points" name="pain_points" placeholder="What are they interested in? Any challenges?" value={form.pain_points} onChange={handleChange} className={`${inputBaseClasses} min-h-[70px]`} disabled={isLoading}/>
             <div className="flex flex-wrap gap-2 mt-2">
                {COMMON_PAIN_POINTS_SUGGESTIONS.map(suggestion => (
                    <Button key={suggestion} type="button" variant="outline" size="sm" onClick={() => appendToTextarea("pain_points", suggestion)} className="text-xs bg-slate-600/70 border-slate-500/80 text-slate-300 hover:bg-slate-500/70 hover:border-slate-400" disabled={isLoading}>+ {suggestion}</Button>
                ))}
             </div>
           </div>
           <div>
             <Label htmlFor="interaction_history" className={labelBaseClasses}><MessageSquareText size={14} className="inline mr-1.5 text-sky-400"/>Quick Notes / Interaction Log</Label>
             <Textarea id="interaction_history" name="interaction_history" placeholder="Log important dates, preferences, or past conversations..." value={form.interaction_history} onChange={handleChange} className={`${inputBaseClasses} min-h-[90px]`} disabled={isLoading}/>
             <div className="flex flex-wrap gap-2 mt-2">
                {COMMON_INTERACTION_SUGGESTIONS.map(suggestion => (
                    <Button key={suggestion} type="button" variant="outline" size="sm" onClick={() => appendToTextarea("interaction_history", suggestion)} className="text-xs bg-slate-600/70 border-slate-500/80 text-slate-300 hover:bg-slate-500/70 hover:border-slate-400" disabled={isLoading}>+ {suggestion}</Button>
                ))}
             </div>
           </div>
           {businessId ? (
             <div>
               <Label className={`${labelBaseClasses} mb-2`}><Tags size={14} className="inline mr-1.5 text-green-400"/>Categorize with Tags</Label>
               <TagInput
                 businessId={businessId}
                 initialTags={currentTags}
                 onChange={handleTagsChange}
               />
             </div>
           ) : (
            <div>
                <Label className={labelBaseClasses}>Tags</Label>
                <div className={`${inputBaseClasses} h-[40px] flex items-center justify-center text-slate-500 italic`}>
                    {isFetching ? <Loader2 className="h-4 w-4 animate-spin text-slate-400 mr-2"/> : null}
                    {isFetching ? 'Loading tags...' : 'Tag editor unavailable'}
                </div>
            </div>
           )}
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
             <p className="text-xs text-slate-400">Ensures messages arrive at a considerate time.</p>
           </div>
        </div>

        {error && <p className="text-red-400 text-sm text-center p-2 bg-red-900/20 border border-red-700/40 rounded-md mt-1">{error}</p>}

        <div className="flex flex-col sm:flex-row justify-end gap-3 pt-6 border-t border-slate-700/60 mt-8">
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
  );
}