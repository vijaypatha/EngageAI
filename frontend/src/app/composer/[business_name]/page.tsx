// frontend/app/composer/[business_name]/page.tsx
"use client";

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { apiClient } from '@/lib/api';
import NudgeComposer from '@/components/composer/NudgeComposer'; // Import the component
import { Loader2, AlertCircle } from 'lucide-react';

export default function ComposerPage() {
    const { business_name } = useParams<{ business_name: string }>();
    const [businessId, setBusinessId] = useState<number | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchBusinessId = async () => {
            if (!business_name) {
                setError("Business name not found in URL.");
                setIsLoading(false);
                return;
            }
            try {
                console.log(`ComposerPage: Fetching ID for slug: ${business_name}`);
                const response = await apiClient.get(`/business-profile/business-id/slug/${business_name}`);
                if (response.data?.business_id) {
                    setBusinessId(response.data.business_id);
                    console.log(`ComposerPage: Found business ID: ${response.data.business_id}`);
                } else {
                    throw new Error("Business ID not found for the provided name.");
                }
            } catch (err: any) {
                console.error("Failed to fetch business ID:", err);
                setError(err.response?.data?.detail || "Could not find the specified business.");
            } finally {
                setIsLoading(false);
            }
        };

        fetchBusinessId();
    }, [business_name]);

    // This function is a placeholder for the "onClose" prop.
    // In a modal-based implementation, this would close the modal.
    // For a full-page view, it could navigate away, but we'll have it do nothing for now.
    const handleCloseComposer = () => {
        console.log("Composer 'onClose' triggered. In a modal, this would close the view.");
        // Example navigation: router.push(`/dashboard/${business_name}`);
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-screen bg-[#0B0E1C] text-white">
                <Loader2 className="w-8 h-8 animate-spin" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-[#0B0E1C] text-red-400">
                <AlertCircle className="w-12 h-12 mb-4 text-red-500" />
                <h2 className="text-xl font-semibold">Error Loading Composer</h2>
                <p>{error}</p>
            </div>
        );
    }
    
    // Render the NudgeComposer only when we have a valid businessId
    return businessId ? <NudgeComposer businessId={businessId} onClose={handleCloseComposer} /> : null;
}