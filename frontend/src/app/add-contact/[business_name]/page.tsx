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
import { Tag } from "@/types";
import { TagInput } from "@/components/ui/TagInput";
import { Loader2, Info, UserPlus, AlertTriangle, Zap, MessageSquareText, Tags, Lightbulb, CheckCircle } from "lucide-react"; // Added more icons
import { formatPhoneNumberForDisplay } from "@/lib/phoneUtils";
import { cn } from "@/lib/utils";

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

const LIFECYCLE_STAGES = ["New Lead", "Active Client", "Past Client", "Prospect", "VIP"];
const COMMON_PAIN_POINTS_SUGGESTIONS = ["Pricing", "Availability", "Specific Feature", "Needs Follow-up"];
const COMMON_INTERACTION_SUGGESTIONS = ["Initial Call", "Demo Request", "Support Query", "Feedback Provided"];

export default function AddContactPage() {
  const { business_name: businessSlug } = useParams();
  const router = useRouter();
  const [businessProfile, setBusinessProfile] = useState<BusinessProfile | null>(null);
  const [businessId, setBusinessId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingBusiness, setIsFetchingBusiness] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormData>({
    customer_name: "",
    phone: "",
    lifecycle_stage: "",
    pain_points: "",
    interaction_history: "",
    timezone: "America/Denver",
  });
  const [currentTags, setCurrentTags] = useState<Tag[]>([]);

  // Fetch Business Info (remains the same)
  useEffect(() => {
    // ... (existing fetchBusinessInfo logic)
    const slugParam = Array.isArray(businessSlug) ? businessSlug[0] : businessSlug;
    if (!slugParam) { setError("Business identifier is missing from URL."); setIsFetchingBusiness(false); return; }
    const fetchBusinessInfo = async () => {
      setIsFetchingBusiness(true); setError(null);
      try {
        const idRes = await apiClient.get<{ business_id: number }>(`/business-profile/business-id/slug/${slugParam}`);
        const fetchedBusinessId = idRes.data.business_id; setBusinessId(fetchedBusinessId);
        if (fetchedBusinessId) {
          const profileRes = await apiClient.get<BusinessProfile>(`/business-profile/${fetchedBusinessId}`);
          setBusinessProfile(profileRes.data);
          if (profileRes.data.timezone) { setForm(prev => ({ ...prev, timezone: profileRes.data.timezone || "America/Denver" })); }
        } else { setError("Business not found."); }
      } catch (err) { console.error("Failed to fetch business info:", err); setError("Failed to load business information."); }
      finally { setIsFetchingBusiness(false); }
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

  const handleLifecycleStageClick = (stage: string) => {
    setForm(prev => ({ ...prev, lifecycle_stage: stage }));
    setError(null);
  };

  const appendToTextarea = (fieldName: "pain_points" | "interaction_history", text: string) => {
    setForm(prev => ({
        ...prev,
        [fieldName]: prev[fieldName] + (prev[fieldName] ? "\n- " : "- ") + text + " " // Add a newline and bullet if field not empty
    }));
  };

  const handleTagsChange = useCallback((updatedTags: Tag[]) => {
     setCurrentTags(updatedTags);
  }, []);

  const handleSubmit = async () => {
    if (!businessId) { setError("Business information is missing."); return; }
    if (!form.customer_name.trim() || !form.phone.trim() || !form.lifecycle_stage.trim()) {
        setError("Full Name, Phone, and Lifecycle Stage are required.");
        return;
    }
    setIsLoading(true); setError(null);
    let createdCustomerId: number | null = null;
    try {
      const customerResponse = await apiClient.post("/customers", {
        ...form, business_id: businessId, opted_in: false,
      });
      createdCustomerId = customerResponse.data.id;
      if (createdCustomerId && currentTags.length > 0) {
        await setCustomerTags(createdCustomerId, currentTags.map(tag => tag.id));
      }
      router.push(`/contacts/${businessSlug}`);
    } catch (err: any) {
      const errorDetail = err?.response?.data?.detail || err.message || "An unexpected error occurred.";
      setError(errorDetail);
      if(createdCustomerId) console.warn(`Customer ${createdCustomerId} created, tag association failed.`);
    } finally {
      setIsLoading(false);
    }
  };

    // Loading and initial error states (remain similar)
    if (isFetchingBusiness) { /* ... same loading JSX ... */
        return (<div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6"><Loader2 className="h-12 w-12 animate-spin text-purple-400 mb-4" /><p className="text-xl text-slate-300">Loading Business Info...</p><p className="text-sm text-slate-400">Please wait.</p></div>);
    }
    if (error && (!businessId || !businessProfile)) { /* ... same critical error JSX ... */
         return (<div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex flex-col items-center justify-center p-6 text-center"><AlertTriangle className="h-16 w-16 text-red-500 mb-6" /><h2 className="text-2xl font-semibold text-red-400 mb-3">Failed to Load Business Information</h2><p className="text-slate-300 mb-6 max-w-md bg-red-900/30 border border-red-700/50 p-3 rounded-md">{error}</p><Button onClick={() => window.location.reload()} className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-6 py-2 rounded-lg shadow-md hover:shadow-purple-500/30 transition-all">Retry</Button></div>);
    }


  const previewCustomerName = form.customer_name.trim() || "[Customer Name]";
  const previewRepName = businessProfile?.representative_name?.trim() || "[Your Name]";
  const previewBusinessName = businessProfile?.business_name?.trim() || "[Your Business]";

  const inputBaseClasses = "w-full bg-slate-700 border-slate-600 text-slate-100 placeholder:text-slate-400 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 rounded-md shadow-sm p-2.5 text-sm";
  const labelBaseClasses = "block text-sm font-medium text-slate-300 mb-1.5";
  const sectionClasses = "p-5 bg-slate-800/50 border border-slate-700/70 rounded-lg shadow-lg space-y-4"; // For grouping personalization fields

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans flex items-center justify-center p-4 md:p-6 lg:p-8">
      <div className="w-full max-w-2xl bg-slate-800/70 border border-slate-700/80 rounded-xl shadow-2xl p-6 md:p-8 space-y-8 backdrop-blur-sm"> {/* Increased main spacing to space-y-8 */}
        <h1 className="text-3xl font-bold text-center text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-4 flex items-center justify-center">
            <UserPlus size={32} className="mr-3 opacity-80" /> Add New Contact
        </h1>

        {/* Core Essentials Section */}
        <div className={cn(sectionClasses, "border-purple-500/30")}>
            <h2 className="text-lg font-semibold text-purple-300 border-b border-slate-700 pb-2 mb-4">Core Information</h2>
            <div>
                <Label htmlFor="customer_name" className={labelBaseClasses}>Full Name <span className="text-pink-500">*</span></Label>
                <Input id="customer_name" name="customer_name" placeholder="e.g., Jane Doe" value={form.customer_name} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading} />
            </div>
            <div>
                <Label htmlFor="phone" className={labelBaseClasses}>Phone Number <span className="text-pink-500">*</span></Label>
                <Input id="phone" name="phone" placeholder="e.g., (555) 123-4567" value={form.phone} onChange={handleChange} className={inputBaseClasses} required disabled={isLoading} />
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

        {/* Personalization Hub - Prominent and Engaging */}
        <div className={cn(sectionClasses, "border-sky-500/30")}>
            <h2 className="text-lg font-semibold text-sky-300 border-b border-slate-700 pb-2 mb-4 flex items-center"><Lightbulb size={20} className="mr-2 text-yellow-400"/>Personalization Insights <span className="ml-auto text-xs text-slate-400">(Helps AI craft better messages!)</span></h2>
            
            <div>
                <Label htmlFor="pain_points" className={labelBaseClasses}><Zap size={14} className="inline mr-1.5 text-yellow-400"/>Key Topics / Customer Needs</Label>
                <Textarea id="pain_points" name="pain_points" placeholder="What are they interested in? Any challenges?" value={form.pain_points} onChange={handleChange} className={`${inputBaseClasses} min-h-[70px]`} disabled={isLoading}/>
                <div className="flex flex-wrap gap-2 mt-2">
                    {COMMON_PAIN_POINTS_SUGGESTIONS.map(suggestion => (
                        <Button key={suggestion} type="button" variant="outline" size="sm" onClick={() => appendToTextarea("pain_points", suggestion)} className="text-xs bg-slate-700 border-slate-600 text-slate-300 hover:bg-slate-600 hover:border-slate-500" disabled={isLoading}>+ {suggestion}</Button>
                    ))}
                </div>
            </div>

            <div>
                <Label htmlFor="interaction_history" className={labelBaseClasses}><MessageSquareText size={14} className="inline mr-1.5 text-sky-400"/>Quick Notes / Interaction Log</Label>
                <Textarea id="interaction_history" name="interaction_history" placeholder="Log important dates, preferences, or past touchpoints..." value={form.interaction_history} onChange={handleChange} className={`${inputBaseClasses} min-h-[90px]`} disabled={isLoading}/>
                <div className="flex flex-wrap gap-2 mt-2">
                    {COMMON_INTERACTION_SUGGESTIONS.map(suggestion => (
                        <Button key={suggestion} type="button" variant="outline" size="sm" onClick={() => appendToTextarea("interaction_history", suggestion)} className="text-xs bg-slate-700 border-slate-600 text-slate-300 hover:bg-slate-600 hover:border-slate-500" disabled={isLoading}>+ {suggestion}</Button>
                    ))}
                </div>
            </div>

            {businessId && (
                <div>
                    <Label className={`${labelBaseClasses} mb-2`}><Tags size={14} className="inline mr-1.5 text-green-400"/>Categorize with Tags</Label>
                    <TagInput businessId={businessId} initialTags={currentTags} onChange={handleTagsChange} />
                    {/* Conceptual: AI Suggested Tags could go here */}
                    {/* <p className="text-xs text-slate-400 mt-1">AI Suggestions: <Button variant="link" size="xs" className="text-purple-400">Holiday Shopper</Button></p> */}
                </div>
            )}
             <div className="space-y-1.5">
                <Label htmlFor="timezone" className={labelBaseClasses}>Customer's Timezone</Label>
                <div className="relative">
                    <select id="timezone" name="timezone" value={form.timezone} onChange={handleChange} className={`${inputBaseClasses} appearance-none pr-8`} disabled={isLoading}>
                        {US_TIMEZONES.map((tz) => (<option key={tz} value={tz}>{TIMEZONE_LABELS[tz]}</option>))}
                    </select>
                    <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-400"><svg className="fill-current h-4 w-4" viewBox="0 0 20 20"><path d="M5.516 7.548c.436-.446 1.043-.48 1.576 0L10 10.405l2.908-2.857c.533-.48 1.14-.446 1.576 0 .436.445.408 1.197 0 1.615-.406.418-4.695 4.502-4.695 4.502a1.095 1.095 0 01-1.576 0S5.922 9.581 5.516 9.163c-.409-.418-.436-1.17 0-1.615z"/></svg></div>
                </div>
                <p className="text-xs text-slate-400">Ensures messages arrive at a considerate time.</p>
            </div>
        </div>


        {/* Opt-in Preview */}
        <div className={cn(sectionClasses, "mt-8")}>
            <div className="flex items-center gap-2 mb-2"><Info size={20} className="text-sky-400 flex-shrink-0" /><h3 className="text-slate-200 font-semibold text-base">Initial Opt-in Message Preview</h3></div>
            <p className="text-sm text-slate-400">Upon saving, an automated opt-in request like this will be sent:</p>
            <div className="bg-slate-900/60 p-3.5 rounded-md border border-slate-700 space-y-1 text-sm shadow-inner">
                <p className="text-slate-200 leading-relaxed">Hi <span className="font-medium text-purple-300">{previewCustomerName}</span>! This is <span className="font-medium text-pink-300">{previewRepName}</span> from <span className="font-medium text-sky-300">{previewBusinessName}</span>. We'd love to send you helpful updates & special offers via SMS. To confirm, please reply YES 🙏.</p>
                <p className="text-slate-500 text-xs pt-1">Msg&Data rates may apply. Reply STOP to unsubscribe.</p>
            </div>
        </div>

        {error && !isFetchingBusiness && <p className="text-red-400 text-sm text-center p-2 bg-red-900/20 border border-red-700/40 rounded-md mt-4">{error}</p>}

        <div className="flex flex-col sm:flex-row justify-end gap-3 pt-6 border-t border-slate-700/60 mt-8">
            <Button variant="outline" onClick={() => router.back()} className="border-slate-600 text-slate-300 hover:bg-slate-700 hover:text-slate-100 w-full sm:w-auto" disabled={isLoading}> Cancel </Button>
            <Button
                onClick={handleSubmit}
                className="bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold shadow-lg hover:shadow-pink-500/40 hover:scale-105 transition-all duration-200 rounded-lg px-6 py-2.5 text-sm w-full sm:w-auto flex items-center justify-center"
                disabled={isLoading || isFetchingBusiness || !form.customer_name || !form.phone || !form.lifecycle_stage}
            >
                {isLoading ? <Loader2 className="h-5 w-5 animate-spin mr-2"/> : <CheckCircle size={18} className="mr-2"/>} Save Contact & Send Opt-in
            </Button>
        </div>
      </div>
    </div>
  );
}