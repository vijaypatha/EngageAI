// frontend/src/components/autopilot/InstantRepliesManager.tsx
"use client";

//
// --- Imports ---
//
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { Loader2, Settings, ChevronRight } from 'lucide-react';
import { BusinessProfile } from '@/types'; // Import from centralized types

//
// --- Component Props Interface ---
//
interface InstantRepliesManagerProps {
  businessId: number;
  businessSlug: string;
}

//
// --- Component ---
//
export default function InstantRepliesManager({ businessId, businessSlug }: InstantRepliesManagerProps) {
    //
    // --- State Management ---
    //
    const [profile, setProfile] = useState<BusinessProfile | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();

    //
    // --- Data Fetching ---
    //
    const fetchProfile = useCallback(async () => {
        if (!businessId) return;
        // No need for a full loader on re-fetch, only initial.
        if (!profile) setIsLoading(true); 

        try {
            const response = await apiClient.get<BusinessProfile>(`/business-profile/${businessId}`);
            setProfile(response.data);
        } catch (err) {
            setError("Could not load auto-reply settings.");
        } finally {
            // Only turn off the main loader, not subsequent ones.
            if (isLoading) setIsLoading(false);
        }
    }, [businessId, profile, isLoading]);

    // Initial data fetch on component mount
    useEffect(() => {
        fetchProfile();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [businessId]);
    
    //
    // --- Event Handlers ---
    //
    const handleToggle = async (newValue: boolean) => {
        if (!profile) return;
        setIsSaving(true);
        setError(null);

        // Optimistic UI Update
        setProfile(p => p ? { ...p, enable_ai_faq_auto_reply: newValue } : null);

        try {
            // Persist the change to the database
            await apiClient.put(`/business-profile/${businessId}`, {
                enable_ai_faq_auto_reply: newValue,
            });
            // Optional: Re-fetch to ensure UI is in sync with the DB state after saving.
            // await fetchProfile(); 
        } catch(err) {
            setError("Failed to update status. Your change was not saved.");
            // Revert optimistic update on failure
            setProfile(p => p ? { ...p, enable_ai_faq_auto_reply: !newValue } : null);
        } finally {
            setIsSaving(false);
        }
    };

    //
    // --- Render Logic ---
    //
    if (isLoading) {
        return <div className="p-6 bg-slate-800 rounded-lg flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-purple-400" /></div>;
    }

    if (error || !profile) {
        return <div className="p-6 bg-red-900/20 text-red-400 rounded-lg">{error || "Profile not found."}</div>;
    }

    // Calculate FAQ counts based on reconciled keys
    const standardFaqCount = (['operating_hours', 'address', 'website'] as const)
        .filter(key => profile.structured_faq_data?.[key]).length;
    const customFaqCount = profile.structured_faq_data?.custom_faqs?.length || 0;
    const totalFaqCount = standardFaqCount + customFaqCount;

    return (
        <div className="p-6 bg-slate-800/70 border border-slate-700 rounded-lg">
            {/* Header and Manage Button */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div>
                    <h2 className="text-xl font-bold text-white mb-1">Instant Auto-Replies</h2>
                    <p className="text-sm text-slate-400 max-w-lg">
                        Automatically answer common questions. Manage your knowledge base and settings here.
                    </p>
                </div>
                <button 
                    onClick={() => router.push(`/autopilot/${businessSlug}/manage-replies`)}
                    className="flex-shrink-0 px-4 py-2 text-sm font-semibold text-white bg-slate-600 hover:bg-slate-500 rounded-md transition-colors flex items-center gap-2"
                >
                    <Settings className="w-4 h-4" />
                    Manage All
                    <ChevronRight className="w-4 h-4" />
                </button>
            </div>
            {/* Status and Toggle Control */}
            <div className="mt-4 pt-4 border-t border-slate-700/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                 <div className="text-sm text-slate-300">
                    Status: <span className={`font-bold ${profile.enable_ai_faq_auto_reply ? 'text-green-400' : 'text-slate-500'}`}>
                        {profile.enable_ai_faq_auto_reply ? 'Active' : 'Inactive'}
                    </span>
                    <span className="text-slate-500 mx-2">|</span>
                    Managing <span className="font-bold text-white">{totalFaqCount}</span> auto-replies.
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-slate-200">
                       {profile.enable_ai_faq_auto_reply ? 'Turn Off' : 'Turn On'}
                    </span>
                    <button
                        onClick={() => handleToggle(!profile.enable_ai_faq_auto_reply)}
                        disabled={isSaving}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
                            profile.enable_ai_faq_auto_reply ? 'bg-purple-600' : 'bg-slate-600'
                        }`}
                    >
                       {isSaving ? <Loader2 className="w-4 h-4 animate-spin text-white absolute left-1/2 -translate-x-1/2"/> : <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${profile.enable_ai_faq_auto_reply ? 'translate-x-6' : 'translate-x-1'}`} />}
                    </button>
                </div>
            </div>
        </div>
    );
}