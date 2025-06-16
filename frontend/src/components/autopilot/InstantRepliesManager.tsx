"use client";

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { Loader2, Settings, ChevronRight, CheckCircle, XCircle } from 'lucide-react';
import clsx from 'clsx';

// Type Definitions (assuming these are defined in your types)
interface FaqItem { question: string; answer: string; }
interface StructuredFaqData { operating_hours?: string; business_address?: string; website_url?: string; custom_faqs?: FaqItem[]; }
interface BusinessProfile { id: number; enable_ai_faq_auto_reply: boolean; structured_faq_data?: StructuredFaqData; }
interface InstantRepliesManagerProps { businessId: number; businessSlug: string; }

// --- Visually Redesigned Component ---
export default function InstantRepliesManager({ businessId, businessSlug }: InstantRepliesManagerProps) {
    const [profile, setProfile] = useState<BusinessProfile | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();

    const fetchProfile = useCallback(async () => {
        if (!businessId) return;
        if (!profile) setIsLoading(true);
        try {
            const response = await apiClient.get(`/business-profile/${businessId}`);
            setProfile(response.data);
        } catch (err) {
            setError("Could not load auto-reply settings.");
        } finally {
            if (isLoading) setIsLoading(false);
        }
    }, [businessId, profile, isLoading]);

    useEffect(() => { fetchProfile(); }, [businessId]);
    
    const handleToggle = async (newValue: boolean) => {
        if (!profile) return;
        setIsSaving(true);
        setError(null);
        try {
            await apiClient.put(`/business-profile/${businessId}`, { enable_ai_faq_auto_reply: newValue });
            await fetchProfile();
        } catch(err) {
            setError("Failed to update status.");
        } finally {
            setIsSaving(false);
        }
    };

    if (isLoading) {
        return <div className="p-6 bg-slate-800/70 border border-slate-700 rounded-lg flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-purple-400" /></div>;
    }

    if (error || !profile) {
        return <div className="p-6 bg-red-900/20 text-red-400 rounded-lg">{error || "Profile not found."}</div>;
    }

    const standardFaqCount = (['operating_hours', 'business_address', 'website_url'] as const)
        .filter(key => profile.structured_faq_data?.[key as keyof StructuredFaqData]).length;
    const customFaqCount = profile.structured_faq_data?.custom_faqs?.length || 0;
    const totalFaqCount = standardFaqCount + customFaqCount;

    const isActive = profile.enable_ai_faq_auto_reply;

    return (
        <div className="bg-slate-800/70 border border-slate-700 rounded-lg shadow-md">
            {/* Top Section with Status and Manage Button */}
            <div className="p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                    <div className={clsx("flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center", {
                        "bg-green-500/10 text-green-400": isActive,
                        "bg-slate-600/50 text-slate-400": !isActive,
                    })}>
                        {isActive ? <CheckCircle className="w-6 h-6" /> : <XCircle className="w-6 h-6" />}
                    </div>
                    <div>
                        <h3 className="text-lg font-bold text-white">
                           {isActive ? 'Auto-Replies Active' : 'Auto-Replies Inactive'}
                        </h3>
                        <p className="text-sm text-slate-400">
                           {totalFaqCount > 0 ? `Managing ${totalFaqCount} auto-replies.` : 'No auto-replies configured.'}
                        </p>
                    </div>
                </div>
                <button 
                    onClick={() => router.push(`/autopilot/${businessSlug}/manage-replies`)}
                    className="flex-shrink-0 w-full sm:w-auto px-4 py-2 text-sm font-semibold text-white bg-slate-600 hover:bg-slate-500 rounded-md transition-colors flex items-center justify-center gap-2"
                >
                    <Settings className="w-4 h-4" />
                    Manage Replies
                    <ChevronRight className="w-4 h-4" />
                </button>
            </div>

            {/* Bottom Section with Toggle */}
            <div className="bg-slate-900/50 border-t border-slate-700/80 px-6 py-4 flex items-center justify-end gap-3">
                 <span className="text-sm font-medium text-slate-200">
                    {isActive ? 'Turn Off' : 'Turn On'}
                 </span>
                 <button
                     onClick={() => handleToggle(!isActive)}
                     disabled={isSaving}
                     className={clsx("relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50", {
                        "bg-purple-600": isActive, "bg-slate-600": !isActive,
                     })}
                 >
                    {isSaving ? <Loader2 className="w-4 h-4 animate-spin text-white absolute left-1/2 -translate-x-1/2"/> : <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${isActive ? 'translate-x-6' : 'translate-x-1'}`} />}
                 </button>
            </div>
        </div>
    );
}
