// frontend/src/app/autopilot/[business_name]/manage-replies/page.tsx
"use client";

//
// --- Imports ---
//
import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api';
import { Loader2, ArrowLeft, Save, PlusCircle, AlertCircle } from 'lucide-react';
import { FaqCard } from '@/components/FaqCard';
import { BusinessProfile, StructuredFaqData } from '@/types'; // Use centralized types

//
// --- Type Definitions ---
//
interface UnifiedFaq {
  id: string; // e.g., 'std-operating_hours' or 'cst-1688159...
  question: string;
  answer: string;
  isStandard: boolean; // Differentiates between standard (fixed question) and custom
}

//
// --- Component ---
//
export default function ManageRepliesPage() {
    //
    // --- State Management ---
    //
    const [businessId, setBusinessId] = useState<number | null>(null);
    const [unifiedFaqs, setUnifiedFaqs] = useState<UnifiedFaq[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const router = useRouter();
    const params = useParams<{ business_name: string }>();

    //
    // --- Data Fetching and Transformation ---
    //
    const fetchBusinessId = useCallback(async () => {
        if (!params.business_name) return;
        try {
            const response = await apiClient.get(`/business-profile/business-id/slug/${params.business_name}`);
            setBusinessId(response.data.business_id);
        } catch (err) {
            setError("Could not find this business.");
            setIsLoading(false);
        }
    }, [params.business_name]);

    useEffect(() => {
        fetchBusinessId();
    }, [fetchBusinessId]);

    const fetchAndTransformProfile = useCallback(async () => {
        if (!businessId) return;
        setIsLoading(true);
        try {
            const response = await apiClient.get<BusinessProfile>(`/business-profile/${businessId}`);
            const profile = response.data;
            const data = profile.structured_faq_data || {};
            
            const transformedFaqs: UnifiedFaq[] = [];
            
            // **RECONCILED**: The keys ('operating_hours', 'address', 'website') and question text now match the backend schema and frontend needs.
            if (data.operating_hours !== undefined) transformedFaqs.push({ id: 'std-operating_hours', question: 'Operating Hours', answer: data.operating_hours || "", isStandard: true });
            if (data.address !== undefined) transformedFaqs.push({ id: 'std-address', question: 'Business Address', answer: data.address || "", isStandard: true });
            if (data.website !== undefined) transformedFaqs.push({ id: 'std-website', question: 'Website URL', answer: data.website || "", isStandard: true });
            
            data.custom_faqs?.forEach((faq, index) => {
                transformedFaqs.push({ id: `cst-${index}-${Date.now()}`, question: faq.question, answer: faq.answer, isStandard: false });
            });

            setUnifiedFaqs(transformedFaqs);

        } catch (err) {
            setError("Could not load auto-reply profile.");
        } finally {
            setIsLoading(false);
        }
    }, [businessId]);

    useEffect(() => {
        if (businessId) {
            fetchAndTransformProfile();
        }
    }, [businessId, fetchAndTransformProfile]);

    //
    // --- Event Handlers ---
    //
    const handleSave = async () => {
        if (!businessId) return;
        setIsSaving(true);
        setError(null);

        // **RECONCILED**: Transform the state back into the structure expected by the backend API.
        const structuredData: StructuredFaqData = {
            custom_faqs: [],
            operating_hours: unifiedFaqs.find(f => f.id === 'std-operating_hours')?.answer || "",
            address: unifiedFaqs.find(f => f.id === 'std-address')?.answer || "",
            website: unifiedFaqs.find(f => f.id === 'std-website')?.answer || ""
        };

        unifiedFaqs.forEach(faq => {
            if (!faq.isStandard && faq.question && faq.answer) {
                structuredData.custom_faqs?.push({ question: faq.question, answer: faq.answer });
            }
        });

        try {
            await apiClient.put(`/business-profile/${businessId}`, {
                structured_faq_data: structuredData,
            });

            // On success, go back. The previous page will re-fetch data on its own if needed.
            router.back();
            // Note: router.refresh() is an option but can be heavy. A simple back navigation
            // is often sufficient if the previous component re-fetches on focus or mount.

        } catch (err: any) {
            setError(err.response?.data?.detail || "Failed to save changes.");
        } finally {
            setIsSaving(false);
        }
    };

    const handleAddCustomFaq = () => {
        setUnifiedFaqs(prev => [...prev, { id: `cst-${Date.now()}`, question: "", answer: "", isStandard: false }]);
    };
    
    const handleUpdateFaq = (id: string, field: 'question' | 'answer', value: string) => {
        setUnifiedFaqs(prev => prev.map(faq => faq.id === id ? { ...faq, [field]: value } : faq));
    };

    const handleDeleteFaq = (id: string) => {
        setUnifiedFaqs(prev => prev.filter(faq => faq.id !== id));
    };

    //
    // --- Render Logic ---
    //
    if (isLoading) return <div className="flex h-screen items-center justify-center bg-slate-900"><Loader2 className="w-8 h-8 animate-spin text-purple-400" /></div>;
    if (error && !isSaving) return <div className="flex h-screen items-center justify-center bg-slate-900 text-red-400 p-4 text-center"><AlertCircle className="w-8 h-8 mb-2" />{error}</div>;

    return (
        <div className="flex-1 p-6 md:p-8 bg-slate-900 text-slate-100 min-h-screen font-sans">
            <div className="max-w-6xl mx-auto">
                {/* Page Header */}
                <div className="flex flex-col sm:flex-row items-center justify-between mb-8 gap-4">
                    <div className="flex items-center gap-4 self-start">
                        <button onClick={() => router.back()} className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors">
                            <ArrowLeft className="w-4 h-4" />
                            Back to Autopilot
                        </button>
                    </div>
                    <div>
                         <h1 className="text-2xl font-bold text-white text-center">Manage Instant Replies</h1>
                         <p className="text-sm text-slate-400 text-center mt-1">Add or edit the answers AI Nudge will use to instantly reply to customers.</p>
                    </div>
                    <button onClick={handleSave} disabled={isSaving} className="px-5 py-2.5 text-sm font-semibold text-white bg-purple-600 hover:bg-purple-700 rounded-md flex items-center gap-2 disabled:opacity-70 self-end sm:self-center">
                        {isSaving ? <Loader2 className="w-5 h-5 animate-spin"/> : <Save className="w-5 h-5" />}
                        {isSaving ? 'Saving...' : 'Save & Close'}
                    </button>
                </div>
                
                {error && isSaving && <div className="mb-4 text-center p-3 bg-red-900/30 text-red-300 rounded-lg">{error}</div>}

                {/* Unified FAQ Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {unifiedFaqs.map((faq) => (
                        <FaqCard
                            key={faq.id}
                            item={{
                                id: faq.id,
                                type: faq.isStandard ? 'system' : 'custom',
                                questionText: faq.question,
                                answerText: faq.answer,
                                isEditing: (faq.question === "" && faq.answer === "") // Auto-open new cards
                            }}
                            onAnswerChange={(id, newAnswer) => handleUpdateFaq(id, 'answer', newAnswer)}
                            onQuestionChange={!faq.isStandard ? (id, newQuestion) => handleUpdateFaq(id, 'question', newQuestion) : undefined}
                            onRemove={!faq.isStandard ? handleDeleteFaq : undefined}
                            isSavingOverall={isSaving}
                        />
                    ))}
                    <button
                        onClick={handleAddCustomFaq}
                        className="flex flex-col items-center justify-center p-6 bg-slate-800/50 border-2 border-dashed border-slate-700 rounded-xl text-slate-500 hover:bg-slate-800 hover:border-purple-500 hover:text-purple-400 transition-all duration-200 min-h-[250px]"
                    >
                        <PlusCircle className="w-10 h-10" />
                        <span className="mt-2 font-semibold">Add Custom Q&A</span>
                        <span className="text-xs mt-1 text-center">Click to define a new question and its automatic answer.</span>
                    </button>
                </div>
            </div>
        </div>
    );
}